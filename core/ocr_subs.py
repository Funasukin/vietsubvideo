"""Trích phụ đề hardsub thành segment bằng OCR (RapidOCR/ONNX).

Cách làm: lấy mẫu frame OCR_FPS hình/giây, crop dải phụ đề (OCR_CROP_TOP → đáy,
upscale 2x vì chữ phụ đề thường nhỏ), OCR từng frame, rồi gộp chuỗi frame có
cùng text thành segment {id, text, start, end} — cùng định dạng với whisper.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
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

# VÙNG CHẾT dải dẹt (DEXUAT_OCR_VUNGCHET, đo 2026-07-13): det model của rapidocr
# 1.2.3 scale cạnh NGẮN lên 736 (limit_type=min) — dải crop quá dẹt thành tensor
# cực rộng làm detector mù (đo thật: 7.1:1 sống, 8:1 RỖNG hoàn toàn; phóng to giữ
# tỉ lệ vô ích, THÊM CHIỀU CAO là sống). Trần 5:1 chừa dư an toàn.
MAX_OCR_ASPECT = 5.0


def _pad_for_detection(img):
    """Dải quét dẹt hơn 5:1 → đệm ĐEN phía TRÊN cho đủ tỉ lệ (đen = letterbox
    chuẩn, det bỏ qua vùng đồng màu; KHÔNG replicate mép — kéo thành sọc dọc
    tạo box chữ giả). Trigger theo TỈ LỆ chứ không px tuyệt đối: pipeline đã
    scale 2× và video dọc dải cao thì không việc gì. → (ảnh, pad_top px)."""
    import math
    h, w = img.shape[:2]
    # math.ceil trên float: int(MAX_OCR_ASPECT) sẽ lặng lẽ nuốt phần lẻ nếu ai
    # chỉnh hằng số thành 5.5 (review O#P1)
    target_h = math.ceil(w / MAX_OCR_ASPECT)
    if h >= target_h:
        return img, 0
    return cv2.copyMakeBorder(img, target_h - h, 0, 0, 0,
                              cv2.BORDER_CONSTANT, value=(0, 0, 0)), target_h - h


def _normalize(text: str) -> str:
    return _NORM_DROP.sub("", text)


def _frame_lines(engine, img,
                 pad_top: int = 0) -> list[tuple[float, str, list[float]]]:
    """OCR 1 frame (ndarray) → list (x_trái, text, box 0..1) các dòng đạt ngưỡng tin cậy.

    box = [x0, y0, x1, y1] chuẩn hóa theo kích thước ảnh crop — S8 dùng để
    che mờ tự động đúng vùng chữ sub gốc.

    pad_top: ảnh đã qua _pad_for_detection → trừ offset Ở TỌA ĐỘ PIXEL trước khi
    chuẩn hoá (contract "nbox theo crop GỐC" giữ nguyên — tầng ghép segment và
    che mờ S8 không cần biết padding tồn tại). Box có TÂM nằm trong vùng đệm
    (đen tuyệt đối, không thể có chữ thật) → rác của detector, loại."""
    result, _ = engine(img)
    if not result:
        return []
    h, w = img.shape[:2]
    h -= pad_top                      # chiều cao crop GỐC
    lines = []
    for box, text, conf in result:
        if float(conf) < config.OCR_MIN_CONF or _JUNK.search(text):
            continue
        xs = [p[0] for p in box]
        ys = [p[1] - pad_top for p in box]        # về hệ tọa độ crop gốc
        if sum(ys) / len(ys) < 0:                 # tâm box trong vùng đệm → rác
            continue
        ys = [min(h, max(0.0, y)) for y in ys]    # kẹp phần lấn nhẹ vào đệm
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
    padded, pad_top = _pad_for_detection(img)   # chống vùng chết dải dẹt
    return [(text, box)
            for _, text, box in _frame_lines(_worker_engine, padded, pad_top)]


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


def _duration(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(video)],
                       capture_output=True, text=True)
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        return 0.0


def _auto_crop_top(video: Path, work_dir: Path, sample: int = 16) -> float | None:
    """Tự đo mép TRÊN của dải phụ đề: OCR ~sample frame rải đều TOÀN khung, gom vị trí
    y các dòng chữ trong [0.22, 0.97] (bỏ watermark đỉnh + UI đáy), rồi chọn DẢI TRỘI —
    băng y xuất hiện NHIỀU dòng nhất qua các frame chính là phụ đề (hiện ở mọi cảnh,
    vị trí cố định); chữ khác trên hình (bảng menu, biển hiệu, giá tiền...) chỉ hiện
    ở vài cảnh nên băng của chúng thưa hơn. (Bản đầu lấy phân vị 15% của MỌI dòng —
    video quán ăn đầy chữ giữa màn hình kéo crop lên tận sàn → OCR nuốt menu vào thoại.)
    Trả None nếu không đủ dữ liệu (→ dùng mặc định)."""
    dur = _duration(video)
    if dur <= 1:
        return None
    probe = work_dir / "ocr_probe"
    if probe.exists():
        shutil.rmtree(probe)
    probe.mkdir(parents=True)
    fps = max(0.03, min(2.0, sample / dur))
    # quét toàn khung (không crop), thu nhỏ về 640px cho nhanh — đủ để ĐỊNH VỊ chữ
    ffmpeg.run("-i", str(video), "-vf", f"fps={fps},scale=640:-2",
               "-qscale:v", "3", str(probe / "%04d.jpg"))
    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR(intra_op_num_threads=2, use_angle_cls=False)
    tops: list[float] = []
    frame_tops: list[tuple] = []   # (path, tops của frame) — giữ cho kiểm nhất quán O-2
    for p in sorted(probe.glob("*.jpg")):
        img = cv2.imread(str(p))
        if img is None:
            continue
        f_tops = [nbox[1] for _x, _text, nbox in _frame_lines(eng, img)  # đã lọc conf+junk
                  if 0.22 <= nbox[1] <= 0.97]
        tops.extend(f_tops)
        frame_tops.append((p, f_tops))
    if len(tops) < 4:
        shutil.rmtree(probe, ignore_errors=True)
        return None
    # gom mép-trên vào băng 0.05 → băng nhiều dòng nhất = dải phụ đề; đồng điểm thì
    # lấy băng THẤP hơn trên màn hình (phụ đề luôn nằm dưới chữ trang trí cùng tần suất)
    band = Counter(round(t / 0.05) * 0.05 for t in tops)
    best = max(band.items(), key=lambda kv: (kv[1], kv[0]))[0]
    members = [t for t in tops if best - 0.03 <= t <= best + 0.08]
    # round 2 chữ số NGAY TẠI ĐÂY: extract quy về 2 chữ số cho ffmpeg/map box —
    # log in 0.743 mà chạy 0.74 là đánh lừa user tái hiện tay (review O#P3)
    ct = max(0.30, min(0.80, round(min(members) - 0.06, 2)))
    # O-2 (DEXUAT_OCR_VUNGCHET): kiểm NHẤT QUÁN — probe toàn-khung ĐÃ thấy chữ
    # trong băng sub, vậy biến đổi production (crop→2×→pad) trên CHÍNH các frame
    # đó cũng phải thấy. Mù ở phần lớn frame = vùng chết mới/crop hỏng → cảnh
    # báo TO (không tự retry — tốn full-scan + có thể kéo nhiễu, user quyết).
    # Job hỏng 64fd4e từng đạt 4.4 câu/phút vẫn lọt gate mật độ — ngưỡng cố định
    # vô dụng, chỉ có so probe-vs-production mới bắt được (Codex).
    band_frames = [p for p, ts in frame_tops
                   if any(best - 0.03 <= t <= best + 0.08 for t in ts)]
    if len(band_frames) >= 3:
        checked = band_frames[:8]
        seen = 0
        for p in checked:
            img = cv2.imread(str(p))
            if img is not None and _production_sees(eng, img, ct):
                seen += 1
        if seen * 3 < len(checked):
            print(f"  CANH BAO OCR: probe thay phu de o {len(checked)} frame nhung ban "
                  f"quet san xuat chi thay {seen} (crop_top={ct}) - nghi VUNG CHET "
                  f"vung quet. Kiem tra OCR_CROP_TOP hoac chuyen TRANSCRIPT_SOURCE=whisper.")
    shutil.rmtree(probe, ignore_errors=True)
    return ct


def _production_sees(eng, img_full, ct: float) -> bool:
    """Mô phỏng ĐÚNG chuỗi biến đổi production trên 1 frame probe (crop dải →
    scale 2× → đệm chống dẹt) rồi hỏi detector có thấy chữ không — canary cho
    vùng chết. Frame probe 640px nhưng TỈ LỆ dải y hệt production (vùng chết là
    hiện tượng theo tỉ lệ — đã kiểm chứng bằng thí nghiệm phóng to/đệm)."""
    h = img_full.shape[0]
    strip = img_full[int(ct * h):]
    if strip.size == 0:
        return False
    strip = cv2.resize(strip, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    padded, pad_top = _pad_for_detection(strip)
    return bool(_frame_lines(eng, padded, pad_top))


def probe_crop_top(video: Path, work_dir: Path) -> float | None:
    """Dò dải phụ đề (rẻ, ~16 frame). Trả crop_top hoặc None = KHÔNG thấy dải sub ổn
    định. Audit #4: chế độ transcript 'auto' dùng làm CỬA SƠ LOẠI — video không có
    hardsub thì khỏi OCR full (từng quét cả nghìn frame rồi vứt), đi thẳng Whisper.
    Kết quả truyền lại extract(crop_top=...) để khỏi dò lần 2."""
    return _auto_crop_top(video, work_dir)


def _resolve_crop_top(video: Path, work_dir: Path) -> float:
    """Giải nghĩa config.OCR_CROP_TOP: 'auto' → tự đo (fallback 0.70); số → dùng thẳng."""
    raw = config.OCR_CROP_TOP
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        ct = _auto_crop_top(video, work_dir)
        if ct is None:
            print("  OCR: không đo được dải phụ đề → dùng crop_top=0.70")
            return 0.70
        print(f"  OCR: tự đo dải phụ đề → crop_top={ct} (quét từ {ct * 100:.0f}% xuống đáy)")
        return ct
    try:
        return max(0.0, min(0.95, float(raw)))
    except (TypeError, ValueError):
        return 0.70


def extract(video: Path, work_dir: Path, crop_top: float | None = None) -> list[dict]:
    """OCR video → list segment. work_dir dùng chứa frame tạm (tự dọn khi xong).
    crop_top: caller đã dò sẵn (probe_crop_top) thì truyền vào — khỏi dò lần 2."""
    frames_dir = work_dir / "ocr_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    if crop_top is None:
        crop_top = _resolve_crop_top(video, work_dir)
    else:
        print(f"  OCR: dùng dải phụ đề đã dò → crop_top={crop_top}")
    # dùng MỘT giá trị hiệu dụng cho CẢ ffmpeg lẫn map box (Codex bắt lỗi: filter
    # format :.2f cắt theo 0.74 nhưng box map theo 0.743 → che mờ lệch vài px)
    crop_top = round(float(crop_top), 2)
    crop_h = round(1.0 - crop_top, 2)
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

    # Pha 1: OCR song song (map trả kết quả LƯỜI theo thứ tự → đếm được tiến độ
    # theo frame, ghi stage_progress.json). Executor.map ≠ Pool.imap — đừng nhầm.
    print(f"  OCR: {len(frame_paths)} frame, {config.OCR_WORKERS} worker")
    from concurrent.futures import ProcessPoolExecutor
    from core import progress
    total = len(frame_paths)
    progress.write(work_dir, "transcribing", 0, total)
    all_lines = []
    with ProcessPoolExecutor(max_workers=config.OCR_WORKERS,
                             initializer=_init_worker) as pool:
        for i, res in enumerate(
                pool.map(_ocr_one, [str(p) for p in frame_paths], chunksize=8), 1):
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

    n_pos = 0   # frame có chữ THẬT (sau lọc watermark) — cho telemetry O-2
    for t, lines in frames:
        raw, boxes = _select_lines(lines, blacklist)
        norm = _normalize(raw)
        if norm:
            n_pos += 1

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

    # Telemetry O-2 (vào run.log): dữ liệu thô để chẩn đoán vùng quét + làm nền
    # cho vòng "auto thông minh hơn" sau — KHÔNG dùng một con số đơn lẻ để phán.
    # n_pos đếm SAU lọc watermark (review O#P4: video có logo đứng yên mà đếm
    # thô là positive ~100% dù không có sub).
    if frames:
        dur_min = len(frames) * step / 60
        gaps = [b["start"] - a["end"] for a, b in zip(segments, segments[1:])]
        print(f"  OCR telemetry: frame có chữ {n_pos}/{len(frames)} "
              f"({n_pos / len(frames) * 100:.0f}%) · {len(segments)} câu / "
              f"{dur_min:.1f} phút ({len(segments) / max(0.1, dur_min):.1f} câu/phút)"
              f" · khoảng trống dài nhất {max(gaps, default=0):.0f}s")
    return segments
