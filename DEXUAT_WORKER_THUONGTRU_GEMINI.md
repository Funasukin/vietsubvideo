# Phản biện & Đóng góp Đề xuất: Worker Thường Trú (Gemini Agent)

Tài liệu này ghi lại các ý kiến phản biện, phân tích kiến trúc và đề xuất thiết kế từ Gemini Agent cho tài liệu [DEXUAT_WORKER_THUONGTRU.md](file:///F:/MyProject/vietsubvideo/DEXUAT_WORKER_THUONGTRU.md).

---

## 1. Phản biện A/B/C & Đề xuất Phương án D (FastAPI Server làm Model Host)

Chúng tôi phản biện phân tích 3 phương án A/B/C và đề xuất **Phương án D (Tích hợp Model Host vào chính server FastAPI hiện tại)** làm phương án tối ưu nhất.

### 1.1. So sánh và Phản biện
*   **Phương án B (In-Process Monolith Worker): BÁC BỎ.** Việc bỏ hoàn toàn subprocess sẽ phá vỡ hai cơ chế cốt lõi đang chạy cực kỳ ổn định: (1) Hủy job ngay lập tức bằng `taskkill /T /F` trên cây tiến trình con; và (2) Sự cách ly cấu hình tuyệt đối qua `FLOWAPP_JOB_OVERRIDES` (env vars). Nếu chạy in-process, việc reload config và hủy an toàn các tác vụ ffmpeg/CUDA giữa chừng sẽ cực kỳ phức tạp và dễ gây rò rỉ bộ nhớ/deadlock.
*   **Phương án C (Warm Pool): BÁC BỎ.** Việc duy trì một pool các tiến trình ấm làm tăng đáng kể độ phức tạp quản lý vòng đời tiến trình trên Windows (vốn không hỗ trợ `fork` hiệu quả như Linux, buộc phải spawn mới). Việc kiểm soát config reload trong tiến trình ấm vẫn là một bài toán khó và dễ phát sinh bug bất ngờ.
*   **Phương án A (Model Host riêng biệt): KHÁ TỐT.** Cô lập lỗi tốt, giữ nguyên cơ chế cancel. Tuy nhiên, nó bắt buộc người dùng phải vận hành một tiến trình thứ 3 (phải viết watchdog, quản lý cổng port thứ hai, xử lý logs riêng).
*   **Phương án D (FastAPI làm Model Host - Đề xuất tối ưu):**
    Chúng ta không cần tạo tiến trình mới. Chính tiến trình FastAPI (`server.py`) sẽ giữ các model trong RAM và cung cấp các endpoint nội bộ (chỉ cho phép localhost truy cập, ví dụ `/api/internal/vixtts`).
    *   *Vì sao D khả thi?* Cả Whisper, viXTTS và Demucs khi chạy trên GPU đều giải phóng GIL (Global Interpreter Lock) của Python khi chạy nhân tính toán C++ CUDA. Do đó, việc chạy inference không hề khóa luồng chính của Python.
    *   *Tránh nghẽn Event-Loop:* Để tránh việc Uvicorn bị nghẽn (khiến UI bị đơ), các request gọi model sẽ được đẩy vào threadpool của FastAPI (chạy thông qua `anyio.to_thread.run_sync` hoặc `BackgroundTasks` hoặc executor riêng).
    *   *Đồng nhất đường nghe thử (Preview) và Render:* Đây là ưu điểm lớn nhất của D. Vì dashboard preview và worker `cli.py` đều gọi chung một instance model duy nhất nằm trên RAM của server, **chúng ta loại bỏ hoàn toàn việc tranh chấp GPU**. Không còn cảnh `unload()` model để nhường VRAM qua lại nữa.

---

## 2. Script đo bước 0 (Đo lường trung thực)

Trước khi quyết định code, bắt buộc phải đo thời gian tải lạnh (cold-start) để đánh giá lợi ích thực tế. Dưới đây là mã Python thiết kế riêng cho Bước 0.

Người dùng có thể tạo file `scripts/measure_cold_start.py` và chạy thử:

```python
# scripts/measure_cold_start.py
import time
import sys

def measure_step(name, import_fn, load_fn=None):
    print(f"\n=== Đo lường: {name} ===")
    
    # 1. Đo import time
    t0 = time.perf_counter()
    import_fn()
    t_import = time.perf_counter() - t0
    print(f"  - Thời gian import thư viện: {t_import:.2f} giây")
    
    # 2. Đo load time (nạp model lên CPU/GPU)
    t_load = 0.0
    if load_fn:
        t0 = time.perf_counter()
        load_fn()
        t_load = time.perf_counter() - t0
        print(f"  - Thời gian nạp model lên thiết bị: {t_load:.2f} giây")
        
    return t_import, t_load

# Khai báo các hàm import trì hoãn
def imp_whisper():
    global WhisperModel
    from faster_whisper import WhisperModel

def load_whisper():
    import config
    # Sử dụng model nhỏ nhất để test tốc độ nạp
    _ = WhisperModel("tiny", device="cpu", compute_type="int8")

def imp_vixtts():
    global xttok, XttsConfig, Xtts
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import TTS.tts.layers.xtts.tokenizer as xtok

def load_vixtts():
    import config
    from core import vixtts
    # Chỉ gọi nạp model, không chạy inference
    vixtts._load()

def imp_demucs():
    global main
    from demucs.separate import main

if __name__ == "__main__":
    print("Bắt đầu đo lường Cold-Start trên môi trường hiện tại...")
    results = {}
    
    # Đo hệ thống cơ bản
    t0 = time.perf_counter()
    import torch
    print(f"Import torch thô: {time.perf_counter() - t0:.2f} giây")
    
    # Đo Whisper
    results["whisper"] = measure_step("Whisper ASR", imp_whisper, load_whisper)
    
    # Đo viXTTS (chỉ đo nếu thư mục model tồn tại)
    import config
    if (config.VIXTTS_DIR / "config.json").exists():
        results["vixtts"] = measure_step("viXTTS Clone", imp_vixtts, load_vixtts)
    else:
        print("\n[Bỏ qua viXTTS] Chưa cài đặt hoặc thiếu model viXTTS.")
        
    # Đo Demucs
    results["demucs"] = measure_step("Demucs BGM Separate", imp_demucs, None)
    
    print("\n" + "="*40)
    print("TỔNG KẾT THỜI GIAN CHỜ LẠNH (COLD-START):")
    total_waste = 0.0
    for name, (t_imp, t_load) in results.items():
        print(f" - {name:15}: Import {t_imp:5.2f}s | Load Model {t_load:5.2f}s | Tổng {t_imp+t_load:5.2f}s")
        total_waste += (t_imp + t_load)
    print(f"Tổng thời gian chết do nạp lại mỗi Job: {total_waste:.2f} giây")
    print("="*40)
```

---

## 3. Thiết kế chi tiết cho Phương án D (FastAPI làm Host)

### 3.1. Giao thức IPC
Sử dụng giao thức **HTTP qua Localhost Loopback** (`http://127.0.0.1:8790`).
*   *Vì sao?* Server FastAPI và tiến trình con `cli.py` chạy trên cùng một máy, sử dụng đường truyền loopback nội bộ cực kỳ nhanh.
*   *Truyền dữ liệu:* Sử dụng cơ chế truyền đường dẫn tệp (File Path). Vì cả hai tiến trình dùng chung ổ đĩa (workspace), client chỉ cần gửi JSON `{ "wav_path": "F:/.../audio_16k.wav" }`, server nạp tệp trực tiếp từ đĩa cứng và xử lý, sau đó trả về dữ liệu JSON (đối với ASR) hoặc ghi trực tiếp ra tệp đích (đối với TTS). Điều này tránh hoàn toàn việc truyền tải mảng audio bytes cồng kềnh qua HTTP.

### 3.2. Bảo mật (Authentication)
*   Để tránh các phần mềm khác trên máy Windows của user gọi trộm API model (gây OOM GPU), server khi khởi động sẽ sinh một token ngẫu nhiên `FLOWAPP_IPC_TOKEN = uuid.uuid4().hex`.
*   Token này được truyền vào tiến trình con `cli.py` qua biến môi trường (Environment Variable) khi gọi `subprocess.Popen`.
*   Mọi yêu cầu gọi API nội bộ từ `cli.py` phải đính kèm Header `X-IPC-Token: <token>`. Server chỉ xử lý các request có token khớp.

### 3.3. Quản lý vòng đời Model (Idle Unload)
Để tránh việc GPU bị chiếm dụng VRAM 24/7 khi người dùng treo app nhưng không chạy job:
*   Mỗi khi một model được gọi (preview hoặc render), cập nhật biến thời gian hoạt động cuối: `self.last_active = time.monotonic()`.
*   Một luồng nền (scheduler hoặc background loop của FastAPI) chạy định kỳ mỗi 60 giây để quét:
    ```python
    # Giả lập vòng quét dọn dẹp RAM/VRAM
    if time.monotonic() - self.last_active > config.MODEL_IDLE_TIMEOUT_S (ví dụ: 300 giây):
        self.unload_model() # Giải phóng VRAM bằng gc.collect() và torch.cuda.empty_cache()
    ```

---

## 4. Cancel Semantics: Xử lý khi hủy Job

Khi người dùng nhấn nút Hủy Job (Cancel):
1.  Server gọi `_kill_proc_tree(proc)` để giết chết ngay lập tức tiến trình con `cli.py`.
2.  Nếu `cli.py` đang đợi kết quả từ API HTTP của server (ví dụ đang synth dở một câu viXTTS), kết nối socket sẽ bị đứt đột ngột.
3.  Server phát hiện kết nối bị đóng (`ConnectionResetError` hoặc kiểm tra trạng thái job trong RAM đã bị đổi thành `failed/cancelled`) -> Dừng vòng lặp synth câu tiếp theo ngay lập tức.
4.  **Kết quả:** Hệ thống dừng tức thì, không bị rò rỉ tài nguyên, file ghi dở của `cli.py` bị khóa hủy, không bị lỗi dữ liệu chồng lấn.

---

## 5. Đánh giá mức độ ưu tiên: Có nên làm bây giờ không?

**Khuyến nghị: HOÃN lại và ưu tiên làm hạng mục #16/17 (Tách Monolith) trước.**

*   *Lý do:*
    1.  Việc tách Monolith sẽ thay đổi hoàn toàn cách thức điều phối job (chuyển sang kiến trúc hàng đợi tin nhắn / queue / scheduler sạch sẽ hơn). Nếu làm Model Host trước, chúng ta sẽ phải viết lại toàn bộ phần tích hợp IPC khi cấu trúc điều phối thay đổi.
    2.  Tách Monolith giải quyết vấn đề cốt lõi về độ tin cậy và sự rõ ràng của luồng dữ liệu. Model Host chỉ giải quyết vấn đề thời gian chờ (hiệu năng).
    3.  Khi Monolith đã được tách thành công thành các mô-đun dịch vụ riêng biệt, việc cắm thêm dịch vụ Model Host (Option D hoặc A) sẽ cực kỳ tự nhiên và không dẫm chân lên các phần code stage đang xen kẽ.

---
*Tài liệu phân tích kết thúc. Xin mời phản hồi để thống nhất kế hoạch hành động tiếp theo.*
