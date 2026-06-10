"""Cấu hình tập trung: đọc .env + hằng số pipeline."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"

load_dotenv(BASE_DIR / ".env")

# API keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Dịch (S4)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
TRANSLATE_BATCH_SIZE = 25   # số segment mỗi lần gọi API
TRANSLATE_BATCH_OVERLAP = 3  # segment cuối batch trước gửi kèm làm context

# Transcript (S3)
TRANSCRIPT_SOURCE = os.getenv("TRANSCRIPT_SOURCE", "auto")  # auto | ocr | whisper
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")     # tiny/base/small/medium/large-v3
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "")    # rỗng = tự nhận diện

# OCR phụ đề hardsub (S3)
OCR_FPS = 2.0          # số frame lấy mẫu mỗi giây
OCR_CROP_TOP = 0.70    # vùng quét: từ 70% chiều cao xuống đáy
OCR_MIN_CONF = 0.55    # bỏ kết quả OCR dưới ngưỡng tin cậy này

# TTS (S5)
TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-NamMinhNeural")
TTS_CONCURRENCY = 2   # 4 luồng dễ bị Microsoft throttle trên video dài
TTS_TIMEOUT_S = 90    # mỗi lần gọi edge-tts; tránh treo vô hạn khi đứt kết nối

# BGM duck (S6)
DUCK_GAIN_DB = -14.0

# Mix (S7): tăng tốc tối đa khi audio dịch dài hơn slot gốc
MAX_SPEEDUP = 1.4

# Phụ đề tiếng Việt (S8): soft = track bật/tắt được (nhanh) | burn = vẽ cứng
# vào hình (re-encode, chậm) | none = không phụ đề. File sub_vi.srt luôn được tạo.
SUBTITLE_MODE = os.getenv("SUBTITLE_MODE", "soft")
# kiểu chữ phụ đề vẽ cứng: mặc định + override theo job ở core/stages/s8_render.py

# Che phụ đề gốc cháy sẵn trong hình: none | blur (làm mờ) | black (dải đen).
# Khác none sẽ tự ép SUBTITLE_MODE=burn vì phải re-encode mới sửa được pixel.
COVER_SOURCE_SUBS = os.getenv("COVER_SOURCE_SUBS", "none")
COVER_TOP = float(os.getenv("COVER_TOP", "0.78"))  # che từ tỉ lệ chiều cao này xuống đáy

# Upload (Phase 3)
YT_CLIENT_SECRET_FILE = os.getenv("YT_CLIENT_SECRET_FILE", "secrets/yt_client_secret.json")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
