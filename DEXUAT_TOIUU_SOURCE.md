# ĐỀ XUẤT: Tối ưu source code — danh sách việc ĐO ĐƯỢC, xếp theo lợi-ích/rủi-ro

> Kết quả audit 2026-07-13 (ruff + vulture + 5 agent đọc code song song + bench
> thật trên máy desktop + kiểm chứng đối kháng 12 đề xuất nặng ký). Gửi Codex/
> Gemini soi thêm nếu muốn (`*_CODEX.md`/`*_GEMINI.md`). User chốt đợt ở mục 5.
> KHOAN CODE cho tới khi chốt.

## 0. Kết luận tổng — nói thật trước

Codebase KHÔNG bừa: ruff chỉ 30 cảnh báo/14.590 dòng (14 là lazy-import CÓ chủ
đích), vulture **0 dead code Python**, **0 hàm JS mồ côi** (đã grep chéo 188
hàm + 51 biến qua cả 6 file lẫn onclick trong index.html). Phần "dọn nhà" lớn
đã làm dần các đợt trước. Vậy nên KHÔNG đại phẫu — dưới đây là việc chọn lọc
có lợi ích thật, chia 3 đợt nhỏ, mỗi đợt tự đứng + test riêng.

## 1. Đợt V-1 — Quick wins an toàn (rủi ro THẤP, ~1 buổi, không đụng pipeline)

| ID | Việc | Lợi ích đo được |
|---|---|---|
| LINT-1 | `ruff --fix` nhóm auto-fix + sửa tay 8 F401 (ĐÃ verify từng cái không phải probe-import: atexit + 3 tên worker thừa ở server.py, `from webui import worker` thừa ở routes_editor, time ở common...) + UP035 typing.Callable deprecated | ruff 30 → 0: từ nay regression thật nổi bật ngay |
| PERF-3 | Dời import apscheduler + `_start_trending_scheduler()` khỏi lúc import module → thread nền/lifespan | −0.7s MỖI lần restart server (uvicorn không --reload — restart là thao tác lặp nhiều nhất khi dev) |
| DUP-2 | `/segments`: parse state.json 3 lần → 1; `_read_env()` gọi TRONG dict-comprehension = đọc .env 21 lần + 1 lần nữa cho engine_caps → 1 biến dùng chung | Bỏ 24 lần đọc/parse file mỗi lần mở editor; hết rủi ro snapshot .env nửa cũ nửa mới trong 1 request |
| DUP-3 | Đưa `_errDetail` (đang kẹt trong app-trending.js) thành helper chung; 5 chỗ đang gọi `(await res.json()).detail` KHÔNG guard (app-visual xóa job...) | Server 500 dạng text → hiện toast lỗi thay vì nút chết im lặng |
| ROBUST-1 | openGloss: `.catch` gắn nhầm vào `.json()` thay vì `fetch()` → server đang restart là unhandled rejection, modal không mở không báo gì | Sửa đúng tình huống xảy ra thường xuyên (restart server mỗi lần sửa .py) |
| LEAK-1 | openEditor gắn `resize` listener mỗi lần mở, không bao giờ gỡ — mà openEditor được GỌI LẠI tự động sau mỗi lần render xong | Hết rò listener tăng vô hạn trong phiên sửa-render nhiều vòng |
| LEAK-2 | Nút 🔊 tab Cấu hình tạo blob URL không bao giờ revoke (pattern revoke đã có sẵn ở edPreview — áp lại) | Hết rò vài chục KB–1MB mỗi lần bấm nghe thử |
| JS-1 | #pending-bar bị gán innerHTML lại MỖI tick 3s kể cả khi không đổi → nút ⏸/▶ bị hủy-tạo ~20 lần/phút, click rơi đúng lúc thay node bị NUỐT | Cache chuỗi như lastJson của card job — click hết hụt |
| SAFE-1 | `except Exception: pass` quanh đọc env_overrides ở worker (+ resume_job): state.json bị khoá → job chạy KHÔNG override per-job mà không vết nào | Thêm 1 dòng print cảnh báo — hết "app lờ cấu hình" âm thầm |

## 2. Đợt V-2 — Hiệu năng lớn nhất (đây là món chính)

**PERF-1 — OCR: ProcessPool đang SCALING ÂM trên desktop** (verdict: đáng làm)

Bench thật trên chính video job của user (720p, đúng biến đổi production):
- Tuần tự 1 engine: **447–465 ms/frame** (intra_op 2/8/default gần như nhau —
  onnxruntime không ăn thêm luồng).
- Pool: 1w=465 · 2w=601 · **4w=542–817 (máy đang dùng)** · 6w=855 · 10w=879
  ms/frame — CÀNG NHIỀU WORKER CÀNG CHẬM, cộng 20–27s khởi động pool (spawn +
  nạp model ×4). Log production còn tệ hơn: 848 frame mất **1334–1580s**
  (~1.6–1.9 s/frame) — stage ĐẮT NHẤT pipeline.

Việc: thêm nhánh chạy TUẦN TỰ trong tiến trình khi `OCR_WORKERS=1` (tái dùng
engine đã nạp lúc probe, bỏ lớp pool) + đổi khuyến nghị/auto cho desktop.
Kỳ vọng: OCR 848 frame ~1334–1580s → **~380–400s** (tiết kiệm 15–20 phút MỖI
video 7 phút). Verify: clone job chạy OCR trước/sau, transcript phải giống
từng byte (cùng `_ocr_one`, chỉ bỏ lớp pool).

**PERF-2 — /api/stats rglob toàn bộ data/jobs mỗi 10 giây**: cache TTL 30–60s
cho `_dir_size` + tổng transcript (50 job ≈ 10–15k file → 0.5–2s đĩa/nhịp vô
ích hiện nay).

## 3. Đợt V-3 — Đúng đắn / chống lệch (cần cẩn thận hơn, có test parity)

- **DUP-4** (verdict: đáng làm — TÌM RA 1 LỆCH THẬT): parse bool env có 3 idiom
  rải ~18 chỗ, cho kết quả KHÁC nhau với giá trị bất thường. Ca thật:
  `TTS_SINGLE_VOICE=` (rỗng, sửa tay) → config.py ra **False** (2 giọng) nhưng
  /override-impact qua `voicesig._truthy` ra **True** (1 giọng) → impact dự
  đoán khác S5 làm thật — đụng đúng thiết kế chốt voicesig-parity. Việc: MỘT
  helper `env_bool(v, default)` dùng chung + parity test.
- **GON-1** (verdict: đáng làm, verify đúng 6/6): 6 bản copy helper đo thời
  lượng ffprobe → 1 hàm `core/ffmpeg.probe_duration(path, default)` + **thêm
  timeout** (hiện cả 6 chỗ KHÔNG timeout — file nguồn hỏng là ffprobe treo,
  job kẹt vô hạn). Đã kiểm: 0 chỗ bắt CalledProcessError → đổi an toàn.
- **DUP-5**: voicesig.from_env là BẢN THỨ 3 của factory defaults (paid voices,
  clamp...) nhưng CLAUDE.md chỉ ghi quy tắc 2 nơi → bổ sung tài liệu + đưa vào
  drift-check (không sửa code — trùng là chủ đích để resolver thuần).
- **RM-17**: tự động hoá drift-check schema ↔ config.py (script so default đã
  từng chạy tay trong đợt G — biến thành `scripts/check_defaults.py` chạy
  trước commit).

## 4. KHÔNG làm (kiểm chứng đối kháng đã bác / lợi ích không đủ)

- **DUP-1 gộp editor/visual UI** — verdict KHÔNG ĐÁNG: trùng lặp có thật
  (~250 dòng) nhưng ngữ nghĩa 2 bên khác nhau CÓ CHỦ ĐÍCH (cover 'auto' vs
  'none', readOpts('vis') sẽ crash), tiền lệ viện dẫn sai 2/3. Để nguyên.
- Chuyển ES modules / thêm type-hints toàn cục / đổi cấu trúc thư mục — không
  lợi ích đo được, rủi ro load-order (RM-3).
- Cache decode pydub giữa S5/S7 (~10–15s/job trên nền TTS 76–614s), gom ffmpeg
  per-câu (chỉ 3/62 câu tràn), numpy micro-opt — đã đo, không đáng.
- 14 cảnh báo E402 — lazy-load chủ đích, giữ nguyên.

## 5. User chốt theo số

1. **V-1** quick wins (9 mục bảng trên) — OK?
2. **V-2** OCR tuần tự + stats cache (kèm verify OCR clone byte-for-byte) — OK?
3. **V-3** bool-parse hợp nhất + ffprobe hợp nhất + drift-check — OK?
4. Thứ tự đề xuất: V-2 trước (lợi nhất) → V-1 → V-3. Mỗi đợt: code → test →
   review đối kháng → commit riêng. OK?

## Phụ lục: BẢN ĐỒ RỦI RO (RM-1..17 — đọc trước MỌI đợt tối ưu, đã verify từng mục)

Vùng cấm đụng / đụng phải có parity test (chi tiết đầy đủ trong audit log):
sig giọng 2-nơi phải khớp từng byte kể cả clamp/format `:b{x:g}`/ngưỡng 1.001
(RM-1/2) · thứ tự nạp 6 file JS + global scope, cấm ES module (RM-3) · biến vô
hướng worker qua `worker.X` (RM-4) · marker migration PROSODY/EMOTION trong
.env, write_env phải giữ comment (RM-5) · unset = XOÁ key, cấm ghi default vào
file (RM-6) · trim_silence MỘT thước đo chung S5/S7, cấm đổi thresh/pad (RM-7)
· cross-term round-trước-ceil + cặp EDGE_RATE_MAX 2 nơi (RM-8) · budget_left
nhận style PER-SEGMENT từ fit_report, cấm đọc config toàn cục (RM-9) · contract
box OCR: trừ pad ở pixel, crop_top round 2 chữ số dùng chung, pad đen 5:1
(RM-10) · allow_empty mặc định False (RM-11) · print lúc import config = ASCII
+ try/except (RM-12) · tombstone STRETCH_SHORT giữ 1 release (RM-13) · format
marker ducked.mode (RM-14) · trường `character` không được rớt khi build lại
transcript (RM-15) · thêm knob per-job = cập nhật đủ bộ allowlist/depth/UI
(RM-16) · default 2 mặt schema↔config (RM-17).
