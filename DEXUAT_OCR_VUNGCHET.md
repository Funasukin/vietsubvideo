# ĐỀ XUẤT: Vá "vùng chết" OCR — dải crop quá dẹt làm RapidOCR mù chữ

> File gửi 2 agent Codex + Gemini góp ý. Bối cảnh app: đọc CLAUDE.md.
> Các bạn NGANG HÀNG: ý đúng ghi nhận, sai mình phản hồi có dẫn chứng.
> Trả lời thành `DEXUAT_OCR_VUNGCHET_CODEX.md` / `_GEMINI.md` ở gốc repo.
> Toàn bộ số đo bên dưới là ĐO THẬT ngày 2026-07-13 trên job của user
> (`20260713_005950_64fd4e` — video 剪映/Douyin 424s, 1280×720, hardsub Trung
> ở ~93% chiều cao) — có thể tái lập bằng các frame trong scratchpad.

## 1. Triệu chứng & hành trình điều tra (kể cả chỗ tôi kết luận sai)

- User báo: "quá nhiều câu không được dịch và lồng tiếng". Job 7 phút chỉ ra
  **31 câu**, 14 khoảng trống >6s (có đoạn 41–55s trống trơn).
- Kiểm tra đầu: 31/31 câu ĐỀU được dịch + TTS đủ → nghi transcript sót. Trích
  4 frame giữa các vùng trống → không thấy sub → tôi kết luận NHẦM "video
  không có hardsub ở đó, chỉ cần chuyển Whisper".
- **User phản bác kèm 3 ảnh chụp có sub rõ ràng** (好嘞 / 谢了老板 / 我叫姬弃仁)
  — cả 3 đều KHÔNG có trong transcript. Điều tra lại từ đầu → ra bug thật.

## 2. Bằng chứng — vùng chết theo mức crop

Job chạy `OCR_CROP_TOP=auto` → `_auto_crop_top` trả **0.80** (chạm đúng trần
`min(0.80, ...)` của hàm — ocr_subs.py:146). Cùng MỘT frame (f_12.jpg, sub
"我叫姬弃仁" nằm y=93%), chỉ đổi mức crop rồi đưa vào RapidOCR:

| crop_top | dải quét (px) | kết quả |
|---|---|---|
| 0.60 | 1280×288 | ✅ 我叫姬弃仁 (0.73) |
| 0.65 | 1280×252 | ✅ (0.79) |
| 0.72 | 1280×202 | ✅ (0.83) |
| 0.75 | 1280×180 | ✅ (0.83) |
| **0.78** | 1280×159 | ❌ **RỖNG** |
| **0.80 (job dùng)** | 1280×144 | ❌ **RỖNG** |
| 0.85 | 1280×108 | ⚠ đọc SAI chữ (姬奔仁, 0.76) |

Frame thứ hai (f_66 "客官桌子坏了要赔") cho đúng ranh giới đó. Khớp triệu chứng:
đa số frame rỗng → mất câu; số ít lọt qua thì **sai chữ** (transcript hiện có
东西→东四, 浆→汁, đầy lỗi). Tức fix này nâng CẢ độ phủ lẫn độ chính xác.

Lưu ý quan trọng: bước DÒ dải (`probe_crop_top`) OCR **toàn khung** (resize
640px) nên nó THẤY sub và đo đúng vị trí — chỉ bước quét sản xuất với dải mỏng
mới mù. Nghĩa là auto-detect đúng hướng, sai ở cái TRẦN 0.80.

## 3. Thí nghiệm phân định CƠ CHẾ (quyết định phương án sửa)

Trên chính dải chết 1280×144 (kết quả rỗng):

| Biến đổi | Kích thước | Kết quả |
|---|---|---|
| Phóng to ×2 giữ tỉ lệ | 2560×288 | ❌ vẫn rỗng |
| Phóng to ×1.5 | 1920×216 | ❌ vẫn rỗng |
| **Đệm ĐEN phía trên +150px** (cỡ chữ giữ nguyên) | 1280×294 | ✅ 我叫姬弃仁 (0.78) |
| Kéo cao y×2 (chữ méo) | 1280×288 | ✅ (0.72) |

→ Thủ phạm là **TỈ LỆ KHUNG quá dẹt (~9:1)**, không phải cỡ chữ (phóng to giữ
tỉ lệ vẫn chết; thêm chiều cao là sống). Khớp với cách det model của RapidOCR
resize theo cạnh giới hạn: khung quá dẹt làm feature map phát hiện chữ vỡ.

## 4. Các phương án sửa (`core/ocr_subs.py`)

- **F-A (khuyên chọn — sửa gốc): ĐỆM ĐEN dải crop trước khi OCR.** Trong
  `extract()` (và mọi chỗ OCR dải), nếu dải có tỉ lệ w/h > ~5:1 (hoặc
  h < ~25% w) thì `np.vstack` đệm đen phía TRÊN cho đủ. Ưu: chữa mọi mức crop
  (auto LẪN crop tay 0.85 của user khác), không mất chữ nào, rẻ (vstack).
  Nhược: **tọa độ box trả về lệch** — `_frame_lines` chuẩn hoá nbox theo ảnh
  ĐÃ đệm, mà S8 dùng box để che mờ sub gốc → phải TRỪ offset đệm trước khi
  chuẩn hoá (bắt buộc, quên là che mờ sai vùng).
- **F-B (kèm F-A): hạ trần auto-crop.** `min(0.80, ...)` → bảo đảm dải ≥
  ~28% chiều cao khung (720p → ceiling 0.72; điểm chết 0.78 đo được, chừa dư).
  Trần 0.80 cũ sinh ra để "dải tối thiểu 20%" — ý đúng nhưng 20% của 720p =
  144px rơi đúng vùng chết. Có F-A rồi thì F-B là đai an toàn thứ hai.
- **F-C: probe tự kiểm chứng.** Sau khi chọn crop_top, OCR lại vài frame probe
  bằng CHÍNH dải đã crop; nếu probe toàn khung thấy chữ mà dải trả rỗng → hạ
  crop dần tới khi khớp. Ưu: phát hiện vùng chết per-video, không hằng số cứng.
  Nhược: thêm ~5-10 lần OCR + logic; chồng chéo với F-A (đã chữa gốc).
- **F-D: lưới an toàn "OCR thưa bất thường".** Sau extract, nếu mật độ câu
  quá thấp (vd < 2 câu/phút trên video có tiếng nói) → log cảnh báo to + (tuỳ
  chọn) tự thử lại crop 0.65. Bắt được cả các ca mù vì lý do KHÁC trong tương
  lai. Câu hỏi: tự-retry hay chỉ cảnh báo để user quyết?

Đề xuất của tôi: **F-A + F-B** (một fix gốc + một đai), F-D dạng CẢNH BÁO
(không tự retry vội), F-C bỏ qua đợt này.

## 5. Kế hoạch verify (sau khi chốt)

1. Unit: OCR 2 frame mẫu ở crop 0.78/0.80/0.85 có đệm → phải ra đúng chữ +
   box sau khi trừ offset khớp vị trí thật (che mờ S8 không lệch).
2. Chạy lại từ transcribing trên BẢN CLONE của job 64fd4e (job thật của user
   không đụng — user sẽ tự chạy lại sau khi xác nhận): số câu phải tăng mạnh
   (kỳ vọng 31 → 100+ cho 7 phút thoại dày), lỗi chữ kiểu 东四 giảm.
3. Job cũ không ảnh hưởng (fix chỉ đổi hành vi lần OCR mới).

## 6. Câu hỏi cho 2 agent

1. F-A: ngưỡng đệm bao nhiêu là đúng — theo TỈ LỆ (w/h ≤ 5:1?) hay theo chiều
   cao tối thiểu tuyệt đối (≥200px?), hay cả hai? Đệm phía trên hay chia đều
   trên-dưới (ảnh hưởng offset box)?
2. F-A: đệm ĐEN có ca nào phản tác dụng không (sub chữ đen viền trắng? nền
   det model kỵ vùng đồng màu lớn?). Có nên đệm bằng REPLICATE mép thay vì đen?
3. F-B: ceiling theo % (0.72) hay theo px (h−200)? Video 4K/1080p/dọc 720×1280
   thì công thức nào đúng cho mọi cỡ? (Vùng chết đo ở 720p ngang — chưa đo dọc.)
4. Điểm 0.85 đọc-được-nhưng-sai-chữ (108px < 144px lại KHÔNG rỗng) — ai giải
   thích được cơ chế này thì nêu (không chặn fix, nhưng tôi muốn hiểu).
5. F-D: ngưỡng "thưa bất thường" đặt thế nào cho khỏi báo động giả với video
   ít thoại thật (MV, cảnh hành động)?
6. Rủi ro nào tôi chưa thấy? (probe 640px downscale có vùng chết riêng không;
   ảnh hưởng che-mờ S8 khi box offset; video dọc crop auto ~0.65 dải rất cao
   thì F-A không kích hoạt — ổn chứ?)

## 7. Ngoài phạm vi (để vòng sau, đừng gộp)

- Chế độ LAI OCR + Whisper (Whisper lấp khoảng không-sub) — video này sau khi
  vá crop vẫn có thể còn thoại không-sub (Whisper đã nghe thấy 7 câu trong
  đoạn 130–195s, cần đối chiếu lại sau fix).
- Việc dạy chế độ "auto" kiểm tra độ phủ OCR trước khi chọn OCR thay Whisper.
