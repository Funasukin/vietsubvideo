# Phản biện vá vùng chết OCR — Codex

> Kiểm tra trên commit `66736a2`, ngày 2026-07-13. Đã đọc `CLAUDE.md`, đầu
> `CHANGELOG.md`, `core/ocr_subs.py`, consumer box ở S8 và đúng source package
> `rapidocr-onnxruntime 1.2.3` đang cài. Chỉ phân tích; không sửa code và không
> đụng job thật `20260713_005950_64fd4e`.

## 0. Kết luận

Tôi đồng ý mạnh với **F-A**, nhưng đề xuất triển khai nó độc lập trước:

- điều kiện và target theo **aspect ratio**, không theo số pixel tuyệt đối;
- khi `w / h > 5`, đệm đen **phía trên** tới `w / h <= 5`;
- box phải được đổi từ hệ tọa độ ảnh padded về crop gốc trước khi normalize;
- giữ trần auto-crop 0.80 ở đợt đầu để đo đúng tác động của F-A.

Tôi **chưa đồng ý làm F-B 0.72 cùng lúc**. F-A thêm context giả không chứa chữ;
F-B lại mở rộng vùng pixel thật lên phía trên, có thể kéo menu/biển hiệu trở lại,
đúng loại nhiễu mà auto-crop hiện tại đã được thiết kế để tránh. Nếu F-A vẫn
không đủ trên corpus, F-B nên là ceiling thích nghi theo aspect ratio, không là
một số 0.72 cho mọi video.

F-C không cần retry trong đợt này. F-D nên là cảnh báo dựa trên sự mâu thuẫn
**probe thấy sub nhưng production gần như không thấy**, không dùng ngưỡng cố
định câu/phút.

## 1. Cơ chế vùng chết đã được xác nhận rõ hơn

Package trên máy là `rapidocr-onnxruntime 1.2.3`. Detector của phiên bản này
dùng:

```text
limit_side_len = 736
limit_type = "min"
```

Trong `DetResizeForTest.resize_image_type0`, nếu cạnh ngắn nhỏ hơn 736, nó phóng
cạnh ngắn lên 736 và giữ tỷ lệ; hai kích thước sau đó được làm tròn về bội 32.
Đây là source thật trong:

```text
.venv/Lib/site-packages/rapidocr_onnxruntime/ch_ppocr_v3_det/utils.py:144-187
```

Điều này giải thích hoàn chỉnh hai thí nghiệm:

- phóng ảnh 1.5×/2× nhưng giữ tỷ lệ gần như không đổi tensor hình học cuối của
  detector, nên vẫn rỗng;
- padding làm cạnh ngắn lớn hơn tương đối, giảm aspect ratio cực đoan và thay
  tensor detector, nên text sống lại.

Ví dụ production thực tế còn scale 2× trong FFmpeg. Crop 0.80 của video 1280×720
được ghi thành khoảng 2560×288, vẫn là 8.9:1. Preprocess sẽ đưa nó về khoảng
736×6.5k. Nếu pad tới 5:1, ảnh thành 2560×512 và tensor khoảng 736×3.7k. Không
chỉ thêm context, nó còn giảm mạnh chiều ngang tensor detector trong ca này.

RapidOCR là wrapper/model chuyển từ PaddleOCR và hành vi resize phụ thuộc phiên
bản; source upstream ở [RapidOCR GitHub](https://github.com/RapidAI/RapidOCR).
Vì vậy unit test phải khóa đúng package đang dùng, không chỉ test helper padding.

## 2. Trả lời câu hỏi 1: ngưỡng và hướng padding

### Dùng tỷ lệ, không dùng `>=200px`

Pixel tuyệt đối không bền vì:

- pipeline đã scale crop 2× trước OCR;
- 720p, 1080p, 4K và video dọc có kích thước rất khác;
- chính detector còn resize cạnh ngắn về 736;
- cùng aspect ratio mới tái hiện cùng hình học cực đoan.

Đề xuất công thức:

```text
MAX_OCR_ASPECT = 5.0
target_h = ceil(w / MAX_OCR_ASPECT)
pad_top = max(0, target_h - h)
```

Ngưỡng 5.0 là bảo thủ nhưng hợp dữ liệu: 7.1 còn chạy, khoảng 8.0 bắt đầu chết;
target 5 tạo headroom thay vì đứng sát biên chưa được khảo sát. `h < 25% w`
tương đương `w/h > 4`, không tương đương 5:1; proposal nên tránh ghi hai điều
kiện như thể giống nhau.

Có thể benchmark thêm target 5/6/7, nhưng bản production đầu nên chọn 5 vì chi
phí inference không chắc tăng: với `limit_type=min`, giảm tensor quá rộng có thể
còn nhanh hơn.

### Đệm phía trên

Chọn **top padding**, không chia đều:

- đây là biến thể đã được đo thật và thành công;
- subtitle vẫn nằm ở vùng thấp quen thuộc của ảnh padded;
- bottom padding sẽ đẩy subtitle lên cao tương đối;
- symmetric padding đổi vị trí subtitle sang giữa ảnh nhưng chưa có bằng chứng.

Top padding cũng làm phép đổi box có một offset duy nhất. Đây không phải lý do
chính, nhưng giảm bề mặt lỗi.

## 3. Trả lời câu hỏi 2: đen hay replicate

Chọn **đen cố định** ở đợt đầu.

Lý do:

- thí nghiệm đen đã thành công trên đúng frame lỗi;
- vùng đen đồng nhất không đưa thêm cạnh/chữ giả;
- replicate hàng pixel trên cùng có thể kéo dài cạnh vật thể thành các sọc dọc,
  tạo feature giả cho DB detector;
- padding không chạm/ghi đè content nên chữ đen viền trắng vẫn còn nguyên trong
  crop thật.

Màu đen lớn có thể ảnh hưởng normalization hoặc tạo cảm giác letterbox, nhưng
đây là input detector chứ không phải output video; bằng chứng thực nghiệm đang
ủng hộ nó. Unit corpus nên có chữ trắng viền đen, chữ đen viền trắng và nền tối.

Không tuyên bố F-A “chữa mọi crop, không mất chữ”: nếu crop_top đã cắt mất một
phần glyph thật thì padding không thể tái tạo pixel bị mất. F-A chỉ chữa ca
content còn đủ nhưng canvas quá dẹt.

## 4. Biến đổi box bắt buộc

Hiện `_frame_lines()` normalize box bằng kích thước chính ndarray nó nhận. Nếu
truyền ảnh padded trực tiếp, `nbox.y` sẽ nằm trong hệ `H + P`, trong khi
`close_group()` vẫn map như thể nó nằm trong crop cao `H`. Kết quả che mờ S8 sẽ
lệch theo chiều dọc.

Với crop gốc kích thước `(H, W)`, top pad `P`, polygon detector `(x, y_pad)`:

```text
x_crop = clamp(x, 0, W) / W
y_crop = clamp(y_pad - P, 0, H) / H
```

Phải trừ offset ở **tọa độ pixel trước khi normalize**. Sau đó output của
`_frame_lines` vẫn có contract “box chuẩn hóa theo crop gốc”, nên mapping hiện
tại:

```text
y_full = crop_top + y_crop * crop_h
```

được giữ nguyên và S8 không cần biết padding tồn tại.

Thiết kế sạch là helper OCR nhận một `content_rect=(0, P, W, H)` hoặc helper
`_pad_for_detection()` trả `(padded, pad_top, orig_h, orig_w)`. Reject polygon
có tâm nằm hoàn toàn trong padding; polygon giao content thì clip về content.

Không nên sửa box sau khi đã gộp segment vì lúc đó mất polygon/frame origin và
dễ trộn box padded với box không padded.

### Sai số crop hiện có cần sửa cùng vùng tọa độ

FFmpeg filter đang format `crop_top` và `crop_h` bằng `:.2f`, nhưng mapping box
phía sau dùng float gốc có thể có 3 chữ số (`ocr_subs.py:185-191, 257-259`). Với
crop auto như 0.743, pixel được cắt theo 0.74 nhưng box được map theo 0.743.

Nên dùng cùng một giá trị effective cho cả FFmpeg và mapping, hoặc truyền đủ độ
chính xác vào filter. Ca 0.80 không lộ lỗi này, nhưng test box padding có thể bị
nhiễu vài pixel nếu không xử lý.

## 5. Trả lời câu hỏi 3: F-B theo phần trăm hay pixel

Trong đợt đầu: **không làm F-B**, giữ auto ceiling 0.80 và đo F-A độc lập.

Lý do:

- auto chọn dải hẹp để loại chữ menu/biển hiệu;
- hạ 0.80 → 0.72 thêm 8% chiều cao pixel thật của frame 16:9;
- OCR có thể bắt thêm CJK không phải subtitle và ghép vào thoại;
- F-A đã giải quyết aspect ratio mà không thêm content thật.

Nếu corpus cho thấy cần F-B, dùng aspect ratio nguồn:

```text
crop_aspect = source_width / (source_height * (1 - crop_top))
crop_top_max = 1 - source_aspect / SAFE_UNPADDED_ASPECT
```

Sau đó clamp trong miền product. Với `SAFE_UNPADDED_ASPECT` khoảng 6–6.5,
video 16:9 cho ceiling gần 0.70–0.73, còn video dọc vẫn có thể giữ 0.80 vì crop
của nó không dẹt. Đây là lý do phần trăm cố định 0.72 không tổng quát; pixel
`h-200` cũng không tổng quát qua resolution/scale.

F-B có thể trở thành fallback cho video cụ thể sau self-check, không nhất thiết
là default toàn app.

## 6. Trả lời câu hỏi 4: vì sao crop 0.85 lại trả chữ sai?

Không nên diễn giải 0.85 là detector “sống lại”. Nó trả **một detection chất
lượng thấp và recognition sai**, tức một false/partial success.

Pipeline detector không bảo đảm độ chính xác đơn điệu theo chiều cao crop:

- mỗi kích thước được scale theo cạnh ngắn và làm tròn bội 32;
- aspect/position của text trong tensor thay đổi;
- DB threshold, contour và unclip có thể tạo hoặc mất polygon đột ngột;
- polygon méo/thiếu context vẫn được recognizer đọc thành chữ gần giống với
  confidence khá cao.

Ở 0.85, tensor còn cực rộng hơn 0.80; một box tình cờ vượt threshold nhưng đọc
sai không phủ định cơ chế aspect ratio. Nó là bằng chứng rằng “có output” không
đủ; verify phải kiểm cả text/box/coverage.

Đây là suy luận từ preprocessing và kết quả đo, không phải khẳng định chính xác
activation nào trong model gây bước nhảy.

## 7. Trả lời câu hỏi 5: F-D không dùng câu/phút cố định

Job thật đã chứng minh ngưỡng đó không đủ:

```text
duration       7.06 phút
segments       31 = 4.4 câu/phút
raw frames     848
positive frame 76 = 9%
gap > 6s       14
max gap        74.8s
```

Gate hiện tại chấp nhận OCR nếu `segments >= duration / 30`, khoảng 2 câu/phút.
Job này vượt hơn hai lần gate mà vẫn mất rất nhiều sub. Một threshold 2
câu/phút sẽ không cảnh báo chính ca cần bắt.

F-D tốt hơn là **consistency diagnostic**:

1. probe lưu số frame thấy band subtitle, box/confidence và timestamp;
2. chạy chính crop + padding trên các probe frame đó;
3. nếu full-frame probe thấy chữ band nhưng production transform không thấy ở
   phần lớn cùng timestamp, cảnh báo lỗi crop/detector ngay;
4. sau full extract, log `positive_frames / total_frames`, segment/minute và
   longest gap như telemetry, nhưng không dùng một số đơn lẻ để kết luận.

Đây gần F-C nhưng chỉ self-check/cảnh báo, không tự đổi crop và không rerun full
OCR. Chi phí thêm khoảng số frame probe, nhỏ hơn nhiều so với quét 848 frame.

MV/cảnh hành động ít thoại sẽ không báo giả nếu probe cũng không thấy subtitle
band ổn định. Với mode OCR ép tay không có probe, chỉ log warning mức thấp dựa
trên nhiều tín hiệu; không tự retry.

Không tự chạy lại crop 0.65 trong đợt này: full OCR tốn thời gian, có thể kéo
nhiễu thật vào transcript và làm overwrite output mà user không biết.

## 8. Trả lời câu hỏi 6 và rủi ro còn thiếu

### Probe 640px

Probe toàn frame có aspect bình thường nên không gặp chính vùng chết dải dẹt.
Nhưng 640px có rủi ro khác: glyph subtitle nhỏ bị downscale quá mức, tạo false
negative và làm mode auto chuyển Whisper. Ca này probe đã thấy sub, nên không
chặn F-A.

Vòng sau có thể dùng two-pass: nếu probe 640 chỉ có 1–3 hit, thử lại vài frame ở
960px trước khi kết luận không có hardsub. Không cần gộp vào fix này.

### Video dọc

Video 720×1280 với crop khoảng 0.65 tạo dải aspect thấp; F-A tự không kích hoạt,
đúng mong muốn. Đây là ưu điểm của ratio trigger so với `height >= 200`.

### Hiệu năng và RAM

Padding/vstack không hoàn toàn “miễn phí”: nó cấp ndarray mới cho mỗi frame và
tăng vùng ảnh. Tuy nhiên với detector `limit_type=min`, việc giảm aspect cực
đoan có thể giảm đáng kể tensor width và inference time. Verify phải đo:

- OCR wall time/frame;
- peak RSS của `OCR_WORKERS`;
- số pixel tensor sau DetResize;
- coverage/confidence.

`cv2.copyMakeBorder` phù hợp hơn ghép thủ công nếu code, nhưng hành vi cần test
giống hệt padding đen đã đo.

### 4K và scale 2×

Pipeline luôn scale crop 2×, kể cả nguồn đã lớn. Với 4K, frame OCR có thể rất
lớn; padding theo ratio vẫn đúng về hình học nhưng RAM/compute có thể cao. Đây là
rủi ro hiện hữu độc lập. Không đổi scale policy trong đợt fix, nhưng thêm case
1080p/4K vào benchmark.

### Cache/output cũ

Fix chỉ có hiệu lực khi S3 thực sự chạy lại. `transcript_zh.json` tồn tại thì S3
skip. UI/reset phải xóa `ocr_raw.json`, `sub_boxes.json` và transcript downstream
đúng như flow hiện có; không được để box cũ đi với transcript mới.

### Tăng coverage làm lộ bug tầng sau

Khi OCR bắt được nhiều frame hơn:

- `SequenceMatcher` có thể gặp nhiều jitter hơn;
- watermark blacklist 15% có thể loại text đứng lâu;
- nhiều CJK trên menu có thể được chọn nếu crop mở rộng;
- `sub_boxes.json` dài hơn làm chuỗi delogo S8 lớn hơn.

Đó là thêm lý do không làm F-B mở rộng content cùng lúc với F-A.

## 9. Verify đề xuất

### Unit/helper

- ratio 4.9: không pad, output text/box byte-for-byte như trước;
- ratio 5.1/8/12: pad đúng target, không âm/overflow;
- top pad offset transform về box crop gốc;
- polygon nằm trong padding bị loại;
- box luôn trong `[0,1]`, `x0<x1`, `y0<y1`;
- crop float không tròn lệch giữa FFmpeg và mapping;
- video dọc không pad oan.

### Fixture OCR

- hai frame thật ở crop 0.78/0.80/0.85;
- thêm frame chữ đen viền trắng, nền tối, hai dòng subtitle;
- assert text kỳ vọng, không chỉ `result != []`;
- compare box với box full-frame trong tolerance pixel;
- dựng một frame auto-cover bằng S8 và kiểm tra vùng che phủ đúng glyph.

### Integration

Sau khi user chốt code, clone job theo quy ước và reset từ transcribing; không
đụng job thật. So trước/sau:

- positive-frame ratio;
- segment count và longest gap;
- CER trên tập câu user đã cung cấp;
- box overlay;
- runtime/RSS;
- lượng menu/watermark false positive.

Kỳ vọng 31→100+ là giả thuyết tốt nhưng không dùng làm pass/fail duy nhất. Pass
phải dựa trên các câu known-missing, coverage tăng, text đúng hơn và không tăng
nhiễu rõ rệt.

## 10. Quyết định đề xuất

**Làm F-A + F-D cảnh báo consistency. Hoãn F-B và F-C retry.**

F-A: top black padding theo ratio, target tối đa 5:1, box transform về crop gốc.
F-D: probe-versus-production self-check và telemetry nhiều tín hiệu, không auto
retry. Chỉ thêm F-B aspect-adaptive nếu corpus sau F-A còn chứng minh cần mở rộng
pixel thật.
