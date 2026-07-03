"""Khung viền quanh video (áp khi render S8).

- Procedural (ffmpeg drawbox): 'solid' (viền đơn), 'double' (viền đôi) — chọn màu + độ dày.
- PNG: 'png:<tên>' — phủ ảnh khung (nền GIỮA trong suốt) trong thư mục frames/ lên video.

append_to_vf() trả chuỗi -vf đã CHÈN khung vào cuối (sau cover/sub). Khung = sửa pixel
→ s8 ép re-encode (mode burn) khi frame != none.
"""
from __future__ import annotations

import os
import re

import config

_HEX = re.compile(r"^#?([0-9A-Fa-f]{6})$")
# khung vẽ bằng ffmpeg (procedural). twocolor dùng thêm màu 2; corner = bo 4 góc
PRESETS = [("solid", "Viền đơn"), ("double", "Viền đôi"),
           ("twocolor", "Viền 2 màu"), ("corner", "Bo góc / 4 góc")]


def _color(hexs: str) -> str:
    """#RRGGBB → 0xRRGGBB cho drawbox (mặc định trắng nếu sai định dạng)."""
    m = _HEX.match(str(hexs or ""))
    return "0x" + (m.group(1).upper() if m else "FFFFFF")


def list_png() -> list[str]:
    """Tên các file .png trong frames/ (khung trang trí người dùng thả vào)."""
    d = config.FRAMES_DIR
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*.png"))


def _png_relpath(name: str, job_dir) -> str | None:
    """Đường dẫn TƯƠNG ĐỐI (từ job_dir) tới frames/<name>.png — chặn path traversal +
    né escape ':' ổ đĩa Windows trong filtergraph. None nếu file không hợp lệ."""
    safe = os.path.basename(name or "")          # bỏ mọi thành phần thư mục
    # tên chứa ký tự phá filtergraph (movie=filename='...') → bỏ, kẻo vỡ render/inject filter
    if not safe or any(ch in safe for ch in "',:;[]\\"):
        return None
    p = config.FRAMES_DIR / safe
    if p.suffix.lower() != ".png" or not p.is_file():
        return None
    return os.path.relpath(p, job_dir).replace("\\", "/")


def _drawboxes(frame: str, color: str, color2: str, width_frac: float, w: int, h: int) -> str:
    c, c2 = _color(color), _color(color2)
    wf = min(0.15, max(0.001, float(width_frac)))   # chặn giá trị vô lý (double → w âm)
    b = max(2, int(wf * h))                          # độ dày px = tỉ lệ * chiều cao video
    if frame == "double":
        off = 2 * b
        b2 = max(2, b // 2)
        return (f"drawbox=x=0:y=0:w=iw:h=ih:color={c}:t={b}"
                f",drawbox=x={off}:y={off}:w=iw-{2 * off}:h=ih-{2 * off}:color={c}:t={b2}")
    if frame == "twocolor":   # viền ngoài màu 1 + viền trong màu 2 (kề nhau)
        return (f"drawbox=x=0:y=0:w=iw:h=ih:color={c}:t={b}"
                f",drawbox=x={b}:y={b}:w=iw-{2 * b}:h=ih-{2 * b}:color={c2}:t={b}")
    if frame == "corner":     # 4 góc kiểu ngoặc L (chỉ ở góc, không viền hết)
        L = max(b * 4, int(0.08 * min(w, h)))
        seg = [
            (0, 0, L, b), (0, 0, b, L),                       # góc trên-trái
            (f"iw-{L}", 0, L, b), (f"iw-{b}", 0, b, L),       # trên-phải
            (0, f"ih-{b}", L, b), (0, f"ih-{L}", b, L),       # dưới-trái
            (f"iw-{L}", f"ih-{b}", L, b), (f"iw-{b}", f"ih-{L}", b, L),  # dưới-phải
        ]
        return ",".join(
            f"drawbox=x={x}:y={y}:w={bw}:h={bh}:color={c}:t=fill" for x, y, bw, bh in seg)
    return f"drawbox=x=0:y=0:w=iw:h=ih:color={c}:t={b}"   # solid


def append_to_vf(base: str, frame: str, color: str, color2: str, width: float,
                 w: int, h: int, job_dir) -> str:
    """Chèn khung vào CUỐI chuỗi -vf. base = filter cover+sub (có thể là graph có ';').
    base luôn khác rỗng khi gọi từ s8 (ít nhất là subtitles)."""
    if not frame or frame == "none":
        return base
    base = base or "null"                         # đảm bảo có filter nguồn (s8 luôn truyền base thật)
    if frame.startswith("png:"):
        rel = _png_relpath(frame[4:], job_dir)
        if not rel:                               # file mất/không hợp lệ → bỏ khung
            return base
        ov = f"movie=filename='{rel}',scale={w}:{h}[fr];"
        return f"{base}[fb];{ov}[fb][fr]overlay=0:0"
    return f"{base},{_drawboxes(frame, color, color2, width, w, h)}"   # procedural
