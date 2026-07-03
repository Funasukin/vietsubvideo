"""Tiến độ trong-stage (OCR/Whisper/dịch) → stage_progress.json trong thư mục job.

_job_summary đọc file này; dashboard hiện thanh % cho stage đang chạy. Ghi best-effort
(lỗi ghi không được làm hỏng pipeline). Mỗi stage ghi kèm tên stage để dashboard chỉ
hiện khi đúng stage hiện tại (tránh dữ liệu tiến độ cũ của stage trước).
"""
from __future__ import annotations

import json

_FILE = "stage_progress.json"


def write(job_dir, stage: str, done: int, total: int) -> None:
    try:
        (job_dir / _FILE).write_text(
            json.dumps({"stage": stage, "done": int(done), "total": int(total)}),
            encoding="utf-8")
    except OSError:
        pass


def read(job_dir) -> dict | None:
    p = job_dir / _FILE
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clear(job_dir) -> None:
    try:
        (job_dir / _FILE).unlink(missing_ok=True)
    except OSError:
        pass
