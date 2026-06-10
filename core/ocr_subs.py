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


def _frame_lines(engine, img_path: Path) -> list[tuple[float, str]]:
    """OCR 1 frame → list (x_trái, text) các dòng đạt ngưỡng tin cậy."""
    result, _ = engine(str(img_path))
    if not result:
        return []
    lines = []
    for box, text, conf in result:
        if float(conf) < config.OCR_MIN_CONF or _JUNK.search(text):
            continue
        lines.append((min(p[0] for p in box), text.strip()))
    return sorted(lines)


def _join_lines(texts: list[str], blacklist: set[str]) -> str:
    texts = [t for t in texts if _normalize(t) not in blacklist]
    if not texts:
        return ""
    # phụ đề song ngữ / watermark chữ Latin: nếu có dòng CJK thì chỉ giữ CJK
    cjk = [t for t in texts if _CJK.search(t)]
    return " ".join(cjk or texts)


def extract(video: Path, work_dir: Path) -> list[dict]:
    """OCR video → list segment. work_dir dùng chứa frame tạm (tự dọn khi xong)."""
    from rapidocr_onnxruntime import RapidOCR

    frames_dir = work_dir / "ocr_frames"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)

    crop_h = 1.0 - config.OCR_CROP_TOP
    ffmpeg.run(
        "-i", str(video),
        "-vf",
        f"fps={config.OCR_FPS},"
        f"crop=iw:ih*{crop_h:.2f}:0:ih*{config.OCR_CROP_TOP:.2f},"
        "scale=iw*2:ih*2:flags=lanczos",
        "-qscale:v", "2",
        str(frames_dir / "%06d.jpg"),
    )

    engine = RapidOCR()
    step = 1.0 / config.OCR_FPS

    # Pha 1: OCR toàn bộ frame, gom dòng thô
    frames: list[tuple[float, list[str]]] = []
    for frame in sorted(frames_dir.glob("*.jpg")):
        t = (int(frame.stem) - 0.5) * step
        frames.append((t, [text for _, text in _frame_lines(engine, frame)]))

    (work_dir / "ocr_raw.json").write_text(
        json.dumps([{"t": round(t, 3), "lines": lines} for t, lines in frames],
                   ensure_ascii=False),
        encoding="utf-8",
    )

    # Dòng xuất hiện ở ≥15% số frame = watermark/logo đứng yên — loại toàn bộ
    line_freq = Counter()
    for _, lines in frames:
        for text in set(_normalize(x) for x in lines):
            if len(text) >= 2:
                line_freq[text] += 1
    blacklist = {text for text, n in line_freq.items()
                 if n >= max(10, 0.15 * len(frames))}

    # Pha 2: ghép segment từ text đã lọc
    segments: list[dict] = []
    cur_norm = ""          # bản chuẩn hóa dài nhất của nhóm, dùng để so sánh
    cur_raws: list[str] = []  # các bản raw, chọn bản phổ biến nhất làm text
    cur_start = cur_last = 0.0

    def close_group() -> None:
        nonlocal cur_norm, cur_raws
        if cur_norm:
            duration = cur_last - cur_start + step
            if duration >= MIN_DURATION_S and len(cur_norm) >= MIN_CHARS:
                segments.append({
                    "text": Counter(cur_raws).most_common(1)[0][0],
                    "start": round(cur_start, 3),
                    "end": round(cur_last + step / 2, 3),
                })
        cur_norm, cur_raws = "", []

    for t, lines in frames:
        raw = _join_lines(lines, blacklist)
        norm = _normalize(raw)

        if not norm:
            close_group()
        elif cur_norm and SequenceMatcher(None, norm, cur_norm).ratio() >= SIMILARITY:
            cur_last = t
            cur_raws.append(raw)
            if len(norm) > len(cur_norm):  # frame đầu/cuối hay mất ký tự
                cur_norm = norm
        else:
            close_group()
            cur_norm, cur_raws = norm, [raw]
            cur_start = cur_last = t

    close_group()
    shutil.rmtree(frames_dir, ignore_errors=True)

    for i, seg in enumerate(segments, start=1):
        seg["id"] = i
    return segments
