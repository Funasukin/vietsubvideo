"""Upload final.mp4 lên YouTube qua Data API v3 (OAuth).

Lưu ý: upload = 1600 units / quota 10000 units/ngày (~6 video/ngày);
app OAuth chưa verify thì video bị khóa private.

TODO Phase 3.
"""
from core.job import Job


def upload(job: Job) -> str:
    """Trả về URL video đã đăng."""
    raise NotImplementedError("YouTube upload — Phase 3")
