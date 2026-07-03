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
