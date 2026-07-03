"""Cấu hình tập trung: đọc .env + hằng số pipeline."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Tin kho chứng chỉ của hệ điều hành thay vì bộ certifi tĩnh. Bắt buộc khi máy
# có phần mềm chặn/giải mã HTTPS (vd Norton, ESET, proxy công ty) cài root CA
# riêng vào Windows — certifi không có root đó nên yt-dlp/anthropic/edge-tts đều
# lỗi CERTIFICATE_VERIFY_FAILED. inject_into_ssl() vá ssl toàn cục → mọi thư
# viện in-process (yt-dlp, httpx, aiohttp) dùng cách verify của OS. Phải chạy
# TRƯỚC khi bất kỳ kết nối mạng nào được tạo, nên đặt ngay đầu config.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:  # thiếu truststore → quay về certifi mặc định
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JOBS_DIR = DATA_DIR / "jobs"
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR = BASE_DIR / "fonts"   # font tùy biến: thả .ttf/.otf vào đây để dùng

load_dotenv(BASE_DIR / ".env")

# API keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Dịch (S4)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
TRANSLATE_BATCH_SIZE = 25   # số segment mỗi lần gọi API
TRANSLATE_BATCH_OVERLAP = 3  # segment cuối batch trước gửi kèm làm context
# Kiểu nội dung → chọn văn phong dịch: donghua (Trung cổ trang: Hán-Việt, xưng hô cổ)
# hay general (mọi thể loại/ngôn ngữ: dịch tự nhiên hiện đại, giữ tên gốc). Xem s4_translate.
CONTENT_STYLE = os.getenv("CONTENT_STYLE", "donghua").strip().lower()
# #16 Ngôn ngữ ĐÍCH lồng tiếng+phụ đề (vi|en|zh|ja|ko|es|fr|id|th|pt — core/langs.py).
# Khác "vi": dịch + đọc bằng giọng edge của ngôn ngữ đó; viXTTS/casting tạm không áp dụng.
TARGET_LANG = os.getenv("TARGET_LANG", "vi").strip().lower()
# Vòng review sau dịch: đọc lại toàn bộ, sửa tên riêng/xưng hô lệch giữa các batch
REVIEW_TRANSLATION = os.getenv("REVIEW_TRANSLATION", "1").lower() not in ("0", "false")
# Tự trích bảng tên riêng từ transcript (1 call Claude/job) để dịch tên nhất quán
GLOSSARY_AUTO = os.getenv("GLOSSARY_AUTO", "1").lower() not in ("0", "false")

# Metadata/thumbnail (S9): title là mặt tiền kênh, chỉ 1 call/job (~$0.02)
# nên mặc định dùng model tốt hơn model dịch
METADATA_MODEL = os.getenv("METADATA_MODEL", "claude-sonnet-4-6")

# Transcript (S3)
TRANSCRIPT_SOURCE = os.getenv("TRANSCRIPT_SOURCE", "auto")  # auto | ocr | whisper
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")     # tiny/base/small/medium/large-v3
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "")    # rỗng = tự nhận diện
# cpu luôn chạy được; cuda nhanh hơn nhiều nhưng cần cài CUDA 12 + cuDNN (thiếu
# cublas64_12.dll sẽ crash). device="auto" tự dò GPU nên dễ lỗi → mặc định cpu.
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")     # cpu | cuda
WHISPER_COMPUTE = os.getenv("WHISPER_COMPUTE", "int8")  # int8 (cpu) | float16 (cuda)

# OCR phụ đề hardsub (S3)
OCR_FPS = float(os.getenv("OCR_FPS", "2.0"))   # frame lấy mẫu/giây (giảm = nhanh hơn)
OCR_CROP_TOP = 0.70    # vùng quét: từ 70% chiều cao xuống đáy
OCR_MIN_CONF = 0.55    # bỏ kết quả OCR dưới ngưỡng tin cậy này
OCR_WORKERS = int(os.getenv("OCR_WORKERS", "6"))  # số tiến trình OCR song song (mỗi cái 2 luồng)
# auto mode: video DÀI hơn ngưỡng này (phút) thì bỏ OCR, dùng thẳng Whisper —
# OCR 2fps quá chậm với phim dài (1 giờ ≈ 7200 frame → hàng giờ trên CPU).
# Video ngắn hơn vẫn OCR để giữ độ chính xác hardsub. "ocr" thuần thì luôn OCR.
OCR_MAX_MINUTES = int(os.getenv("OCR_MAX_MINUTES", "20"))

# Số lần tự chạy lại một job bị LỖI trước khi bỏ cuộc (0 = tắt). Chỉ hợp lý với
# lỗi tạm thời (mạng chập chờn, API quá tải); lỗi cố định sẽ lại lỗi rồi dừng.
AUTO_RETRY = int(os.getenv("AUTO_RETRY", "1"))

# Nhận diện giới tính người nói theo cao độ giọng (F0) ở S4 → gán nam/nu chính xác
# hơn Claude đoán từ chữ. Chắc thì đè nhãn Claude; mơ hồ thì giữ nhãn Claude.
GENDER_DETECT = os.getenv("GENDER_DETECT", "1").lower() not in ("0", "false", "")

# #8 Nhận diện NGƯỜI NÓI từ audio thật (diarization, pyannote) — xem core/speakers.py.
# Cần: pip install pyannote.audio (khuyến nghị desktop GPU) + HF_TOKEN huggingface.co
# (chấp nhận điều khoản model pyannote/segmentation-3.0 và speaker-diarization-3.1).
DIARIZE = os.getenv("DIARIZE", "0")               # 1 = bật; thiếu điều kiện thì tự bỏ qua
HF_TOKEN = os.getenv("HF_TOKEN", "")              # token HuggingFace (bí mật — UI không đọc ra)
DIARIZE_MAX_SPK = int(os.getenv("DIARIZE_MAX_SPK", "0") or "0")  # 0 = tự đoán số người nói

# TTS (S5) — giọng theo nhãn voice (nam/nu): ưu tiên dò theo audio, fallback Claude
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge").strip().lower()  # edge | vixtts (nhân bản, GPU)
TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-NamMinhNeural")      # nam + mặc định
TTS_VOICE_NU = os.getenv("TTS_VOICE_NU", "vi-VN-HoaiMyNeural")  # nữ
# Hậu kỳ giọng khi render (S8): off | canbang | amday | rosang | dienanh | toithieu — xem core/voice_fx.py
VOICE_FX = os.getenv("VOICE_FX", "off").strip().lower()
# Tông giọng theo audio gốc (PLAN mục 11, mức 1 — core/prosody.py): đo cao độ/tốc độ/
# năng lượng từng câu → chỉnh rate/pitch/volume edge-tts. Bảo thủ: mơ hồ = không chỉnh.
# Giữ dạng chuỗi "1"/"0" cho khớp dropdown tab Cấu hình (parse ở prosody.enabled()).
PROSODY = os.getenv("PROSODY", "1").strip()
# Nhãn cảm xúc từng câu (PLAN 11 mức 2 — core/emotion.py): Claude gắn khi dịch →
# edge chỉnh rate/pitch/volume thêm, viXTTS chọn clip mẫu hợp cảm xúc. "0" = tắt.
EMOTION = os.getenv("EMOTION", "1").strip()

# Khung viền quanh video (S8) — xem core/frames.py. frame: none|solid|double|png:<file>
FRAMES_DIR = BASE_DIR / "frames"   # thả file .png khung (nền giữa trong suốt) vào đây
FRAME = os.getenv("FRAME", "none").strip()
FRAME_COLOR = os.getenv("FRAME_COLOR", "#FFD700")        # màu viền procedural (vàng gold)
FRAME_COLOR2 = os.getenv("FRAME_COLOR2", "#FFFFFF")      # màu 2 (cho kiểu "viền 2 màu")
FRAME_WIDTH = float(os.getenv("FRAME_WIDTH", "0.02"))    # độ dày viền = tỉ lệ chiều cao (2%)
FRAME_PAD = os.getenv("FRAME_PAD", "0")   # 1 = "khung ngoài": thu video vào trong, khung không che hình

# Brand/xuất bản (S8) — asset dùng chung cả kênh: đặt file vào music/ logo/ clips/. Xem core/brand.py
MUSIC = os.getenv("MUSIC", "none")            # tên file nhạc nền trong music/ (none = tắt)
MUSIC_VOL = os.getenv("MUSIC_VOL", "0.15")    # âm lượng nhạc nền (0..1), tự duck khi có thoại
LOGO = os.getenv("LOGO", "none")              # tên file logo .png trong logo/ (none = tắt)
LOGO_POS = os.getenv("LOGO_POS", "br")        # góc: tl|tr|bl|br
LOGO_SCALE = os.getenv("LOGO_SCALE", "0.12")  # bề rộng logo = tỉ lệ bề rộng video
LOGO_OPACITY = os.getenv("LOGO_OPACITY", "0.85")
INTRO = os.getenv("INTRO", "none")            # clip intro trong clips/ (ghép đầu video)
OUTRO = os.getenv("OUTRO", "none")            # clip outro trong clips/ (ghép cuối video)
MASTER = os.getenv("MASTER", "0")             # 1 = master chuẩn độ to toàn video (-14 LUFS YouTube)

# #14 Khử ồn audio TRƯỚC Whisper (afftdn) — chỉ lọc bản 16k cho ASR nghe rõ hơn,
# KHÔNG đụng audio nền dùng để mix. Bật khi nguồn nhiều tiếng ồn/nhạc to.
DENOISE = os.getenv("DENOISE", "0").lower() not in ("0", "false", "")

# #18 Nhắc Like/Đăng ký: overlay chữ vài giây đầu video (buộc render burn). off = tắt.
SUBSCRIBE = os.getenv("SUBSCRIBE", "off").strip().lower()   # off | on
SUBSCRIBE_TEXT = os.getenv("SUBSCRIBE_TEXT", "Nhớ Like & Đăng ký kênh nhé!")

# #11 Telegram: báo job xong/lỗi (TELEGRAM_BOT_TOKEN ở trên). Điền cả token + chat id để bật.
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# #1 Upload YouTube (tùy chọn): file client_secrets OAuth do BẠN tạo ở Google Cloud
# (bật YouTube Data API v3). Token lưu ở data/youtube_token.json sau lần đăng nhập đầu.
YOUTUBE_CLIENT_SECRETS = os.getenv("YOUTUBE_CLIENT_SECRETS", "").strip()
YOUTUBE_PRIVACY = os.getenv("YOUTUBE_PRIVACY", "private").strip().lower()  # private|unlisted|public

# Bảng xếp hạng phim AI hot (core/trending.py) — Phase 1: Bilibili + (tuỳ chọn) YouTube check
TRENDING_KEYWORDS = [k.strip() for k in os.getenv(
    "TRENDING_KEYWORDS",
    "AI动画,AIGC,AI短片,AI电影,AI科幻,AI绘画,AI生成,AI视频,文生视频,AI微电影,可灵AI,即梦AI"
).split(",") if k.strip()]
TRENDING_PER_KW = int(os.getenv("TRENDING_PER_KW", "20"))      # số video lấy mỗi từ khoá
TRENDING_YT_LIMIT = int(os.getenv("TRENDING_YT_LIMIT", "40"))  # số dòng top check YouTube/ngày (giới hạn quota)
TRENDING_HOUR = int(os.getenv("TRENDING_HOUR", "8"))           # giờ quét tự động hằng ngày (0-23)
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()     # bật cột "đã có trên YouTube" khi có key

# viXTTS (lồng tiếng nhân bản giọng, chạy GPU) — xem core/vixtts.py
VIXTTS_DIR = BASE_DIR / "models" / "viXTTS"   # model tải từ capleaf/viXTTS
VOICES_DIR = BASE_DIR / "voices"              # thư viện clip giọng mẫu (.wav)
VIXTTS_DEVICE = os.getenv("VIXTTS_DEVICE", "cuda")  # cuda | cpu
# clip mẫu trong voices/ gán cho nhãn nam/nu (rỗng = dùng mẫu mặc định của model)
VIXTTS_VOICE_NAM = os.getenv("VIXTTS_VOICE_NAM", "")
VIXTTS_VOICE_NU = os.getenv("VIXTTS_VOICE_NU", "")
# FFmpeg SHARED (major 4-7) cho torchcodec đọc audio — KHÁC bản static dùng render
FFMPEG_SHARED_BIN = os.getenv(
    "FFMPEG_SHARED_BIN", r"C:\ffmpeg-shared\ffmpeg-7.1-full_build-shared\bin")
TTS_CONCURRENCY = 2   # 4 luồng dễ bị Microsoft throttle trên video dài
TTS_TIMEOUT_S = 90    # mỗi lần gọi edge-tts; tránh treo vô hạn khi đứt kết nối

# BGM duck (S6)
DUCK_GAIN_DB = -14.0
# Giữ nhạc+SFX gốc bằng demucs (tách giọng Trung ra hẳn) thay vì hạ nhỏ cả audio.
# Cần GPU + ffmpeg-shared; chậm thêm (~tách bằng ~1/4 thời lượng). Mặc định tắt.
KEEP_BGM = os.getenv("KEEP_BGM", "0").lower() not in ("0", "false", "")

# Mix (S7): tăng tốc tối đa khi audio dịch dài hơn slot gốc
MAX_SPEEDUP = 1.4

# Nhịp phụ đề (S8): 1 = câu gộp (cho giọng đọc) được TÁCH hiển thị lại theo đúng
# mốc thời gian từng dòng sub gốc — nhịp như bản gốc | 0 = hiện cả câu gộp.
# Giọng đọc không bị ảnh hưởng. Job cũ thiếu dữ liệu mốc → tự về cả câu.
SUB_SPLIT = os.getenv("SUB_SPLIT", "1").strip()

# Phụ đề tiếng Việt (S8): soft = track bật/tắt được (nhanh) | cover_only = chỉ che
# sub gốc/khung/logo, KHÔNG in sub Việt (upload sub_vi.srt riêng lên YouTube Studio
# → viewer bật/tắt, không chồng sub) | burn = vẽ cứng vào hình (re-encode, chậm)
# | none = không phụ đề. File sub_vi.srt luôn được tạo.
SUBTITLE_MODE = os.getenv("SUBTITLE_MODE", "soft")
# kiểu chữ phụ đề vẽ cứng: mặc định + override theo job ở core/stages/s8_render.py

# Che phụ đề gốc cháy sẵn trong hình: none | blur (làm mờ) | black (dải đen).
# Khác none sẽ tự ép SUBTITLE_MODE=burn vì phải re-encode mới sửa được pixel.
COVER_SOURCE_SUBS = os.getenv("COVER_SOURCE_SUBS", "none")
COVER_TOP = float(os.getenv("COVER_TOP", "0.78"))  # che từ tỉ lệ chiều cao này xuống đáy

# Batch: tối đa số video bung ra từ 1 lần dán playlist/nhiều link
BATCH_LIMIT = int(os.getenv("BATCH_LIMIT", "50"))

# Cookie cho yt-dlp — Bilibili chặn HTTP 412 nếu thiếu phiên ĐĂNG NHẬP (cookie
# ẩn danh không đủ). Chỉ cần một trong hai (file được ưu tiên):
# - YTDLP_COOKIES_FILE: đường dẫn cookies.txt (Netscape). Dùng được cả khi trình
#   duyệt đang mở. Xuất bằng tiện ích "Get cookies.txt LOCALLY" sau khi đăng nhập
#   bilibili.com.
# - YTDLP_COOKIES_BROWSER: tên trình duyệt (edge/chrome/firefox) để yt-dlp tự đọc
#   cookie — PHẢI ĐÓNG trình duyệt đó (Windows khóa file cookie khi đang mở).
YTDLP_COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE", "")
YTDLP_COOKIES_BROWSER = os.getenv("YTDLP_COOKIES_BROWSER", "")

# Upload (Phase 3)
YT_CLIENT_SECRET_FILE = os.getenv("YT_CLIENT_SECRET_FILE", "secrets/yt_client_secret.json")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
