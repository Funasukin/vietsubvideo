# Tinh gọn + nâng cấp tab "⚙️ Cấu hình" — đề xuất thảo luận 3 phía

> Claude soạn 2026-07-11 theo yêu cầu user: rà tab Cấu hình TOÀN CỤC (khác panel
> ⚙️ per-job đã làm đợt U1–U16), tinh gọn knob thừa, đề xuất nâng cấp đáng giá,
> tinh chỉnh UI/UX. **Chưa code — tài liệu thảo luận.** Codex + Gemini phản biện
> theo mục 6, ghi vào `DEXUAT_CAUHINH_TAB_CODEX.md` / `_GEMINI.md`. User chốt
> theo số G1–G15.
> Code tham chiếu: `webui/static/app-core.js` (loadConfig, dòng ~281–560;
> CFG_FIELDS ~523), `webui/server.py` (SAFE_ENV_KEYS/SECRET_ENV_KEYS ~40–61,
> /api/config), `config.py` (defaults).

## 1. Hiện trạng: 9 nhóm, ~50 control

| Nhóm (mặc định mở?) | Knob |
|---|---|
| 🔑 Khóa API & Token (MỞ, trên cùng) | 8 ô secret + VBEE_APP_ID + TELEGRAM_CHAT_ID |
| Dịch & phụ đề (MỞ) | TRANSLATE_PROVIDER, GEMINI_MODEL, GEMINI_MIN_INTERVAL, CLAUDE_MODEL, TRANSLATE_STYLE_EXTRA, CONTENT_STYLE, TARGET_LANG, **SUBTITLE_MODE, SUB_SPLIT** |
| Nhận dạng thoại (MỞ) | TRANSCRIPT_SOURCE, WHISPER_MODEL, OCR_WORKERS, OCR_FPS, OCR_CROP_TOP, **AUTO_RETRY** |
| Lồng tiếng TTS (MỞ) | TTS_ENGINE, TTS_SINGLE_VOICE, KEEP_BGM, DUCK_GAIN_DB, VOICE_FX, PROSODY, EMOTION, PROSODY_TRANSFER, MAX_SPEEDUP, STRETCH_SHORT, preset 🎯/🌿, cặp giọng theo engine (edge/viXTTS/ElevenLabs/VBee/FPT — mỗi engine 2 ô) |
| Thương hiệu / xuất bản (MỞ) | MUSIC, MUSIC_VOL, LOGO ×4, INTRO, OUTRO, MASTER |
| Diarization (mở nếu bật) | DIARIZE, DIARIZE_MAX_SPK |
| Shorts (gập) | SHORTS_COUNT, SHORTS_LEN, SHORTS_STYLE |
| Khử ồn & Nhắc Đăng ký (điều kiện) | DENOISE, SUBSCRIBE, SUBSCRIBE_TEXT |
| Đăng YouTube (điều kiện) | YOUTUBE_CLIENT_SECRETS, YOUTUBE_PRIVACY |

Nhận xét tổng: sau các đợt audit, help-text từng knob đã tốt (tooltip ⓘ chi
tiết, có số đo thật); vấn đề còn lại là **bố cục theo lịch sử code thay vì theo
người dùng**, vài knob đặt sai nhà, và thiếu các tiện nghi "nhìn phát biết
trạng thái" (máy này chạy được gì, mình đã đổi gì so với mặc định).

## 2. Nguyên tắc (nối tiếp bộ nguyên tắc panel per-job)

1. Tab Cấu hình = **chính sách của KÊNH** (đặt 1 lần, thi thoảng chỉnh); đặc thù
   từng video đã có panel ⚙️ per-job — tránh lặp khái niệm khác nhau giữa 2 nơi.
2. Knob phải trung thực: nhãn không được mâu thuẫn với default thật.
3. Nhóm theo NGƯỜI DÙNG nghĩ (dịch/đọc/xuất bản), không theo module code.
4. Thứ tự theo tần suất đụng tới; thứ đặt-1-lần-rồi-quên xuống dưới/gập lại.
5. Knob phụ thuộc phần cứng → auto-detect làm default, knob chỉ để override.

## 3. TINH GỌN (G1–G6)

- **G1 — AUTO_RETRY đặt sai nhà**: đang nằm trong "Nhận dạng thoại" nhưng là
  chính sách HÀNG ĐỢI (worker chạy lại job lỗi, mọi stage). → dời về nhóm
  "Hệ thống" mới (xem bố cục G13) hoặc chí ít sang nhóm riêng cạnh Shorts.
- **G2 — Giải tán 2 nhóm lửng**: "Diarization" (2 knob) nhập vào **Nhận dạng
  thoại** (bản chất là tầng transcript nâng cao); "Khử ồn & Nhắc Đăng ký" là
  nhóm tạp — DENOISE về **Nhận dạng thoại**, SUBSCRIBE + SUBSCRIBE_TEXT về
  **Thương hiệu/Xuất bản**. 9 nhóm → 7.
- **G3 — SUBTITLE_MODE + SUB_SPLIT rời nhóm Dịch**: chúng là tuỳ chọn RENDER
  (áp ở S8, có bản per-job trong panel 🎨) — dời sang **Thương hiệu/Xuất bản**.
  Nhóm "Dịch" còn thuần dịch thuật.
- **G4 — Knob phần cứng/kỹ thuật xuống Nâng cao**: OCR_WORKERS default nên
  auto theo `os.cpu_count()` (knob chỉ để override); GEMINI_MIN_INTERVAL là
  knob né rate-limit 99% người không đụng. Cả hai vào phần "Nâng cao" gập
  trong nhóm của mình (pattern panel per-job U15 — nhất quán).
- **G5 — ⭐ Chất lượng dịch lên mặt tiền, model-list xuống Nâng cao**: per-job
  đã có núm Tiết kiệm/Cân bằng/Tốt nhất; tab Cấu hình vẫn phơi 2 danh sách
  model → 2 nơi 2 khái niệm. Đồng bộ: mặt tiền nhóm Dịch là ⭐ (map
  QUALITY_MODELS đã có), CLAUDE_MODEL/GEMINI_MODEL thành Nâng cao cho ai muốn
  chỉ định đích danh (ưu tiên: model đích danh thắng ⭐ nếu cả hai được đặt —
  cần chốt ngữ nghĩa).
- **G6 — Sửa nhãn DỐI ở PROSODY/EMOTION**: nhãn đang ghi "Bật (khuyên dùng)"
  trong khi default THẬT là 0 (đã tắt sau audit giọng — prosody đo dính nhạc
  nền, emotion 4 tầng rate chồng nhau). Sửa nhãn trung thực + EMOTION thêm
  cảnh báo "nhãn chỉ sinh lúc dịch — video đã dịch muốn dùng phải dịch lại"
  (per-job đã có cảnh báo này, tab chung thì chưa).

## 4. NÂNG CẤP (G7–G12)

- **G7 — Card "Trạng thái máy" đầu tab** (read-only): GPU + VRAM, NVENC có
  không (đã dò được từ `ffmpeg.h264_args`), model viXTTS đã tải chưa, demucs/
  pyannote cài chưa, key nào đã đặt (server đã trả `*_key_set`), phiên bản
  ffmpeg. Trả lời ngay "máy này chạy được engine/tính năng gì" — hiện phải tự
  suy từ nhiều chỗ. Server thêm 1 endpoint `/api/health` rẻ (không nạp model).
- **G8 — Chấm "khác mặc định"**: row nào đang lệch default (server đã trả
  `defaults` trong /api/config) → chấm màu cạnh nhãn + nút ↺ per-row về mặc
  định; đầu tab đếm "Đang đổi N mục so với mặc định". Nhìn phát biết mình đã
  vọc gì — đỡ hẳn nạn "quên mất từng chỉnh cái gì" (đúng ca MAX_SPEEDUP=1.2
  user tự đổi mà audit phải đi truy).
- **G9 — Ô tìm kiếm**: ~50 control xứng đáng có ô lọc theo nhãn + nội dung
  tooltip; gõ "giọng" là mọi knob liên quan hiện, nhóm không khớp tự mờ đi.
- **G10 — Cảnh báo engine thiếu key ngay tại dropdown TTS_ENGINE** (đồng bộ
  U7 của panel per-job): chọn ElevenLabs mà chưa có key → dòng đỏ ngay dưới +
  option đánh dấu " — thiếu key". Server capability (`_engine_caps`) có sẵn.
- **G11 — Profile cấu hình có tên**: lưu toàn bộ non-secret keys thành profile
  ("Donghua kiếm hiệp", "Vlog tiếng Anh"...), 1 nút áp lại + export/import
  .json (KHÔNG bao giờ gồm secrets). User làm đa thể loại đổi cả bộ 1 phát —
  đúng nỗi đau app đa thể loại. Lưu `data/profiles/*.json` (không commit).
- **G12 — Nghe mẫu ngay tại chỗ**: nút 🔊 cạnh VOICE_FX phát file mẫu tĩnh
  trong `voice_samples/` (chuỗi FX của file mẫu GIỐNG HỆT render —
  core/voice_fx.py ghi rõ); nút 🔊 cạnh cặp giọng edge/viXTTS gọi
  /api/tts-preview sẵn có. Khỏi nhảy sang tab Nghe thử chỉ để chọn FX.

## 5. UI/UX — bố cục mới (G13–G15)

- **G13 — Thứ tự nhóm theo tần suất** (trên → dưới):
  1. *Card Trạng thái máy* (G7) + thanh: ô tìm kiếm (G9) · đếm khác-mặc-định
     (G8) · Profile (G11)
  2. **Lồng tiếng (TTS)** — nhóm đụng nhiều nhất
  3. **Dịch** (thuần dịch sau G3/G5)
  4. **Nhận dạng thoại** (+ diarization + khử ồn sau G2)
  5. **Xuất bản / Thương hiệu** (+ phụ đề + subscribe sau G2/G3)
  6. **Shorts** (gập)
  7. **Hệ thống**: AUTO_RETRY (G1) + Đăng YouTube + Telegram (dời 2 ô
     TELEGRAM_* từ nhóm Keys sang đây cho tròn ngữ cảnh "thông báo"? — token
     vẫn ở Keys, chỉ CHAT_ID đi; mời phản biện)
  8. **🔑 Khóa API & Token** — XUỐNG CUỐI, tự gập khi các key đang dùng đã đặt
     (lần đầu cài app thì vẫn mở). Lý do: đặt 1 lần rồi gần như không đụng,
     nhưng đang chiếm vị trí vàng trên cùng.
- **G14 — "Nâng cao" gập TRONG nhóm** (pattern panel per-job): mỗi nhóm knob
  thường ở trên, phần ít đụng (OCR_WORKERS, GEMINI_MIN_INTERVAL, model-list,
  PROSODY_TRANSFER, LOGO_SCALE/OPACITY...) sau `<details>` "Nâng cao" — cùng
  một ngôn ngữ UI với editor, học một lần dùng hai nơi.
- **G15 — Thanh Lưu dính đáy (sticky)**: nút 💾 Lưu + "N thay đổi chưa lưu"
  luôn hiện khi cuộn (tab dài ~3 màn hình, nút Lưu hiện tại trôi mất); cảnh
  báo khi rời tab/đóng trang còn thay đổi chưa lưu; sau khi lưu, toast liệt kê
  đúng các key đã đổi (server đã trả `saved`).

Nếu chốt hết: tab còn 7 nhóm + 1 card trạng thái; mặt tiền mỗi nhóm 4–6 knob
hay dùng, phần còn lại trong Nâng cao; Keys xuống cuối; có tìm kiếm, chấm
khác-default, profile, nghe mẫu tại chỗ.

## 6. Câu hỏi cho Codex / Gemini

1. Phản biện G1–G15: cái nào sai/thiếu? Knob nào tôi CHƯA liệt kê mà đáng
   thêm/bớt nhìn từ code (`config.py` còn env nào chưa lộ UI đáng lộ? vd
   WHISPER_DEVICE/WHISPER_COMPUTE đang phải sửa .env tay — có nên lên UI
   Nâng cao không, kèm rủi ro gì)?
2. **G5**: ngữ nghĩa khi cả ⭐ Chất lượng dịch lẫn model đích danh cùng được
   đặt — ai thắng, lưu .env thế nào cho không rối (⭐ có nên chỉ là setter cho
   2 key model như per-job, hay thành key riêng)?
3. **G7 health card**: đo gì là RẺ và đáng tin (không nạp model, không chậm
   lúc mở tab)? Thiết kế endpoint /api/health cụ thể.
4. **G11 profile**: schema file, xử lý key thiếu/ thừa khi import bản cũ,
   có nên kèm cả per-job default (pause_before_render...)?
5. **G13**: thứ tự nhóm và vụ đẩy 🔑 Keys xuống cuối — có phản đối không
   (first-run experience: lần đầu chưa có key thì sao)?
6. KHÔNG code. Ghi phân tích vào `DEXUAT_CAUHINH_TAB_CODEX.md` /
   `DEXUAT_CAUHINH_TAB_GEMINI.md` cạnh file này.
