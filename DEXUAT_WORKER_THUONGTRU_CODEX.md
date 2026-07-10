# Phản biện worker thường trú — Codex

> Kiểm tra độc lập trên commit `7d59f70`, ngày 2026-07-11. Phạm vi chỉ đọc code
> và log hiện có; không sửa pipeline, server hay cấu hình.

## 0. Kết luận

Chưa nên triển khai worker thường trú ngay. Bước đúng tiếp theo là đo cold/warm
và thêm telemetry đủ tin cậy. Dữ liệu hiện có chỉ gồm 3 job có `run.log`: không
log nào cho thấy Whisper, viXTTS hoặc demucs đã chạy; một job có OCR. Mẫu này quá
nhỏ để kết luận hiệu năng, nhưng chưa có bằng chứng rằng đổi kiến trúc sẽ hoàn
vốn với workflow hiện tại.

Nếu số đo sau đó chứng minh viXTTS được dùng thường xuyên và tiết kiệm trên
khoảng 20–30 giây/job, tôi chọn **A thu hẹp**:

- host là tiến trình riêng, không nằm trong FastAPI dashboard;
- giai đoạn đầu chỉ host viXTTS;
- Whisper chỉ thêm khi log chứng minh nhu cầu;
- chưa host demucs;
- một bộ điều phối GPU, mặc định chỉ một model GPU nặng được resident;
- subprocess `cli.py` per-job, kill-tree và config snapshot vẫn giữ nguyên.

B không phù hợp codebase hiện tại. C có thể làm được nhưng trả gần đủ chi phí
config/cancel lifecycle của B trong khi khó debug hơn A.

## 1. Kiểm chứng facts trên code hiện tại

Các bất biến trong đề xuất vẫn đúng trên `7d59f70`:

- `webui/server.py` có một worker thread và mỗi job chạy bằng
  `subprocess.Popen([python, cli.py, --resume, job_id])` (`:185-228`).
- Override được chụp vào `FLOWAPP_JOB_OVERRIDES` trước lúc spawn (`:214-226`).
- Cancel dùng `taskkill /T /F` trên Windows (`:136-149`) và server thoát sẽ kill
  job đang chạy (`:270-277`).
- Dashboard unload viXTTS trước khi xếp job để tránh hai process giữ VRAM
  (`:79-96`, `:117-125`).
- Whisper được import muộn nhưng tạo `WhisperModel` mới mỗi lần S3 dùng Whisper
  (`core/stages/s3_transcript.py:60-71`).
- viXTTS có model cache và latent cache module-level, nhưng cache chỉ sống trong
  process hiện tại (`core/vixtts.py:19-24, 55-63, 131-150`).
- OCR tạo `ProcessPoolExecutor` mới mỗi lượt (`core/ocr_subs.py:199-213`).
- demucs hiện gọi thẳng `demucs.separate.main()` (`core/separate.py:29-42`),
  không có abstraction model/cache riêng để host chỉ bằng một shim nhỏ.

Một hiệu chỉnh cho ước lượng import: `cli.py` import toàn bộ `core.pipeline`, và
pipeline import tất cả stage ngay lúc khởi động. Dù model nặng được import muộn,
process vẫn trả chi phí import `yt_dlp`, `anthropic`, numpy, pydub, các module
render... mỗi job. Con số 3–8 giây có thể đúng trên máy này nhưng không nên coi
là fact trước benchmark.

## 2. Đánh giá A/B/C và phương án D

### A — Model host riêng: đúng hướng, nhưng không nên ôm cả ba model ngay

Ưu điểm quan trọng nhất của A không chỉ là cache model. Nó giữ nguyên ba ranh
giới đang có giá trị:

1. process job có thể bị giết mạnh;
2. config mỗi job là snapshot mới;
3. crash Python thường của pipeline không làm dashboard chết.

Điểm cần sửa trong đề xuất gốc:

- Không fallback local vô điều kiện. Host có thể mất kết nối nhưng vẫn sống và
  giữ VRAM; lúc đó nạp local dễ OOM. Chỉ fallback sau khi supervisor xác nhận
  host đã chết/đã nhả GPU, hoặc khi feature host bị tắt từ đầu.
- File-path IPC phải có allowlist. Host chỉ được đọc trong `data/jobs`, `voices`
  và model directory; output phải nằm trong job hiện tại. Mọi output ghi file
  tạm rồi `os.replace`, tránh job bị hủy để lại MP3 hợp lệ giả.
- Host phải nhận toàn bộ setting liên quan trong request. Không dùng `config`
  đã import lâu làm nguồn sự thật cho setting per-job.
- Preview và pipeline phải cùng đi qua host; nếu chỉ chuyển pipeline, xung đột
  VRAM với preview vẫn còn.

Không nên host demucs ở vòng đầu. Code hiện dùng CLI Python cấp cao; để giữ model
thật sự cần chuyển sang API `get_model/apply_model`, xử lý chunk/overlap/output
và kiểm chứng output parity. Thời gian tách audio thường lớn hơn thời gian load,
nên ROI của cache demucs có thể thấp.

### B — Pipeline in-process: bác bỏ

B làm hỏng isolation để tiết kiệm startup. Không chỉ cần cờ cancel trong Python:
phải quản mọi child process FFmpeg/yt-dlp/OCR, generator Whisper, request mạng,
GPU inference và cleanup file dở. Một lỗi native/CUDA hoặc leak cũng có thể làm
dashboard chết hoặc phình theo thời gian.

`importlib.reload(config)` không giải quyết sạch config lifecycle: nhiều module
đã import `config` và giữ object/giá trị/cache phát sinh từ lần trước. Mutation
và rollback toàn bộ setting sau mỗi job là một giao thức mới, dễ rò state giữa
job. Lợi ích không tương xứng.

### C — Process ấm: không phải trung gian rẻ như vẻ ngoài

C giữ được hard cancel bằng cách giết worker, nhưng sau mỗi cancel/OOM lại mất
cache. Nó vẫn phải giải quyết config reload, reset module cache, child-process
ownership, state sau exception và chính sách tái sinh. Đây là phần khó nhất của
B, chỉ được đóng trong một process có thể vứt đi.

C chỉ đáng cân nhắc nếu benchmark cho thấy chi phí import Python đáng kể nhưng
không có model cụ thể nào đủ lớn để tách host. Với import dự kiến vài giây, chưa
có lý do chọn C.

### D — GPU broker theo nhu cầu (A thu hẹp)

Phương án tôi chọn thực chất là một biến thể D của A: **một GPU broker, từng
backend được bật theo số liệu**, thay vì một daemon cố giữ Whisper + viXTTS +
demucs cùng lúc.

Giai đoạn 1 chỉ viXTTS vì:

- đã có interface hẹp `synth(text, ref, output, speed)`;
- model và speaker latent đã có cache rõ ràng;
- preview dashboard cũng dùng cùng module;
- thời gian load/VRAM được kỳ vọng lớn nhất;
- mỗi job gọi nhiều câu, nên cancel có thể chặn ở biên từng câu.

Whisper là backend thứ hai nếu tần suất đủ cao. Demucs để cuối hoặc giữ local.

## 3. Có nên đặt model host trong FastAPI dashboard?

Không khuyến nghị.

Các route sync của FastAPI được chạy trong threadpool, nên GPU synth trong một
route `def` không nhất thiết khóa trực tiếp event loop. GIL cũng không phải rủi
ro lớn nhất vì torch/CUDA thường nhả GIL. Rủi ro thật là:

- OOM, lỗi CUDA/native hoặc DLL có thể làm process dashboard mất ổn định;
- model/latent chiếm RAM/VRAM cùng vòng đời với server;
- `vixtts._gpu_lock` có thể làm thread request chờ dài;
- cancel job không thể giết riêng inference mà không giết dashboard;
- restart dashboard vừa làm mất UI vừa làm mất cache/model service.

Host riêng vẫn do dashboard supervisor quản, nên vận hành chỉ tăng một child
process nhưng giữ được ranh giới lỗi. Đây là chi phí đáng trả nếu benchmark xác
nhận ROI.

## 4. Benchmark bước 0

### Nguyên tắc

Không benchmark bằng một process duy nhất rồi gọi mọi thứ liên tiếp. Cần tách:

- **process-cold**: process Python mới, nhưng có thể hưởng OS file cache;
- **machine-cold**: lượt đầu sau reboot;
- **model-warm**: model đã resident trong cùng process;
- **voice-warm**: viXTTS đã có latent của cùng file ref;
- **kernel-warm**: đã chạy inference GPU ít nhất một lần.

Không xóa Windows file cache để tạo số “cold” nhân tạo. Ghi riêng lượt đầu sau
reboot và median các process mới là đủ gần workflow thật.

### Các phép đo

1. Baseline process: mở Python rồi thoát.
2. Import hiện tại: thời gian từ process start đến ngay trước `Job.load`, gồm
   `cli -> pipeline -> stages`.
3. Whisper:
   - import `faster_whisper`;
   - constructor theo `(model, device, compute_type)`;
   - first transcribe trên clip cố định 30–60 giây;
   - second transcribe cùng process.
4. viXTTS:
   - import TTS stack;
   - `_build_model()`;
   - synth đầu với ref A;
   - synth lần hai cùng ref A;
   - synth với ref B để tách lợi ích latent cache.
5. Demucs:
   - import;
   - load model;
   - xử lý clip 30–60 giây;
   - lượt hai cùng process nếu dùng API cache được.
6. OCR: thời gian spawn pool + init RapidOCR riêng với 16 frame và 200 frame.

Mỗi case process-cold chạy tối thiểu 3 lần; warm chạy 5 lần. Ghi wall time,
peak RSS, VRAM trước/sau/peak, model/device/compute, phiên bản package, kích thước
input và trạng thái OS-cache. Model/checkpoint phải tải sẵn; không để network
download lẫn vào thời gian load.

Kết quả cần báo median và p90 hoặc min/max, không chỉ một lượt đẹp nhất. Script
benchmark phải chạy subprocess cho từng case và xuất JSONL/CSV để lần sau so
được sau nâng cấp package.

### Ước lượng trước đo trên RTX 3070/Windows

Đây chỉ là khoảng dự kiến, không phải số đo của repo:

| Thành phần | Cold/load dự kiến | Warm lại | Ghi chú |
|---|---:|---:|---|
| Python + import pipeline | 1–6 s | không áp dụng | phụ thuộc antivirus và OS cache |
| Whisper small GPU | 2–10 s | gần 0 s load | first inference còn warm CUDA |
| Whisper small CPU | 1–6 s | gần 0 s load | inference mới là phần lớn chi phí |
| viXTTS | 10–40 s | gần 0 s load | first synth/latent thêm vài giây |
| demucs htdemucs | 3–15 s load | gần 0 s load | separation thường lớn hơn load |
| RapidOCR pool 4 process | 1–6 s init | pool hiện không sống qua job | cần đo riêng |

Ngưỡng quyết định nên dựa trên **giây tiết kiệm trung bình mỗi job thực tế**, ví
dụ `tần suất_backend × load_saved`, không dựa trên case viXTTS đẹp nhất.

## 5. Telemetry sử dụng thực tế

Log hiện tại không đủ tốt để thống kê model: không có event chuẩn cho backend
load/hit/unload và không có duration stage. Ba log còn lại trên máy không có
dấu hiệu Whisper/viXTTS/demucs; chỉ một log ghi OCR. Không nên suy rộng từ mẫu
này.

Trước khi đổi kiến trúc, thêm event một dòng dạng JSON hoặc key-value:

```text
MODEL backend=vixtts event=load seconds=18.42 vram_mb=2870 cache=miss
MODEL backend=vixtts event=synth seconds=3.10 latent=hit job=...
STAGE name=tts seconds=94.2
```

Cần thống kê ít nhất 20–30 job đại diện hoặc 1–2 tuần workflow thật. Không ghi
text thoại, API key hay đường dẫn nhạy cảm vào telemetry.

## 6. IPC và vòng đời cho phương án D

### Giao thức

Chọn HTTP trên `127.0.0.1`:

- codebase đã dùng FastAPI/Pydantic và HTTP client;
- dễ timeout, health check, log request id và phân loại lỗi;
- hỗ trợ cả subprocess pipeline lẫn preview dashboard;
- dễ kiểm thử hơn protocol JSONL tự viết.

`multiprocessing.connection`/named pipe tránh port nhưng phải tự làm framing,
timeout, reconnect, multiplex và error schema. `stdin-jsonl` không hợp vì host
có hai loại client độc lập và cần cancel/health check.

Host bind port `0` để Windows chọn port trống. Supervisor nhận handshake gồm
port/protocol version, sinh token ngẫu nhiên theo phiên và truyền endpoint/token
vào child job qua env. Chỉ bind loopback, vẫn xác thực bearer token để process
local khác không gọi tùy ý.

### Vòng đời

- Dashboard spawn host nhẹ khi startup hoặc lazy trước job/preview đầu tiên;
  host chưa load model.
- Supervisor giữ process handle, health check khi cần và restart khi host chết.
- Server thoát thì terminate host; startup mới dọn descriptor/PID stale.
- Model idle 10 phút là mặc định khởi đầu hợp lý, nhưng timeout phải được chọn
  từ phân bố khoảng cách giữa job. Host process vẫn sống sau khi unload.
- Preview lúc GPU đang chạy job nên xếp sau hoặc trả “GPU đang bận”; không được
  load model thứ hai hay preempt job.

### Cache key

- Whisper model: `(model_name/path, revision, device, compute_type)`.
- viXTTS model: canonical checkpoint/config/vocab identity + mtime/size + device.
- viXTTS latent: canonical ref path + mtime + size; đổi voice chỉ invalid latent,
  không reload checkpoint.
- `TARGET_LANG`, prompt, text, speed không phải model key; chúng là request data.
- Host trả protocol/model version trong response để log và debug.

Không cố giữ Whisper GPU và viXTTS đồng thời trên 8 GB. Chính sách ban đầu nên
đơn giản: một model GPU nặng resident; request backend khác thì unload model cũ,
`gc.collect`/`cuda.empty_cache`, rồi load model mới. CPU Whisper có thể coexist.
LRU nhiều model chỉ thêm sau khi đo VRAM thật chứng minh an toàn.

## 7. Cancel semantics

HTTP client bị kill không tự dừng GPU inference trong host. Vì vậy mọi request
phải có `job_id` và `request_id`; host có registry trạng thái và endpoint cancel.

Với viXTTS, S5 đã gọi theo từng segment. Cancel mềm sẽ:

1. đánh dấu job canceled;
2. không nhận segment kế tiếp;
3. bỏ output của segment đang chạy;
4. dừng ở biên inference hiện tại.

Không nên cố ngắt CUDA giữa một `model.inference()` bằng thread exception. Nếu
user cần hard cancel như hiện tại, supervisor kill cả process host khi request
đang chạy thuộc job bị hủy, rồi spawn host sạch. Mất cache là chấp nhận được;
đúng nghĩa cancel quan trọng hơn giữ model ấm.

Luồng cancel đầy đủ:

```text
UI Hủy
  -> server đánh dấu job canceled
  -> taskkill cây cli.py như hiện tại
  -> host.cancel(job_id)
  -> nếu inference không dừng trong grace ngắn: kill/restart host
  -> xóa file tạm; checkpoint stage vẫn quyết định resume
```

Với Whisper, generator có thể kiểm tra cancel giữa các segment. Hard cancel vẫn
dùng kill/restart host nếu native inference không trả quyền điều khiển kịp.

## 8. Phác thảo module và luồng

Phạm vi tối thiểu sau khi benchmark đạt ngưỡng:

- `core/model_client.py`: protocol, timeout, retry, error classification;
- `core/model_host.py`: process HTTP nội bộ, health/cancel endpoints;
- `core/model_runtime.py`: GPU lock, resident backend, cache key, idle unload;
- `webui/model_host_manager.py`: spawn/watchdog/terminate, endpoint+token;
- `core/vixtts.py`: adapter host/local cùng một interface;
- `core/stages/s3_transcript.py`: adapter Whisper ở giai đoạn sau;
- `tools/bench_models.py`: benchmark bước 0, tách khỏi production pipeline.

Luồng:

```text
Dashboard queue ----spawn----> cli.py --resume JOB
       |                           |
       | preview                   | model request + explicit settings
       v                           v
 model_client ----------------> model_host process
                                  |
                                  v
                        GPU broker / one resident model
                                  |
                                  v
                       temp output -> atomic replace
```

Pipeline phải chạy được ở `local` mode như hiện tại trong giai đoạn rollout.
Chế độ `host` chỉ được bật khi supervisor khỏe; không tự chuyển local trong lúc
host không rõ còn giữ VRAM hay không.

## 9. Thứ tự so với tách monolith #16/17

Thứ tự ít dẫm chân nhau nhất:

1. Làm benchmark + telemetry trước; đây là thay đổi nhỏ và cho quyết định thật.
2. Tách phần queue/worker/process lifecycle khỏi `webui/server.py` thành module
   backend riêng trong hạng mục monolith.
3. Tách frontend `index.html` có thể làm độc lập; nó không chặn model host.
4. Thu đủ dữ liệu. Nếu đạt ngưỡng, thêm model-host manager cạnh worker manager,
   trước tiên chỉ cho viXTTS.
5. Sau rollout ổn định mới đánh giá Whisper; demucs cuối cùng.

Tách backend monolith trước làm A dễ hơn vì ownership spawn/cancel/watchdog có
một chỗ rõ ràng và giảm xung đột khi cùng sửa `server.py`. Không cần đợi toàn bộ
frontend #17 hoàn tất mới benchmark hoặc thiết kế protocol.

## 10. Quyết định đề xuất

**Hiện tại: HOÃN implementation worker thường trú.** Chấp nhận bước đo và
telemetry ngay khi user chốt code. Song song, ưu tiên tách worker lifecycle khỏi
monolith backend.

**Điều kiện mở lại:** dữ liệu workflow thật cho thấy load model chiếm phần đáng
kể, ưu tiên viXTTS, với lợi ích kỳ vọng ít nhất khoảng 20–30 giây/job hoặc giảm
rõ độ trễ preview lặp lại.

**Khi mở lại:** làm D/A-thu-hẹp bằng host process riêng + HTTP loopback + GPU
độc quyền + hard-cancel bằng kill/restart host. Không chọn B; không chọn C trừ
khi benchmark chỉ ra import startup mới là nút thắt chính.
