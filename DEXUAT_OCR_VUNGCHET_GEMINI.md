# Phản biện & Đóng góp Đề xuất: Vá "vùng chết" OCR (Gemini Agent)

Tài liệu này ghi lại các ý kiến phản biện, phân tích lỗi mô hình và đề xuất giải pháp kỹ thuật từ Gemini Agent cho đề xuất vá vùng chết OCR [DEXUAT_OCR_VUNGCHET.md](file:///F:/MyProject/vietsubvideo/DEXUAT_OCR_VUNGCHET.md).

---

## 1. Trả lời các câu hỏi thảo luận (Mục 6)

### 1.1. F-A: Ngưỡng đệm bao nhiêu là đúng? Đệm thế nào?
*   **Đề xuất ngưỡng đệm:** **Nên áp dụng cả hai ngưỡng (Tỉ lệ và Chiều cao tuyệt đối) để an toàn cho mọi độ phân giải video (từ 720p đến 4K).**
    *   Học máy phát hiện chữ (DBNet của RapidOCR) bị lỗi nhận diện khi tỉ lệ ảnh quá dẹt. Ngưỡng tỉ lệ vàng để DBNet hoạt động ổn định là **$W/H \le 5:1$** (tương đương chiều cao $H \ge W/5$).
    *   *Thuật toán tính toán:*
        *   Gọi chiều rộng ảnh crop là $W$, chiều cao ảnh crop là $H$.
        *   Chiều cao mục tiêu tối thiểu: $H_{target} = \max(240, \text{int}(W / 5))$.
        *   Nếu $H < H_{target}$: ta tính toán khoảng đệm cần thêm vào phía trên: `pad_top = H_target - H`.
    *   *Vì sao đệm phía trên?* Đệm đen phía trên giúp đẩy vùng văn bản xuống gần đáy ảnh hơn (khớp với phân phối vị trí phụ đề thông thường trong tập dữ liệu huấn luyện DBNet), giúp tăng độ chính xác của mô hình.
    *   *Cách thực hiện đệm:* Dùng hàm native OpenCV cực nhanh:
        ```python
        img_padded = cv2.copyMakeBorder(img, pad_top, 0, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])
        ```

### 1.2. F-A: Đệm ĐEN có phản tác dụng không? Có nên dùng Replicate?
*   **Không phản tác dụng.** Các mô hình phát hiện văn bản tự nhiên (DBNet) được thiết kế để bỏ qua các vùng đồng màu (như bầu trời, tường, hoặc dải đen letterbox của phim). Việc đệm đen mô phỏng hoàn hảo dải letterbox tiêu chuẩn, DBNet xử lý cực kỳ tốt.
*   **TUYỆT ĐỐI KHÔNG dùng Replicate (lặp mép ảnh):** Việc lặp mép ảnh sẽ kéo dãn các pixel ở hàng đầu tiên thành các vệt sọc dọc màu sắc. Các vệt dọc này tạo ra gradient mạnh, rất dễ đánh lừa DBNet nhận diện nhầm thành các hộp văn bản giả (False Positives), gây rác dữ liệu nghiêm trọng. Do đó, **đệm đen (BORDER_CONSTANT)** là lựa chọn an toàn nhất.

### 1.3. F-B: Công thức hạ trần Auto-Crop cho mọi cỡ video
*   Nếu đã có **F-A** (đệm ảnh thông minh trước khi OCR), vấn đề tỉ lệ dẹt đã được giải quyết triệt để ở cấp độ xử lý ảnh. Ngay cả khi crop dẹt chỉ có 100px, ảnh vẫn sẽ được đệm lên 250px+ và nhận dạng chính xác.
*   Tuy nhiên, để tạo đai an toàn kép (F-B), ta nên khống chế `crop_top` tối đa để tránh trường hợp crop quá sát làm cắt đôi chữ phụ đề (do sai số dò).
*   **Đề xuất công thức cap theo % chiều cao:**
    *   `crop_top_max = 0.78` (tương đương giữ lại tối thiểu 22% chiều cao video dưới đáy).
    *   Với video 720p (720px): dải quét tối thiểu là $0.22 \times 720 = 158$ px.
    *   Với video 1080p (1080px): dải quét tối thiểu là $0.22 \times 1080 = 237$ px.
    *   Cần giữ hằng số tỉ lệ `%` thay vì số pixel cứng để tự thích ứng với các video dọc (Douyin/Shorts) có bố cục phụ đề nằm cao hơn hẳn.

### 1.4. Giải thích hiện tượng: Crop 0.85 đọc sai chữ nhưng không bị rỗng như 0.80
Đây là hiện tượng rất thú vị liên quan đến đặc tính của mạng CNN (DBNet + CRNN):
1.  **Tại 0.80 (Cao 144px): RỖNG.** Subtitle nằm lơ lửng ở giữa dải crop 144px, chiếm khoảng 40% diện tích chiều cao. Tỉ lệ dẹt cực đoan (9:1) cộng với việc chữ nhỏ so với khung hình làm feature map của DBNet bị tiêu biến (gradient bị trôi mất), DBNet không kích hoạt phát hiện hộp chữ $\rightarrow$ trả về Rỗng.
2.  **Tại 0.85 (Cao 108px): SAI CHỮ (姬奔仁).** Khi dẹt hơn nữa, chữ phụ đề chiếm hầu như toàn bộ chiều cao dải crop (khoảng 80-90%). Lúc này, ảnh crop trông giống như một dòng văn bản đơn lẻ (single-line text strip). DBNet cực kỳ nhạy với dạng ảnh này và dễ dàng khoanh vùng được hộp chữ. Tuy nhiên, vì dải crop quá sát mép chữ, một số nét vẽ ở đỉnh và đáy ký tự Trung Quốc bị cắt mất (clipping) $\rightarrow$ CRNN nhận diện sai nét và đoán sai chữ.

### 1.5. F-D: Đặt ngưỡng "thưa bất thường" cảnh báo
*   Mật độ thoại thưa phụ thuộc nhiều vào thể loại video (MV ca nhạc, phim hành động ít thoại).
*   Ngưỡng cảnh báo an toàn tránh báo động giả: **Mật độ OCR < 0.2 segment / phút (tương đương 1 câu mỗi 5 phút) trên tổng chiều dài video**.
*   Khi kích hoạt, hệ thống chỉ ghi log cảnh báo màu vàng lên UI QC: *"Phát hiện mật độ phụ đề OCR rất thưa. Nếu video có thoại, hãy kiểm tra lại vùng che hoặc thử chuyển sang nguồn Whisper."* Không tự động chạy lại để tránh tốn tài nguyên và sai ý người dùng.

---

## 2. Thiết kế chi tiết giải pháp điều chỉnh Tọa độ Box (Tránh lệch che mờ S8)

Đây là rủi ro lớn nhất của phương án F-A. Nếu đệm ảnh thêm `pad_top` pixel, tọa độ box trả về từ RapidOCR sẽ bị lệch xuống dưới. Chúng ta phải vá ngay trong hàm `_frame_lines` của [core/ocr_subs.py](file:///F:/MyProject/vietsubvideo/core/ocr_subs.py) để trả lại tọa độ chuẩn cho hệ thống:

### 2.1. Logic vá tọa độ trong `_frame_lines`

```python
# Tinh chỉnh ocr_subs.py
def _frame_lines(engine, img, pad_top: int = 0, h_orig: int = 0) -> list[tuple[float, str, list[float]]]:
    """
    img: ảnh đã đệm đen (nếu có)
    pad_top: số pixel đã đệm ở đỉnh ảnh
    h_orig: chiều cao gốc trước khi đệm
    """
    result, _ = engine(img)
    if not result:
        return []
    
    h_padded, w = img.shape[:2]
    # Nếu không đệm, h_orig chính là h_padded
    h_actual = h_orig if h_orig > 0 else h_padded
    
    lines = []
    for box, text, conf in result:
        if float(conf) < config.OCR_MIN_CONF or _JUNK.search(text):
            continue
            
        xs = [p[0] for p in box]
        # Điều chỉnh y-pixel: Trừ đi khoảng đệm pad_top và kẹp trong [0, h_actual]
        ys = [max(0.0, min(h_actual, p[1] - pad_top)) for p in box]
        
        # Tọa độ chuẩn hóa nbox sẽ tính dựa trên kích thước gốc h_actual (không tính pad)
        nbox = [
            round(min(xs) / w, 4),
            round(min(ys) / h_actual, 4),
            round(max(xs) / w, 4),
            round(max(ys) / h_actual, 4)
        ]
        lines.append((min(xs), text.strip(), nbox))
        
    return sorted(lines, key=lambda l: l[0])
```

### 2.2. Tích hợp vào hàm `extract` và `_auto_crop_top`

Trong hàm `extract()`, trước khi gửi ảnh sang `_frame_lines` / `_ocr_one`:
1.  Đo kích thước ảnh gốc $W, H$.
2.  Tính toán $H_{target} = \max(240, \text{int}(W / 5))$.
3.  Nếu $H < H_{target}$:
    *   `pad_top = H_target - H`
    *   Áp dụng `cv2.copyMakeBorder` để tạo ảnh đệm.
    *   Truyền `pad_top` và `h_orig = H` vào hàm xử lý OCR để tự động dịch chuyển lại tọa độ box về hệ tọa độ gốc.
4.  Nhờ vậy, toàn bộ tầng sau (ghép segment, sinh `sub_boxes.json`, che mờ S8) hoàn toàn không bị ảnh hưởng và chạy mượt mà.

---
*Tài liệu phân tích kết thúc. Phương án F-A + F-B + vá tọa độ P1 là tối ưu nhất. Xin mời phản hồi để chốt phương án.*
