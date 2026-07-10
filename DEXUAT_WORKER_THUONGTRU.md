# Đề xuất: worker THƯỜNG TRÚ (giữ model trong RAM) — thảo luận 3 phía

> Claude soạn 2026-07-11 theo yêu cầu user, để Codex + Gemini phản biện độc lập
> (cùng vai trò kỹ sư trên repo). Đây là hạng mục #3 của audit toàn app — hạng
> mục LỚN cuối cùng cùng với tách monolith (#16/17). **Chưa code — tài liệu
> thảo luận.** Trả lời vào `DEXUAT_WORKER_THUONGTRU_CODEX.md` /
> `_GEMINI.md` cạnh file này; user chốt phương án rồi mới làm.
> Luật dự án: chỉ ĐỌC code khi phân tích; mọi trích dẫn tự kiểm chứng lại.

## 1. Kiến trúc hiện tại (facts, đã kiểm trên commit 53d0e06)

- 1 worker THREAD trong server, chạy job tuần tự; **mỗi job = 1 SUBPROCESS**
  `cli.py --resume <id>` (`webui/server.py:224-228`), stdout/stderr → run.log,
  override per-job truyền qua env `FLOWAPP_JOB_OVERRIDES` (`:214-221`).
- **Hủy job = kill cây tiến trình** (`_kill_proc_tree`, xử lý cả race lúc Popen
  khởi động — `:229-237`). Server tắt → atexit kill job đang chạy. Checkpoint
  theo stage (`completed_stages`) nên "Chạy tiếp" nối lại được.
- **Config semantics dựa vào tiến trình mới**: `config.py` chạy
  `load_dotenv(override=True)` lúc import — mỗi job đọc .env TƯƠI + áp override
  job một lần, sống trọn đời tiến trình. Không có cơ chế reload trong process.
- **Model nặng nạp lại MỖI job** (trong tiến trình con):
  - faster-whisper (S3, chỉ khi OCR không dùng được): nạp model + (tùy máy) DLL
    CUDA. WHISPER_MODEL=small/cpu-int8 hiện tại.
  - viXTTS (S5, khi engine=vixtts hoặc câu cast voice_ref): nạp checkpoint XTTS
    lên GPU — nặng nhất (ước 15–40s + ~2–3GB VRAM; CẦN ĐO thật trước khi chốt).
  - demucs (S6, KEEP_BGM=1): nạp htdemucs mỗi lần tách.
  - RapidOCR (S3): pool N tiến trình OCR riêng per job.
  - Import Python + torch/TTS stack: ~3–8s mỗi lần spawn (cần đo).
- **Điều phối VRAM hiện tại**: dashboard có thể giữ viXTTS (nghe thử) →
  `_enqueue` gọi `vixtts.unload()` trước khi spawn worker (`server.py:89-95`,
  `core/vixtts.py:unload` có `_gpu_lock`) — tránh 2 tiến trình cùng ôm GPU 8GB.

## 2. Chi phí thật sự tiết kiệm được — ĐỪNG quyết trước khi đo

Lưu ý quan trọng: với workflow HIỆN TẠI của user (OCR hardsub + engine **edge** +
KEEP_BGM=flat), mỗi job chỉ tốn **import stack (~3–8s)** — Whisper không chạy
(OCR gate), viXTTS không chạy (edge, trừ câu cast), demucs không chạy. Lợi ích
lớn CHỈ xuất hiện khi: video không hardsub (Whisper), engine viXTTS/casting
nhiều, hoặc KEEP_BGM=1 (demucs).

Đề nghị bước 0 (làm trước mọi quyết định): script đo cold-start từng thành phần
trên máy này (import, whisper load, vixtts load, demucs load) + thống kê tần suất
dùng từng model trong run.log các job gần đây → con số "giây tiết kiệm / job
thực tế". Nếu ra < 10s/job với workflow hiện tại thì đề xuất của tôi là HOÃN
hạng mục này (ưu tiên #16/17 tách monolith trước).

## 3. Ba phương án

### A — "Model host" riêng (tách phần đắt, giữ nguyên phần lành)
Daemon nhỏ (tiến trình riêng, hoặc chính server) giữ model sống: Whisper +
viXTTS (+ demucs?). `cli.py` per-job VẪN NHƯ CŨ, nhưng thay vì tự nạp model thì
gọi model host qua IPC local (HTTP 127.0.0.1 riêng port / named pipe):
- API dạng file-path-in file-path-out (cùng máy → không serialize audio):
  `POST /asr {wav_path} → segments`, `POST /tts {text, ref, speed, out_path}`.
- Idle-timeout: không job nào dùng X phút → tự unload nhả VRAM (preview của
  dashboard cũng chuyển sang gọi host → hết vụ unload() đá qua lại).
- GIỮ nguyên: kill-tree cancel (pipeline process vẫn giết được; host không chết
  theo), .env tươi mỗi job, crash 1 job không kéo model host sập (host chỉ chết
  nếu chính nó crash — supervisor restart).
- Nhược: thêm 1 tiến trình phải quản (spawn khi nào? theo server?), lỗi IPC phải
  fallback nạp local như cũ (không được chết job), thêm mặt cắt để debug.

### B — Worker thường trú chạy pipeline IN-PROCESS
Bỏ subprocess: worker (thread hoặc process con SỐNG LÂU) import stages 1 lần,
model cache module-level, chạy job nối nhau.
- Ưu: nhanh nhất có thể, không IPC, ít code mới nhất.
- Nhược (đắt):
  1. **Cancel đổi bản chất**: đang kill-tree ăn ngay giữa stage → phải chuyển
     sang cancel HỢP TÁC (cờ kiểm giữa các bước; ffmpeg/demucs đang chạy phải
     tự kill con). Nhiều điểm chọc.
  2. **Config semantics vỡ**: `config.py` là module toàn cục đọc 1 lần — phải
     làm reload-per-job + áp/gỡ FLOWAPP_JOB_OVERRIDES thủ công. Đây đúng vùng
     từng có bug (load_dotenv override) và vùng resolver U-2 vừa phải tách vì
     mutation config trong server là race.
  3. Crash/leak 1 job (torch OOM, DLL hỏng) → worker chết/phình RAM → cần vòng
     tái sinh process định kỳ → lại quay về gần phương án C.
  4. VRAM bị giữ liên tục → đá nhau với nghe thử viXTTS của dashboard.

### C — Pool tiến trình ẤM (trung gian)
Giữ subprocess per-job nhưng pre-spawn sẵn 1 tiến trình "ấm" đã import stack
(chưa nạp model), nhận job qua lệnh; model cache SỐNG QUA CÁC JOB trong tiến
trình ấm; tái sinh sau N job / khi RSS vượt ngưỡng / khi user đổi engine.
- Ưu: tiết kiệm import + model load giữa các job liên tiếp; cancel = kill tiến
  trình ấm (mất cache, tự spawn lại — chấp nhận được).
- Nhược: config per-job phải reload trong tiến trình ấm (nhược 2 của B, nhẹ hơn
  vì được phép giết bỏ bất kỳ lúc nào); phức tạp vòng đời (ấm ↔ chạy ↔ tái sinh).

## 4. Khuyến nghị sơ bộ của Claude

1. **Bước 0 bắt buộc**: đo (mục 2). Số xấu → hoãn, làm #16/17 trước.
2. Nếu số đẹp (ví dụ viXTTS/Whisper dùng thường xuyên, tiết kiệm >30s/job):
   chọn **A (model host)** — vì nó là phương án DUY NHẤT không đụng vào 3 bất
   biến đang lành: kill-tree cancel, .env-tươi-mỗi-job, crash isolation. Phạm vi
   A gọn: `core/model_host.py` (FastAPI mini hoặc socket server) + 2 client shim
   trong `s3_transcript`/`vixtts.synth` có fallback local. Nghe thử dashboard
   chuyển sang gọi host → xoá luôn vụ `vixtts.unload()` đá VRAM.
3. B chỉ đáng nếu chấp nhận viết lại cancel + config lifecycle — tôi thấy rủi ro
   > lợi ích ở codebase này. C là fallback nếu A bị chê phức tạp vận hành.

## 5. Rủi ro chung phải trả lời trước khi code (bất kể phương án)

- **VRAM 8GB**: viXTTS (~2-3GB) + demucs (~2GB) + Whisper-cuda cùng sống được
  không? Chính sách trục xuất (LRU? chỉ 1 model GPU tại một thời điểm?).
- **Đổi cấu hình model** (WHISPER_MODEL, VIXTTS_VOICE mới, TARGET_LANG...):
  host phải phát hiện và nạp lại — key cache là gì?
- **Windows**: DLL dance (FFMPEG_SHARED_BIN, cublas add_dll_directory) trong
  host; named pipe vs localhost port (port thứ 2 cần tránh đụng).
- **Đo lường trung thực**: log per-job "model đã ấm/nạp mới, tiết kiệm Xs" để
  biết tính năng có trả tiền thuê nhà không.

## 6. Câu hỏi cho Codex / Gemini

1. Phản biện phân tích A/B/C — đặc biệt: có phương án D nào tốt hơn không
   (vd: model host CHÍNH LÀ server FastAPI hiện tại — thêm endpoint nội bộ,
   khỏi tiến trình mới; đánh giá rủi ro GIL/blocking event-loop khi synth GPU
   trong server)?
2. Ước lượng của bạn về chi phí nạp từng model trên RTX 3070/Windows (hoặc cách
   đo rẻ nhất) — thiết kế script đo bước 0 thế nào cho ra số đáng tin?
3. Với phương án A: giao thức IPC nào hợp Windows + codebase này nhất (HTTP
   localhost / multiprocessing.connection / stdin-jsonl)? Cách quản vòng đời
   host (server spawn? watchdog? idle unload bao lâu)?
4. Cancel semantics: phương án bạn chọn xử lý "Hủy job" đang synth GPU thế nào?
5. Có đáng làm BÂY GIỜ không, so với #16/17 (tách monolith) — thứ tự nào ít
   dẫm chân nhau nhất (tách monolith trước có làm A dễ hơn không)?
6. KHÔNG code. Ghi phân tích + phương án bạn chọn (kèm phác thảo module/luồng)
   vào file trả lời của mình.
