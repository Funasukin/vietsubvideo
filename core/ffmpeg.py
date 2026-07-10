"""Helper gọi ffmpeg qua subprocess, báo lỗi kèm stderr."""
from __future__ import annotations

import subprocess


def run(*args: str, cwd=None) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=cwd)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-800:]
        raise RuntimeError(f"ffmpeg lỗi (code {proc.returncode}): {tail}")


# ---- Chọn encoder H.264 tốt nhất CÓ THẬT trên máy (audit #1) ----
# Trước đây code cứng thử h264_qsv (Intel) rồi fallback libx264 (CPU) — máy NVIDIA
# (RTX 3070) không có QSV nên MỌI video đều fail 1 lần rồi encode bằng CPU, bỏ phí
# NVENC nhanh gấp nhiều lần. Giờ dò 1 lần mỗi tiến trình bằng encode thử 0.1s.
_h264_cache: tuple[str, ...] | None = None

# (tên encoder, args chất lượng tương đương CRF~20-23)
_H264_CANDIDATES = [
    ("h264_nvenc", ("-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23")),
    ("h264_qsv", ("-c:v", "h264_qsv", "-global_quality", "23")),
    ("libx264", ("-c:v", "libx264", "-preset", "fast", "-crf", "20")),
]


def h264_args() -> tuple[str, ...]:
    """Args encoder H.264 nhanh nhất máy này hỗ trợ THẬT (đã encode thử, không chỉ
    liệt kê -encoders — driver thiếu vẫn liệt kê được nhưng encode fail).
    Cache theo tiến trình: job = subprocess riêng nên tốn ~0.3s/job, đổi lại mọi
    lần encode sau đều đúng encoder ngay, không còn thử-fail cả video."""
    global _h264_cache
    if _h264_cache is not None:
        return _h264_cache
    for name, args in _H264_CANDIDATES[:-1]:
        probe = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "nullsrc=s=256x144:d=0.1", *args, "-f", "null", "-"],
            capture_output=True, text=True)
        if probe.returncode == 0:
            print(f"  encoder H.264: {name}")
            _h264_cache = args
            return args
    name, args = _H264_CANDIDATES[-1]
    print(f"  encoder H.264: {name} (CPU — không thấy GPU encoder)")
    _h264_cache = args
    return args


def probe_dims(path) -> tuple[int, int]:
    """(width, height) HIỂN THỊ của stream video đầu tiên.

    Phải tính cả side data rotation: ffmpeg tự xoay frame trước mọi filter,
    nên video điện thoại lưu 1920x1080 + rotate 90 thực chất là 1080x1920
    khi vào filter — dùng kích thước lưu trữ sẽ đặt delogo vượt khung hình.
    """
    import json as _json
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:stream_side_data=rotation",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        raise RuntimeError(f"ffprobe lỗi: {(proc.stderr or '')[-300:]}")
    try:
        st = _json.loads(proc.stdout)["streams"][0]
        w, h = int(st["width"]), int(st["height"])
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"ffprobe không đọc được kích thước: {e}")
    rot = next((int(sd["rotation"]) for sd in st.get("side_data_list", [])
                if "rotation" in sd), 0)
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h
