"""#16 Ngôn ngữ ĐÍCH của lồng tiếng (TARGET_LANG) — không chỉ tiếng Việt.

Mỗi ngôn ngữ có cặp giọng edge-tts nam/nữ (tên đã verify bằng `edge-tts --list-voices`).
Ghi chú giới hạn: viXTTS là bản finetune TIẾNG VIỆT nên khi TARGET_LANG != vi, mọi câu
(kể cả casting voice_ref) đọc bằng edge-tts; tên file nội bộ (text_vi, sub_vi.srt,
transcript_vi.json) GIỮ NGUYÊN dù nội dung là ngôn ngữ khác — đổi tên sẽ vỡ resume/editor.
"""
from __future__ import annotations

import config

# code → (tên hiển thị, giọng nam edge, giọng nữ edge)
LANGS: dict[str, tuple[str, str, str]] = {
    "vi": ("Tiếng Việt", "vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"),
    "en": ("English", "en-US-GuyNeural", "en-US-JennyNeural"),
    "zh": ("中文 (Tiếng Trung)", "zh-CN-YunxiNeural", "zh-CN-XiaoxiaoNeural"),
    "ja": ("日本語 (Tiếng Nhật)", "ja-JP-KeitaNeural", "ja-JP-NanamiNeural"),
    "ko": ("한국어 (Tiếng Hàn)", "ko-KR-InJoonNeural", "ko-KR-SunHiNeural"),
    "es": ("Español (Tây Ban Nha)", "es-ES-AlvaroNeural", "es-ES-ElviraNeural"),
    "fr": ("Français (Pháp)", "fr-FR-HenriNeural", "fr-FR-DeniseNeural"),
    "id": ("Bahasa Indonesia", "id-ID-ArdiNeural", "id-ID-GadisNeural"),
    "th": ("ไทย (Tiếng Thái)", "th-TH-NiwatNeural", "th-TH-PremwadeeNeural"),
    "pt": ("Português (Brazil)", "pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"),
}


def code() -> str:
    """Mã ngôn ngữ đích hiện tại (rơi về 'vi' nếu cấu hình lạ)."""
    c = (config.TARGET_LANG or "vi").strip().lower()
    return c if c in LANGS else "vi"


def is_vi() -> bool:
    return code() == "vi"


def name(c: str | None = None) -> str:
    return LANGS[c or code()][0]


def edge_voices(c: str | None = None) -> tuple[str, str]:
    """(giọng nam, giọng nữ) edge-tts của ngôn ngữ đích. Với 'vi' vẫn ưu tiên
    TTS_VOICE/TTS_VOICE_NU trong Cấu hình (giữ hành vi cũ, người dùng đã chỉnh)."""
    c = c or code()
    if c == "vi":
        return config.TTS_VOICE, config.TTS_VOICE_NU
    _, nam, nu = LANGS[c]
    return nam, nu


def cjk_target(c: str | None = None) -> bool:
    """Ngôn ngữ đích viết bằng chữ Hán/kanji → KHÔNG được coi ký tự CJK là 'sót dịch'."""
    return (c or code()) in ("zh", "ja")
