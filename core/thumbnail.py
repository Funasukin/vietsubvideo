"""Tạo thumbnail YouTube 1280x720: chọn frame đẹp + vẽ chữ hook kiểu donghua.

Quy trình: trích 8 frame rải đều phim → cv2 loại frame mờ/tối → Claude vision
chọn frame bắt mắt nhất → PIL vẽ 2 dòng chữ (viền đen dày, vàng + trắng).
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import anthropic
import cv2
from PIL import Image, ImageDraw, ImageFont

import config
from core import ffmpeg

N_CANDIDATES = 8
N_SEND = 6  # số frame gửi Claude vision

_FONTS = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
          r"C:\Windows\Fonts\arial.ttf"]

PICK_SCHEMA = {
    "type": "object",
    "properties": {"best": {"type": "integer"}},
    "required": ["best"],
    "additionalProperties": False,
}


def _duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _candidate_times(dur: float, avoid: list[tuple[float, float]]) -> list[float]:
    """Chọn N thời điểm rải đều, ưu tiên khoảng lặng giữa các câu thoại
    (không thoại = không có phụ đề cháy trong hình)."""
    lo, hi = dur * 0.12, dur * 0.88
    spans = sorted((max(lo, s - 0.4), min(hi, e + 0.4)) for s, e in avoid
                   if e > lo and s < hi)
    gaps, cursor = [], lo
    for s, e in spans:
        if s - cursor >= 1.2:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if hi - cursor >= 1.2:
        gaps.append((cursor, hi))

    times = [g0 + (g1 - g0) / 2 for g0, g1 in gaps]
    if len(times) >= N_CANDIDATES:
        # rải đều: lấy N điểm cách quãng trong danh sách gap
        step = len(times) / N_CANDIDATES
        return [times[int(i * step)] for i in range(N_CANDIDATES)]
    # không đủ khoảng lặng → bù bằng điểm chia đều
    even = [dur * (0.12 + 0.76 * i / (N_CANDIDATES - 1)) for i in range(N_CANDIDATES)]
    return (times + even)[:N_CANDIDATES]


def _extract_candidates(video: Path, work_dir: Path,
                        avoid: list[tuple[float, float]]) -> list[Path]:
    paths = []
    for i, t in enumerate(_candidate_times(_duration(video), avoid)):
        p = work_dir / f"thumb_cand_{i}.jpg"
        ffmpeg.run("-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                   "-qscale:v", "2", str(p))
        paths.append(p)
    return paths


def _score(path: Path) -> float:
    """Điểm chất lượng frame: nét (Laplacian) + đủ sáng + màu sắc."""
    img = cv2.imread(str(path))
    if img is None:
        return -1
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
    bright = gray.mean()
    sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 1].mean()
    if bright < 35 or bright > 220:  # quá tối / cháy sáng
        return -1
    return sharp + sat * 2


def _claude_pick(client: anthropic.Anthropic, frames: list[Path], summary: str) -> Path:
    content = [{"type": "text", "text":
                f"Phim donghua, tóm tắt: {summary}\n"
                f"Chọn 1 frame làm thumbnail YouTube bắt mắt nhất (nhân vật rõ, "
                f"biểu cảm/hành động kịch tính, không phải cảnh trống). "
                f"Trả về best = số thứ tự frame (1-{len(frames)})."}]
    for i, p in enumerate(frames, 1):
        img = Image.open(p)
        img.thumbnail((640, 640))
        from io import BytesIO
        buf = BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        content.append({"type": "text", "text": f"Frame {i}:"})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": base64.standard_b64encode(buf.getvalue()).decode()}})

    resp = client.messages.create(
        model=config.METADATA_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": PICK_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    best = json.loads(text)["best"]
    return frames[max(0, min(len(frames) - 1, best - 1))]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for f in _FONTS:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int,
              start_size: int) -> ImageFont.FreeTypeFont:
    """Co cỡ chữ đến khi dòng vừa khung (chống tràn mép)."""
    size = start_size
    while size > 36:
        font = _font(size)
        if draw.textlength(text, font=font) + 16 <= max_width:
            return font
        size -= 6
    return _font(36)


def _draw_text(img: Image.Image, lines: list[str]) -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    max_width = w - 96
    y = h - 48
    specs = [(96, (255, 214, 51)), (64, (255, 255, 255))]  # dòng 1 vàng, dòng 2 trắng
    rendered = []
    for line, (size, color) in zip(lines[:2], specs):
        line = line.strip().upper()
        if not line:
            continue
        font = _fit_font(draw, line, max_width, size)
        box = draw.textbbox((0, 0), line, font=font, stroke_width=8)
        rendered.append((line, font, color, box[3] - box[1]))
    for line, font, color, line_h in reversed(rendered):
        y -= line_h + 26
        draw.text((48, y), line, font=font, fill=color,
                  stroke_width=8, stroke_fill=(0, 0, 0))


def generate(video: Path, work_dir: Path, hook_lines: list[str],
             summary: str, client: anthropic.Anthropic,
             avoid_spans: list[tuple[float, float]] | None = None) -> Path:
    """Tạo work_dir/thumbnail.jpg, trả về đường dẫn."""
    out = work_dir / "thumbnail.jpg"
    candidates = _extract_candidates(video, work_dir, avoid_spans or [])
    scored = sorted(((p, _score(p)) for p in candidates),
                    key=lambda x: -x[1])
    good = [p for p, s in scored if s > 0][:N_SEND] or [scored[0][0]]
    best = _claude_pick(client, good, summary) if len(good) > 1 else good[0]

    img = Image.open(best).convert("RGB")
    # frame đã chọn ở khoảng lặng (ít khả năng có sub) — vẫn cắt nhẹ đáy đề phòng
    img = img.crop((0, 0, img.width, int(img.height * 0.88)))
    # cover-crop về 1280x720
    scale = max(1280 / img.width, 720 / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)),
                     Image.LANCZOS)
    left, top = (img.width - 1280) // 2, (img.height - 720) // 2
    img = img.crop((left, top, left + 1280, top + 720))

    _draw_text(img, hook_lines)
    img.save(out, "JPEG", quality=90)

    for p in candidates:
        p.unlink(missing_ok=True)
    return out
