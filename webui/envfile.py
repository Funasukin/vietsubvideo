"""Đọc/GHI .env chuẩn hoá — dùng chung cho server (hiển thị + lưu cấu hình),
worker (AUTO_RETRY đọc tươi) và schema (G16). Tách riêng để webui/worker.py
không import ngược webui/server.py (#16 giai đoạn 1).

Đợt G-A: thêm serializer có quote/escape (bug Codex: set_config cũ ghi
`KEY={value}` thô — giá trị chứa `#`/quote sẽ parse khác ở lần đọc sau) và
semantics UNSET (xoá key khỏi .env để quay về factory default — reset kiểu này
thì default app đổi ở phiên bản sau vẫn ăn theo, không bị ghim số cũ).
"""
from __future__ import annotations

import os
import re
import uuid

import config

ENV_PATH = config.BASE_DIR / ".env"

_LINE_RE = re.compile(r"^([A-Z_][A-Z_0-9]*)=(.*)$")


def _unquote(v: str) -> str:
    """Giá trị có thể được quote kiểu dotenv: "..." (có escape) hoặc '...' (thô)."""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1]
    return v


def _quote(v: str) -> str:
    """Quote khi giá trị chứa ký tự dotenv có thể hiểu sai (# comment, quote,
    khoảng trắng đầu/cuối). Giá trị thường giữ nguyên cho .env dễ đọc bằng mắt."""
    if v == "" or re.search(r"""[#'"]""", v) or v != v.strip():
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return v


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            m = _LINE_RE.match(line.strip())
            if m:
                values[m.group(1)] = _unquote(m.group(2))
    return values


def write_env(updates: dict[str, str], unset: set[str] | None = None) -> None:
    """Ghi .env: thay giá trị key có sẵn, thêm key mới, XOÁ key trong `unset`.
    Giữ nguyên comment/dòng lạ. Ghi nguyên tử (tmp + os.replace) — .env là single
    source, ghi dở giữa lúc worker con load_dotenv sẽ mất key."""
    unset = unset or set()
    lines: list[str] = []
    seen: set[str] = set()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            m = _LINE_RE.match(line.strip())
            key = m.group(1) if m else None
            if key in unset:
                seen.add(key)
                continue          # xoá key → về factory default của phiên bản app
            if key in updates:
                lines.append(f"{key}={_quote(updates[key])}")
                seen.add(key)
            else:
                lines.append(line)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={_quote(v)}")
    tmp = ENV_PATH.with_name(f".env.{uuid.uuid4().hex}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, ENV_PATH)
