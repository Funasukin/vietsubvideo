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
