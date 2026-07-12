"""SETTINGS SCHEMA — nguồn sự thật DUY NHẤT cho mọi cấu hình .env (G16, đợt G-A).

Trước đây một setting khai báo lặp ở 3 nơi (default trong config.py, whitelist
SAFE/SECRET trong server.py, control trong app-core.js) → lệch nhau âm thầm
(ELEVENLABS_MODEL có ở 2 nơi đầu nhưng không có UI). Từ giờ:
- server SINH whitelist + validate + factory-default + unset/reset + profile
  allowlist từ đây;
- client chỉ giữ nhãn/tooltip tiếng Việt + bố cục.

QUY TẮC BẢO TRÌ: default ở đây phải KHỚP default trong config.py — đổi một nơi
là đổi cả hai (schema là mặt hành chính, config.py là mặt runtime).

`profile=False` cho setting KHÔNG được đưa vào profile xuất/nhập (đặc thù máy,
tích hợp cá nhân, vận hành server) — theo phản biện Codex: dùng ALLOWLIST chứ
không lọc theo hậu tố tên.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Setting:
    default: str
    options: tuple | None = None   # None = chữ tự do (giới hạn max_len + cấm xuống dòng)
    secret: bool = False
    allow_empty: bool = False      # True = "" là giá trị hợp lệ (vd WHISPER_LANGUAGE rỗng
                                   # = auto). Mặc định False: rỗng bị BỎ QUA khi lưu — khóa
                                   # số/options mà ghi rỗng vào .env là job chết ngay lúc
                                   # import config (review đối kháng F1).
    profile: bool = True           # được xuất vào profile cấu hình
    max_len: int = 200


S = Setting

SETTINGS: dict[str, Setting] = {
    # ---- Dịch ----
    "TRANSLATE_PROVIDER": S("claude", ("claude", "gemini")),
    "CLAUDE_MODEL": S("claude-haiku-4-5-20251001",
                      ("claude-haiku-4-5-20251001", "claude-sonnet-4-6")),
    "GEMINI_MODEL": S("gemini-2.5-flash",
                      ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro",
                       "gemini-2.0-flash", "gemini-2.0-flash-lite")),
    "GEMINI_MIN_INTERVAL": S("0", ("0", "6", "7", "10")),
    "TRANSLATE_STYLE_EXTRA": S("", allow_empty=True, max_len=2000),
    "CONTENT_STYLE": S("donghua", ("donghua", "general")),
    "TARGET_LANG": S("vi", ("vi", "en", "zh", "ja", "ko", "es", "fr", "id", "th", "pt")),
    "REVIEW_TRANSLATION": S("1", ("1", "0")),
    "GLOSSARY_AUTO": S("1", ("1", "0")),
    # ---- Nhận dạng thoại ----
    "TRANSCRIPT_SOURCE": S("auto", ("auto", "ocr", "whisper")),
    "WHISPER_MODEL": S("small", ("tiny", "base", "small", "medium", "large-v3")),
    "WHISPER_LANGUAGE": S("", allow_empty=True),   # rỗng = tự nhận diện
    "WHISPER_DEVICE": S("cpu", ("cpu", "cuda"), profile=False),      # đặc thù máy
    "WHISPER_COMPUTE": S("int8", ("int8", "float16"), profile=False),
    "OCR_WORKERS": S("auto", ("auto", "2", "4", "6", "8"), profile=False),
    "OCR_FPS": S("2.0", ("1.0", "1.5", "2.0")),
    "OCR_CROP_TOP": S("auto", ("auto", "0.50", "0.60", "0.70", "0.80")),
    "OCR_MAX_MINUTES": S("20", ("10", "20", "30", "45", "60")),
    "DENOISE": S("0", ("0", "1")),
    "DIARIZE": S("0", ("0", "1")),
    "DIARIZE_MAX_SPK": S("0", ("0", "2", "3", "4", "5", "6", "8")),
    # ---- Lồng tiếng & âm thanh ----
    "TTS_ENGINE": S("edge", ("edge", "vixtts", "elevenlabs", "vbee", "fpt")),
    "TTS_SINGLE_VOICE": S("1", ("1", "0")),
    "TTS_VOICE": S("vi-VN-NamMinhNeural", ("vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural")),
    "TTS_VOICE_NU": S("vi-VN-HoaiMyNeural", ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural")),
    "VIXTTS_VOICE_NAM": S("", allow_empty=True),   # rỗng = giọng mặc định model
    "VIXTTS_VOICE_NU": S("", allow_empty=True),
    "ELEVENLABS_MODEL": S("eleven_multilingual_v2"),
    "ELEVENLABS_VOICE_NAM": S("pNInz6obpgDQGcFmaJgB"),
    "ELEVENLABS_VOICE_NU": S("21m00Tcm4TlvDq8ikWAM"),
    "VBEE_APP_ID": S("", allow_empty=True, profile=False),   # định danh tài khoản cá nhân
    "VBEE_VOICE_NAM": S("hn_male_manhdung_news_48k-fhg"),
    "VBEE_VOICE_NU": S("hn_female_ngochuyen_full_48k-fhg"),
    "FPT_VOICE_NAM": S("leminh"),
    "FPT_VOICE_NU": S("banmai"),
    "KEEP_BGM": S("0", ("0", "flat", "1")),
    "DUCK_GAIN_DB": S("-20", ("-14", "-17", "-20", "-23", "-26")),
    "PROSODY": S("0", ("1", "0")),
    "EMOTION": S("0", ("1", "0")),
    "PROSODY_TRANSFER": S("0", ("0", "1")),
    "MAX_SPEEDUP": S("1.4", ("1.0", "1.2", "1.4", "1.6", "1.8", "2.0")),
    # Đợt T (2026-07-12): nền tốc độ đọc "gu kênh" — áp MỌI câu TRƯỚC khi trọng
    # tài chống tràn làm việc; KHÔNG tính vào ngân sách MAX_SPEEDUP. Factory 1.0
    # (đổi default = voicesig lệch → re-TTS toàn bộ install cũ, bài học PROSODY).
    "TTS_BASE_SPEED": S("1.0", ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5")),
    # STRETCH_SHORT đã GỠ khỏi schema (đợt T): kéo giãn câu ngắn trái triết lý
    # "nhịp đồng đều, đọc xong sớm là mong muốn" — config.py còn đọc key 1 phiên
    # bản để cảnh báo .env cũ, nhưng luôn coi như tắt.
    "FFMPEG_SHARED_BIN": S(r"C:\ffmpeg-shared\ffmpeg-7.1-full_build-shared\bin",
                           allow_empty=True, profile=False, max_len=500),   # đường dẫn máy local
    # ---- Xuất bản / thương hiệu (render) ----
    "SUBTITLE_MODE": S("soft", ("soft", "cover_only", "burn", "none")),
    "SUB_SPLIT": S("1", ("1", "0")),
    "VOICE_FX": S("off", ("off", "canbang", "amday", "rosang", "dienanh", "toithieu")),
    "MUSIC": S("none", max_len=300),
    "MUSIC_VOL": S("0.15", ("0.08", "0.12", "0.15", "0.20", "0.30")),
    "LOGO": S("none", max_len=300),
    "LOGO_POS": S("br", ("tl", "tr", "bl", "br")),
    "LOGO_SCALE": S("0.12", ("0.08", "0.12", "0.16", "0.20")),
    "LOGO_OPACITY": S("0.85", ("0.5", "0.7", "0.85", "1.0")),
    "INTRO": S("none", max_len=300),
    "OUTRO": S("none", max_len=300),
    "MASTER": S("1", ("1", "0")),
    "SUBSCRIBE": S("off", ("off", "on")),
    "SUBSCRIBE_TEXT": S("Nhớ Like & Đăng ký kênh nhé!", max_len=200),
    # Khung viền MẶC ĐỊNH toàn kênh (G-B phương án A — trước đây s8 có fallback
    # nhưng không có UI; giá trị "png:<file>" cũng hợp lệ nên không dùng options)
    "FRAME": S("none", max_len=300),
    "FRAME_COLOR": S("#FFD700", max_len=9),
    "FRAME_COLOR2": S("#FFFFFF", max_len=9),
    "FRAME_WIDTH": S("0.02", ("0.005", "0.01", "0.02", "0.03", "0.04", "0.06")),
    "FRAME_PAD": S("0", ("0", "1")),
    "METADATA_MODEL": S("claude-sonnet-4-6",
                        ("claude-sonnet-4-6", "claude-haiku-4-5-20251001")),
    # ---- Shorts ----
    "SHORTS_COUNT": S("2", ("1", "2", "3", "4", "5")),
    "SHORTS_LEN": S("45", ("30", "45", "60")),
    "SHORTS_STYLE": S("vertical", ("vertical", "original")),
    # ---- Hệ thống / vận hành (không vào profile) ----
    "AUTO_RETRY": S("1", ("0", "1", "2", "3"), profile=False),
    "BATCH_LIMIT": S("50", ("20", "50", "100"), profile=False),
    "YTDLP_COOKIES_FILE": S("", allow_empty=True, profile=False, max_len=500),
    "YTDLP_COOKIES_BROWSER": S("", ("", "edge", "chrome", "firefox"),
                               allow_empty=True, profile=False),
    # ---- Tích hợp ----
    "YOUTUBE_CLIENT_SECRETS": S("", allow_empty=True, profile=False, max_len=500),
    "YOUTUBE_PRIVACY": S("private", ("private", "unlisted", "public")),
    "TELEGRAM_CHAT_ID": S("", allow_empty=True, profile=False),
    # ---- Secrets (không bao giờ trả giá trị / không vào profile) ----
    "ANTHROPIC_API_KEY": S("", secret=True, profile=False),
    "GEMINI_API_KEY": S("", secret=True, profile=False),
    "ELEVENLABS_API_KEY": S("", secret=True, profile=False),
    "VBEE_TOKEN": S("", secret=True, profile=False),
    "FPT_TTS_API_KEY": S("", secret=True, profile=False),
    "HF_TOKEN": S("", secret=True, profile=False),
    "TELEGRAM_BOT_TOKEN": S("", secret=True, profile=False),
    "YOUTUBE_API_KEY": S("", secret=True, profile=False),   # G-B: hết phải sửa .env tay
}

# ---- Danh sách dẫn xuất (server import các tên này thay literal cũ) ----
SAFE_ENV_KEYS = [k for k, s in SETTINGS.items() if not s.secret]
SECRET_ENV_KEYS = {k for k, s in SETTINGS.items() if s.secret}
FACTORY_DEFAULTS = {k: s.default for k, s in SETTINGS.items() if not s.secret}
PROFILE_KEYS = [k for k, s in SETTINGS.items() if s.profile and not s.secret]
# khóa mà chuỗi RỖNG là giá trị hợp lệ khi LƯU (xoá nội dung) — mọi non-secret
# allow_empty; secret rỗng luôn nghĩa là "giữ nguyên khóa cũ"
EMPTY_OK = {k for k, s in SETTINGS.items() if s.allow_empty and not s.secret}


def validate(key: str, value: str) -> str:
    """Chuẩn hoá + kiểm tra 1 giá trị theo schema. Raise ValueError nếu không hợp lệ.
    KHÔNG đổi kiểu — .env là chữ; parse kiểu là việc của config.py."""
    s = SETTINGS.get(key)
    if s is None:
        raise ValueError(f"khóa lạ: {key}")
    v = str(value).strip()
    if "\n" in v or "\r" in v:
        raise ValueError(f"{key}: không được xuống dòng")
    if len(v) > s.max_len:
        raise ValueError(f"{key}: quá dài (>{s.max_len})")
    if v == "":
        if s.secret or not s.allow_empty:
            raise ValueError(f"{key}: không nhận giá trị rỗng")
        return v
    # options đóng: giá trị phải nằm trong danh sách — TRỪ các khóa file-asset
    # (MUSIC/LOGO/FRAME... options=None sẵn) nên chỉ áp cho tuple
    if s.options is not None and v not in s.options:
        raise ValueError(f"{key}: giá trị '{v[:40]}' không nằm trong lựa chọn cho phép")
    return v
