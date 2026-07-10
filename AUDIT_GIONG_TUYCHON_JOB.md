# Tinh chỉnh panel "⚙️ Tùy chọn video này" — đề xuất để thảo luận 3 phía

> Claude soạn 2026-07-10 theo yêu cầu user: rà từng tùy chọn per-job trong editor
> (webui/static/index.html — `ED_OV_FIELDS` dòng ~2440, `edSettingsPanel`;
> server whitelist `_OV_*` webui/server.py ~1272), đề xuất GIỮ / SỬA / CHUYỂN /
> BỎ / THÊM. **Chưa code — tài liệu thảo luận.** Codex + Gemini phản biện theo
> mục 6, ghi vào `AUDIT_GIONG_TUYCHON_CODEX.md` / `AUDIT_GIONG_TUYCHON_GEMINI.md`.
> User sẽ chốt theo số U1–U14.

## 1. Hiện trạng (23 mục trên panel)

| # | Knob | Nhóm (độ sâu chạy lại) | Nguồn |
|---|------|------------------------|-------|
| 1 | Âm nền gốc (dB) | pseudo — mix | `job.bed_gain_db` (không phải env) |
| 2 | 🐢 STRETCH_SHORT | mix | env override |
| 3 | 🎵 KEEP_BGM | mix | env |
| 4 | Giọng tất cả câu + "Đổi toàn bộ" | pseudo — action | sửa per-segment hàng loạt |
| 5 | Xử lý giọng (VOICE_FX) | pseudo — render | `job.render.fx` (áp lúc RENDER) |
| 6 | ⏩ MAX_SPEEDUP | tts (từ đợt B) | env |
| 7 | 🗣 TTS_ENGINE | tts | env |
| 8 | 🔊 TTS_SINGLE_VOICE | tts | env |
| 9 | 👨 TTS_VOICE | tts | env |
| 10 | 👩 TTS_VOICE_NU (ẩn khi 1 giọng) | tts | env |
| 11 | 🎼 PROSODY | tts | env |
| 12 | 🎭 EMOTION | tts | env |
| 13 | 📈 PROSODY_TRANSFER | tts | env |
| 14 | 🌐 TRANSLATE_PROVIDER | translate | env |
| 15 | Model Claude | translate | env |
| 16 | Model Gemini | translate | env |
| 17 | Kiểu nội dung | translate | env |
| 18 | Ngôn ngữ lồng tiếng | translate | env |
| 19 | Phong cách dịch riêng | translate | env |
| 20 | 📝 TRANSCRIPT_SOURCE | transcript | env |
| 21 | Model whisper | transcript | env |
| 22 | Tốc độ OCR (OCR_FPS) | transcript | env |
| 23 | Vùng quét phụ đề (OCR_CROP_TOP) | transcript | env |

## 2. Nguyên tắc đánh giá (rút từ audit giọng)

1. **Per-job chỉ giữ thứ THAY ĐỔI THEO VIDEO** (nhạc to/nhỏ, có hardsub không,
   video dọc/ngang, ngôn ngữ đích). Quyết định mang tính "chính sách chung"
   (model nào, thử nghiệm nào) để ở Cấu hình toàn cục.
2. **Knob phải trung thực**: đổi là có tác dụng đúng như nhãn nói, đúng chi phí
   nhãn nhóm hứa. Knob no-op/nửa tác dụng phá lòng tin cả panel.
3. **Ít knob, nhiều preset** — vòng xoáy chồng knob là nguồn gốc vụ audit này.
4. **Chi phí phải hiện TRƯỚC khi bấm** (đọc lại bao nhiêu câu, dịch lại mất gì).
5. Knob không áp dụng trong ngữ cảnh hiện tại → **ẩn/disable kèm lý do**, đừng
   để user chỉnh rồi không thấy gì đổi.

## 3. Đề xuất GIỮ NGUYÊN (đúng chỗ, đúng vai)

- **Âm nền gốc (bed_gain_db)** — nhạc mỗi video mỗi khác, chỉnh per-video là
  chuẩn. Chỉ đổi NHÃN thành "Âm nền gốc (dB) — đè núm chung DUCK_GAIN_DB" cho
  thống nhất tên với ô mới ở Cấu hình (2 tên 1 nghĩa dễ loạn).
- **KEEP_BGM** — video nhạc quan trọng thì demucs, video thoại chay thì flat.
- **STRETCH_SHORT** — rẻ (chỉ trộn lại), đúng loại thử-nghiệm-theo-video.
- **TTS_ENGINE** — video monetize dùng paid, video test dùng edge. (Kèm U7.)
- **TARGET_LANG** — đa ngôn ngữ theo video là tính năng #16, dịch lại là đúng giá.
- **TRANSCRIPT_SOURCE + OCR_CROP_TOP** — đặc thù từng video (hardsub? video dọc?).
- **CONTENT_STYLE, TRANSLATE_STYLE_EXTRA, TRANSLATE_PROVIDER** — văn phong/nhà
  cung cấp theo video hợp lý (phim cổ trang vs vlog).
- **"Giọng tất cả câu" + Đổi toàn bộ** — action tiện, giữ.

## 4. Đề xuất SỬA / CHUYỂN / BỎ / THÊM (đánh số để chốt)

### Sửa / nâng cấp
- **U1 — MAX_SPEEDUP: hiện chi phí động.** Từ đợt B knob này nằm trong giọng đã
  đọc (sig `:f`) → đổi là re-TTS. Trước khi Áp dụng, đếm sig lệch và hiện
  "sẽ đọc lại N/M câu (~X phút)" thay vì chỉ dòng cảnh báo chung của nhóm.
  (Sửa luôn: comment `// nhóm TRỘN` trong ED_OV_FIELDS đặt sai chỗ — MAX_SPEEDUP
  đã chuyển nhóm tts nhưng vẫn nằm trên đầu danh sách mix.)
- **U2 — GỘP 3 knob giọng thành 1** (đề xuất đáng bàn nhất): `TTS_SINGLE_VOICE`
  + `TTS_VOICE` + `TTS_VOICE_NU` → một dropdown "Giọng đọc": `1 giọng — NamMinh`
  / `1 giọng — HoaiMy` / `2 giọng — Nam+Nữ (tự gán nhãn)`. Hết cảnh knob nữ ẩn
  hiện, hết tổ hợp vô nghĩa (1 giọng + chỉnh giọng nữ). Server map ngược về 3 env
  cũ — không đổi pipeline.
- **U3 — EMOTION: disable-kèm-lý-do khi transcript chưa có nhãn.** Audit xác
  nhận: nhãn cảm xúc chỉ SINH lúc dịch; job dịch lúc EMOTION=0 mà bật per-job
  (nhóm tts, không dịch lại) = **no-op tuyệt đối**. Đề xuất: transcript không có
  nhãn nào → disable + tooltip "video này dịch khi chưa bật nhãn cảm xúc — muốn
  dùng phải Dịch lại (⚙️ nhóm Dịch)". (Phương án thay thế: chuyển depth sang
  translate — trung thực nhưng đắt; mời phản biện.)
- **U4 — PROSODY: ẩn khi engine hiệu lực = viXTTS/paid** (chỉ áp edge —
  `prosody.py` gate). Thêm chú thích "đo trên audio lẫn nhạc nền" cho tới khi
  làm prosody-trên-vocals.wav (V14 đã giữ file làm nguyên liệu).
- **U5 — Preset đầu panel**: hàng đầu nhóm Trộn: 🎯 Khớp môi chặt / 🌿 Tự nhiên
  (đặt MAX_SPEEDUP + STRETCH_SHORT), đồng bộ với preset tab Cấu hình.
- **U6 — Nút "↺ Về cấu hình chung"** xoá mọi override 1 phát (hiện phải chọn
  "— theo cấu hình chung —" từng ô một).
- **U7 — Engine trả phí thiếu API key → disable option + link tab 🔑** (hiện
  chọn xong chạy mới fail).

### Chuyển chỗ
- **U8 — VOICE_FX rời nhóm "Giọng đọc".** Nó là `render.fx` áp lúc RENDER
  (equalizer/compressor trên audio đã trộn) — nằm cạnh engine giọng làm user
  tưởng đổi là đọc lại. Chuyển xuống panel 🎨 (chỗ phụ đề/khung) hoặc nhóm mới
  "Render". Nhân tiện trả nợ bug audit #12c: `render.fx` đã lưu đè CHẾT knob
  VOICE_FX toàn cục vĩnh viễn cho job đó (`s8_render.py` `r.get("fx",
  config.VOICE_FX)` + editor luôn gửi fx) — cần giá trị "theo cấu hình chung"
  thật sự.

### Bỏ khỏi per-job (vẫn còn ở Cấu hình toàn cục)
- **U9 — PROSODY_TRANSFER**: thử nghiệm, nguy cơ bẻ thanh điệu tiếng Việt (audit
  #10), không ai chỉnh theo từng video. Global-only là đủ.
- **U10 — Model Claude + Model Gemini**: chọn model là chính sách chi phí toàn
  cục; per-job giữ TRANSLATE_PROVIDER là đủ linh hoạt. 2 knob × 7 option chiếm
  chỗ cho thứ gần như không bao giờ đổi theo video.
- **U11 — OCR_FPS + Model whisper**: gần như không chỉnh theo video (auto-gate
  OCR đã tự lo; whisper model theo máy chứ không theo video). TRANSCRIPT_SOURCE
  + OCR_CROP_TOP đủ dùng per-job.

### Thêm mới
- **U12 — Dry-run tác động trước khi Áp dụng**: dialog xác nhận hiện đúng:
  stage sẽ chạy lại (từ nhóm sâu nhất) + số câu đọc lại (đếm sig) + ước phút +
  ước phí API nếu dịch lại. Biến nhãn nhóm từ lời hứa thành con số.
- **U13 — KHÔNG thêm DUCK_GAIN_DB per-job** (đã có bed_gain_db cùng nghĩa) —
  ghi ở đây để khỏi ai đề xuất lại.
- **U14 — Nghe thử in-timeline 10s** trong nhóm Trộn: trộn nhanh 10s quanh câu
  đang chọn với override đang đặt (chưa lưu) — đúng phần còn treo của V11.

### Bố cục
- **U15 — Chia "Thường dùng / Nâng cao"**: mặc định chỉ hiện ~7 knob thường
  dùng (Âm nền, KEEP_BGM, preset khớp thoại, Engine, Giọng (U2), Kiểu nội dung,
  Nguồn transcript); phần còn lại sau `<details>` "Nâng cao". Panel hiện tại 23
  mục là quá tải cho luồng "sửa nhanh 1 video".

## 5. Nếu chốt hết: panel còn lại

**Thường dùng (7):** Âm nền gốc (dB) · Nhạc/SFX gốc · Preset khớp thoại (+2 núm
chi tiết trong Nâng cao) · Engine giọng · Giọng đọc (gộp U2) · Kiểu nội dung ·
Nguồn transcript.
**Nâng cao:** MAX_SPEEDUP · STRETCH_SHORT · PROSODY (chỉ edge) · EMOTION (disable
có lý do) · Nhà cung cấp dịch · Ngôn ngữ lồng tiếng · Phong cách dịch riêng ·
Vùng quét phụ đề · Giọng tất cả câu/Đổi toàn bộ.
**Rời đi:** VOICE_FX → panel render (U8); PROSODY_TRANSFER, 2 Model dịch,
OCR_FPS, Model whisper → chỉ còn ở Cấu hình toàn cục.
Từ 23 mục → 7 thường dùng + 9 nâng cao.

## 6. Câu hỏi cho Codex / Gemini

1. Phản biện từng mục U1–U15: cái nào sai? Đặc biệt **U2** (gộp 3 knob giọng)
   — có phá case nào không (casting series, đa ngôn ngữ đích, paid engine
   voice_pair)? và **U3** (disable vs chuyển depth translate) — chọn phương án
   nào, vì sao?
2. Nhìn từ code pipeline: có knob nào ĐANG THIẾU ở per-job mà đáng thêm không
   (vd DENOISE? SUBTITLE_MODE per-job đã có ở panel 🎨 chưa?)? Có knob nào tôi
   xếp "giữ" mà thực ra cũng nửa tác dụng như MAX_SPEEDUP từng bị?
3. U12 (dry-run đếm sig): thiết kế endpoint thế nào cho rẻ — tính sig lệch
   không cần load model? (gợi ý: `_voice_sig` thuần string, chỉ cần transcript
   + env override giả lập — nhưng config là module global, cần cách áp override
   tạm không đụng tiến trình server.)
4. Bố cục U15: danh sách "thường dùng" của tôi có đúng tần suất dùng thật
   không? Đề xuất bố cục khác nếu có.
5. KHÔNG code. Ghi phân tích vào `AUDIT_GIONG_TUYCHON_CODEX.md` /
   `AUDIT_GIONG_TUYCHON_GEMINI.md` cạnh file này.
