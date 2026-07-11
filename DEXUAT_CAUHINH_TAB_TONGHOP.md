# Tổng hợp 3 phía — tab "⚙️ Cấu hình" (chốt để user duyệt)

> Claude đối chiếu `DEXUAT_CAUHINH_TAB_CODEX.md` + `_GEMINI.md` với code thật
> (2026-07-11). Trạng thái: KẾ HOẠCH CHỐT — chưa code, user duyệt theo đợt mục 4.

## 1. Codex bắt lỗi tôi 3 chỗ — đã kiểm code, nhận cả 3

1. **G8 premise sai**: `/api/config` KHÔNG trả `defaults` (biến cục bộ chỉ dùng
   điền fallback cho `values` — server.py get_config); và `getattr(config, k)`
   đã nhiễm .env nên không dùng làm factory default được. → G8 phải đứng trên
   **settings schema** có factory default riêng (xem mục 2).
2. **G15 đề xuất thứ đã có**: `.cfgfoot` đã `position: sticky` (style.css:203)
   và `cfgDirty` + modal đã chặn chuyển tab (app-core.js:204). G15 thu hẹp còn
   phần thiếu thật: đếm diff draft (về 0 khi đổi lại giá trị cũ), `beforeunload`
   khi đóng trình duyệt, toast danh sách key server đã lưu, disable nút khi đang
   lưu, secret rỗng không tính dirty.
3. **Bằng chứng "3 danh sách lệch nhau"**: `ELEVENLABS_MODEL` có trong config.py
   + SAFE_ENV_KEYS nhưng KHÔNG có control nào trong UI (grep app-core.js = 0).
   Cùng họ: `set_config` ghi `KEY=value` thô không escape (giá trị chứa `#`/quote
   sẽ parse sai lần sau — bug nền có thật).

## 2. Điểm nâng tầm của Codex — SETTINGS SCHEMA (nhận làm nền tảng, đặt là G16)

Mỗi setting hiện khai báo lặp ở ≥3 nơi (config.py default/parser, SAFE/SECRET
whitelist server, CFG_FIELDS + loadConfig client) → thêm reset/profile/validation
trên 3 danh sách rời là chúng lệch nhau tiếp. **G16**: một schema tập trung
(key, type, factory_default, options/range, secret, allow_empty, category,
advanced, profile_scope, dependencies) — server dùng nó sinh whitelist, parse +
validate, trả factory defaults + saved + effective, unset/reset, validate
profile import; client chỉ giữ nhãn/tooltip tiếng Việt + layout. Đúng bài học
resolver voicesig của đợt U-2. Kèm: **dotenv serializer chuẩn** (quote/escape)
+ **API unset** (reset = XOÁ key khỏi .env để hưởng default mới của phiên bản
sau, không ghi cứng default hiện tại — điểm tinh của Codex).

## 3. Phân xử các điểm còn lại

- **G5 (⭐ vs model đích danh)**: 2 agent HỘI TỤ độc lập — ⭐ là setter/view
  thuần UI cho 2 key model thật, KHÔNG tạo env key mới; sửa tay model → núm tự
  hiện "Tùy chỉnh"; .env chỉ lưu 2 model. Codex thêm điểm ăn tiền: khi provider
  = Gemini **đừng ẩn hẳn Model Claude** — nó là model fallback THẬT (tooltip
  hiện tại còn nói dối "fallback Haiku" trong khi có thể là Sonnet) → hiện thành
  "Model chính / Model fallback" trong Nâng cao. CHỐT theo bản hợp nhất này.
- **G7 (health card)**: chốt theo Codex — endpoint tên `/api/capabilities`
  (health = liveness, sai nghĩa), trạng thái 3 mức installed/partial/unknown
  (pyannote cài ≠ đã accept model HF; demucs cài ≠ checkpoint đã tải), probe
  rẻ: cpu_count, nvidia-smi timeout, NVENC xác nhận bằng encode thử (tái dùng
  `ffmpeg.h264_args` đã có), `find_spec` thay vì import, check ĐỦ bộ file
  viXTTS (config+checkpoint+vocab — không chỉ config.json), key từ `_read_env()`
  tươi; cache 30–60s + nút refresh; CẤM gọi `vixtts.is_available()` (nạp model).
  Lấy thêm của Gemini: dung lượng đĩa trống (dùng `shutil.disk_usage` stdlib —
  bản phác của Gemini import `psutil` là dependency chưa có trong repo) và ý
  quét DLL CUDA. Bản phác Gemini có 2 lỗi nhỏ nữa: check `"h264_nvenc" in
  ffmpeg -encoders` chỉ chứng minh CÓ TÊN chứ không chạy được; đọc key qua
  `config.*` là snapshot lúc server start (stale sau khi lưu key mới).
- **G10 (engine thiếu key ở tab global)**: Codex đúng — KHÁC per-job, ở đây
  user có thể chọn engine rồi nhập key TRONG CÙNG form → không disable option,
  chỉ cảnh báo inline + nút nhảy tới ô key + cập nhật ngay khi key được gõ vào
  draft. Kèm sửa nền: `_engine_caps()` phải đọc `_read_env()` tươi (hiện dùng
  config lúc startup — stale sau khi lưu key, ảnh hưởng cả editor U7).
- **G4 (OCR_WORKERS)**: chốt bản tinh của Codex — option `auto` LƯU CHỮ "auto"
  vào .env (máy khác/profile tự thích nghi), resolver runtime = công thức có
  trần (mỗi worker RapidOCR đã ăn 2 thread → cpu_count()//2, cap 4–6), KHÔNG
  ghi cứng con số của máy hiện tại.
- **G11 (profile)**: chốt theo Codex — **allowlist PROFILE_KEYS** (loại secret,
  path máy local, OCR worker/device, TELEGRAM_CHAT_ID, AUTO_RETRY) thay vì lọc
  theo hậu tố `_KEY/_TOKEN` như Gemini (denylist theo tên dễ lọt — vd path
  cookies không có hậu tố); file theo UUID + schema_version + preview diff khi
  áp; key thiếu = GIỮ hiện tại, key lạ = bỏ + warning; KHÔNG kèm
  `pause_before_render` (preference UI, lưu localStorage riêng — khác Gemini).
- **G13 (bố cục)**: hợp nhất — khung thứ tự của Gemini (Trạng thái máy → tìm
  kiếm/profile → TTS → Dịch → Nhận dạng → Thương hiệu/Render → Hệ thống →
  Keys cuối) + cấu trúc của Codex cho nhóm cuối: "Tích hợp & khóa truy cập"
  chia tiểu mục (Dịch/TTS/Thông báo/YouTube) — GIỮ CẶP đi với nhau
  (TELEGRAM token+chat id; VBEE token+app id; YouTube OAuth+privacy), không gom
  token thành danh sách phẳng như hiện tại. First-run: cả 2 agent cùng đề xuất
  banner vàng đầu tab + auto mở & cuộn tới nhóm Keys khi chưa có key dịch nào.
- **Whisper device/compute**: 2 bên cùng muốn lộ nhưng khác kiểu — chốt theo
  Codex: MỘT control mức cao "Auto (khuyên dùng) / CPU tương thích (cpu+int8) /
  NVIDIA GPU (cuda+float16)" thay vì 2 dropdown thô (tổ hợp sai kiểu cpu+float16
  chỉ âm thầm fallback); gate option GPU theo /api/capabilities (ý Gemini).
  `VIXTTS_DEVICE` KHÔNG lộ (viXTTS CPU vô dụng; biến còn bị demucs dùng ké).
- **Expose thêm** (hợp nhất 2 danh sách): `YOUTUBE_API_KEY` (thiếu sót rõ nhất
  — Trends đang bắt sửa .env tay, và phải thêm vào SECRET_ENV_KEYS),
  `REVIEW_TRANSLATION` + `GLOSSARY_AUTO` (Nâng cao Dịch — ảnh hưởng phí mỗi
  job), `WHISPER_LANGUAGE` (Nâng cao Nhận dạng), `ELEVENLABS_MODEL`,
  `METADATA_MODEL` (Nâng cao Xuất bản), `OCR_MAX_MINUTES`, `BATCH_LIMIT`
  (Hệ thống), `YTDLP_COOKIES_*` (Nâng cao + cảnh báo riêng tư),
  `FFMPEG_SHARED_BIN` (ý Gemini — đúng điểm đau DLL Windows của máy này; kèm
  auto-gợi ý path phổ biến), và quyết cho dứt trạng thái nửa lộ nửa ẩn của
  `FRAME_*` global (đề xuất: lộ "Khung mặc định" trong Xuất bản/Nâng cao, dùng
  chung control với editor). KHÔNG lộ: GENDER_DETECT, TRENDING_*, COVER_TOP.
- **G12 (nghe mẫu)**: FX sample từ `voice_samples/` = đồng thuận, rẻ. Nghe thử
  GIỌNG theo draft: Codex đúng là `/api/tts-preview` không nhận draft global →
  cần param settings whitelist (hoặc endpoint config-preview); paid engine phải
  ghi "có tính phí" + chỉ chạy khi bấm chủ động; không auto-preview khi đổi
  dropdown.

## 4. Kế hoạch thi công chốt (chờ user duyệt theo đợt)

- **Đợt G-A — nền tảng (làm trước, mọi thứ sau đứng trên nó):** G16 settings
  schema + dotenv serializer/validation + API unset; `/api/capabilities` (+
  resolver caps đọc env tươi, thay `_engine_caps` stale — sửa lây sang editor
  U7); sửa nhãn dối G6 + tooltip fallback sai của G5 (2 dòng chữ, khỏi chờ).
- **Đợt G-B — dọn nhà + trung thực:** G1–G4 (dời AUTO_RETRY/SUBTITLE_MODE/
  SUB_SPLIT/VOICE_FX*, giải tán 2 nhóm lửng, OCR_WORKERS auto, interval xuống
  Nâng cao — *Codex bổ sung VOICE_FX cũng thuộc render → sang nhóm Xuất bản*);
  G5 ⭐; expose-list mới (gồm YOUTUBE_API_KEY vào SECRET); Whisper control mức
  cao; G10 cảnh báo; G15 phần thiếu.
- **Đợt G-C — bố cục + tiện nghi:** G13/G14 (layout mới, Nâng cao trong nhóm,
  nhớ localStorage, first-run banner); card Trạng thái máy (render từ G-A);
  G8 diff/reset-unset; G9 tìm kiếm (ẩn row không khớp + tự mở details, khôi
  phục trạng thái khi xoá).
- **Đợt G-D:** G11 profile; G12 nghe mẫu/preview draft.

## 5. Câu hỏi còn mở cho user

1. Làm theo thứ tự G-A → G-D một mạch, hay G-A + G-B trước rồi xem thử?
2. `FRAME_*` global: lộ "Khung mặc định" lên UI hay bỏ hẳn đường config global
   (chỉ chỉnh per-job trong editor 🎨)?
3. Danh sách expose thêm ở mục 3 có mục nào bạn KHÔNG muốn lộ không (vd
   YTDLP_COOKIES vì lý do riêng tư)?
