# Nhật ký làm việc

Mỗi phiên làm việc (bất kể máy nào) ghi một mục vào ĐẦU file này — máy kia pull về
đọc là biết chuyện gì đã xảy ra, không phải lần commit hay lục transcript chat.
Bài học: danh sách đề xuất #1–#18 từng bị mất vì chỉ nằm trong hội thoại một máy.

---

## 2026-07-04 (2) — Desktop (F:\MyProject\vietsubvideo)

### PLAN 11 MỨC 2 — Nhãn cảm xúc A+B chung một mạch (`core/emotion.py`, EMOTION=1)

- **A**: Claude gắn nhãn cảm xúc từng câu khi dịch (S4, field "emotion":
  binhthuong|gap|gian|buon|thitham — chỉ gắn khi RÕ RÀNG, lưu trên segment khi
  khác bình thường). Giữ nhãn qua fix_leaks (cùng bài học với character).
- **B**: S5 map nhãn theo engine — edge-tts: offset rate/pitch/volume CỘNG vào
  prosody mức 1 (đo audio), kẹp trần ±25%/±30Hz/±25%; viXTTS: chọn clip mẫu
  voices/ hợp cảm xúc (giận→mau-*-nhanh, buồn→mau-*-cham/nhe-nhang; casting
  voice_ref vẫn thắng — danh tính > cảm xúc). Nhãn vào .sig → đổi nhãn/bật tắt
  là câu bị ảnh hưởng tự đọc lại đúng.
- Nghe thử editor giờ áp CÙNG nhãn cảm xúc + đúng giọng TARGET_LANG (trước là
  giọng vi cứng, không sắc thái — nghe khác render).
- Hai tầng bổ trợ: prosody = đo audio khách quan; nhãn = ngữ nghĩa lời thoại
  (bắt được mỉa mai/đe dọa-nói-nhỏ mà audio không lộ). Config UI cạnh PROSODY.
- Test: unit (clamp/mapping ra file mẫu thật/schema/cache), edge synth thật với
  kwargs giận, tts-preview 2 đường. Review đối kháng: 1 lỗi thật (preview thiếu
  cảm xúc) đã sửa; 2 "CRITICAL" là false positive (sig lệch fallback là thiết kế
  cũ có chủ đích, không do emotion).

### Máy khác pull về: `.env` thêm `EMOTION=1` (xem `.env.example`). Không gói pip mới.

---

## 2026-07-04 — Desktop (F:\MyProject\vietsubvideo)

### Đợt dọn dẹp + tối ưu theo review tổng thể (5 mục, user duyệt)

**1. Dọn rác:** XÓA worker.py, bot/ (aiogram stub), uploaders/ (Phase-3 stub),
_azure_tts.html — tất cả đã bị thay bởi worker thread trong server.py,
core/notify.py, core/youtube_upload.py, không ai import. Gỡ field chết
Job.platforms + Job.chat_id (state.json cũ vẫn nạp được — Job.load lọc key lạ).
Gỡ aiogram khỏi requirements; PIN yt-dlp==2026.6.9 (bản mới vỡ Douyin).
KHÔNG xoá output/*.mp4 cũ — sau khi dọn data/jobs, đó là bản duy nhất còn lại.

**2. Series đồng bộ 2 máy (sửa lỗ thiết kế):** kho series chuyển
data/series (gitignore — mỗi máy một bản!) → **series/ trong repo** (git theo
dõi, push/pull là casting+glossary nhất quán xuyên máy). Glossary mặc định
cũng chuyển → series/_glossary_default.txt. Tự DI TRÚ 1 lần khi chạy.

**3. Log per-job:** worker ghi toàn bộ stdout/stderr của cli.py vào
<job>/run.log (append + header mỗi lượt) → job lỗi lúc vắng mặt vẫn còn vết.
Endpoint GET /api/jobs/{id}/log (đọc 256KB cuối); UI: nút 📜 Log trong menu
Soát. Bonus: hết luôn rủi ro crash in tiếng Việt ra console cp1258.

**4. Đĩa + hiệu năng poll:** nút 🧹 Dọn file tạm (job DONE): xoá wav trung
gian (audio_16k/full, vocals, ducked, dubbed...) + *_sped.wav, GỠ
extracting/bgm/mixing khỏi completed_stages → "Sửa lời thoại" sau đó tự tách
audio lại từ source (đã trace: extracting đứng trước tts nên an toàn).
_job_summary cache seg_total/tts_done theo mtime (hết đọc cả transcript mỗi
3 giây); progress chỉ đọc khi job đang chạy. Vá vận hành: rerender gate khoá
file như save_segments; .env ghi nguyên tử; atexit kill job mồ côi khi server tắt.

**5. UX + hàng đợi:** thẻ job gom 9 nút → 2 nút chính + 2 menu (🔎 Soát ▾ /
📤 Xuất bản ▾). Tab Cấu hình gập 4 nhóm ít dùng (diarization/khử ồn/YouTube/
Telegram — tự mở nếu đã bật). Hàng đợi: nút **⬆ Ưu tiên** (job chờ nhảy lên
đầu) + **⏸ Tạm dừng hàng đợi** (job đang chạy chạy nốt, job kế chờ mở lại).

Review đối kháng (2 vòng, 29 agent tổng): 0 lỗi CRITICAL/HIGH xác nhận.

### Máy khác pull về cần làm

1. Sau pull, series ở máy đó (data/series) sẽ TỰ di trú sang series/ khi chạy
   lần đầu — nếu 2 máy có series TRÙNG TÊN khác nội dung, bản trong repo thắng,
   bản local giữ nguyên ở data/series (không đè) → tự xử lý tay nếu cần.
2. `pip uninstall aiogram` (tuỳ, không bắt buộc); yt-dlp giữ 2026.6.9.

---

## 2026-07-03 (đêm) — Desktop (F:\MyProject\vietsubvideo)

### Tính năng mới — chốt nốt #15 + #16 (hết sạch danh sách #1–18)

- **#15 UI duyệt glossary gợi ý** (`core/glossary.py`, `webui/server.py`, UI):
  nút **📒 Tên riêng** trên thẻ job (sau bước transcript) → modal hiện bảng tên
  riêng hiện tại + danh sách Claude trích từ chính video (S4 giờ LƯU cache
  `glossary_auto.json`; chưa có cache thì trích live 1 call). Bấm ➕ từng mục /
  ➕ tất cả; checkbox **lưu thêm vào series** (chỉ THÊM tên chưa có, không đè);
  **💾 Lưu & dịch lại** = reset job về sau transcript (xoá transcript_vi/tts/
  final/metadata) rồi tự resume — dịch lại với glossary mới.
  `auto_extract` có bản generic (mọi ngôn ngữ nguồn, không CJK gate) khi không
  phải donghua-tiếng-Việt. Endpoint: GET `.../glossary-suggest`, POST `.../glossary`.
- **#16 Lồng tiếng đa ngôn ngữ ĐÍCH** (`core/langs.py`, `TARGET_LANG` trong
  Cấu hình): vi|en|zh|ja|ko|es|fr|id|th|pt. Khác vi → S4 dùng prompt dịch/review
  theo ngôn ngữ đó (bỏ Hán-Việt/donghua), S5 đọc bằng cặp giọng edge-tts của
  ngôn ngữ (tên giọng đã verify `--list-voices`; đổi TARGET_LANG là .sig lệch →
  tự đọc lại), S9 metadata viết cùng ngôn ngữ. Đích zh/ja: TẮT leak-check chữ
  Hán (hợp lệ) + review cho phép CJK; `_CLAUSE_SPLIT` (sub_split) thêm dấu câu
  CJK 。？！、；：. **Giới hạn**: viXTTS/casting clone là finetune tiếng Việt →
  đích ≠ vi thì mọi câu (kể cả voice_ref) đọc edge, có log nhắc.

### Ghi chú kỹ thuật

- Job thật chạy tối nay đã đi qua s4 mới → `glossary_auto.json` sinh tự nhiên
  (5 tên: Đường Tam, Đấu La Đại Lục...) — cache suggest hoạt động ngay.
- Test: reset "dịch lại" đúng stage/file; series merge dedupe; edge en-US OK;
  clause-split CJK/VI đúng; JS node --check sạch.

### Máy khác pull về cần làm

1. `.env` thêm `TARGET_LANG=vi` (xem `.env.example`) — không có gói pip mới.
2. Job cũ muốn thấy gợi ý glossary: bấm 📒 Tên riêng (lần đầu trích live 1 call
   Haiku rồi cache).

---

## 2026-07-03 — Laptop (C:\MyProject\FlowApp)

### Tính năng mới

- **Khung viền nâng cấp** (`69943b3`): khung PNG dựng bằng **9-slice** (góc giữ tỉ
  lệ, cạnh kéo 1 chiều — không méo ở mọi tỉ lệ kể cả video dọc 9:16); phụ đề **tự
  né khung** (đo bề dày khung ở đáy → cộng margin, PNG đo bằng kênh alpha); chế độ
  **"khung ngoài" (pad)** — thu hình vào trong, khung không che nội dung; preview
  "Xem thử" giờ vẽ cả khung.
- **#8 Nhận diện NGƯỜI NÓI — diarization pyannote** (`0a72d77`, `core/speakers.py`):
  nhãn cụm S1/S2… vào batch dịch (Claude gán nhân vật nhất quán), giới tính theo
  CỤM (trung vị F0), engine viXTTS tự chia mỗi cụm một clip `voices/` riêng.
  Casting series/chỉnh tay luôn thắng. Kết quả sửa được trong `speakers.json`.
  Bật: DIARIZE=1 + HF_TOKEN (cần `pip install pyannote.audio` + chấp nhận điều
  khoản 2 model pyannote trên HuggingFace — chỉ desktop GPU; laptop tắt mặc định).
- **Xóa/che watermark kênh gốc** (`072495e`, `core/watermark.py`): 4 cách theo
  vùng vẽ trên editor (khung đỏ) — **delogo** (nội suy, sạch nhất cho watermark
  tĩnh), **blur**, **dải đen**, **đè logo kênh mình**; + **cắt mép** (crop tối đa
  20%/cạnh rồi phóng lại, khung xanh = phần giữ). Crop tự quy đổi tọa độ băng
  che/box sub/vùng wm vẽ sau nó. Test thật: xóa sạch logo 斗罗大陆 góc phải-dưới.
- **Tông giọng theo audio gốc — PLAN 11 mức 1** (`83add51`, `core/prosody.py`):
  đo F0 + tốc độ nói + RMS từng câu so với MỨC NỀN TỪNG NGƯỜI NÓI → chỉnh
  rate/pitch/volume edge-tts. Test job Douyin: 6/21 câu chỉnh; câu hét tên chiêu
  nhận r-12%/p+25Hz/v+10%. Bật tắt: PROSODY (mặc định 1). Đo trên vocals.wav
  (demucs) nếu có — desktop bật KEEP_BGM sẽ chính xác hơn.
- **Nhịp phụ đề (sub_split)** (`169f4f0` + chốt an toàn `04fc5f0`): segtools giờ
  GIỮ mốc thời gian từng dòng gốc khi gộp (`pieces`); render tách câu Việt hiển
  thị theo đúng nhịp sub gốc (cắt tại dấu câu) — GIỌNG vẫn đọc câu gộp liền mạch.
  Option per-job "Nhịp" trong editor + SUB_SPLIT mặc định (=1). Job Douyin:
  21 → 104 block, khớp ~1:1 nhịp gốc. Job cũ thiếu pieces → tự về cả câu.
  Chốt an toàn: <2 từ/mảnh không tách (tránh bổ đôi tên riêng khi mốc nhiễu).

### Sửa lỗi

- **OCR làm MỌI job mới chết ở transcribing** (`524bc07`): code tiến độ (desktop
  #9) gọi `pool.imap` — ProcessPoolExecutor không có imap, đổi `.map`. Lỗi chỉ lộ
  khi chạy job mới đầu tiên sau merge desktop.
- **Khôi phục mode `cover_only`** (trong `69943b3`): bị MẤT khi desktop dựng lại
  cây mã (thư mục không còn .git). Che sub gốc nhưng không in sub Việt — để
  upload sub_vi.srt riêng lên YouTube, viewer bật/tắt không chồng sub.
- **Server in tiếng Việt có thể 500** (trong `072495e`): uvicorn console cp1258 —
  ép stdout/stderr UTF-8 như cli.py.
- **launch.json** (`63737a0`): đường dẫn tuyệt đối F:\ của desktop → `.venv`
  tương đối, chạy được cả hai máy.

### Kết quả test đáng nhớ

- **Bilibili**: API bảng xếp hạng (tab Phim hot) chạy KHÔNG cần đăng nhập (quét
  được 197 video); nhưng TẢI video bị 412 — cần cookie đăng nhập
  (YTDLP_COOKIES_FILE). Chưa test tải vì chưa có cookie Bilibili.
- **Douyin**: yt-dlp KHÔNG tải được kể cả có cookie tươi, kể cả bản nightly —
  extractor thiếu chữ ký `a_bogus` (TODO trong source yt-dlp). Thông báo "Fresh
  cookies needed" gây hiểu lầm. **Đường vòng hoạt động tốt**: tải qua SaveTik →
  nút "📁 Upload video từ máy". yt-dlp giữ bản stable 2026.06.09.
- Job Douyin đầu tiên hoàn chỉnh (2.4 phút, 21 câu, HD 1080p) — dùng làm chuẩn
  test cho prosody + sub_split.
- Video dọc 9:16 chạy trọn pipeline; lưu ý OCR_CROP_TOP nếu sub nằm giữa màn hình.

### Máy khác pull về cần làm

1. `git pull` (không có gói pip mới BẮT BUỘC; pyannote là tùy chọn).
2. Bổ sung khóa mới vào `.env` (xem `.env.example`): `PROSODY=1`, `SUB_SPLIT=1`,
   `DIARIZE=0`, `HF_TOKEN=`, `DIARIZE_MAX_SPK=0`.
3. Desktop muốn dùng diarization: `pip install pyannote.audio` + tạo HF token +
   bấm đồng ý điều khoản `pyannote/segmentation-3.0` và
   `pyannote/speaker-diarization-3.1` trên huggingface.co → DIARIZE=1.
4. PLAN.md: mục 11 (giọng cảm xúc — mức 1 đã làm, A/B/C/D để dành) + mục 12
   (backlog 10 ý tưởng, #8 đã xong) là danh sách việc tương lai.
