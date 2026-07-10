"""Đọc .env thô (không qua dotenv/config module) — dùng chung cho server (hiển thị
cấu hình tươi) và worker (AUTO_RETRY đọc mỗi lượt). Tách riêng để webui/worker.py
không phải import ngược webui/server.py (#16 tách monolith, giai đoạn 1)."""
from __future__ import annotations

import re

import config

ENV_PATH = config.BASE_DIR / ".env"


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2)
    return values
