"""Thông báo job xong/lỗi qua Telegram (#11).

Best-effort tuyệt đối: thiếu cấu hình / lỗi mạng thì IM LẶNG bỏ qua, không bao giờ
làm hỏng worker. Đọc token + chat id TƯƠI từ .env mỗi lần (sửa từ UI có hiệu lực ngay,
khỏi restart) — giống cách AUTO_RETRY đọc lại .env.
"""
from __future__ import annotations

import urllib.parse
import urllib.request

import config


def _cfg() -> tuple[str, str]:
    tok, chat = config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
    try:
        env = config.BASE_DIR / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    chat = line.split("=", 1)[1].strip()
    except OSError:
        pass
    return tok, chat


def enabled() -> bool:
    tok, chat = _cfg()
    return bool(tok and chat)


def send(text: str) -> bool:
    """Gửi 1 tin nhắn Telegram. Trả True nếu gửi được (best-effort)."""
    tok, chat = _cfg()
    if not (tok and chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{tok}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat,
            "text": text[:3900],
            "disable_web_page_preview": "true",
        }).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def job_done(job_id: str, url: str, ok: bool, error: str = "") -> None:
    if ok:
        send(f"✅ FlowApp: job hoàn thành\n{url}\n(id {job_id})")
    else:
        send(f"⚠️ FlowApp: job LỖI\n{url}\n{(error or '')[:500]}\n(id {job_id})")
