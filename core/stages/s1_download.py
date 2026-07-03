"""S1: tải video nguồn bằng yt-dlp → source.<ext> trong thư mục job.

URL có thể là link (YouTube/Bilibili/Douyin/...) hoặc đường dẫn file local.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import yt_dlp

from core import sources
from core.job import Job


def run(job: Job) -> None:
    if job.find_source():
        return  # đã tải rồi (resume) — gồm cả job UPLOAD (source.<ext> lưu sẵn)

    # job upload/cắt nhưng mất file nguồn → báo rõ thay vì ném "[Upload]/[Cắt] ..." cho yt-dlp
    if job.url.startswith("[Upload] ") or job.url.startswith("[Cắt] "):
        raise RuntimeError("Job không thấy file nguồn (source.*) — file có thể đã bị "
                           "xoá/khoá hoặc cắt lỗi. Hãy upload/cắt lại.")

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
        **sources.cookie_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(job.url, download=True)

    if not job.find_source():
        raise RuntimeError("yt-dlp chạy xong nhưng không thấy file video")
