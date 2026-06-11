# FlowApp — Kế hoạch phát triển

> Ứng dụng tự động: tải video (donghua/Douyin/YouTube) → dịch → lồng tiếng Việt (thuyết minh) → upload đa nền tảng, điều khiển qua Telegram bot.
> Lập kế hoạch: 2026-06-10. Tham khảo kiến trúc lõi từ repo `hoquanghai/Auto-Translade-video` (MIT), nhưng tự động hóa hoàn toàn bước dịch và bổ sung OCR phụ đề, bot, uploader.

---

## 1. Mục tiêu

**Sản phẩm:** Ném link video vào bot Telegram → bot báo tiến độ từng bước → nhận lại video đã lồng tiếng Việt + link bài đã đăng trên các nền tảng đã chọn.

**Format đầu ra ưu tiên:** thuyết minh 1 giọng (kiểu kênh Moi Dub) — một giọng TTS đọc toàn bộ thoại theo timestamp gốc, giữ nguyên nhạc nền và hiệu ứng.

**Ngoài phạm vi (giai đoạn đầu):** lip-sync, lồng tiếng đa nhân vật.

**Bổ sung 2026-06-11 — Dashboard web local** (`webui/`, chạy bằng `webui.bat`, port 8790): theo dõi job theo checklist từng stage, thêm job bằng dán link, resume job dở, xem video + tải .srt ngay trong trình duyệt. Hàng đợi job tuần tự trong server — Phase 2 bot Telegram sẽ dùng chung cơ chế này.

## 2. Nguyên tắc thiết kế

1. **Stage-based + checkpoint:** mỗi bước ghi output ra đĩa, pipeline chết ở đâu chạy tiếp ở đó. (Học từ repo gốc — phần giá trị nhất.)
2. **Tự động 100%:** không có bước dừng chờ người (khác repo gốc dừng chờ dịch tay).
3. **Chi phí thấp hợp lệ:** ưu tiên xử lý local (OCR, Whisper, edge-tts) + API rẻ (Claude Haiku) thay vì lách điều khoản (xoay account Azure).
4. **MVP trước:** 1 giọng, duck-mode BGM, upload YouTube trước; nâng cấp dần.

## 3. Kiến trúc tổng thể

```
┌─────────────────┐
│  Telegram Bot    │  aiogram 3.x — nhận link, chọn nền tảng, báo tiến độ
└────────┬────────┘
         │ tạo job
┌────────▼────────┐
│  Job Store       │  SQLite (jobs.sqlite) — id, url, status, stage, options
└────────┬────────┘
         │ poll
┌────────▼────────┐
│  Worker          │  1 process, chạy tuần tự từng job, checkpoint mỗi stage
│                  │
│  S1 download     │  yt-dlp (+ Playwright cho Douyin)
│  S2 extract      │  FFmpeg → WAV 16kHz mono + tách video track
│  S3 transcript   │  OCR phụ đề hardsub (chính) / faster-whisper (fallback)
│  S4 translate    │  Claude API (Haiku) — batch 25 segment, overlap 3
│  S5 tts          │  edge-tts (MVP) / LucyLab (premium) — từng segment
│  S6 bgm          │  duck mode (mặc định) / Demucs htdemucs (nếu có GPU)
│  S7 mix          │  pydub — đặt segment theo timestamp, tăng tốc ≤1.4x
│  S8 render       │  FFmpeg — ghép audio mới vào video gốc
│  S9 metadata     │  Claude API — title/description/tags/hashtag
└────────┬────────┘
         │
┌────────▼────────┐
│  Uploaders       │  YouTube Data API / Facebook Graph API / TikTok (draft)
└─────────────────┘
```

**Vì sao không dùng Redis/Celery ngay:** 1 máy, 1 worker, job chạy hàng chục phút — SQLite queue là đủ và dễ debug. Nâng cấp khi cần nhiều worker.

## 4. Lựa chọn công nghệ & lý do

| Thành phần | Chọn | Lý do | Phương án sau |
|---|---|---|---|
| Bot | aiogram 3.x | async, ổn định, cộng đồng lớn | — |
| Download | yt-dlp | hỗ trợ YouTube/Bilibili/Douyin/1000+ site | Playwright cho site chặn |
| Transcript | **OCR hardsub** (PaddleOCR / video-subtitle-extractor) | donghua luôn có phụ đề Trung gắn cứng → chính xác ~100%, miễn phí, kèm timestamp | faster-whisper large-v3 cho video không hardsub |
| Dịch | Claude API `claude-haiku-4-5-20251001` | rẻ (~vài cent/video), tự động hoàn toàn, chất lượng dịch truyện tốt | Sonnet cho thể loại khó |
| TTS | edge-tts (`vi-VN-NamMinhNeural` / `HoaiMyNeural`) | miễn phí, giọng Việt chấp nhận được | LucyLab / viXTTS local khi cần hay hơn |
| BGM | duck mode (hạ volume gốc khi có thoại) | chạy nhanh trên CPU | Demucs htdemucs khi có GPU |
| Mix/Render | pydub + FFmpeg | chuẩn ngành, như repo gốc | — |
| Upload YT | YouTube Data API v3 + OAuth | chính ngạch duy nhất | lưu ý quota & audit (mục 8) |
| Upload FB | Graph API (Pages) | đăng video lên Page | Reels sau |
| Upload TikTok | Content Posting API — **chế độ draft** | app chưa audit chỉ được đẩy nháp | xin audit để đăng thẳng |

## 5. Cấu trúc thư mục

```
FlowApp/
├── bot/
│   ├── main.py            # khởi động bot, đăng ký handler
│   ├── handlers.py        # /start, nhận link, chọn nền tảng, /status, /cancel
│   └── notifier.py        # worker gọi để báo tiến độ về chat
├── core/
│   ├── job.py             # model Job, state machine, đọc/ghi state.json
│   ├── pipeline.py        # orchestrator: chạy tuần tự stage, checkpoint
│   └── stages/
│       ├── s1_download.py
│       ├── s2_extract.py
│       ├── s3_transcript.py   # OCR trước, fallback whisper
│       ├── s4_translate.py
│       ├── s5_tts.py
│       ├── s6_bgm.py
│       ├── s7_mix.py
│       ├── s8_render.py
│       └── s9_metadata.py
├── uploaders/
│   ├── youtube.py
│   ├── facebook.py
│   └── tiktok.py
├── worker.py              # vòng lặp: lấy job pending → chạy pipeline → upload
├── cli.py                 # chạy pipeline 1 video không qua bot (dev/test)
├── config.py              # đọc .env, hằng số (MAX_SPEEDUP=1.4, batch size…)
├── data/
│   ├── jobs.sqlite
│   └── jobs/<job_id>/     # artifacts mỗi job (xem mục 6)
├── .env.example
├── requirements.txt
└── PLAN.md
```

## 6. Thiết kế checkpoint (thư mục job)

```
data/jobs/20260610_153000_abc123/
├── state.json             # stage hiện tại, options, lỗi gần nhất, retry count
├── source.mp4             # S1
├── audio_16k.wav          # S2
├── transcript_zh.json     # S3: [{id, text, start, end}]
├── transcript_vi.json     # S4: thêm field text_vi
├── tts/seg_0001.wav ...   # S5
├── bgm.wav | ducked.wav   # S6
├── dubbed_audio.wav       # S7
├── final.mp4              # S8
├── metadata.json          # S9: title/desc/tags cho từng nền tảng
└── upload_result.json     # link bài đăng
```

`state.json.stage` là enum: `pending → downloading → extracting → transcribing → translating → tts → bgm → mixing → rendering → metadata → uploading → done | failed`. Worker khởi động lại sẽ resume từ stage chưa hoàn thành. Mỗi lần đổi stage → gọi `notifier` báo về Telegram (đúng UX "làm đến đâu báo đến đó" như ảnh mẫu).

## 7. Lộ trình (4 phase)

### Phase 0 — Nền móng (1–2 ngày)
- [x] `git init`, cấu trúc thư mục, `requirements.txt`, `.env.example`, `config.py` *(2026-06-10)*
- [x] FFmpeg đã có sẵn trong PATH (8.0.1) — môi trường: Python 3.14.4, lưu ý S3 (paddleocr/faster-whisper) có thể cần venv Python 3.12 riêng vì wheel chưa hỗ trợ 3.14
- [x] yt-dlp tải OK + checkpoint/resume hoạt động (job test: `data/jobs/20260610_233125_e9f0d9`, đang dừng ở S2 — dùng làm job test cho Phase 1)
- [ ] **Đăng ký ngay** (vì duyệt mất hàng tuần, làm song song các phase sau):
  - Google Cloud project + YouTube Data API + OAuth consent screen
  - Facebook App + Page access token
  - TikTok developer app (Content Posting API)
  - ~~Claude API key~~ ✓ đã có trong `.env`, test gọi Haiku thành công (2026-06-10)

### Phase 1 — Pipeline lõi chạy CLI (1–2 tuần) ← **giá trị cốt lõi**
- [x] S1–S2: download + extract audio *(2026-06-10)*
- [x] S3: faster-whisper hoạt động trên Python 3.14 (model `small`, đổi qua env `WHISPER_MODEL`) — **OCR hardsub PaddleOCR còn lại, làm khi test donghua thật** (Phase 1.5)
- [x] S4: dịch Claude Haiku — batch + context overlap + structured output (json_schema), prompt văn phong tu tiên trong `s4_translate.py`
- [x] S5: edge-tts song song 4 luồng, resume theo từng file segment
- [x] S6–S7: duck -14dB theo khoảng thoại + mix theo timestamp, tăng tốc ≤1.4x bằng ffmpeg atempo, cảnh báo tràn ghi `mix_report.json`
- [x] S8: render final.mp4 (video copy không re-encode, audio AAC 192k)
- [x] **Nghiệm thu đạt** *(2026-06-10)*: video test 19s chạy hết 8 stage tự động ra final.mp4 (video av1 + audio aac, đủ 18.9s); resume từng stage hoạt động
- [x] **Phase 1.5 — OCR hardsub** *(2026-06-11)*: RapidOCR (ONNX, chạy được Python 3.14) trong `core/ocr_subs.py`; S3 mode auto (OCR → fallback whisper khi video không có hardsub). Test trailer "I am Blade Master": OCR chính xác vượt trội whisper (18 vs 15 segment, hết lỗi nghe nhầm). E2E OCR → final.mp4 OK.
- [x] **Phase 1.6 — gói fix chất lượng từ test tập Wukong 12.7 phút** *(2026-06-11)*:
  - `core/segtools.py`: 3 lớp lọc rác (logo Latin/bracket, segment lặp ≥3 lần, token có mặt >20% segment = watermark) + gộp dòng phụ đề nháy nhanh thành câu ≤8s. Kết quả: 689 → 104 segment, tràn timing 587 → 2.
  - `core/ocr_subs.py`: OCR 2 pha — blacklist dòng xuất hiện ≥15% số frame (watermark đứng yên) ngay từ nguồn; lưu `ocr_raw.json` để đổi bộ lọc không cần OCR lại.
  - `s4_translate.py`: tự phát hiện câu dịch sót ký tự Trung → retry tối đa 2 lần (`fix_leaks`); glossary Tây Du Ký (Wukong → Ngộ Không...).
  - `s5_tts.py`: timeout 90s/request + concurrency 2 (chống treo khi Microsoft throttle video dài).
  - Script tiện ích trong `scripts/`: `refix_job.py` (áp lại bộ lọc segment), `fix_leak_job.py` (dịch lại câu sót chữ Hán), `rerender.py`, `check_api.py` — đều resume không làm lại từ đầu.
- [x] **Phase 1.7 — gói tối ưu tốc độ** *(2026-06-11)*:
  - OCR song song 6 tiến trình × 2 luồng onnxruntime (`OCR_WORKERS` trong .env) — nhanh ~2.6x cùng điều kiện máy. Đã thử dedup frame trùng (pixel thô + mặt nạ sáng): thí nghiệm đối chiếu OCR thật cho thấy mọi ngưỡng đều gây sai văn bản → loại bỏ, không đánh đổi chất lượng.
  - S6 duck + S7 mix viết lại bằng numpy (`core/audio_np.py`) — thao tác PCM trực tiếp thay vì pydub copy cả track; kết quả mix giống hệt.
  - S8 burn dùng Intel QuickSync (`h264_qsv`, ~7x realtime) với fallback tự động về libx264.
  - Đo thực tế tập 12.7 phút: duck + mix + render burn+blur = **135 giây** (trước: 15–20 phút).
  - Lưu ý vận hành: tốc độ máy dao động 4–5 lần theo nhiệt/app khác đang chạy (2 server dev của user); đã tắt sleep khi cắm điện (`powercfg /change standby-timeout-ac 0`) vì máy sleep từng giết tiến trình nền 2 lần.
- [ ] **Tối ưu còn lại (không chặn Phase 2):**
  - OCR vẫn là nút cổ chai cho video dài (~1.5–2h cho video 1 tiếng tùy tải máy) → cân nhắc GPU (onnxruntime-directml) hoặc máy bàn
  - Nếu chất lượng dịch cần cao hơn nữa → `CLAUDE_MODEL=claude-sonnet-4-6` trong .env

### Phase 2 — Telegram bot + worker (1 tuần)
- [ ] Bot nhận link, hỏi nền tảng đăng (inline keyboard), tạo job vào SQLite
- [ ] Worker poll job, chạy pipeline, notifier báo tiến độ từng stage (✓ như ảnh mẫu)
- [ ] `/status` xem hàng đợi, `/cancel` hủy job, gửi file video về chat khi xong
- [ ] **Nghiệm thu:** thao tác hoàn toàn qua điện thoại, không đụng máy tính

### Phase 3 — Upload đa nền tảng (1–2 tuần, phụ thuộc duyệt API)
- [ ] S9: sinh metadata bằng Claude (title giật đúng thể loại, description, tags)
- [ ] YouTube trước (API ổn định nhất) → Facebook Page → TikTok draft
- [ ] Trả link bài đăng về Telegram
- [ ] **Nghiệm thu:** 1 lệnh duy nhất từ Telegram → video xuất hiện trên YouTube

### Phase 4 — Nâng chất lượng (liên tục)
- [ ] Demucs tách BGM (khi có GPU) thay duck mode
- [ ] Diarization (pyannote) + 2 giọng nam/nữ
- [ ] Thumbnail tự động, batch nhiều video, lịch đăng
- [ ] Nâng TTS: LucyLab hoặc viXTTS local

## 8. Chi phí & giới hạn vận hành

**Chi phí biến đổi mỗi video ~60 phút** (OCR + edge-tts + Haiku):
- Dịch Claude Haiku: ~$0.05–0.15
- OCR, TTS, mix: $0 (local/free)
- → **< 4.000đ/video**, không phụ thuộc free tier của ai, không cần xoay account.

**Giới hạn cần nhớ:**
- YouTube API: upload = 1.600 units / quota 10.000 units/ngày → **~6 video/ngày**; app OAuth chưa verify thì video upload bị khóa private → cần làm verify sớm.
- TikTok chưa audit: chỉ đẩy được **nháp** (user tự bấm đăng trong app).
- edge-tts là dịch vụ không chính thức — nếu Microsoft chặn, chuyển LucyLab/viXTTS (đã chừa sẵn interface trong S5).
- Thời gian xử lý ước tính video 60': OCR ~10–20', dịch ~2', TTS ~10', mix+render ~10' → **~45 phút/video trên CPU**.

## 9. Rủi ro chính

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Bản quyền donghua (Tencent/iQiyi/Bilibili đánh mạnh trên YT) | **Cao** — đã chấp nhận | Không dồn 1 kênh; coi kênh là tài sản dùng một lần; cân nhắc dần nội dung có quyền |
| YouTube siết "inauthentic content" với kênh AI hàng loạt | Cao | Đầu tư metadata/thumbnail riêng từng video, không đăng máy móc |
| OCR sai vùng phụ đề / video không hardsub | Trung bình | Fallback faster-whisper tự động khi OCR ra quá ít text |
| Giọng edge-tts đều đều, kém cảm xúc | Trung bình | Nghe thử sớm ở Phase 1; interface TTS thay được engine |
| API platform đổi/khóa | Trung bình | Uploader tách module riêng, lỗi upload không làm hỏng job (video vẫn lưu local) |

## 10. Việc cần làm ngay tiếp theo

1. Phase 0: dựng skeleton project + cài đặt môi trường (Python 3.11+, FFmpeg).
2. Nộp đăng ký API các nền tảng (mục Phase 0) — đường găng dài nhất.
3. Bắt đầu Phase 1 với 1 video donghua mẫu ngắn (~5 phút) làm video test chuẩn.
