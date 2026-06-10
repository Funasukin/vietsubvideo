"""S1: tải video nguồn bằng yt-dlp → source.<ext> trong thư mục job.

URL có thể là link (YouTube/Bilibili/Douyin/...) hoặc đường dẫn file local.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import yt_dlp

from core.job import Job


def run(job: Job) -> None:
    if job.find_source():
        return  # đã tải rồi (resume)

    local = Path(job.url)
    if local.is_file():
        shutil.copy2(local, job.dir / f"source{local.suffix.lower()}")
        return

    opts = {
        "outtmpl": str(job.dir / "source.%(ext)s"),
        # ưu tiên mp4 ≤1080p để FFmpeg/render nhẹ nhàng, fallback best
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(job.url, download=True)

    if not job.find_source():
        raise RuntimeError("yt-dlp chạy xong nhưng không thấy file video")
