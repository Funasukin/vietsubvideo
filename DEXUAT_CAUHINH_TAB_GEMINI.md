# Phản biện & Đóng góp Tinh gọn tab Cấu hình (Gemini Agent)

Tài liệu này ghi lại các ý kiến phản biện, phân tích mã nguồn và đề xuất thiết kế từ Gemini Agent cho đề xuất tinh gọn cấu hình toàn cục [DEXUAT_CAUHINH_TAB.md](file:///F:/MyProject/vietsubvideo/DEXUAT_CAUHINH_TAB.md).

---

## 1. Phản biện các đề xuất G1 – G15 & Tùy chọn ẩn chưa lên UI

Chúng tôi đồng ý với định hướng tinh giản cấu hình của Claude. Dưới đây là phân tích chi tiết và các đề xuất bổ sung từ mã nguồn:

### 1.1. Các tùy chọn ẩn trong `.env` chưa được lên UI
Trong [config.py](file:///F:/MyProject/vietsubvideo/config.py), có hai nhóm biến số cực kỳ quan trọng liên quan đến phần cứng đang bị giấu kín trong `.env` và bắt buộc user phải sửa tay:
1.  **`WHISPER_DEVICE`** (`cpu` hoặc `cuda`) & **`WHISPER_COMPUTE`** (`int8` hoặc `float16`):
    *   *Rủi ro:* Nếu người dùng chọn `cuda` / `float16` nhưng máy tính thiếu DLL CUDA (`cublas64_12.dll`...) hoặc GPU không tương thích, Whisper sẽ crash ngay lập tức khi chạy S3.
    *   *Giải pháp:* Đưa hai tùy chọn này lên nhóm **Nhận dạng thoại -> Nâng cao** dưới dạng dropdown, nhưng **kết nối trực tiếp với kết quả đo của G7 Health Card**. Nếu hệ thống kiểm tra thấy thiết bị không hỗ trợ CUDA, tùy chọn `cuda` sẽ bị disabled kèm thông báo giải thích rõ ràng.
2.  **`FFMPEG_SHARED_BIN`**:
    *   Đường dẫn thư mục FFmpeg shared cho thư viện `torchcodec` (dùng trong viXTTS). Đây là nguyên nhân hàng đầu gây lỗi nạp viXTTS trên Windows.
    *   *Giải pháp:* Đưa ô nhập đường dẫn này vào nhóm **Lồng tiếng (TTS) -> Nâng cao**, hỗ trợ tự động điền các đường dẫn phổ biến nếu phát hiện thấy.

---

## 2. Giải quyết Ngữ nghĩa G5 (Quality Preset vs Model đích danh)

Để giao diện sạch sẽ mà vẫn giữ tính tùy biến cao, chúng tôi đề xuất quy tắc ngữ nghĩa sau:

1.  **Chất lượng dịch (Quality Preset)** sẽ là một **UI Sugar (phím tắt đổi nhanh)** trên Client, hoàn toàn không ghi xuống tệp `.env`.
2.  Khi người dùng chọn Preset, client JavaScript sẽ tự động thay đổi giá trị trong 2 ô nhập ẩn ở nhóm Nâng cao của `CLAUDE_MODEL` và `GEMINI_MODEL`:
    *   `Cân bằng` $\rightarrow$ Claude: `claude-haiku-...` | Gemini: `gemini-2.5-flash`
    *   `Tốt nhất` $\rightarrow$ Claude: `claude-sonnet-...` | Gemini: `gemini-2.5-pro`
3.  Trong phần Nâng cao, người dùng vẫn có thể thay đổi thủ công model đích danh. Nếu giá trị trong ô nhập không khớp với bất kỳ Preset định nghĩa sẵn nào, dropdown Preset ở ngoài sẽ tự động hiển thị nhãn `"Tùy chỉnh"`.
4.  Tệp `.env` chỉ lưu trữ 2 biến gốc duy nhất: `CLAUDE_MODEL` và `GEMINI_MODEL`. Việc này giúp loại bỏ hoàn toàn nguy cơ mâu thuẫn dữ liệu giữa hai cấu hình.

---

## 3. Thiết kế kỹ thuật cho Endpoint Health `/api/health` (G7)

Endpoint này bắt buộc phải chạy cực kỳ nhanh (**dưới 100ms**) và không được import các thư viện nặng của PyTorch/CTranslate2.

```python
# Phác thảo logic cho webui/server.py
@app.get("/api/health")
def get_health_status() -> dict:
    import shutil
    import subprocess
    from core import vixtts
    
    # 1. Kiểm tra FFmpeg & GPU Encoder
    has_nvidia = False
    try:
        # Gọi lệnh nhanh kiểm tra GPU Encoder h264_nvenc
        r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=2)
        if "h264_nvenc" in r.stdout:
            has_nvidia = True
    except Exception:
        pass

    # 2. Kiểm tra trạng thái nạp viXTTS và CUDA DLLs
    vixtts_ready = False
    cuda_dll_ok = False
    try:
        # Chỉ kiểm tra file model tồn tại
        if (config.VIXTTS_DIR / "config.json").exists():
            vixtts_ready = True
        # Quét nhanh xem có DLL cublas trong PATH/nvidia folder không
        # (Không import torch/faster-whisper)
        import os
        for p in os.environ.get("PATH", "").split(os.pathsep):
            if os.path.exists(os.path.join(p, "cublas64_12.dll")):
                cuda_dll_ok = True
                break
    except Exception:
        pass

    # 3. Trích xuất thông tin RAM / Disk
    import psutil
    disk = psutil.disk_usage(config.DATA_DIR)
    
    return {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "nvenc": has_nvidia,
        "vixtts_model": vixtts_ready,
        "cuda_libraries": cuda_dll_ok,
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "keys_set": {
            "anthropic": bool(config.ANTHROPIC_API_KEY),
            "gemini": bool(config.GEMINI_API_KEY),
            "vbee": bool(config.VBEE_TOKEN),
            "fpt": bool(config.FPT_TTS_API_KEY),
            "elevenlabs": bool(config.ELEVENLABS_API_KEY)
        }
    }
```

---

## 4. Thiết kế Schema Profile cấu hình (G11)

Tệp Profile cấu hình sẽ được lưu trữ dưới dạng JSON tại thư mục `data/profiles/` (đã được cấu hình loại trừ trong `.gitignore`).

### 4.1. Schema Profile
```json
{
  "name": "Donghua Cổ Trang Thuyết Minh",
  "description": "Cấu hình tối ưu để lồng tiếng phim hoạt hình Trung Quốc cổ trang bằng viXTTS",
  "pause_before_render": true, // Cho phép lưu cả thiết lập luồng job mặc định
  "config": {
    "CONTENT_STYLE": "donghua",
    "TRANSLATE_PROVIDER": "claude",
    "TTS_ENGINE": "vixtts",
    "TTS_SINGLE_VOICE": "true",
    "KEEP_BGM": "true",
    "MAX_SPEEDUP": "1.4",
    "SUB_SPLIT": "1",
    "EMOTION": "1"
  }
}
```

### 4.2. Nguyên tắc import / export
*   **Bảo mật:** Loại bỏ hoàn toàn mọi key có chứa hậu tố `_KEY`, `_TOKEN`, `_SECRET` khỏi bộ lọc xuất cấu hình (không bao giờ export secrets).
*   **Tương thích ngược:** Khi nạp cấu hình thiếu các trường mới, hệ thống sẽ bỏ qua và giữ nguyên giá trị hiện có trên `.env` thay vì xóa trắng. Các trường lạ (không nằm trong danh sách whitelist cấu hình) sẽ bị JavaScript lọc bỏ ngay lập tức để tránh lỗi chèn mã rác.

---

## 5. Trải nghiệm lần đầu (First-run Experience) đối với nhóm 🔑 Keys

Đề xuất đẩy nhóm Keys xuống cuối cùng là hoàn toàn chính xác để phục vụ cho nhu cầu sử dụng lặp lại hàng ngày. Để giải quyết rào cản cho người dùng mới chạy app lần đầu, chúng tôi thiết kế giải pháp sau:

1.  Khi tải trang Cấu hình, client JavaScript sẽ kiểm tra:
    `if (!health.keys_set.anthropic && !health.keys_set.gemini)`
2.  Nếu chưa có API Key nào được cài đặt:
    *   Hiển thị một **Alert Box màu vàng nổi bật ở ngay đầu trang**: *"Bạn chưa cấu hình API Key dịch thuật. Hãy nhấn vào đây để điền khóa."*
    *   Tự động mở rộng phần Keys (`<details open>`) ở cuối trang và tự động cuộn (focus) màn hình xuống nhóm này.
3.  Nếu đã cấu hình Key:
    *   Alert Box biến mất, phần Keys mặc định thu gọn lại dưới đáy trang để nhường chỗ cho các tùy chọn lồng tiếng, dịch thuật.

---

## 6. Đề xuất cải tiến Bố cục tab mới (G13 - Tối ưu tần suất)

Chúng tôi đề xuất bố cục cuối cùng cho tab Cấu hình như sau:

1.  **Card Trạng thái máy** (Đọc nhanh GPU, FFmpeg, CUDA, dung lượng đĩa).
2.  **Bộ lọc tìm kiếm nhanh & Quản lý Profile**.
3.  **Lồng tiếng (TTS)**: *Mặt tiền:* Engine, Cặp giọng mặc định, Single Voice, Duck Gain. *Nâng cao:* Prosody, Emotion, Prosody Transfer, Max Speedup, Stretch Short, FFMPEG_SHARED_BIN.
4.  **Dịch thuật**: *Mặt tiền:* Chất lượng dịch (Preset), Nhà cung cấp dịch (Claude/Gemini), Phong cách dịch riêng. *Nâng cao:* Model Claude cụ thể, Model Gemini cụ thể, Khoảng cách gọi Gemini (Gemini Interval).
5.  **Nhận dạng thoại**: *Mặt tiền:* Nguồn transcript (OCR/Whisper), Vùng che sub (OCR_CROP_TOP). *Nâng cao:* Whisper Device, Whisper Compute, Denoise (Khử ồn trước Whisper), Diarize (Phân chia người nói).
6.  **Thương hiệu & Render**: *Mặt tiền:* Nhạc nền, Âm lượng nhạc, Logo watermark, Nhịp phụ đề (Sub Split). *Nâng cao:* Tùy chỉnh Logo (Scale/Opacity), Khung viền video, Nhắc Like/Đăng ký.
7.  **Hệ thống & Tự động hóa**: Auto Retry, Shorts tự động.
8.  **Khóa API & Token** (Tự động gập).

---
*Tài liệu phân tích kết thúc. Vui lòng phản hồi để chúng tôi có cơ sở thống nhất phương án triển khai hoàn chỉnh cho UI.*
