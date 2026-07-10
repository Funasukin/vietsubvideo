# Phản biện & Đóng góp Tinh chỉnh Panel "Tùy chọn video này" (Gemini Agent)

Tài liệu này ghi lại các ý kiến phản biện, phân tích mã nguồn và đề xuất thiết kế từ Gemini Agent cho đề xuất tinh chỉnh panel cấu hình per-job [AUDIT_GIONG_TUYCHON_JOB.md](file:///F:/MyProject/vietsubvideo/AUDIT_GIONG_TUYCHON_JOB.md). Mọi phản biện đều dựa trên cấu trúc kỹ thuật thực tế của dự án.

---

## 1. Phản biện chi tiết các đề xuất U1 – E15

### U1 — MAX_SPEEDUP: hiện chi phí động
*   **Đồng ý mạnh mẽ nhưng cần bổ sung bộ lọc:**
    Cần lưu ý rằng chữ ký `.sig` của các segment chạy bằng **viXTTS** hoặc **paid_tts** không chứa biến số `:f` (chỉ edge-tts mới có `:f{_fit_budget()}`, xem [s5_tts.py:58-63](file:///F:/MyProject/vietsubvideo/core/stages/s5_tts.py#L58-L63)). Do đó, khi thay đổi `MAX_SPEEDUP`:
    *   Các câu thoại dùng edge-tts sẽ bị lệch `.sig` và buộc phải đọc lại ở S5 (re-TTS).
    *   Các câu thoại dùng viXTTS/paid_tts **không bị lệch `.sig`** và sẽ không bị đọc lại ở S5, S7 chỉ đơn giản là chạy lại mixing và nén bằng `atempo` (cực kỳ nhanh và không tốn phí).
    *   **Giải pháp:** Thuật toán tính toán chi phí động cần bỏ qua các câu viXTTS/paid_tts để không báo khống số lượng câu cần re-TTS.

### U2 — Gộp 3 knob giọng thành 1 (Dropdown "Giọng đọc")
*   **Đồng ý, giải quyết triệt để rác giao diện. Đánh giá các trường hợp đặc biệt:**
    1.  **Casting nhân vật (voice_ref):** Hoàn toàn tương thích. Vì casting lưu trực tiếp vào từng segment, nó luôn được xử lý trước và thắng cấu hình mặc định của job.
    2.  **Đa ngôn ngữ đích (`TARGET_LANG != vi`):** Dropdown này **bắt buộc phải thay đổi động theo ngôn ngữ**. Nếu `TARGET_LANG == en` (tiếng Anh), dropdown phải hiện danh sách giọng Anh (ví dụ: `1 giọng — Guy (Nam)`, `1 giọng — Jenny (Nữ)`, `2 giọng — Nam+Nữ`). Nếu hiển thị cứng NamMinh/HoaiMy của tiếng Việt sẽ gây lỗi giao diện.
    3.  **Paid Engine (ElevenLabs, VBee, FPT):** Dropdown tương tự phải hiển thị các cặp giọng của engine trả phí (ví dụ: VBee ManhDung/NgocHuyen) tương ứng.
    *   **Giải pháp kiến trúc:** Frontend sẽ render Dropdown động dựa trên `(TARGET_LANG, TTS_ENGINE)`. Khi người dùng chọn, frontend sẽ phân tách giá trị đó để gửi về 3 trường tương ứng cho server: `TTS_SINGLE_VOICE` (0 hoặc 1), `TTS_VOICE`, và `TTS_VOICE_NU`.

### U3 — EMOTION: disable-kèm-lý-do khi transcript chưa có nhãn
*   **Lựa chọn tối ưu: Chọn Phương án 1 (disable + tooltip giải thích).**
    *   **Lý do phản biện Phương án 2 (chuyển depth sang translate):** Dịch lại toàn bộ ở S4 không chỉ tốn chi phí gọi API LLM, mà còn **ghi đè và xóa sạch mọi chỉnh sửa văn bản bằng tay** (editor) mà người dùng đã làm trước đó trên các segment. Đây là rủi ro mất mát dữ liệu nghiêm trọng. Việc khóa tùy chọn và hướng dẫn người dùng tự nhấn nút "Dịch lại toàn bộ" (chấp nhận ghi đè) là giải pháp an toàn nhất.

### U4 — PROSODY: ẩn khi engine hiệu lực = viXTTS/paid
*   **Đồng ý.** Prosody đo pitch/rate/volume từ audio gốc chỉ có hiệu lực với edge-tts. viXTTS tự mô phỏng ngữ điệu clip mẫu và paid engine có nhịp điệu riêng nên đều bỏ qua prosody.

### U8 — VOICE_FX rời nhóm "Giọng đọc" xuống "Render"
*   **Đồng ý.** Đây là bộ lọc âm hậu kỳ áp lúc render video, không tác động đến bước tổng hợp giọng.
*   **Sửa bug #12c:** Cần bổ sung giá trị tùy chọn `"system"` (hoặc `"default"`) cho trường `render.fx` của job để cho phép fallback về cấu hình global của hệ thống, thay vì lưu chết cứng giá trị như hiện tại.

### U9, U10, U11 — Bỏ các tùy chọn thử nghiệm/toàn cục khỏi per-job
*   **Đồng ý.** `PROSODY_TRANSFER`, `Model Claude/Gemini`, `OCR_FPS`, `Model whisper` phụ thuộc vào phần cứng server và chính sách chi phí toàn cục của kênh, không cần thiết phải thay đổi theo từng video.

---

## 2. Điểm khuyết thiếu & Knob "nửa tác dụng" phát hiện thêm

1.  **Thiếu per-job: Khử ồn audio `DENOISE`**
    *   Mức độ tạp âm và nhạc nền của video nguồn là yếu tố đặc thù của từng video. Có video rất ồn cần bật `DENOISE=1` để Whisper nhận dạng đúng; có video âm thanh sạch sẵn thì không nên bật (tránh méo giọng gốc).
    *   **Đề xuất:** Thêm `DENOISE` vào whitelist override per-job (nhóm `_OV_TRANSCRIPT`).
2.  **Knob "giữ" nguy hiểm: `CONTENT_STYLE` và `TRANSLATE_STYLE_EXTRA`**
    *   Hai tùy chọn này thuộc nhóm dịch (`_OV_TRANSLATE`). Nếu người dùng thay đổi chúng sau khi đã dịch xong, hệ thống sẽ chạy lại stage dịch S4.
    *   Tương tự như U3, điều này sẽ **ghi đè và làm mất sạch các sửa đổi lời thoại thủ công** trong editor. Giao diện cần hiển thị cảnh báo đỏ xác nhận ghi đè dữ liệu trước khi áp dụng.

---

## 3. Thiết kế kỹ thuật cho Endpoint Dry-run U12 (Rẻ & Nhanh)

Để tính toán số lượng câu thoại cần đọc lại mà không làm ảnh hưởng đến tiến trình chạy thực tế của server, ta xây dựng endpoint `/api/jobs/{job_id}/dry-run-overrides`:

1.  **Dòng chảy xử lý:**
    *   Nhận JSON chứa các cấu hình override giả lập từ client gửi lên.
    *   Đọc tệp `transcript_vi.json` của job để lấy danh sách các segment hiện tại.
    *   Khởi tạo một dict cấu hình giả lập bằng cách copy từ `config.py` và cập nhật các đè cấu hình mới lên.
    *   Duyệt qua danh sách segment, gọi hàm tính toán chữ ký giả định `_voice_sig(seg)` (sử dụng dict cấu hình giả lập).
    *   So sánh chữ ký giả định này với nội dung tệp `.sig` thực tế trên đĩa (ví dụ: `tts/seg_NNNN.sig`).
    *   Nếu khác biệt hoặc thiếu tệp `.sig`, tăng biến đếm `re_tts_count`.
2.  **Đầu ra trả về:**
    ```json
    {
      "rebuild_depth": "tts", // hoặc mix, translate, transcript
      "re_tts_count": 12,     // số câu phải đọc lại
      "est_tts_minutes": 0.5, // ước tính thời gian tts
      "warn_overwrite": false  // cảnh báo nếu chạy lại từ translate gây mất dữ liệu
    }
    ```
    *   *Đánh giá:* Logic này chạy hoàn toàn trên RAM và so khớp chuỗi I/O đĩa cơ bản, phản hồi trong vài mili-giây, hoàn toàn không tốn tài nguyên GPU hay chi phí API.

---

## 4. Đề xuất Bố cục Giao diện Tối ưu (U15)

Chúng tôi đề xuất phân bổ lại 16 tùy chọn sau khi đã tinh gọn như sau để đạt hiệu quả UX tốt nhất:

### Nhóm Thường dùng (8 tùy chọn)
1.  **Âm nền gốc (dB)** (Chỉnh độ to/nhỏ của nhạc nền).
2.  **Nhạc/SFX gốc (KEEP_BGM)** (Chọn mode giữ nhạc nền gốc: flat, tắt, hoặc tách demucs).
3.  **Preset khớp thoại** (Khớp môi chặt / Tự nhiên / Tùy chọn).
4.  **Engine giọng** (Edge-tts / viXTTS / Paid).
5.  **Giọng đọc** (Dropdown gộp U2, hiển thị tên giọng động theo TARGET_LANG và Engine).
6.  **Nguồn transcript** (OCR / Whisper / Auto).
7.  **Vùng quét phụ đề (OCR_CROP_TOP)** (Đặc thù theo bố cục từng video dọc/ngang).
8.  **Phong cách dịch riêng** (Rất hay dùng để thêm teencode hoặc văn phong vui nhộn theo video).

### Nhóm Nâng cao (Details) (8 tùy chọn)
1.  *Tỷ lệ tốc độ tối đa (MAX_SPEEDUP)* (Chỉ hiện khi chọn preset Tùy chọn).
2.  *Kéo giãn câu ngắn (STRETCH_SHORT)*.
3.  *Tông giọng theo audio (PROSODY)* (Chỉ hiện khi dùng edge-tts).
4.  *Sắc thái cảm xúc (EMOTION)* (Hiện disable kèm lý do nếu không có nhãn cảm xúc).
5.  *Nhà cung cấp dịch (TRANSLATE_PROVIDER)* (Claude / Gemini).
6.  *Kiểu nội dung* (Donghua / Hiện đại).
7.  *Ngôn ngữ lồng tiếng (TARGET_LANG)*.
8.  *Khử ồn âm thanh gốc (DENOISE)* (Thêm mới).

---
*Bản phản biện kết thúc. Xin mời thảo luận và lựa chọn các mã phương án từ U1–U15 để tiến hành hiện thực hóa.*
