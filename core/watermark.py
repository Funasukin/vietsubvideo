"""Xóa/che WATERMARK kênh gốc (S8) — 3 nhóm cách, chọn theo job qua render:

  render["wm_method"] + render["wm_box"] = [x0, y0, x1, y1] (chuẩn hóa 0..1):
    delogo — FFmpeg nội suy từ pixel quanh vùng: watermark TĨNH thành vệt mờ nhẹ,
             thường khó thấy trên nền chuyển động. Watermark động/giữa hình → xấu.
    blur   — làm mờ vùng (gblur), giống che sub gốc.
    black  — dải đen đè vùng.
    logo   — đè logo KÊNH MÌNH (thư mục logo/) vừa bề ngang vùng, căn giữa dọc —
             không vệt, nhìn "chính chủ".

  render["crop"] = [trái, trên, phải, dưới] (tỉ lệ 0..0.2): CẮT dải sát rìa chứa
  watermark rồi phóng lại đúng kích thước gốc — sạch tuyệt đối, đổi lại mất một
  dải hình. Dùng khi watermark là chữ chạy dọc mép.

Crop đứng ĐẦU chuỗi -vf nên mọi tọa độ vẽ sau nó (vùng wm, băng che sub, box sub
tự động) phải quy đổi bằng map_box()/map_y() — S8 và preview cùng gọi.
"""
from __future__ import annotations

import config
from core import brand

CROP_MAX = 0.2      # không cho cắt quá 20% mỗi cạnh (nhập nhầm → nát hình)
_MIN_PX = 8         # vùng wm nhỏ hơn cỡ này coi như không có

METHODS = ("none", "delogo", "blur", "black", "logo")


def _crop4(crop) -> tuple[float, float, float, float]:
    """[l,t,r,b] → tuple đã clamp 0..CROP_MAX; thiếu/hỏng = 0."""
    out = []
    for i in range(4):
        try:
            v = float(crop[i])
        except (TypeError, ValueError, IndexError):
            v = 0.0
        out.append(min(CROP_MAX, max(0.0, v)))
    return tuple(out)


def crop_active(crop) -> bool:
    return any(v > 0.001 for v in _crop4(crop))


def crop_filter(crop, w: int, h: int) -> str:
    """Chuỗi crop + scale về đúng (w,h) gốc — mọi filter sau khỏi quan tâm crop."""
    l, t, r, b = _crop4(crop)
    if not crop_active(crop):
        return ""
    cw = max(16, int(w * (1 - l - r)))
    ch = max(16, int(h * (1 - t - b)))
    return (f"crop={cw}:{ch}:{int(w * l)}:{int(h * t)},"
            f"scale={w}:{h}")


def map_y(y: float, crop) -> float:
    """Tọa độ dọc chuẩn hóa TRƯỚC crop → SAU crop (crop tắt = giữ nguyên)."""
    l, t, r, b = _crop4(crop)
    return min(1.0, max(0.0, (y - t) / max(0.001, 1 - t - b)))


def map_box(box, crop) -> list[float] | None:
    """Box [x0,y0,x1,y1] chuẩn hóa → tọa độ sau crop; None nếu hỏng/teo mất."""
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    l, t, r, b = _crop4(crop)
    kw, kh = max(0.001, 1 - l - r), max(0.001, 1 - t - b)
    x0, x1 = (x0 - l) / kw, (x1 - l) / kw
    y0, y1 = (y0 - t) / kh, (y1 - t) / kh
    x0, y0 = max(0.0, x0), max(0.0, y0)
    x1, y1 = min(1.0, x1), min(1.0, y1)
    if x1 - x0 < 0.005 or y1 - y0 < 0.005:
        return None
    return [x0, y0, x1, y1]


def _box_px(box, w: int, h: int) -> tuple[int, int, int, int] | None:
    """Box chuẩn hóa → (x, y, bw, bh) px, né mép 2px (delogo cần pixel xung quanh)."""
    if not box:
        return None
    x0 = max(2, int(box[0] * w))
    y0 = max(2, int(box[1] * h))
    x1 = min(w - 2, int(box[2] * w))
    y1 = min(h - 2, int(box[3] * h))
    if x1 - x0 < _MIN_PX or y1 - y0 < _MIN_PX:
        return None
    return x0, y0, x1 - x0, y1 - y0


def region_filter(method: str, box, w: int, h: int) -> str:
    """Đoạn -vf xử lý vùng wm bằng delogo/blur/black ('' nếu không áp dụng)."""
    px = _box_px(box, w, h)
    if not px or method not in ("delogo", "blur", "black"):
        return ""
    x, y, bw, bh = px
    if method == "delogo":
        return f"delogo=x={x}:y={y}:w={bw}:h={bh}"
    if method == "black":
        return f"drawbox=x={x}:y={y}:w={bw}:h={bh}:color=black:t=fill"
    return (f"split[wa][wb];[wb]crop={bw}:{bh}:{x}:{y},gblur=sigma=12[wf];"
            f"[wa][wf]overlay={x}:{y}")


def logo_overlay(vf: str, box, w: int, h: int, job_dir, logo_name: str) -> str:
    """Đè logo kênh mình vừa bề ngang vùng wm, căn giữa dọc. Không có logo → giữ
    nguyên vf (đã báo). Logo vẽ TRƯỚC che/sub/khung nên không đè lên phụ đề."""
    px = _box_px(box, w, h)
    if not px:
        return vf
    lp = brand._pick(logo_name, brand.LOGO_DIR, brand._LOGO_EXTS)
    if not lp:
        print("  Watermark: chưa có file logo trong logo/ — bỏ qua cách đè logo")
        return vf
    x, y, bw, bh = px
    rel = brand._rel(lp, job_dir)
    base = vf or "null"
    return (f"{base}[wl];movie=filename='{rel}',scale={bw}:-1,format=rgba[wlg];"
            f"[wl][wlg]overlay={x}:{y}+({bh}-h)/2")


def pre_chain(r: dict, w: int, h: int, job_dir) -> str:
    """Chuỗi -vf ĐẦU TIÊN của S8/preview: crop mép + xử lý vùng watermark.
    '' nếu job không dùng gì. Tọa độ wm_box tự quy đổi theo crop."""
    method = (r.get("wm_method") or "none").strip().lower()
    crop = r.get("crop") or []
    parts = []
    cf = crop_filter(crop, w, h)
    if cf:
        parts.append(cf)
    box = map_box(r.get("wm_box"), crop)
    if method in ("delogo", "blur", "black"):
        rf = region_filter(method, box, w, h)
        if rf:
            parts.append(rf)
    vf = ",".join(parts)
    if method == "logo" and box:
        logo_name = r.get("wm_logo") or r.get("logo") or config.LOGO
        vf = logo_overlay(vf, box, w, h, job_dir, logo_name)
    return vf


def active(r: dict) -> bool:
    """Job có dùng xử lý watermark không (để S8 ép mode burn)."""
    method = (r.get("wm_method") or "none").strip().lower()
    return ((method in ("delogo", "blur", "black", "logo") and bool(r.get("wm_box")))
            or crop_active(r.get("crop") or []))
