"""S9: sinh metadata đăng bài bằng Claude API → metadata.json.

Chỉ cần khi job có chọn nền tảng upload; job chạy CLI không upload thì bỏ qua
để pipeline hoàn thành. Phần sinh metadata thật làm ở Phase 3.
"""
import json

from core.job import Job


def run(job: Job) -> None:
    out_path = job.dir / "metadata.json"
    if out_path.exists():
        return

    if not job.platforms:
        out_path.write_text(
            json.dumps({"skipped": "không có nền tảng upload"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return

    raise NotImplementedError("S9 metadata cho upload — Phase 3")
