# TỔNG HỢP 3 phía: Vá vùng chết OCR (dải crop quá dẹt)

> Tổng hợp DEXUAT_OCR_VUNGCHET.md (Claude) + _CODEX.md + _GEMINI.md.
> Mọi claim kiểm chứng được đã VERIFY ngày 2026-07-13 (bảng mục 2). User chốt mục 5.

## 1. Đồng thuận 3 bên

- **F-A là fix gốc**: đệm ĐEN phía TRÊN dải crop trước khi OCR, bằng
  `cv2.copyMakeBorder(..., BORDER_CONSTANT, value=0)`. Cả 3 cùng bác REPLICATE
  (lặp mép kéo thành sọc dọc → box chữ giả cho DB detector).
- **Bắt buộc vá tọa độ box** ngay trong `_frame_lines`: trừ `pad_top` Ở TỌA ĐỘ
  PIXEL trước khi chuẩn hoá (kẹp [0, H_gốc]); loại polygon nằm trọn trong vùng
  đệm; contract "nbox chuẩn hoá theo crop gốc" giữ nguyên → S8 che mờ không cần
  biết padding tồn tại. (Công thức Codex + sketch Gemini trùng nhau.)
- **KHÔNG tự động chạy lại** khi nghi thưa — chỉ cảnh báo; tự-retry tốn thời
  gian + có thể ghi đè output ngoài ý user.
- F-C (probe retry-loop) bỏ qua đợt này.

## 2. Bảng verify claim

| Claim | Verify |
|---|---|
| Codex: rapidocr 1.2.3 det dùng `limit_side_len=736, limit_type=min` (scale cạnh NGẮN lên 736, làm tròn /32) — giải thích trọn cả 2 thí nghiệm (phóng to giữ tỉ lệ = vô ích, thêm chiều cao = sống) | ✅ đọc tận config.yaml + `resize_image_type0` trong .venv — đúng từng dòng |
| Codex: pipeline đã **scale 2×** trước OCR → dải thật 2560×288, pixel tuyệt đối càng vô nghĩa, trigger phải theo TỈ LỆ | ✅ ocr_subs.py:192 `scale=iw*2:ih*2` |
| Codex: **bug lệch độ chính xác** — ffmpeg crop format `:.2f` nhưng map box dùng float 3 chữ số (0.743 cắt 0.74, map 0.743) | ✅ ocr_subs.py:190-191 vs :257-259 — bug thật, sửa cùng đợt |
| Codex: gate auto `segments >= max(3, duration/30)` (~2 câu/phút) — job hỏng này 31 ≥ 14 vẫn LỌT → ngưỡng mật độ cố định không cứu được | ✅ s3_transcript.py:136 |
| Codex: 76/848 frame dương tính (9%) | ✅ đếm lại khớp |
| Codex: ranh giới đo được ~7.1:1 sống / ~8:1 chết → target 5:1 có headroom | ✅ khớp bảng đo (0.75=7.1:1 ✓, 0.78=8.05:1 ✗) |
| Gemini: copyMakeBorder + đệm trên + đen, sketch vá box (trừ pad trước normalize, clamp) | ✅ đúng, trùng Codex |
| Gemini: trần F-B = **0.78** ("dải tối thiểu 22%") | ❌ BÁC — 0.78 tại 720p = 1280×159 ĐO ĐƯỢC LÀ CHẾT (bảng mục 2 đề xuất gốc). Lấy đúng điểm chết làm "đai an toàn" là phản tác dụng |
| Gemini: giải thích 0.85 bằng "nét chữ bị cắt đỉnh/đáy" | ❌ sai chi tiết — sub băng ~93% (glyph ≈ y655–695) nằm TRỌN trong dải 0.85 (612–720), không cắt nét nào; "chữ chiếm 80-90% chiều cao dải" cũng sai (~28%). Nhận định của Codex đứng vững: đó là false/partial success, detector không đơn điệu theo chiều cao — "có output" ≠ "đúng" |
| Gemini: ngưỡng F-D = 0.2 câu/phút | ❌ vô dụng — job hỏng này 4.4 câu/phút, cao gấp 22 lần ngưỡng đó mà vẫn mất già nửa sub |
| Gemini: sàn tuyệt đối `max(240, W/5)` | ⚠ vế 240px không cần (ratio đã phủ; còn làm pad oan dải video dọc vốn không dẹt — đúng ưu điểm trigger-theo-ratio mà Codex chỉ ra) |

## 3. Thiết kế CHỐT (sau phản biện)

**O-1 — F-A + vá box + fix độ chính xác (một đợt code):**
- Helper `_pad_for_detection(img) -> (padded, pad_top)`: nếu `w/h > 5.0` →
  đệm đen phía TRÊN tới `h_target = ceil(w / 5.0)`. Trigger THEO TỈ LỆ, không
  sàn pixel tuyệt đối (bác vế 240px). Video dọc/dải cao: không kích hoạt.
- `_frame_lines` nhận `pad_top` + `h_orig`: trừ offset ở pixel → kẹp
  [0, h_orig] → chuẩn hoá theo h_orig; polygon có TÂM trong vùng đệm → loại.
- Sửa lệch `:.2f`: dùng CÙNG giá trị effective cho cả ffmpeg lẫn map box
  (round crop_top về 2 chữ số TRƯỚC, dùng chung một biến).
- GIỮ trần auto-crop 0.80 (hoãn F-B — Codex thuyết phục: F-A thêm nền giả
  không thêm chữ thật; F-B mở rộng pixel THẬT dễ kéo menu/biển hiệu vào thoại,
  đúng thứ auto-crop sinh ra để né; đo F-A độc lập đã, corpus còn thiếu mới
  tính F-B dạng thích nghi theo aspect).

**O-2 — F-D dạng "kiểm tra nhất quán" (không ngưỡng mật độ):**
- Probe đã thấy chữ ở N frame (kèm timestamp) → chạy lại ĐÚNG biến đổi
  production (crop + pad) trên chính các frame đó; probe thấy mà production
  mù ở phần lớn frame → cảnh báo TO trong run.log + state ("nghi lỗi vùng
  quét OCR — xem lại OCR_CROP_TOP hoặc chuyển Whisper"). Không auto-retry.
- Telemetry vào run.log: positive_frames/total, câu/phút, khoảng trống dài
  nhất (làm dữ liệu cho vòng "auto thông minh hơn" sau).
- Chuỗi cảnh báo ASCII-an-toàn (bài học đợt T#1).

**Unit/verify (chưng cất từ checklist Codex + fixture Gemini):**
- ratio 4.9 → KHÔNG pad, output byte-for-byte như cũ; 5.1/8/12 → pad đúng.
- 2 frame thật ở crop 0.78/0.80 (đang rỗng) → có pad phải ra ĐÚNG TEXT; box
  sau transform khớp box full-frame (dung sai vài px) — assert text, không
  chỉ `result != []`.
- Che mờ S8: dựng thử 1 frame auto-cover, vùng che trùng glyph.
- Video dọc: không pad oan.
- Integration: CLONE job 64fd4e (job thật không đụng), chạy MỘT MÌNH bước OCR
  (script gọi ocr_subs.extract — không cần credit API): so positive-frame
  ratio, số câu, khoảng trống dài nhất, 3 câu user chụp (好嘞/谢了老板/我叫姬弃仁)
  PHẢI xuất hiện, lỗi chữ kiểu 东四 giảm. Con số 31→100+ là kỳ vọng, pass/fail
  dựa trên các câu known-missing + không tăng nhiễu.

## 4. Ghi nhận thêm ngoài phạm vi (không làm đợt này)

- Probe 640px có rủi ro false-negative riêng (chữ nhỏ bị downscale) → two-pass
  960px khi probe chỉ 1–3 hit (Codex) — vòng sau.
- Coverage tăng sẽ stress tầng sau (dedup jitter, blacklist 15%, chuỗi delogo
  S8 dài hơn) — thêm lý do hoãn F-B, theo dõi qua job thật.
- Chế độ lai OCR + Whisper lấp khoảng không-sub — vòng riêng như đã hẹn.

## 5. User chốt theo số

1. **O-1** (F-A pad theo ratio 5:1 + vá box + fix lệch :.2f; GIỮ trần 0.80,
   hoãn F-B) — OK?
2. **O-2** (cảnh báo nhất quán probe-vs-production + telemetry, không
   auto-retry) — OK?
3. Verify trên **clone** job 64fd4e chạy riêng bước OCR (không tốn credit API);
   job thật của bạn để nguyên, bạn tự bấm chạy lại sau khi ưng kết quả — OK?
