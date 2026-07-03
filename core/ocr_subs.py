"""Trích phụ đề hardsub thành segment bằng OCR (RapidOCR/ONNX).

Cách làm: lấy mẫu frame OCR_FPS hình/giây, crop dải phụ đề (OCR_CROP_TOP → đáy,
upscale 2x vì chữ phụ đề thường nhỏ), OCR từng frame, rồi gộp chuỗi frame có
cùng text thành segment {id, text, start, end} — cùng định dạng với whisper.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import cv2

import config
from core import ffmpeg

_CJK = re.compile(r"[一-鿿㐀-䶿]")
_NORM_DROP = re.compile(r"[\s，。！？、…：；·,.!?:;\"'“”‘’\-—~～]+")
# watermark/credit của nhóm reup — không phải lời thoại
_JUNK = re.compile(
    r"(?i)(animexin|www\.|https?://|\.(com|net|dev|org|tv|me|vn)\b"
    r"|youtube|subscribe|telegram|facebook|tiktok|donghua\s*(stream|world))"
)

# OCR jitter: cùng một phụ đề nhưng vài frame đọc sai 1-2 ký tự
SIMILARITY = 0.7
MIN_DURATION_S = 0.4
MIN_CHARS = 2


def _normalize(text: str) -> str:
    return _NORM_DROP.sub("", text)


def _frame_lines(engine, img) -> list[tuple[float, str, list[float]]]:
    """OCR 1 frame (ndarray) → list (x_trái, text, box 0..1) các dòng đạt ngưỡng tin cậy.

    box = [x0, y0, x1, y1] chuẩn hóa theo kích thước ảnh crop — S8 dùng để
    che mờ tự động đúng vùng chữ sub gốc.
    """
    result, _ = engine(img)
    if not result:
        return []
    h, w = img.shape[:2]
    lines = []
    for box, text, conf in result:
        if float(conf) < config.OCR_MIN_CONF or _JUNK.search(text):
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        nbox = [min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h]
        lines.append((min(xs), text.strip(), nbox))
    return sorted(lines, key=lambda l: l[0])


# ---- OCR song song: worker process (Windows spawn cần hàm module-level) ----
_worker_engine = None


def _init_worker() -> None:
    global _worker_engine
    from rapidocr_onnxruntime import RapidOCR
    # onnxruntime hầu như không scale theo luồng với model này (đo thực tế:
    # 16 luồng chỉ nhanh hơn 2 luồng ~13%) → mỗi worker 2 luồng, nhiều worker.
    # use_angle_cls=False: phụ đề luôn nằm ngang, bỏ bước phân loại góc chữ
    # (bản 1.2.3 chỉ nhận cờ này ở constructor, truyền vào __call__ bị lờ đi)
    _worker_engine = RapidOCR(intra_op_num_threads=2, use_angle_cls=False)


def _ocr_one(path: str) -> list[tuple[str, list[float]]]:
    img = cv2.imread(path)
    if img is None:
        return []
    return [(text, box) for _, text, box in _frame_lines(_worker_engine, img)]


# Ghi chú: đã thử dedup frame trùng (so pixel thô lẫn mặt nạ pixel sáng) —
# thí nghiệm trên dữ liệu thật cho thấy mọi ngưỡng đều gây sai văn bản
# (nền video động sau phụ đề phá tín hiệu so sánh) nên không dùng.


def _select_lines(lines: list[tuple[str, list[float]]],
                  blacklist: set[str]) -> tuple[str, list[list[float]]]:
    """Lọc dòng rác → (text ghép, box các dòng được giữ)."""
    kept = [(t, b) for t, b in lines if _normalize(t) not in blacklist]
    if not kept:
        return "", []
    # phụ đề song ngữ / watermark chữ Latin: nếu có dòng CJK thì chỉ giữ CJK
    cjk = [(t, b) for t, b in kept if _CJK.search(t)]
    use = cjk or kept
    return " ".join(t for t, _ in use), [b for _, b in use]


def extract(video: Path, work_dir: Path) -> list[dict]:
    """OCR video → list segment. work_dir dùng chứa frame tạm (tự dọn khi xong)."""
    frames_dir = work_dir / "ocr_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    crop_top = config.OCR_CROP_TOP
    crop_h = 1.0 - crop_top
    ffmpeg.run(
        "-i", str(video),
        "-vf",
        f"fps={config.OCR_FPS},"
        f"crop=iw:ih*{crop_h:.2f}:0:ih*{crop_top:.2f},"
        "scale=iw*2:ih*2:flags=lanczos",
        "-qscale:v", "2",
        str(frames_dir / "%06d.jpg"),
    )

    step = 1.0 / config.OCR_FPS
    frame_paths = sorted(frames_dir.glob("*.jpg"))

    # Pha 1: OCR song song (imap để đếm tiến độ theo frame → ghi stage_progress.json)
    print(f"  OCR: {len(frame_paths)} frame, {config.OCR_WORKERS} worker")
    from concurrent.futures import ProcessPoolExecutor
    from core import progress
    total = len(frame_paths)
    progress.write(work_dir, "transcribing", 0, total)
    all_lines = []
    with ProcessPoolExecutor(max_workers=config.OCR_WORKERS,
                             initializer=_init_worker) as pool:
        for i, res in enumerate(
                pool.imap(_ocr_one, [str(p) for p in frame_paths], chunksize=8), 1):
            all_lines.append(res)
            if i % 15 == 0 or i == total:
                progress.write(work_dir, "transcribing", i, total)

    frames: list[tuple[float, list[tuple[str, list[float]]]]] = []
    for frame, lines in zip(frame_paths, all_lines):
        t = (int(frame.stem) - 0.5) * step
        frames.append((t, lines))

    (work_dir / "ocr_raw.json").write_text(
        json.dumps([{"t": round(t, 3), "lines": [x for x, _ in lines]}
                    for t, lines in frames],
                   ensure_ascii=False),
        encoding="utf-8",
    )

    # Dòng xuất hiện ở ≥15% số frame = watermark/logo đứng yên — loại toàn bộ
    line_freq = Counter()
    for _, lines in frames:
        for text in set(_normalize(x) for x, _ in lines):
            if len(text) >= 2:
                line_freq[text] += 1
    blacklist = {text for text, n in line_freq.items()
                 if n >= max(10, 0.15 * len(frames))}

    # Pha 2: ghép segment từ text đã lọc
    segments: list[dict] = []
    cur_norm = ""          # bản chuẩn hóa dài nhất của nhóm, dùng để so sánh
    cur_raws: list[str] = []  # các bản raw, chọn bản phổ biến nhất làm text
    cur_boxes: list[list[float]] = []  # box các dòng được giữ (tọa độ dải crop)
    cur_start = cur_last = 0.0

    def close_group() -> None:
        nonlocal cur_norm, cur_raws, cur_boxes
        if cur_norm:
            duration = cur_last - cur_start + step
            if duration >= MIN_DURATION_S and len(cur_norm) >= MIN_CHARS:
                seg = {
                    "text": Counter(cur_raws).most_common(1)[0][0],
                    "start": round(cur_start, 3),
                    "end": round(cur_last + step / 2, 3),
                }
                if cur_boxes:
                    # hợp box cả nhóm, đổi từ tọa độ dải crop → tỉ lệ khung hình đầy đủ
                    seg["box"] = [
                        round(min(b[0] for b in cur_boxes), 4),
                        round(crop_top + min(b[1] for b in cur_boxes) * crop_h, 4),
                        round(max(b[2] for b in cur_boxes), 4),
                        round(crop_top + max(b[3] for b in cur_boxes) * crop_h, 4),
                    ]
                segments.append(seg)
        cur_norm, cur_raws, cur_boxes = "", [], []

    for t, lines in frames:
        raw, boxes = _select_lines(lines, blacklist)
        norm = _normalize(raw)

        if not norm:
            close_group()
        elif cur_norm and SequenceMatcher(None, norm, cur_norm).ratio() >= SIMILARITY:
            cur_last = t
            cur_raws.append(raw)
            cur_boxes.extend(boxes)
            if len(norm) > len(cur_norm):  # frame đầu/cuối hay mất ký tự
                cur_norm = norm
        else:
            close_group()
            cur_norm, cur_raws, cur_boxes = norm, [raw], list(boxes)
            cur_start = cur_last = t

    close_group()
    shutil.rmtree(frames_dir, ignore_errors=True)

    # Vị trí sub gốc theo thời gian — S8 dùng cho chế độ che mờ tự động.
    # Ghi trước khi bỏ key "box": transcript giữ nguyên format cũ.
    # start lùi 1.5*step: timestamp frame là điểm giữa mẫu và sub có thể đã hiện
    # ngay sau lần lấy mẫu trước — không bù thì chữ gốc lóe lên đầu mỗi câu
    # (end đã được close_group bù sẵn +step/2 tới đúng thời điểm mẫu kế tiếp).
    (work_dir / "sub_boxes.json").write_text(
        json.dumps([{"start": round(max(0.0, s["start"] - 1.5 * step), 3),
                     "end": s["end"], "box": s["box"]}
                    for s in segments if s.get("box")],
                   ensure_ascii=False),
        encoding="utf-8",
    )
    for seg in segments:
        seg.pop("box", None)

    for i, seg in enumerate(segments, start=1):
        seg["id"] = i
    return segments
