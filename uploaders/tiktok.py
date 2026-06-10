"""Đẩy final.mp4 vào TikTok dạng nháp qua Content Posting API.

App chưa qua audit chỉ đẩy được draft — user tự bấm đăng trong app TikTok.

TODO Phase 3.
"""
from core.job import Job


def upload(job: Job) -> str:
    """Trả về thông báo trạng thái draft."""
    raise NotImplementedError("TikTok upload — Phase 3")
