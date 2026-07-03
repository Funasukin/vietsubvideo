"""Khung viền quanh video (áp khi render S8).

- Procedural (ffmpeg drawbox): 'solid' (viền đơn), 'double' (viền đôi) — chọn màu + độ dày.
- PNG: 'png:<tên>' — khung ảnh trong frames/ (nền GIỮA trong suốt), dựng đúng kích thước
  video bằng 9-SLICE (4 góc giữ nguyên tỉ lệ, 4 cạnh chỉ kéo theo 1 chiều) → hoa văn
  không méo ở mọi tỉ lệ video (ngang/dọc/vuông).
- pad=True ("khung ngoài"): thu video vào trong vừa đủ rồi mới vẽ khung ra phần lề —
  khung không che mất pixel nội dung nào.

append_to_vf() trả chuỗi -vf đã CHÈN khung vào cuối (sau cover/sub). Khung = sửa pixel
→ s8 ép re-encode (mode burn) khi frame != none.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

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


# Cỡ ô góc 9-slice = tỉ lệ này × cạnh ngắn (của ảnh nguồn lẫn video đích)
_CORNER_FRAC = 0.30


def _src_png(name: str) -> Path | None:
    """frames/<name>.png — chặn path traversal. None nếu file không hợp lệ."""
    safe = os.path.basename(name or "")          # bỏ mọi thành phần thư mục
    p = config.FRAMES_DIR / safe
    if p.suffix.lower() != ".png" or not p.is_file():
        return None
    return p


def _nine_slice(src, tw: int, th: int):
    """Dựng khung (tw,th) từ ảnh nguồn theo 9-slice: chia 3×3, góc giữ đúng tỉ lệ,
    cạnh kéo theo 1 chiều, phần giữa (thường trong suốt) kéo cả 2 chiều."""
    from PIL import Image
    sw, sh = src.size
    c = max(1, int(min(sw, sh) * _CORNER_FRAC))
    ct = max(1, min(int(min(tw, th) * _CORNER_FRAC), tw // 2 - 1, th // 2 - 1))
    sx = [0, c, sw - c, sw]
    sy = [0, c, sh - c, sh]
    dx = [0, ct, tw - ct, tw]
    dy = [0, ct, th - ct, th]
    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    for i in range(3):
        for j in range(3):
            if sx[i + 1] <= sx[i] or sy[j + 1] <= sy[j]:
                continue
            if dx[i + 1] <= dx[i] or dy[j + 1] <= dy[j]:
                continue
            tile = src.crop((sx[i], sy[j], sx[i + 1], sy[j + 1])).resize(
                (dx[i + 1] - dx[i], dy[j + 1] - dy[j]), Image.Resampling.LANCZOS)
            out.paste(tile, (dx[i], dy[j]))
    return out


def build_sized_png(name: str, w: int, h: int, job_dir) -> str | None:
    """Sinh <job_dir>/frame_overlay.png đúng (w,h) bằng 9-slice từ frames/<name>.
    Trả TÊN FILE (dùng với cwd=job_dir, tên cố định nên không cần escape filtergraph);
    None nếu nguồn không hợp lệ."""
    p = _src_png(name)
    if p is None:
        return None
    from PIL import Image
    src = Image.open(p).convert("RGBA")
    _nine_slice(src, w, h).save(Path(job_dir) / "frame_overlay.png")
    return "frame_overlay.png"


def _insets_from_alpha(img) -> tuple[int, int, int, int]:
    """(top, bottom, left, right): bề dày lớp khung đục ở mỗi cạnh — hàng/cột xa mép
    nhất còn alpha đáng kể, đo trên 1/3 GIỮA của cạnh đối diện để hoa văn góc
    (vốn to hơn cạnh) không làm dày giả. Cap 35% kích thước."""
    import numpy as np
    a = np.asarray(img)[:, :, 3]
    h, w = a.shape

    def extent(m, cap):
        idx = [i for i in range(min(cap, len(m))) if m[i] >= 32]
        return (idx[-1] + 1) if idx else 0

    xs = slice(w // 3, 2 * w // 3)
    ys = slice(h // 3, 2 * h // 3)
    cap_v, cap_h = int(0.35 * h), int(0.35 * w)
    return (extent(a[:, xs].max(axis=1), cap_v),
            extent(a[::-1, xs].max(axis=1), cap_v),
            extent(a[ys, :].max(axis=0), cap_h),
            extent(a[ys, ::-1].max(axis=0), cap_h))


def _proc_inset(frame: str, width_frac: float, h: int) -> int:
    """Bề dày khung procedural tính từ mép (px) — khớp hình học trong _drawboxes."""
    wf = min(0.15, max(0.001, float(width_frac)))
    b = max(2, int(wf * h))
    if frame == "double":
        return 2 * b + max(2, b // 2)   # viền ngoài + khoảng hở + viền trong
    if frame == "twocolor":
        return 2 * b                    # 2 viền kề nhau
    return b                            # solid / corner


def bottom_inset_px(frame: str, width_frac: float, w: int, h: int, job_dir) -> int:
    """Bề dày khung ở mép DƯỚI (px) — để S8 tự đẩy phụ đề lên khỏi khung."""
    if not frame or frame == "none":
        return 0
    if frame.startswith("png:"):
        name = build_sized_png(frame[4:], w, h, job_dir)
        if not name:
            return 0
        from PIL import Image
        return _insets_from_alpha(Image.open(Path(job_dir) / name))[1]
    if frame == "corner":
        return 0    # ngoặc chỉ ở góc, giữa đáy trống — phụ đề căn giữa không đụng
    return _proc_inset(frame, width_frac, h)


def pad_inset_px(frame: str, width_frac: float, w: int, h: int, job_dir) -> int:
    """Bề dày lề cho chế độ 'khung ngoài' (đều 4 cạnh, chẵn để scale yuv420 hợp lệ)."""
    if frame.startswith("png:"):
        name = build_sized_png(frame[4:], w, h, job_dir)
        if not name:
            return 0
        from PIL import Image
        ins = max(_insets_from_alpha(Image.open(Path(job_dir) / name)))
        ins = min(ins, int(0.20 * min(w, h)))
    else:
        ins = _proc_inset(frame, width_frac, h)
    return max(2, ins - ins % 2)


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
                 w: int, h: int, job_dir, pad: bool = False) -> str:
    """Chèn khung vào CUỐI chuỗi -vf. base = filter cover+sub (có thể là graph có ';').
    base luôn khác rỗng khi gọi từ s8 (ít nhất là subtitles).

    pad=True: thu video vào trong đúng bề dày khung rồi mới vẽ khung ra lề —
    không che pixel nội dung (khung PNG hoa văn thưa sẽ lộ lề đen phía sau)."""
    if not frame or frame == "none":
        return base
    base = base or "null"                         # đảm bảo có filter nguồn (s8 luôn truyền base thật)
    if pad:
        i = pad_inset_px(frame, width, w, h, job_dir)
        if i:
            base = (f"{base},scale={w - 2 * i}:{h - 2 * i}"
                    f",pad={w}:{h}:{i}:{i}:black")
    if frame.startswith("png:"):
        name = build_sized_png(frame[4:], w, h, job_dir)
        if not name:                              # file mất/không hợp lệ → bỏ khung
            return base
        return f"{base}[fb];movie=filename='{name}'[fr];[fb][fr]overlay=0:0"
    return f"{base},{_drawboxes(frame, color, color2, width, w, h)}"   # procedural
