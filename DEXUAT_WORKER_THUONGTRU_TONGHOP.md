# Tổng hợp 3 phía — worker thường trú (chốt để user duyệt)

> Claude đối chiếu `DEXUAT_WORKER_THUONGTRU_CODEX.md` + `_GEMINI.md` (2026-07-11).
> Trạng thái: KẾT LUẬN THẢO LUẬN — chưa code.

## 1. Đồng thuận 3/3 (chốt luôn)

1. **HOÃN worker thường trú.** Chưa có bằng chứng hoàn vốn: Codex soi 3 run.log
   còn lại trên máy — không job nào chạy Whisper/viXTTS/demucs (OCR + edge).
   Tiền đề "tiết kiệm 15–40s/job" chỉ đúng với workflow khác workflow hiện tại.
2. **Bác phương án B** (in-process) — phá kill-tree cancel + config lifecycle,
   crash native/CUDA kéo sập dashboard. **Bác C** (pool ấm) — trả gần đủ chi phí
   của B mà khó debug hơn A.
3. **Bước 0 trước mọi quyết định**: benchmark cold/warm + TELEMETRY sử dụng thật
   (log `MODEL backend=... event=load seconds=... cache=hit/miss` + `STAGE
   name=... seconds=...` vào run.log), thống kê 20–30 job thật rồi mới quay lại.
4. **Ưu tiên #16/17 (tách monolith) TRƯỚC** — cả hai độc lập cùng kết luận:
   tách phần queue/worker/process-lifecycle khỏi server.py xong thì cắm model
   host vào là tự nhiên, không dẫm chân.
5. Nếu làm host: **HTTP loopback + token ngẫu nhiên truyền qua env** (2 bên
   cùng thiết kế giống nhau đến bất ngờ), truyền FILE PATH không truyền bytes,
   idle-timeout nhả VRAM, preview dashboard cũng đi qua host (hết vụ
   `vixtts.unload()` đá VRAM qua lại).

## 2. Điểm 2 bên khác nhau — phân xử

**Host đặt Ở ĐÂU?** Gemini muốn host TRONG server FastAPI (đỡ 1 tiến trình,
threadpool + GIL-release lo phần chạy); Codex muốn host RIÊNG (A thu hẹp).

Tôi theo **Codex**, vì:
- Lợi thế lớn nhất Gemini nêu cho D-in-server ("hết tranh chấp VRAM
  preview/render") **phương án host riêng CŨNG có** — preview đi qua host là hết
  tranh chấp, không cần ở chung tiến trình.
- Rủi ro Gemini chưa trả lời được: OOM/lỗi CUDA/DLL trên stack GPU Windows là
  loại lỗi CHẾT TIẾN TRÌNH (máy này từng dính torchcodec DLL) — host trong
  server nghĩa là mất luôn dashboard; host riêng chỉ mất cache, watchdog dựng lại.
- Cancel của Gemini (phát hiện client đứt socket để dừng synth) mỏng manh —
  server không phát hiện đáng tin kết nối chết GIỮA một `model.inference()`.
  Thiết kế Codex đúng hơn: request mang job_id, endpoint cancel tường minh,
  không dừng kịp trong grace thì kill/restart host (mất cache chấp nhận được —
  "đúng nghĩa Hủy quan trọng hơn giữ model ấm").
- Codex cũng chỉnh đúng 2 điểm trong đề xuất gốc của tôi: (a) KHÔNG fallback
  nạp local vô điều kiện khi IPC lỗi (host có thể còn sống giữ VRAM → local
  load là OOM); (b) demucs không nên host vòng đầu (code đang gọi CLI cấp cao,
  muốn cache phải chuyển hẳn sang API get_model/apply_model — ROI thấp vì thời
  gian tách > thời gian load).

**Benchmark**: script mẫu của Gemini là khởi điểm tốt nhưng đo MỌI THỨ trong 1
tiến trình (whisper import xong mới đo vixtts → torch đã ấm, số vixtts đẹp giả).
Phương pháp Codex đúng: MỖI case một subprocess, tách process-cold / machine-cold
/ model-warm / latent-warm, ghi median + p90 ra JSONL. Script cuối = khung
Gemini + kỷ luật Codex.

## 3. Kế hoạch chốt (chờ user duyệt)

- **W-0 (nhỏ, làm được ngay khi user gật):** `tools/bench_models.py` (per-case
  subprocess, JSONL) + telemetry MODEL/STAGE 1-dòng vào run.log. Không đổi hành
  vi pipeline. Từ đây về sau cứ dùng app là số liệu tự tích luỹ.
- **W-1 = hạng mục #16 (backend):** tách queue/worker/process-lifecycle khỏi
  `webui/server.py` thành module riêng (đường cho model-host manager sau này).
- **W-2 (chỉ khi telemetry nói có lãi ≥20–30s/job, ưu tiên viXTTS):** model host
  RIÊNG theo thiết kế Codex mục 6–8: HTTP loopback port tự chọn + bearer token,
  1 model GPU resident (đổi backend = unload cũ nạp mới), cache key rõ ràng,
  allowlist path, output ghi tạm + os.replace, cancel endpoint + kill/restart
  host làm hard-cancel, viXTTS trước → Whisper sau → demucs không host.
- **#17 (frontend index.html)**: độc lập, làm lúc nào cũng được.

## 4. Trạng thái

User chưa chốt. Câu hỏi đang chờ: (1) làm W-0 (bench + telemetry) ngay?
(2) bắt đầu W-1/#16 tách backend? Tab phối/test giọng vẫn xếp hàng riêng.
