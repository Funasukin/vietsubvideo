# Phản biện & Đóng góp Đề xuất: Nền Tốc Độ Giọng Đọc (Gemini Agent)

Tài liệu này ghi lại các ý kiến phản biện, phân tích kỹ thuật và đề xuất thiết kế từ Gemini Agent cho đề xuất nền tốc độ giọng đọc toàn cục [DEXUAT_TOCDO_GIONGDOC.md](file:///F:/MyProject/vietsubvideo/DEXUAT_TOCDO_GIONGDOC.md).

---

## 1. Trả lời các câu hỏi thảo luận (Mục 4)

### 1.1. Default của `SPEECH_RATE` là bao nhiêu?
*   **Đồng ý với mức đề xuất: +30% (tương đương ~4.2 âm tiết/giây đối với HoaiMyNeural).**
    *   *Lý do:* Tốc độ đọc mặc định của edge-tts (+0%) là ~3.24 âm tiết/giây, nghe khá chậm và rề rà đối với các thể loại video hoạt hình, review phim hoặc vlog hiện đại. Mức **+30%** giúp giọng đọc nhanh, dứt khoát và hoạt ngôn nhưng **vẫn giữ được độ tự nhiên và tròn vành rõ chữ** của Microsoft Neural voices.
    *   Nếu đặt quá cao (ví dụ +40% đến +50% để đạt mức 5.4 âm tiết/giây như CapCut), edge-tts sẽ bắt đầu bị nuốt chữ, mất phụ âm cuối và nghe rất cơ khí. Hãy để mức +30% làm mặc định và cho phép người dùng tự nâng lên +40% hoặc +50% trong tab Cấu hình tùy theo tai nghe của họ.

### 1.2. Tên khóa và Phạm vi: `SPEECH_RATE` per-job
*   **Tên khóa:** `SPEECH_RATE` là tên khóa rất rõ ràng và chuẩn xác.
*   **Phạm vi:** **Bắt buộc phải hỗ trợ per-job override (panel ⚙️) ngay từ đầu.**
    *   *Lý do:* Nhịp độ video phụ thuộc hoàn toàn vào thể loại nội dung. Video review phim võ thuật/donghua cần tiết tấu cực nhanh (+35% đến +45%), nhưng video tài liệu, vlog tâm sự hay hướng dẫn chậm lại cần nhịp độ trung bình (+10% đến +15%). Nếu chỉ để global, người dùng sẽ phải đổi cấu hình liên tục mỗi khi chuyển video, vi phạm nguyên tắc thiết kế của panel per-job.
    *   *Độ sâu chạy lại:* Khóa này thuộc nhóm **`_OV_TTS`** (depth: `tts`). Khi đổi `SPEECH_RATE` của job, chữ ký giọng (`voicesig`) sẽ thay đổi và hệ thống sẽ tự động chạy lại S5 để tổng hợp lại tệp âm thanh với tốc độ nền mới. Đây là hành vi chính xác và trung thực.

### 1.3. viXTTS: Tách "nền gu đọc" khỏi trần nén `VIXTTS_SPEED_MAX = 1.25`
Trần `VIXTTS_SPEED_MAX = 1.25` của Coqui XTTS là **trần giới hạn chất lượng của mô hình** (nếu synth với `speed > 1.25`, giọng sẽ bị vỡ, méo tiếng hoặc nuốt câu). 
Nếu `SPEECH_RATE` là +30% (tốc độ nền `speed_base = 1.30`) và câu đó cần nén thêm một lượng $k$ để vừa slot, tốc độ tổng yêu cầu là $S_{total} = 1.30 \times k$. Nếu gửi thẳng $S_{total}$ vào viXTTS, giọng đọc chắc chắn sẽ bị hỏng.
*   **Giải pháp phân tách sạch sẽ:**
    *   Chia target tốc độ tổng $S_{total}$ thành hai phần:
        1.  **Tốc độ nạp vào model viXTTS khi synth (giới hạn ở 1.25):**
            $$speed\_model = \min(S_{total}, 1.25)$$
        2.  **Tốc độ nén hậu kỳ bằng `atempo` (áp dụng trong S5 sau khi synth hoặc S7 mix):**
            $$speed\_post = \frac{S_{total}}{speed\_model}$$
    *   *Cách triển khai:* 
        *   Trong `core/vixtts.py`, hàm `synth()` sẽ nhận tham số `speed` (tối đa 1.25).
        *   Nếu $S_{total} > 1.25$, sau khi synth ra file audio tạm thời ở tốc độ `speed_model`, chúng ta áp dụng một bộ lọc nhanh `atempo=speed_post` bằng ffmpeg ngay trong S5 trước khi ghi đè ra file `.mp3` chính thức.
        *   Hành vi này giúp tệp `.mp3` đầu ra của S5 luôn đạt chuẩn tốc độ và độ dài sạch sẽ, S5 `trimmed_dur_s` sẽ đo được chính xác thời lượng thực tế của tệp đã sped-up, và S7 mix chỉ việc đặt lên timeline mà không cần nén thêm.

### 1.4. ElevenLabs không có speed API trực tiếp
*   **Giải pháp:** **Chấp nhận áp dụng `atempo` hậu kỳ cho ElevenLabs.**
    *   *Lý do:* Fmpeg `atempo` (sử dụng thuật toán WSOLA) giữ nguyên cao độ (pitch) và có chất lượng cực kỳ tốt đối với các đoạn tăng tốc nhẹ (1.0x - 1.3x). Do giọng ElevenLabs rất sạch và chất lượng cao, việc tăng tốc bằng `atempo` hậu kỳ vẫn cho ra chất lượng âm thanh xuất sắc.
    *   *Cách triển khai:* Tương tự viXTTS, tại cuối hàm `_tts_paid` của `s5_tts.py`, nếu phát hiện `SPEECH_RATE` của job được đặt, ta chạy một lệnh ffmpeg `atempo` nhanh để convert tệp audio vừa tải về trước khi lưu `.mp3` và `.sig`. Giao diện UI sẽ ghi chú rõ: *"ElevenLabs: Tự động tăng tốc hậu kỳ bằng atempo"*.

### 1.5. Hiệu chỉnh `SYL_MAX_PER_S` theo nền
*   **Đồng ý scale tuyến tính.**
    *   *Lý do:* Nếu tốc độ đọc nền nhanh hơn 30%, khả năng chứa chữ của một slot thời gian sẽ tăng lên tương ứng. Nếu giữ nguyên trần cứng `4.5` âm tiết/giây, Claude/Gemini ở S4 sẽ bị ép dịch quá ngắn, cắt xén câu chữ vô lý trong khi giọng đọc thực tế thừa sức đọc hết.
    *   Công thức scale tuyến tính đề xuất:
        $$SYL\_MAX\_PER\_S_{eff} = 4.5 \times \left(1 + \frac{\text{SPEECH\_RATE}}{100}\right)$$
        $$SYL\_TARGET\_PER\_S_{eff} = 4.0 \times \left(1 + \frac{\text{SPEECH\_RATE}}{100}\right)$$
    *   Mức trần này sẽ được truyền động vào payload dịch của S4 và bộ validator đếm âm tiết V6.

### 1.6. Loại bỏ `STRETCH_SHORT`
*   **Đồng ý loại bỏ hoàn toàn khỏi giao diện UI.**
    *   *Lý do:* Triết lý mới của user là "chấp nhận khoảng lặng" và "nhịp đọc đồng đều". Việc kéo giãn câu ngắn (làm chậm tốc độ) trực tiếp phá vỡ sự đồng đều về tempo của kênh, tạo ra cảm giác lê thê.
    *   Để tránh phá vỡ tương thích ngược với các file config cũ, ta giữ biến `STRETCH_SHORT` ẩn trong `settings_schema.py` (mặc định là `False` hoặc `0`), nhưng xóa bỏ hoàn toàn control của nó khỏi UI tab Cấu hình và panel per-job.

---

## 2. Rủi ro kỹ thuật bổ sung

1.  **Khoảng lặng giữa các câu bị kéo dài (Inter-segment silence gap):**
    *   Khi đọc nhanh hơn, thời lượng phát âm thực tế của câu co lại, làm tăng khoảng lặng ở cuối câu (ví dụ: slot 3s, trước đọc mất 2.8s $\rightarrow$ gap 0.2s; nay đọc mất 2.0s $\rightarrow$ gap 1.0s).
    *   Nếu video có nhiều câu thoại ngắn liên tiếp, người nghe sẽ trải qua cảm giác "bắn chữ liên thanh" rồi dừng khựng lại 1 giây, sau đó lại "bắn chữ". 
    *   *Cần lưu ý:* Đây là hành vi đúng theo yêu cầu của user, nhưng nếu gap quá lớn gây mất tự nhiên, giải pháp triệt để là hướng dẫn user điều chỉnh gộp segment (`segtools.clean_and_merge`) hoặc điều chỉnh lại timing gốc.
2.  **Lỗi phát âm số và từ viết tắt của edge-tts ở rate cao:**
    *   Khi tăng tốc rate lên +30% đến +50%, edge-tts thỉnh thoảng phát âm méo mó các số (ví dụ: "2026") hoặc từ viết tắt tiếng Anh.
    *   *Giải pháp:* Đảm bảo hàm chuẩn hóa văn bản hoạt động tốt, chuyển số thành chữ tiếng Việt trước khi gửi sang edge-tts.
3.  **Tương tác với PROSODY/EMOTION:**
    *   Nếu người dùng bật lại Emotion (ví dụ nhãn `gap` thêm +12% rate), tổng rate của edge-tts sẽ là `SPEECH_RATE + 12 = 42%`.
    *   Nếu tổng rate vượt quá `EDGE_RATE_MAX = 50%`, hệ thống phải cap lại ở 50% và offload phần dư thừa sang `atempo` ở S7. Công thức tích hợp chéo `edge_total_rate` cần được kiểm tra kỹ để tránh bị lỗi nhảy vọt âm thanh.

---
*Tài liệu phân tích kết thúc. Vui lòng phản hồi để chúng tôi tiến hành xây dựng và kiểm thử sau khi có chốt từ user.*
