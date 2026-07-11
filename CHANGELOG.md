# Nhật ký làm việc

Mỗi phiên làm việc (bất kể máy nào) ghi một mục vào ĐẦU file này — máy kia pull về
đọc là biết chuyện gì đã xảy ra, không phải lần commit hay lục transcript chat.
Bài học: danh sách đề xuất #1–#18 từng bị mất vì chỉ nằm trong hội thoại một máy.

---

## 2026-07-11 (8) — Desktop (F:\MyProject\vietsubvideo)

### Đợt G: làm lại tab ⚙️ Cấu hình trên nền settings schema (G-A→G-D một mạch)

Theo DEXUAT_CAUHINH_TAB_TONGHOP.md (đồng thuận 3 agent + user chốt "làm 1 mạch",
FRAME phương án A, expose hết knob mới kể cả cookies kèm cảnh báo riêng tư).

**G-A backend (nền):**
- MỚI `webui/settings_schema.py` — nguồn sự thật DUY NHẤT cho mọi khóa .env
  (81 khóa: 73 safe + 8 secret; default/options/secret/allow_empty/profile/
  max_len + `validate()`). Server sinh SAFE/SECRET/FACTORY_DEFAULTS/
  PROFILE_KEYS/EMPTY_OK từ đây — hết lệch 3 nơi (bug ELEVENLABS_MODEL không UI).
- `webui/envfile.py` viết lại: quote/escape chuẩn dotenv (fix bug Codex: giá trị
  chứa #/quote ghi thô sẽ parse sai lần đọc sau) + `write_env(updates, unset)`
  nguyên tử; **unset = XOÁ key khỏi .env** → về factory default (app đổi default
  phiên bản sau vẫn ăn theo).
- `POST /api/config` validate theo schema (400 kèm lý do), nhận `"_unset"`;
  `GET /api/config` trả thêm `factory` + `pinned` + `frame_files` +
  `youtube_api_key_set`. `GET /api/capabilities` MỚI (probe rẻ: GPU nvidia-smi,
  ffmpeg + encoder H.264 thật, find_spec 5 package, đủ bộ file viXTTS, engines
  theo env tươi, disk; cache 60s + `?refresh`). Fix find_spec("pyannote.audio")
  raise ModuleNotFoundError khi thiếu package cha — bọc try.
- `common.engine_caps(env)` dùng chung server + routes_editor (bỏ bản cục bộ).
- config.py: OCR_WORKERS nhận "auto" (≈ nửa số nhân, trần 6).

**G-B/G-C frontend:** MỚI `webui/static/app-config.js` (~620 dòng, nạp giữa
app-core và app-jobs-extra) — cắt loadConfig/saveConfig/CFG_FIELDS/applyEngineUI/
applyProviderUI/applySingleVoiceUI/reloadConfig khỏi app-core.js (940→530 dòng),
CFG_FIELDS chết hẳn (saveConfig mới quét DOM):
- Bố cục mới: card **Trạng thái máy** (chip GPU/ffmpeg/whisper/viXTTS/demucs/
  pyannote/OCR/đĩa + nút ↻) + ô **tìm kiếm** + cụm **profile** trên đầu; 7 nhóm
  theo pipeline (⭐ Dịch / Nhận dạng / Lồng tiếng & âm thanh / Xuất bản / Shorts /
  Hệ thống / 🔑 Tích hợp cuối trang có tiểu mục); mỗi nhóm có `<details>` Nâng
  cao nhớ trạng thái mở (localStorage); banner first-run khi chưa có khóa dịch.
- ⭐ Chất lượng dịch = núm gộp đặt CẶP model 2 provider (2 chiều: đổi model lẻ
  → nhảy «Tùy chỉnh»); nhãn Model chính/dự phòng đổi theo provider (sửa tooltip
  dối "fallback Haiku"); PROSODY/EMOTION nhãn khớp default 0 (sửa nhãn dối
  "Bật (khuyên dùng)" trong khi default đã tắt).
- Núm **Thiết bị Whisper** (Tự động/CPU/GPU) ghi cặp WHISPER_DEVICE+COMPUTE,
  Tự động = unset cả 2; option GPU disable khi máy không có GPU.
- Knob mới expose: REVIEW_TRANSLATION, GLOSSARY_AUTO, WHISPER_LANGUAGE,
  OCR_MAX_MINUTES, OCR_WORKERS=auto, ELEVENLABS_MODEL, FFMPEG_SHARED_BIN,
  FRAME + FRAME_COLOR/COLOR2 (input color)/WIDTH/PAD (khung mặc định toàn kênh,
  dropdown gồm PNG trong frames/), METADATA_MODEL, BATCH_LIMIT, AUTO_RETRY→Hệ
  thống, YTDLP_COOKIES_FILE/BROWSER (kèm cảnh báo cookies=phiên đăng nhập),
  YOUTUBE_API_KEY (hết phải sửa .env tay cho tab Phim hot).
- G8: chấm ● cạnh knob khác mặc định gốc + nút ↺ per-row (Lưu sẽ XOÁ key khỏi
  .env — không đếm 55 key ghim-bằng-factory di sản saveConfig cũ, chỉ 10 khác
  thật); G9 tìm kiếm lọc row + tự mở nhóm/Nâng cao, clear khôi phục; G10 cảnh
  báo engine thiếu key ngay dưới dropdown + nút "→ Nhập key" scroll+flash, gõ
  key vào form là cảnh báo đổi "bấm Lưu là sẵn sàng"; G15 đếm thay đổi thật
  trên nút Lưu (💾 Lưu (3)), chỉ gửi key ĐỔI (hết ghim cả 60 key mỗi lần lưu),
  beforeunload chặn đóng trang khi chưa lưu, disable nút khi đang lưu.
- Bug tự bắt khi verify: scheduleCfgDiff dùng requestAnimationFrame → tab nền
  không vẽ = diff đứng im; đổi setTimeout 60ms.

**G-D:**
- Profile cấu hình: `GET/POST/DELETE /api/profiles` (+GET /{id}) — snapshot 62
  khóa NỘI DUNG (PROFILE_KEYS allowlist: không secret, không khóa máy-local như
  WHISPER_DEVICE/FFMPEG_SHARED_BIN/COOKIES/VBEE_APP_ID), ghi nguyên tử
  data/profiles/{uuid}.json; UI: 💾 lưu / ▶ áp (confirm kèm danh sách diff,
  POST /api/config chỉ key đổi) / ⬇ xuất / ⬆ nhập (validate từng khóa, bỏ khóa
  lạ + báo skipped — test: chặn ANTHROPIC_API_KEY, HACKER_KEY, MAX_SPEEDUP=9.9) /
  🗑 xóa.
- `GET /api/fx-sample/{fx}` phát mẫu VOICE_FX tĩnh (voice_samples/_lbl_*.mp3,
  đủ 6 kiểu kể cả off=bản gốc, allowlist dict — traversal 404); nút 🔊 cạnh
  dropdown Xử lý giọng.
- `/api/tts-preview` nhận `settings` (allowlist 7 khóa TTS) → nút 🔊 cạnh ô
  giọng edge/viXTTS nghe thử ĐÚNG BẢN NHÁP đang chỉnh chưa cần Lưu; engine trả
  phí hỏi xác nhận tốn phí trước khi gọi.

**Review đối kháng (agent riêng, cả diff) — 5 phát hiện, sửa cả 5:**
- F1 nghiêm trọng: `allow_empty` mặc định True cho CẢ 73 khóa → profile import
  xấu/ô text xoá trống ghi được `MAX_SPEEDUP=""` vào .env → `float("")` chết
  MỌI job + server ngay lúc import config. Sửa: đảo mặc định False, chỉ 10 khóa
  thật sự rỗng-hợp-lệ (WHISPER_LANGUAGE, VIXTTS_VOICE_*, cookies…).
- F2 nghiêm trọng: block migration PROSODY/EMOTION (2026-07-10) thấy .env thiếu
  key là tự mọc lại `=1` → nút ↺ unset 2 khóa này VÔ NGHĨA, máy cài mới cũng bị
  bật nhầm. Sửa: idempotent bằng dòng marker comment (write_env giữ comment) —
  test 3 ca trên .env giả trong scratchpad.
- F3: lưu key xong cảnh báo engine vẫn "chưa nhập key" tới 60s (cache
  capabilities) → set_config invalidate `_caps_cache`.
- F4: nghe thử draft BỎ giá trị rỗng → chọn "(giọng mặc định model)" vẫn nghe
  clip cũ → draft giữ cả rỗng, thắng .env.
- F5: tìm kiếm trúng row trong block đang ẩn (engine khác/ô nữ) → "section bung
  mà trống" → bỏ row có tổ tiên display:none khỏi kết quả.
- (tự phát hiện thêm) áp profile gửi giá trị thô từ .env di sản ("True"/"-20.0")
  sẽ 400 validate → client chuẩn hoá `_cfgNorm` trước khi gửi.

**Verify (server thật + browser):** roundtrip .env set→ghim/unset→xoá/validate
400/quote giữ nguyên `#"` — .env sau toàn bộ test giống backup TỪNG BYTE;
capabilities trả RTX 3070 + h264_nvenc + 4/5 package; profiles CRUD + import
lọc; UI test có kịch bản: quality 2 chiều, dirty 0↔1↔0, ↺ + unset qua nút Lưu
thật, search "khung" → 3 nhóm/8 row, engine warn elevenlabs + typed-key, tts-
preview draft 200 audio/mpeg. Console 0 lỗi. node --check + scan ký tự điều
khiển sạch. LƯU Ý anh em máy kia: job thật 20260711_101200_9b69d9 đang ⏸ chờ
xem thử — đừng đụng.

---

## 2026-07-11 (7) — Desktop (F:\MyProject\vietsubvideo)

### #17: tách index.html (3.750 dòng → 208 dòng markup + 6 file static)

Mảnh monolith cuối. Cắt NGUYÊN VĂN bằng splice có kiểm chứng biên, giữ ĐÚNG THỨ
TỰ nạp (classic script tuần tự = cùng global scope — hành vi không đổi, không
phải ES module):
- `static/style.css` (306 dòng) + 5 file js: `app-core.js` (940 — helpers/tab/
  jobs/Cấu hình), `app-jobs-extra.js` (575 — queue/series/QC/log/glossary/
  YouTube/cắt video), `app-trending.js` (305 — Phim hot + PHẦN ĐẦU editor:
  fmtT/edVoiceSel/edFitChip/openEditor, do file gốc xen kẽ), `app-editor.js`
  (954 — editor + panel ⚙️/🎨 + nghe thử), `app-visual.js` (465 — tab Chỉnh
  giao diện + khởi động app). Header mỗi file ghi rõ nội dung thật.
- index.html còn 208 dòng markup + link/script src.
- Server: route mới `GET /static/{filename}` — allowlist đuôi .js/.css +
  basename (chặn traversal, đã test `..%2F` → 404), `Cache-Control: no-cache`
  (đổi code là trình duyệt lấy bản mới ngay, khỏi dính JS cũ).
- Verify trên trang thật: 7 asset đều 200; 17/17 hàm cross-file gọi được; tab
  Cấu hình render 63 control; editor mở job test đủ 19 câu + 12 chip cảnh báo
  + panel ⚙️/⭐ Chất lượng dịch/👂 nghe 10s/🎛 fx; console 0 lỗi.

Toàn bộ #16+#17 (tách monolith) đến đây HOÀN TẤT: server.py 2306→~1225,
index.html 3750→208. Các mạch lớn còn lại: W-2 model host (chờ telemetry),
tab phối/test giọng (chờ duyệt thiết kế).

---

## 2026-07-11 (6) — Desktop (F:\MyProject\vietsubvideo)

### #16 giai đoạn 2: tách cụm route EDITOR khỏi server.py

Tiếp mạch giai đoạn 1 (worker) — refactor CƠ HỌC, chuyển NGUYÊN VĂN bằng splice
có kiểm chứng biên từng khối:
- **`webui/routes_editor.py` (MỚI, ~915 dòng, APIRouter)**: RenderOptions,
  rerender + preview khung, segments GET/POST (+ _save_segments_inner),
  SegmentEdit(s), nhóm _OV_* + _JOB_OVERRIDE_KEYS, _has_emotion_labels,
  _ov_depth_for, _engine_caps, _mix_detail, override-impact, mix-preview,
  tts-preview + _resolve_voice_ref. Server chỉ còn `include_router`.
- **`webui/common.py` (MỚI, 130 dòng)**: helper dùng CHUNG giữa server và route
  module — _JOB_ID_RE/_check_job_id, _job_summary (+_cached_seg_total/_cached_
  tts_done), _unlink_quiet.
- **server.py: 2208 → ~1210 dòng** (giảm ~45%; trước toàn bộ đợt #16: 2306).
- 2 lỗi splice bắt được nhờ verify: `_QC_CJK` bị cuốn nhầm theo khối editor
  (trả về route /qc còn ở server) và routes_editor thiếu import `_JOB_ID_RE`
  (tts-preview 500 — smoke test bắt được, đã sửa).
- Verify: 54 route đăng ký đủ; smoke 16/16 endpoint (5 cụm đã dời + 11 cụm ở
  lại, gồm cả trang chủ) đều 200 qua server thật.

Còn lại của #16: server.py giờ chủ yếu là jobs/media/config/glossary/series/
youtube — đã ở mức dễ bảo trì; tách tiếp nếu cần sau #17 (index.html).

---

## 2026-07-11 (5) — Desktop (F:\MyProject\vietsubvideo)

### #16 giai đoạn 1: tách worker/queue khỏi server.py → webui/worker.py

Refactor CƠ HỌC không đổi hành vi (bước 2 trong thứ tự Codex đề xuất — dọn đường
cho model-host manager W-2 nếu telemetry nói có lãi):
- **`webui/worker.py` (MỚI, 243 dòng)**: toàn bộ state hàng đợi
  (_pending/_lock/_active/_cancel/_retries/_running_id/_current_proc/
  _queue_paused) + _enqueue/_reserve_job/_release_job/_enqueue_reserved +
  _drain_remove + _kill_proc_tree + _notify_done + vòng _worker + thread tự
  khởi động khi import + atexit kill job đang chạy. Chuyển NGUYÊN VĂN.
- **`webui/envfile.py` (MỚI)**: `read_env()` tách từ server (worker cần đọc
  AUTO_RETRY tươi mà không import ngược server).
- **server.py** (2306 → 2208 dòng): import object dùng chung trực tiếp; 3 biến
  VÔ HƯỚNG bị gán lại bên worker (_running_id/_current_proc/_queue_paused)
  đọc/ghi qua `worker.` — import from sẽ dính bản cũ (đã ghi chú ngay tại chỗ).
- Verify end-to-end qua server thật: pause queue → resume job (hiện "trong
  hàng") → CANCEL rút khỏi hàng sạch → unpause → resume chạy tới done qua
  worker mới; run.log vẫn nhận STAGE telemetry; import-test khẳng định object
  identity chia sẻ đúng + thread flowapp-worker sống.

Giai đoạn sau của #16 (tách routes theo nhóm) + #17 (index.html) — làm tiếp khi
user gọi; nền tảng worker giờ đã là module độc lập.

---

## 2026-07-11 (4) — Desktop (F:\MyProject\vietsubvideo)

### W-0: benchmark model + telemetry (user chốt "W-0 trước, gọn rồi qua #16")

- **`scripts/bench_models.py`**: đo cold/warm theo kỷ luật Codex — MỖI case một
  subprocess mới (đo chung 1 tiến trình là torch ấm, số đẹp giả), 3 lượt,
  median[min–max], append `data/bench_models.jsonl` để so sau nâng cấp package.
- **Telemetry 1-dòng vào run.log** (tự tích luỹ từ giờ): `STAGE name=<stage>
  seconds=X` (core/pipeline.py); `MODEL backend=whisper event=load seconds=X
  model= device=` (s3); `MODEL backend=vixtts event=load seconds=X vram_mb=`
  (vixtts._build_model); `MODEL backend=demucs event=run seconds=X` (separate).
- **SỐ ĐO THẬT (RTX 3070, máy này, 2026-07-11):**
  | case | median [min–max] |
  |---|---|
  | import pipeline (mỗi job trả) | **1.6s** [1.5–1.6] |
  | whisper small cpu: import + load | **16.1 + 7.9s** [cold máy: 44 + 14s] |
  | viXTTS: load lên GPU | **25.7s** [cold máy: 84s]; synth warm 2.9–3.2s/câu |
  | demucs: import + load weights | 1.7 + 0.2s (tách mới tốn, load không đáng) |
  | OCR RapidOCR init | ~0.3s |
  → Kết luận số: workflow OCR+edge hiện tại chỉ phí 1.6s/job (model host KHÔNG
  lãi); job dùng Whisper lãi ~25–60s, dùng viXTTS lãi ~30–90s. Ngưỡng 20–30s/job
  của Codex đạt NGAY khi 2 backend đó được dùng — telemetry sẽ đếm tần suất
  thật, đủ 20–30 job thì quyết W-2 (model host riêng, thiết kế đã chốt).
- Verify: chạy lại mixing→metadata job test, run.log có đủ dòng STAGE.

---

## 2026-07-11 (3) — Desktop (F:\MyProject\vietsubvideo)

### Nhóm bug #12–15 audit gốc (user: "thực hiện tiếp") — cả 4 đã sửa + verify

- **#12 race sửa-file vs xếp-chạy**: `save_segments`/`rerender_job` trước đây chỉ
  CHECK `_active` rồi buông lock — "Chạy tất cả"/resume có thể xếp job chạy ĐÚNG
  LÚC endpoint đang xoá transcript/mp3/final dở → cli đọc dữ liệu nửa vời. Thêm
  `_reserve_job/_release_job/_enqueue_reserved`: giữ chỗ trong `_active` suốt
  mutation; mọi đường lỗi nhả chỗ; không đổi gì thì nhả không xếp hàng.
  Verify API: save no-change ×2 đều 200 (không kẹt); rerender xong save ngay → 409.
- **#13 `ducked.mode` thiếu trạng thái**: marker cũ chỉ có mode:gain → (a) dịch
  lại/đổi Mute xong stage bgm chạy lại mà marker VẪN khớp → nền duck theo cửa sổ
  thoại CŨ; (b) KEEP_BGM=1 nhưng demucs lỗi rơi về audio gốc, marker vẫn ghi như
  demucs → không bao giờ thử tách lại. Marker mới:
  `{mode}:{gain}:w{md5-cửa-sổ-thoại}:src={nv|full}` — cửa sổ đổi là dựng lại;
  muốn demucs mà lần trước fallback → thử tách lại. Verify: mute 1 câu → vân tay
  lệch → ducked.wav dựng lại; không đổi → tái dùng.
- **#14 loudnorm 1-pass dynamic**: master trong `brand.build_audio` là loudnorm
  1-pass — chế độ DYNAMIC đổi gain theo thời gian (đầu video một mức cuối mức
  khác, "bơm"), ngược triết lý chuẩn hoá tuyến tính của S7. Giờ 2-PASS: đo trước
  (print_format=json) rồi áp `measured_* + linear=true` — MỘT hệ số gain cả
  video, tương quan giọng/nền giữ nguyên; đo lỗi thì rơi về 1-pass như cũ.
  Verify: output −14.11 LUFS / TP −0.99 (đích −14/−1).
- **#15 rơi rớt `final_io.mp4`**: ghép intro/outro chết giữa chừng để lại file
  dở vĩnh viễn (không nằm trong danh sách dọn nào). Bọc try/finally unlink ở CẢ
  2 nhánh render (dub + visual) + thêm vào `_CLEAN_FILES` của 🧹 Dọn dẹp để quét
  bản rơi rớt từ trước.

Đã xử xong toàn bộ nhóm bug audit. Còn treo (việc lớn, chờ confirm riêng):
worker thường trú giữ model RAM (#3), tách monolith server.py/index.html
(#16/17), tab phối/test giọng (mới đánh giá).

---

## 2026-07-11 (2) — Desktop (F:\MyProject\vietsubvideo)

### Panel ⚙️ đợt U-3+U-4 (user: "làm U-3 và U-4") — HOÀN TẤT toàn bộ U1–U16

**U-3 — bố cục:**
- Panel chia **🧰 Thường dùng** (7 control: Âm nền · Nhạc/SFX · 🎯 Preset khớp
  thoại · Engine · Chế độ giọng · Giọng tất cả câu · 👂 Nghe thử 10s) + **🛠
  Nâng cao** gập lại — cả 2 nhớ trạng thái đóng/mở qua localStorage. Panel cũ
  20+ knob phẳng → 7 thường dùng.
- **U2 bản Codex**: "🔊 Số giọng" → "Chế độ giọng" (1/2 giọng — danh tính giọng
  do engine quyết, ghi rõ trong help); "Giọng chính/phụ (edge)" nằm Nâng cao,
  chỉ hiện khi engine edge + đích vi (như cũ).
- **⭐ Chất lượng dịch** (user chốt "có"): 1 núm Tiết kiệm (Haiku/Flash-Lite) /
  Cân bằng (Haiku/Flash) / Tốt nhất (Sonnet/Pro) → phát ra CLAUDE_MODEL +
  GEMINI_MODEL cùng lúc (provider nào hiệu lực ăn model đó, Gemini fallback
  Claude cũng đúng); suy ngược giá trị núm từ override cũ của job.
- RÚT khỏi per-job: PROSODY_TRANSFER + 2 danh sách model (U9/U10 — vẫn ở Cấu
  hình); nhãn thân thiện Whisper (Nhanh→Chính xác nhất) + OCR (Nhanh/Kỹ) —
  U11 theo Codex, vẫn hiện theo Nguồn transcript.
- edOvDepth thêm map CLAUDE_MODEL/GEMINI_MODEL→translate (Chất lượng dịch phát
  2 khóa này nhưng không còn field riêng — thiếu map là depth rơi nhầm "mix").

**U-4:**
- **`POST /api/jobs/{id}/mix-preview`** (U14): nghe thử ~10s quanh câu đang chọn
  với Âm nền/Nhạc SFX/Kéo giãn ĐANG chỉnh chưa lưu. Dựng bằng ĐÚNG primitive
  render thật: refactor `s6_bgm.apply_duck(bed, ...)` + `s7_mix.render_voice(...)`
  tách từ run() — parity test: mixing chạy lại y hệt từng field mix_report, md5
  ducked.wav khớp. Giới hạn trung thực ghi trong help: không preview được đổi
  engine/giọng/MAX_SPEEDUP (cần re-TTS); demucs chưa tách → nền tạm audio gốc.
  Verify: WAV 10.0s/44.1k/stereo, giọng -16.6 dBFS nổi trên nền -37.7 (thử
  gain -26 + stretch qua API).
- **U16 DENOISE per-job** với depth MỚI "extract" (`_OV_EXTRACT`): sâu hơn
  transcript — xoá audio_16k.wav + chạy lại từ S2-trích (Codex: nhét nhóm
  transcript là knob nửa tác dụng). Impact endpoint báo đúng depth extract.
- `audio_np.read_wav_slice` (đọc khúc wav không nạp cả file).

Toàn bộ kế hoạch panel U1–U16 (AUDIT_GIONG_TUYCHON_TONGHOP.md) đến đây HOÀN TẤT.
UI verify bằng node --check + static assert (browser bridge vẫn chưa nối lại);
server logic verify bằng API thật + parity test.

---

## 2026-07-11 — Desktop (F:\MyProject\vietsubvideo)

### Panel ⚙️ đợt U-1+U-2 (user chốt: "1. có / 2. nghiêng codex / 3. U-1+U-2 trước")

Theo AUDIT_GIONG_TUYCHON_TONGHOP.md (đã cập nhật mục 5-6 với quyết định user).

**U-1 — trung thực hoá knob:**
- **U3 EMOTION**: bật khi transcript CHƯA có nhãn → server tự LEO THANG chạy lại
  từ DỊCH (`_ov_depth_for` — nhãn chỉ sinh lúc dịch, depth tts là no-op tuyệt
  đối); client cảnh báo ngay dưới knob + edOvDepth leo thang y hệt để confirm
  không nói dối. (Biến thể "leo thang + cảnh báo" thay vì disable cứng như bàn
  ban đầu — vẫn đúng tinh thần: không no-op, hành động rõ giá.)
- **U4 PROSODY**: ẩn khi engine hiệu lực ≠ edge; mô tả nguồn đo sửa lại theo
  code thật (ưu tiên vocals.wav đã tách — Codex bắt lỗi mô tả cũ).
- **U7**: `GET /segments` trả `engines` capability (paid thiếu key/model viXTTS
  chưa tải → option disable kèm lý do; engine ĐANG chọn không bị khoá để còn
  chuyển đi được).
- **U8 VOICE_FX**: dời từ nhóm "Giọng đọc" (gây hiểu lầm re-TTS) sang panel 🎨
  (đúng chỗ render); thêm lựa chọn "— theo cấu hình chung —" và server CHỈ lưu
  key `fx` khi user thật sự override → fix hẳn bug ghim `off` vĩnh viễn làm knob
  VOICE_FX toàn cục chết (audit #12c). RenderOptions.fx default "off"→"".
- **U13**: 🎚 Âm nền gốc hiện Ở MỌI mode Nhạc/SFX (trước chỉ flat — S6 áp gain
  cả 3 mode, Codex bắt bug visibility).

**U-2 — hạ tầng tác động:**
- **`core/voicesig.py` (MỚI)**: resolver chữ ký giọng THUẦN DỮ LIỆU
  (`TtsSettings.from_env(dict)` + `voice_signature(seg, st)`) — S5 `_voice_sig`
  giờ gọi qua đây (parity test 65/65 sig thật của 3 job test, cả edge lẫn
  viXTTS); trả nợ kiến trúc "sig phụ thuộc module config" (finding 11 audit).
- **`POST /api/jobs/{id}/override-impact`**: dry-run tác động của ⚙️ đề xuất —
  depth (kèm leo thang EMOTION), stages, `tts_regenerate` (so sig dự kiến vs
  .sig đĩa — đúng cơ chế resume), `paid_tts_chars`, `manual_edits_at_risk`,
  `estimated_seconds` [min,max], warnings (PROSODY toggle = chặn trên; engine
  thiếu key; translate/transcript = không giả vờ đếm, báo mất sạch).
  Test 5 kịch bản: noop→null; STRETCH_SHORT→mix; MAX_SPEEDUP 1.4→19/19 câu
  (sig cũ ghi lúc 2.0); EMOTION→translate+cảnh báo; elevenlabs→923 ký tự trả
  phí + cảnh báo thiếu key.
- **UI**: confirm trước Áp dụng/Lưu giờ CÓ SỐ từ endpoint (fallback confirm tĩnh
  cũ nếu lỗi mạng); nút "↺ Về cấu hình chung" xoá mọi override 1 phát (U6).

Lưu ý kỹ thuật: Edit tool lại biến 1 space literal thành U+0000 (bài học cũ) —
đã quét và thay bằng sentinel "none-selected". Browser pane đổi sang tool ext
giữa phiên (Chrome extension chưa nối) → UI verify bằng node --check + static
assert + 5 test API; user xem giao diện thật khi test.

---

## 2026-07-10 (4) — Desktop (F:\MyProject\vietsubvideo)

### Đợt C+D audit giọng (user: "thực hiện các bước tiếp theo") — V5-V7, V9-V12, V14

**Đợt C — khớp từ tầng DỊCH (s4_translate):**
- **V5** payload dịch mang ngân sách KÉP từ trọng tài: `target_s` (miệng =
  end−start, nhắm ≈4×target_s âm tiết), `max_s` (slot tới câu kế − 0.25s đệm thở
  — CÙNG định nghĩa với tầng nén S5/S7, hết cảnh 2 thước 2 tầng), `max_syll`
  (trần âm tiết, CHỈ đích tiếng Việt). 3 system prompt cập nhật rule ĐỘ DÀI.
- **V6** validator ĐẾM THẬT âm tiết sau dịch (`duration.syllables`): câu >4.5 âm
  tiết/giây-limit → dịch lại NGẮN 1 vòng gom batch, chỉ nhận bản thật sự ngắn
  hơn. Test thật: bắt đúng 1 câu (#13), rút gọn 1/1.
- **V7** review pass nhận `max_syll` + guard programmatic: bản sửa vừa dài hơn
  câu cũ vừa vượt trần → từ chối.

**Đợt D:**
- **V10** `segtools.absorb_tiny`: nhập câu CỤT (≤2 chữ) vào câu bên khi gap
  ≤0.8s, không trộn 2 speaker. Gọi ở **S4 sau diarize** (review đối kháng bắt
  lỗi bản đầu đặt ở S3: seg chưa có speaker → guard chết). Test thật: 23→19 câu,
  hết sạch câu 1-2 chữ.
- **V9** `STRETCH_SHORT` (mặc định TẮT — tính năng từng bị revert 30e285c, cần
  user chủ động bật): câu hụt >30% slot → atempo 0.92–1.0 kéo về độ dài MIỆNG
  (không lấp khoảng lặng tự nhiên). Knob ở Cấu hình + ⚙️ per-job nhóm mix.
- **V11** nghe thử 🔊 trung thực: nhận `job_id` → áp ⚙️ override
  (engine/giọng/1-giọng/TARGET_LANG); engine viXTTS + câu không cast → nghe thử
  cũng viXTTS giọng mặc định (+ clip cảm xúc như render) thay vì rơi xuống edge.
- **V12** preset Cấu hình (🎯 Khớp môi chặt = 2.0×+kéo giãn / 🌿 Tự nhiên =
  1.2×); nhãn "Nữ (1 giọng — không tác dụng)" theo giá trị HIỆU LỰC của job;
  default code PROSODY/EMOTION "1"→"0" KÈM migration tự append giá trị cũ vào
  .env máy đã dùng (không âm thầm đổi giọng/re-TTS — laptop pull về là an toàn).
- **V14** demucs giữ lại `vocals.wav` (bọc OSError — file phụ hỏng không được
  phá lần tách GPU; review bắt lỗi bản đầu thiếu try/except).

**Kiểm chứng:** pipeline chạy lại từ transcribing trên clone
`20260710_155613_aaa003` (edge): 19 câu, chỉ 2 câu nén (max 1.37×), 0 tràn,
0 cắt — so bản gốc 12 câu nén (max 2.0×), 10 tràn. Review đối kháng 19 agent
trên diff: 15 CONFIRMED (nặng nhất: STRETCH_SHORT/DUCK_GAIN_DB thiếu trong
CFG_FIELDS → tab Cấu hình không lưu được — đã sửa cùng 6 lỗi khác), tất cả đã
xử lý trước khi commit. Còn treo: đợt sau nếu muốn — 2 chế độ nghe thử
(raw/in-timeline), preview cho câu voice_ref khi đích ≠ vi.

---

## 2026-07-10 (3) — Desktop (F:\MyProject\vietsubvideo)

### Nền át giọng Việt (user phàn nàn sau khi nghe test) + đổi engine edge 1 giọng

Đo thật trên job test: giọng TTS chỉ nổi hơn nền ~+5.9dB (muốn rõ lời cần
+12–15dB) — nền duck −14dB chưa đủ VÀ giọng edge hơi nhỏ (-18.9 dBFS). Sửa cả 2 đầu:
- **DUCK_GAIN_DB thành cấu hình** (config.py — trước là hằng số −14 cứng), default
  mới **−20**; thêm ô "Âm nền gốc dưới thoại" trong tab Cấu hình (SAFE_ENV_KEYS).
  Per-job 🎚 âm nền trong editor vẫn thắng như cũ.
- **S7 chuẩn hoá âm lượng giọng** (`_norm_voice`): RMS từng câu về −16 dBFS, kẹp
  ±6dB (không thổi phồng câu cố tình nói nhỏ) — sẵn tiện hết luôn cảnh câu to câu
  nhỏ (đo được lệch ~2.5dB giữa các câu). Ghi `voice_gain_db` vào mix_report detail.
- **.env máy này**: TTS_ENGINE=edge (1 giọng — TTS_SINGLE_VOICE vốn =1),
  DUCK_GAIN_DB=-20.
Kết quả đo lại trên job test aaa002 (edge): tách lời **+15dB** (trước +5.9dB),
voice_gain áp +1.5..+5.4dB. Máy laptop lưu ý: default DUCK_GAIN_DB đổi −14→−20
trong code — muốn giữ nền to như cũ thì đặt DUCK_GAIN_DB=-14 trong .env.

---

## 2026-07-10 (2) — Desktop (F:\MyProject\vietsubvideo)

### Trọng tài thời lượng giọng đọc — ĐỢT A+B theo AUDIT_GIONG_TONGHOP.md (user confirm "làm A B trước")

**Đợt A (V13 — đo trước sửa sau, ý Codex):** mix_report.json thêm mảng `detail`
per-câu: trimmed_ms (bản đọc đã cắt lặng) / target_ms (miệng = end−start) /
slot_ms / engine_speed / post_atempo / total_speed (tích) / final_ms / gap_ms /
clipped_ms. Editor: `GET /segments` trả kèm `mix_detail`, mỗi dòng câu có chip
cảnh báo — ĐỎ `⏩ 1.61×` (nén tổng ≥1.3, rút gọn lời là hết), ĐỎ `✂ cắt 0.4s`
(hết ngân sách vẫn dài → đã fade-cắt), VÀNG `⏳ 12.5s` (đọc xong sớm — đa phần
là khoảng lặng tự nhiên của video gốc).

**Đợt B (V1→V4 — một trọng tài, một thước, một ngân sách):**
- **V1 `core/duration.py` (MỚI)**: `trim_silence`/`trimmed_dur_s` dùng CHUNG —
  S5 hết đo bằng ffprobe full-mp3 (dính đuôi lặng edge 0.5–0.9s gây "tràn giả"),
  S5 và S7 giờ nhìn cùng một con số (lệch ≤1ms, đã đối chiếu).
- **V3 ngân sách TÍCH**: `MAX_SPEEDUP` thành trần NHÂN thật — S5 ghi phần engine
  đã nén vào `tts/fit_report.json`, S7 chỉ atempo trong phần CÒN LẠI
  (`budget_left = MAX_SPEEDUP / engine_speed`). Deadzone: câu lọt limit
  (slot − 0.1s fade guard) thì không đụng. Edge fit dùng công thức SỐ HẠNG CHÉO
  của Gemini (`edge_total_rate`) — hết cảnh fit xong vẫn hụt → S7 nén thêm 91%
  câu như trước. `engine_speed` ghi mức nén YÊU CẦU chứ không phải đạt-được
  (XTTS nondeterministic — variance đọc-ngắn-tình-cờ không tính là nén, kẻo
  "tổng nén" báo ảo 2.6×).
- **V2 viXTTS fit bằng `speed`**: `vixtts.synth(..., speed=)` truyền
  length_scale XTTS (trước đây BỎ PHÍ — độ dài thả nổi median 2.5× thoại gốc);
  vượt limit >3% → synth lại đúng 1 lần với speed = min(cần, 1.25, MAX_SPEEDUP),
  chỉ nhận bản thật sự ngắn hơn. Sig vix thêm `:f{budget}` như edge → đổi núm
  MAX_SPEEDUP là tự đọc lại; per-job override MAX_SPEEDUP chuyển nhóm
  `_OV_MIX`→`_OV_TTS` (audit merged-3: xếp mix là knob nửa tác dụng).
- **V4 fade thay đè**: hết ngân sách mà vẫn vượt slot → fade-out 100ms rồi CẮT
  tại biên. KHÔNG BAO GIỜ đè giọng sang câu kế / thoại gốc chưa duck nữa.

**Số đo trước/sau (job test clone từ a20f78, 23 câu — 2 clone giữ lại để nghe:
`20260710_150158_aaa001` viXTTS, `20260710_151322_aaa002` edge):**
| | tràn đè câu kế | nén ≥1.3× | max tổng nén | bị cắt |
|---|---|---|---|---|
| TRƯỚC (viXTTS) | **10 câu, max 826ms** | 7 | 2.00 (mù — không ai đo tích) | 0 |
| SAU (viXTTS) | **0** | 6 | 2.00 (= đúng trần, có kiểm chứng) | 2 (max 417ms) |
| SAU (edge) | **0** | 2 | **1.39** | 0 |
Gap im lặng TĂNG nhẹ (35→40s viXTTS) — đúng thiết kế: chưa kéo giãn câu ngắn
(V9 đợt D, chờ user duyệt riêng vì từng revert). Nhánh edge sau cross-term chỉ
còn 2 câu nén ≥1.3 và không câu nào chạm trần.

Phát hiện tiện thể: id job test tự đặt đuôi chữ (`_dgtes1`) bị `_JOB_ID_RE`
(vá traversal) chặn 404 — đã đổi tên; job thật không ảnh hưởng (id luôn hex).
CHƯA LÀM (chờ confirm): đợt C (V5–V7 ngân sách dịch + đếm âm tiết), đợt D
(V8–V12, V14).

---

## 2026-07-10 — Desktop (F:\MyProject\vietsubvideo)

### Đợt tối ưu theo audit toàn app (user confirm "thực hiện hết theo thứ tự")

Audit đa-agent toàn codebase (có bước phản biện loại 4 phát hiện SAI: XSS innerHTML,
.env không gitignore, FileResponse thiếu Range, subprocess ×9/job — đều đã refute).
5 nhóm được confirm làm ngay; đã làm + VERIFY từng mục trên máy này:

1. **GPU encode (`core/ffmpeg.py: h264_args()`)** — dò encoder 1 lần/process bằng
   nullsrc probe: h264_nvenc → h264_qsv → libx264. Máy này (RTX 3070) chọn
   `h264_nvenc -preset p5 -cq 23`. Trước đây MỌI render đều libx264 CPU. Áp vào
   s8_render (cả 2 nhánh encode), splitter, shorts — giữ fallback libx264 nếu
   NVENC chết giữa chừng. Verify end-to-end: job visual test render 10.5s clip
   trong ~4s, run.log ghi `encoder H.264: h264_nvenc`, tag stream xác nhận.
2. **Dọn ổ đĩa** — (a) output/ đổi tên `final-{timestamp}.mp4` → `final-{job.id}.mp4`
   (ổn định: re-render GHI ĐÈ thay vì sinh bản mới — nguyên nhân 1.5GB rác trùng);
   (b) endpoint mới `POST /api/cleanup?dry=` dọn file trung gian (WAV/tts sped/…)
   của mọi job DONE + khử output trùng byte (group size→md5, giữ bản mới nhất);
   (c) nút "🧹 Dọn dẹp ổ đĩa" ở tab Tổng quan: dry-run → confirm số MB → dọn thật.
   Đã bấm thật: lấy lại 296MB (data/jobs 1.1GB→846MB, output 1.5GB→1.4GB).
3. **Vá path traversal** — `_check_job_id()` (regex id) áp vào `/api/jobs/{id}/video`
   + `/srt` (trước đây ghép thẳng vào path → `..%2F..` đọc được file ngoài data/).
   Verify: cả 2 endpoint trả 404 với payload traversal.
4. **Cửa sơ loại OCR (auto)** — `ocr_subs.probe_crop_top()` (~16 frame) chạy TRƯỚC
   OCR full khi `TRANSCRIPT_SOURCE=auto` + `OCR_CROP_TOP=auto`: không thấy dải sub
   ổn định → đi thẳng Whisper, khỏi quét cả nghìn frame rồi vứt. Thấy sub → truyền
   crop_top đã dò cho `extract()` (không dò lại lần 2). Verify: video không sub →
   None (skip); 0706.mp4 → 0.765.
5. **Tối ưu lặt vặt đã đo**: S2 gộp 2 lệnh ffmpeg thành 1 lệnh đa-output (decode
   nguồn 1 lần, 0.91s cho clip test); `s5_tts._mp3_dur_s` pydub→ffprobe (21ms vs
   49ms warm, không nạp cả file vào RAM); `refresh()` index.html chỉ poll 1/5 tick
   (10s) khi KHÔNG ở tab Jobs và không mở editor (verify: ẩn tab 1/5 fetch, hiện
   tab 3/3).

**Chưa làm (chờ confirm riêng, đúng luật "confirm mới làm")**: #3 worker thường trú
giữ model trong RAM; #16/#17 tách monolith server.py/index.html; nhóm bug #12–15
(race cancel rerender, ducked-mode state, loudnorm 1-pass/2-pass lệch nhau, temp
final_io.mp4 rơi rớt).

### Audit chuỗi xử lý GIỌNG (chỉ BÁO CÁO — chưa code, chờ user chọn theo số V1–V13)

User báo: âm thanh lúc ngắn lúc dài, đọc không tự nhiên cả tốc độ lẫn âm điệu; nghi
chồng chéo config. Audit đa-agent (23 agent, có vòng phản biện): 4 CONFIRMED,
8 PARTIAL, 0 sai. Số đo job thật (a20f78, viXTTS): bản đọc dài median 2.5× thoại
gốc (max 14.6× — "Niệm Bảo" 0.25s→3.56s); 52% câu bị atempo (median 1.41×, 2 câu
kịch trần 2.0× VẪN tràn 826ms); 26–32% câu hụt slot → tổng 35.2s im lặng/103s video.

**Nguyên nhân đã xác nhận:**
1. Nhánh viXTTS (engine đang dùng) KHÔNG có tầng kiểm soát độ dài nào ở S5 —
   `_fit_slot` chỉ gọi cho edge (s5_tts.py:165); tham số `speed` của XTTS có sẵn
   nhưng vixtts.py:144 không truyền → độ dài thả nổi, dồn hết vào atempo 1 chiều S7.
2. MAX_SPEEDUP tiêu 2 LẦN độc lập (S5 fit budget + S7 atempo cap, không đâu kẹp
   TÍCH → tới 3.0×) trong khi UI hứa là "núm TỔNG"; công thức fit thiếu số hạng
   chéo → 91% câu edge bị atempo THÊM sau khi đã fit (job 292928).
3. Hai THƯỚC ĐO khác nhau: S5 đo full mp3 (gồm đuôi lặng edge 0.5–0.9s), S7 cắt
   lặng rồi mới so → "tràn giả", 7/27 câu job 40de66 bị cộng oan tới +26% rate.
4. Hai NGÂN SÁCH khác nhau: S4 cấp chữ theo end−start, S5/S7 nén theo
   next.start−start; độ dài bản dịch chỉ ràng bằng LỜI DẶN prompt (không đếm âm
   tiết, không vòng dịch-lại; review được phép nới dài không ai chặn).
5. Chỉ có chiều NÉN, không chiều kéo chậm (bản 2 chiều a613cbc đã revert) → hụt
   thì im lặng; tràn sau trần thì ĐÈ lên câu kế (đo được 826–2233ms, 2 giọng chồng).
6. Nút 🔊 nghe thử dùng ĐƯỜNG KHÁC render (engine khác luôn: nghe edge, render
   viXTTS; bỏ prosody/fit/atempo/voice_fx) → tinh chỉnh theo preview là ảo.
7. Âm điệu phẳng hiện tại: PROSODY=0 + EMOTION=0 + clone đúng 1 clip
   rieng-nam-review.wav cho mọi câu; khi bật lại (nhánh edge) thì 4 nguồn rate
   độc lập đánh nhau không trọng tài.

**Đề xuất V1–V13 (chưa làm):** GÓI 1 trọng tài thời lượng — V1 cắt đuôi lặng ngay
sau synth (mọi engine, S5/S7 cùng thước); V2 viXTTS truyền speed + fit 1 vòng như
edge; V3 tốc độ quyết định MỘT nơi, MAX_SPEEDUP thành trần TÍCH thật; V4 tràn sau
trần → cắt/fade thay vì đè câu kế. GÓI 2 khớp từ tầng dịch — V5 S4 nhận đúng slot
(trừ đệm thở); V6 đếm âm tiết sau dịch, câu >~4.3 âm tiết/giây slot thì dịch lại
NGẮN riêng câu đó (vòng phản hồi đang thiếu); V7 review nhận max_s. GÓI 3 tự
nhiên — V8 mục tiêu = khớp MIỆNG (end−start), trần = slot; V9 kéo chậm NHẸ có trần
(0.92×) khi hụt >30%; V10 segtools nhập câu 1-từ vào câu bên (né sàn ~2.3s viXTTS),
tách câu gộp quá dài. GÓI 4 dọn bề mặt — V11 preview 🔊 dùng đúng engine+đường
render; V12 gom PROSODY/EMOTION/PT/VOICE_FX/MAX_SPEEDUP thành 3 preset, ẩn knob
chết; V13 mix_report ghi hệ số từng câu + editor tô đỏ câu nén >1.3×/hụt >30%.
Gợi ý thêm: cắt 3–4 clip mẫu từ 10 phút giọng user (bình thường/nhấn/trầm) để
chỉnh âm điệu viXTTS tự nhiên thay vì knob số.

Bàn giao chéo: user nhờ thêm 2 agent (Codex, Gemini) phản biện độc lập — toàn bộ
bối cảnh + kết luận + câu hỏi phản biện nằm trong **AUDIT_GIONG.md** ở gốc repo;
họ sẽ ghi kết quả vào AUDIT_GIONG_CODEX.md / AUDIT_GIONG_GEMINI.md (không sửa code).

### Giọng mới: voices/rieng-nam-review.wav (giọng CỦA USER tự lồng)

User xác nhận chính họ là người lồng tiếng trong clip nguồn. Tách bằng demucs
(two-stems, GPU ~15s/10phút; cần `os.add_dll_directory(FFMPEG_SHARED_BIN)` trước
import — torchcodec thiếu DLL y hệt core/separate.py). Tự động quét cửa sổ 20s
sạch nhất (RMS 1s, ≥85% voiced), chọn 05:57–06:17, trim lặng + loudnorm I=-18 →
mono 24kHz cho viXTTS clone.

---

## 2026-07-06 (2) — Desktop (F:\MyProject\vietsubvideo)

### Tính năng MỚI: tab "🎨 Chỉnh giao diện" — chỉ nạp video để thêm khung/logo/watermark, KHÔNG dịch/lồng tiếng

User muốn 1 luồng nhẹ: nạp video → chỉnh khung viền/logo/watermark/crop/che sub gốc
→ xuất — không tốn phí Claude/Whisper/TTS, không cần chờ dịch. Thiết kế: job MỚI
`mode="dub"` (mặc định, y hệt cũ) | `"visual"` — pipeline rút còn 2 stage
`[DOWNLOADING, RENDERING]` (`core/job.py: VISUAL_STAGES`), `core/pipeline.py` chọn
stage-list theo `job.mode`.

- **`core/stages/s8_render.py: _run_visual(job)`** (song song với `run()` cũ, không
  đụng code dịch): dùng THẲNG audio gốc của video nguồn (không cần transcript/dub
  audio) — remux nhanh (`-c:v copy`) nếu không chỉnh gì, re-encode khi có khung/che/
  watermark/crop/logo. Nhạc nền/logo/master vẫn dùng CHUNG cấu hình "Thương hiệu"
  toàn cục như job dịch (nhất quán thương hiệu kênh). "Che sub gốc" chỉ có dải THỦ
  CÔNG (không "tự động" vì chưa từng OCR).
- **webui/server.py**: `NewJob.mode`, `create_job`/`upload_job` nhánh visual (tự
  `_enqueue`, ép `pause_before_render=True` để dừng đúng trước render cho user chỉnh
  trước khi xuất lần đầu); `list_jobs(mode="dub")` mặc định — API cũ `/api/jobs`
  không tham số vẫn CHỈ trả job dịch (zero thay đổi hành vi cho code cũ); thêm
  `mode="visual"`/`"all"`. `rerender_job` bỏ qua xoá/reset stage "metadata" cho job
  visual (s9_metadata đọc transcript → crash nếu lỡ chạy). Endpoint mới nhẹ
  `GET /api/jobs/{id}/visual` (render dict + danh sách khung PNG + has_final/audio).
- **webui/static/index.html**: tab mới + `pane-visual` (danh sách/thêm video, tách
  biệt hoàn toàn khỏi Jobs) + `pane-visual-edit` (editor riêng: video preview +
  panel 🎨 khung viền/watermark/crop/che sub — KHÔNG có font/subtitle-mode vì
  không bao giờ vẽ phụ đề mới). Tái dùng triệt để hạ tầng có sẵn: CSS `.wm-ov`/
  `.crop-ov` (đổi từ `#ed-wm-ov`/`#ed-crop-ov` sang class dùng chung, giữ nguyên
  rule ID cũ), `syncBand()`/`jobProgressHTML()`/`openJob()`/`resumeJob()` generic
  sẵn, và 2 endpoint `/preview` + `/rerender` y hệt editor lồng tiếng (chỉ khác
  payload gửi lên).
- **Fix bug tiện thể phát hiện**: `/api/jobs/{id}/preview` mặc định lấy mẫu ở giây
  30 khi job chưa có transcript — video NGẮN hơn 30s (test clip 10.5s, hay gặp ở
  video visual-mode/Shorts) khiến `-ss` vượt quá thời lượng → ffmpeg không trích
  được khung nào → 500. Giờ kẹp `t` theo `brand._duration(source)`. Sửa dùng chung
  cho cả 2 chế độ, không đổi hành vi job dịch bình thường (t luôn nhỏ hơn duration).

Verify end-to-end qua HTTP thật (không chỉ gọi hàm Python): tạo job visual bằng
link/upload → tự chạy → dừng đúng chỗ → mở editor → đổi khung màu + che mờ → xem
trước CSS (tức thời) khớp xem trước FFmpeg (chính xác) → bấm Xuất video → render
xong → final.mp4 đúng kích thước/audio nguyên vẹn → xóa job. Xác nhận job visual
KHÔNG lẫn vào tab Jobs (dịch) và ngược lại. Không lỗi console suốt test.

---

## 2026-07-06 (BÀN GIAO SANG MÁY MỚI) — Desktop (F:\MyProject\vietsubvideo)

### User sắp chuyển sang máy mới. Toàn bộ code đã commit + push (HEAD = 30e285c).

**Máy mới làm gì sau khi `git clone`:**
1. Tạo `.env` từ `.env.example` rồi ĐẶT LẠI 3 SECRET (không có trong git):
   `ANTHROPIC_API_KEY` (bắt buộc — bước dịch), `GEMINI_API_KEY` (nếu dùng Gemini),
   và HF/ElevenLabs/VBee/FPT/Telegram token nếu dùng. Nhập trong app: ⚙️ Cấu hình →
   nhóm "🔑 Khóa API & Token".
2. `data/jobs/` (các video đã test) KHÔNG theo git — máy mới bắt đầu trắng, tự tải/
   upload lại video để test.
3. Tạo venv + cài lại deps (requirements.txt). Whisper GPU: `WHISPER_DEVICE=cuda`
   + cài nvidia-*-cu12 (xem _add_cuda_dll_dirs trong s3_transcript.py). Không GPU
   thì để `cpu`/`int8`, model `small`.
4. Chạy server: launch.json "flowapp" (uvicorn webui.server:app :8790, KHÔNG --reload
   → sửa .py phải restart; sửa .env thì KHÔNG cần nữa nhờ load_dotenv override=True).

**Cấu hình NON-SECRET user đã tinh chỉnh trên máy F: (chép sang .env máy mới nếu muốn
giống hệt):** TTS_ENGINE=edge, TTS_SINGLE_VOICE=1, MAX_SPEEDUP=2.0, KEEP_BGM=flat,
PROSODY=1, EMOTION=1, PROSODY_TRANSFER=0, CONTENT_STYLE=donghua, OCR_CROP_TOP=auto,
TRANSCRIPT_SOURCE=ocr, WHISPER_MODEL=large-v3+cuda, SUB_SPLIT=1, MASTER=1,
TRANSLATE_PROVIDER=claude (CLAUDE_MODEL=haiku-4-5), FPT_VOICE_NU=banmai/NAM=leminh.

**Phiên này đã làm (2026-07-05 → 07-06, xem các entry bên dưới):** loạt fix chất
lượng lồng tiếng (1-giọng triệt để, khớp thoại theo núm MAX_SPEEDUP, nền hạ đều,
OCR auto-crop cho video dọc + video nhiều chữ), đại tu editor "Chỉnh sửa" (panel
⚙️ override cấu hình THEO JOB — 19 option 4 nhóm, dependent, 2 cột, helptext ⓘ,
thanh nút dính đáy), fix bug nền tảng load_dotenv override. + 1 nghiên cứu (không
code): giọng review phim Trung nổi bật chủ yếu là TTS FPT.AI "Ban Mai/Lê Minh";
license thương mại: Vbee/FPT/ElevenLabs (paid) OK — xem [[tts-license-monetize]].

**Trạng thái pipeline/tính năng:** tất cả xanh, không có việc dở dang giữa chừng.
Job test cuối `20260705_212220_8691dd` đã render xong với override PROSODY=0,EMOTION=0
(giọng đều) — chỉ là data local, không cần mang sang.

---

## 2026-07-06 (3) — Desktop (F:\MyProject\vietsubvideo)

### REVERT "khớp nhịp 2 chiều" — user chỉ hỏi confirm, KHÔNG yêu cầu làm

Đã lỡ thêm tính năng kéo chậm câu ngắn (a613cbc) khi user chỉ hỏi xác nhận hành vi.
Hành vi user muốn = bản 1 CHIỀU sẵn có: câu ngắn đọc tốc độ BÌNH THƯỜNG, câu dài
mới ép nhanh cho khỏi tràn (trần theo núm MAX_SPEEDUP). Revert sạch về b71e97f.

**QUY TẮC LÀM VIỆC MỚI từ user:** "nếu tôi hỏi thì chỉ trả lời; tôi confirm thì
mới làm" — câu hỏi ≠ yêu cầu tính năng.

---

## 2026-07-06 (2) — Desktop (F:\MyProject\vietsubvideo)

### "Giọng lúc nhanh lúc chậm": MAX_SPEEDUP thành núm TỔNG cho mọi lớp tăng tốc

User nghe giọng đọc không đều. Đo job 8691dd: PROSODY chỉnh rate −12..+20% cho
10/23 câu (bám tốc độ giọng gốc) + _fit_slot ép +15..+50% cho câu dài hơn slot —
hai tầng chồng nhau → câu cạnh nhau lệch tốc độ rõ.

Fix thiết kế: `_fit_slot` giờ TÔN TRỌNG núm MAX_SPEEDUP — ngân sách ép-nhanh-vì-
khớp = (MAX_SPEEDUP−1)×100%, kẹp trần 50%. **1.0× = không ép nhanh chút nào**
(giọng đều tự nhiên, chấp nhận tràn) — trước đó 1.0× chỉ tắt atempo S7 còn fit
edge vẫn ép +50% (núm nói dối). Thêm `:f{budget}` vào .sig → đổi núm là các câu
edge tự đọc lại đúng mức mới (trước đổi núm không có tác dụng với mp3 đã có).
Helptext 2 nơi cập nhật. Muốn giọng ĐỀU: tắt PROSODY (±20%) + hạ MAX_SPEEDUP.

---

## 2026-07-06 (1) — Desktop (F:\MyProject\vietsubvideo)

### Hoàn thiện UX panel ⚙️ editor: dependent, 2 cột, dọn header, helptext ⓘ

Chuỗi 3 commit theo yêu cầu user khi test tính năng override theo job:
- **6ee2549** — field PHỤ THUỘC ẩn/hiện theo giá trị HIỆU LỰC (`applyOvDeps`):
  1 giọng → ẩn Giọng nữ; engine ≠ edge / đích ≠ vi → ẩn cặp giọng edge;
  provider → chỉ hiện model tương ứng; transcript ocr/whisper → ẩn option lẻ.
  Field ẩn không được gửi khi Lưu (check style.display, KHÔNG dùng offsetParent
  kẻo details đóng xóa nhầm hết override). Lưới `.ov-grid` 2 cột, nhãn 180px +
  input giãn đều — thẳng hàng dọc.
- **d2766f2** — header editor chỉ còn "← Quay lại" + tiêu đề; control dời về đúng
  nhóm ngữ cảnh trong panel ⚙️ (Giọng tất cả câu + Xử lý giọng → 🔊; Âm nền gốc
  → 🎛, CHỈ hiện khi Nhạc/SFX = hạ đều); nút Áp dụng/Lưu & render + edmsg →
  thanh DÍNH ĐÁY `.ed-actionbar`.
- **(commit này)** — helptext ⓘ cho CẢ 22 control panel ⚙️ (19 field + Âm nền/
  Giọng tất cả câu/Xử lý giọng), cùng kiểu `.finfo/.ftip` với trang Cấu hình.
  Relabel "Giọng đọc/Giọng nam" chỉ sửa text node đầu — textContent sẽ xoá mất
  icon tooltip con.

---

## 2026-07-05 (7) — Desktop (F:\MyProject\vietsubvideo)

### "⚙️ Tùy chọn video này" mở rộng 19 option, chia 4 NHÓM theo độ sâu làm lại

User muốn test hết cấu hình trên 1 video. Panel giờ gồm 4 nhóm (server tự chạy lại
từ stage SÂU NHẤT bị đổi — nhóm `_OV_*` trong server.py phải khớp `ED_OV_FIELDS`):

| Nhóm | Option | Làm lại gì |
|---|---|---|
| 🎛 Trộn âm | MAX_SPEEDUP, KEEP_BGM | chỉ nền+trộn+render (NHANH, giọng giữ nguyên) |
| 🔊 Giọng đọc | TTS_ENGINE, TTS_SINGLE_VOICE, TTS_VOICE(_NU), PROSODY, EMOTION, PROSODY_TRANSFER | đọc lại câu bị ảnh hưởng (.sig) + trộn + render |
| 🌐 Dịch | TRANSLATE_PROVIDER, CLAUDE/GEMINI_MODEL, CONTENT_STYLE, TARGET_LANG, TRANSLATE_STYLE_EXTRA (ô chữ) | DỊCH LẠI toàn bộ — xóa transcript_vi/tts/metadata (confirm ⚠️ mất sửa tay) |
| 📝 Nhận dạng | TRANSCRIPT_SOURCE, WHISPER_MODEL, OCR_FPS, OCR_CROP_TOP | làm lại từ transcript — xóa cả transcript_zh/ocr_raw/sub_boxes (confirm ⚠️) |

Editor cảnh báo confirm trước khi Lưu nếu đổi nhóm Dịch/Nhận dạng. Verify sống:
19/19 field, depth logic đúng 4 tầng; override MAX_SPEEDUP=1.8 trên job 8691dd →
CHỈ reset bgm/mixing/rendering (tts+translating giữ nguyên), render nhanh.

---

## 2026-07-05 (6) — Desktop (F:\MyProject\vietsubvideo)

### "⚙️ Tùy chọn video này" trong editor + đổi tên "Chỉnh sửa" + fix đường gạch nút

1. **Đổi tên nút "✏️ Sửa lời thoại" → "✏️ Chỉnh sửa"** (thẻ job + tiêu đề editor +
   các chỗ nhắc).
2. **Fix "đường gạch" trên nút Soát/Xuất bản**: rule `details` toàn cục (border-top
   + margin-top, dùng cho separator) đánh cả vào `details.btnmenu` → vẽ vạch + lệch
   hàng. Đè margin/border/padding=0 cho `.btnmenu`.
3. **Override cấu hình THEO JOB** — panel "⚙️ Tùy chọn video này" trong editor:
   Số giọng, Đồng bộ khớp thoại, Nhạc/SFX gốc, Tông giọng, Cảm xúc, Chuyển ngữ điệu.
   Output không vừa ý → chỉnh tại đây rồi 💾 Lưu & render lại, KHÔNG đụng cấu hình
   chung/video khác. Cơ chế: `Job.env_overrides` {ENV_KEY: value} → worker truyền
   `FLOWAPP_JOB_OVERRIDES` (JSON) khi spawn cli.py → config.py áp SAU .env. Server
   whitelist `_JOB_OVERRIDE_KEYS`, đổi → reset tts/bgm/mixing/rendering (sig cache
   chỉ đọc lại câu bị ảnh hưởng; nền theo ducked.mode). Option trống = "theo cấu
   hình chung (giá trị hiện tại)"; {} = bỏ hết đè.
4. Fix nhỏ: `edSubAt` đọc nhầm id `sspl` → `sspl-ed` (overlay giờ tôn trọng select
   "Nhịp" trong editor).

Verify: subprocess với FLOWAPP_JOB_OVERRIDES ra đúng giá trị đè; UI 6 field nhãn
"theo cấu hình chung (X)" đúng .env; endpoint no-op không enqueue; console sạch.

---

## 2026-07-05 (5) — Desktop (F:\MyProject\vietsubvideo)

### Fix BUG NỀN TẢNG: Cấu hình lưu qua UI âm thầm KHÔNG áp dụng tới khi restart server

Lộ khi user bật "Chuyển ngữ điệu gốc" rồi chạy lại job → 0/23 câu được transfer.
Nguyên nhân: `config.py` dùng `load_dotenv()` mặc định (`override=False`) — server
nạp `.env` vào os.environ lúc khởi động; job con (`cli.py --resume`) THỪA KẾ
environment đó; dotenv trong con thấy biến đã có → giữ giá trị CŨ → mọi thay đổi
Cấu hình qua UI chỉ ăn sau khi restart server. Không lộ trước giờ vì dev hay restart.

Fix: `load_dotenv(BASE_DIR/".env", override=True)` — `.env` là nguồn sự thật duy
nhất (UI ghi vào đây), luôn thắng environment thừa kế. Verify bằng mô phỏng đúng
kịch bản (env cũ 0, .env mới 1 → đọc ra 1).

---

## 2026-07-05 (4) — Desktop (F:\MyProject\vietsubvideo)

### 4 yêu cầu: nền hạ đều, chỉnh âm nền trong editor, list cao bằng video, fix "vẫn nhiều giọng"

1. **"Giữ nhạc/SFX gốc" thêm chế độ "Hạ audio gốc ĐỀU suốt video"** (`KEEP_BGM=flat`,
   `config.DUCK_ALL`): hết kiểu nền "bơm" to–nhỏ theo thoại gây khó chịu. s6 ghi
   marker `ducked.mode` (demucs?/all|speech/gain) → đổi chế độ/gain là tự dựng lại
   nền, không kẹt bản cũ. `.env` user đã đặt flat.
2. **Editor thêm 🎚 "Âm nền gốc"** (−8/−14/−20/−26/−34 dB): chỉnh âm nền THEO JOB
   sau khi nghe output — `Job.bed_gain_db` (field mới, thắng DUCK_GAIN_DB), gửi qua
   `SegmentEdits.bed_gain_db`; đổi giá trị → chỉ dựng lại nền+trộn+render, KHÔNG
   đọc lại giọng.
3. **Danh sách câu editor cao BẰNG video** (fitList theo `#ed-stage`, đo lại khi
   loadedmetadata/resize) — video dọc không còn thừa khoảng trống.
4. **Fix "vẫn nghe nhiều giọng khi 1 giọng"** — dubbed audio thực tế ĐÃ 1 giọng
   (23/23 NamMinh p0); nguồn lệch là: (a) nút 🔊 nghe thử đọc theo NHÃN nam/nữ →
   câu "Nữ" ra HoaiMy trong khi render NamMinh — `tts_preview` giờ gate theo
   `TTS_SINGLE_VOICE` (cả edge lẫn engine trả phí); (b) pitch CẢM XÚC (±4–10Hz)
   giờ cũng =0 khi 1 giọng (rate/volume giữ diễn cảm), sig `:e<label>1` → tự đọc
   lại đúng câu có nhãn; (c) editor hiện chú thích "1 giọng: mọi câu đọc giọng chính".
5. Prompt dịch: cân đối 2 CHIỀU với nhịp câu gốc (không vượt, không ngắn hơn hẳn).

Job 8691dd (AI donghua) đã process lại: 7 câu cảm xúc đọc lại pitch-0 + nền flat + render.

---

## 2026-07-05 (3) — Desktop (F:\MyProject\vietsubvideo)

### Fix OCR video nhiều chữ trên hình (vlog quán ăn) — crop dải TRỘI + trần gộp 4 dòng

User test video 大学生饭店兼职 (vlog quán ăn, thoại bắn nhanh) → chất lượng tệ:
transcript ngập menu/giá tiền (15元 80元, tên món), câu gộp tới 7 lượt thoại.

1. **`_auto_crop_top` chọn DẢI TRỘI thay vì phân vị 15%**: video quán ăn đầy chữ
   giữa hình (bảng menu y=0.5-0.6) kéo crop lên sàn 0.30 → OCR nuốt menu vào thoại.
   Giờ gom mép-trên vào băng 0.05, chọn băng NHIỀU DÒNG NHẤT (phụ đề hiện mọi cảnh
   vị trí cố định; menu/biển hiệu chỉ vài cảnh), đồng điểm lấy băng thấp hơn.
   Đo lại: quán ăn 0.30→0.575, Douyin cũ 0.582 (không đổi hành vi video sạch).
2. **`segtools.MERGE_MAX_PIECES=4`**: trần số dòng sub gốc gộp vào 1 câu đọc —
   thoại bắn nhanh không trần sẽ gộp 6-7 lượt (nhiều người nói) thành câu tràng
   giang, giọng đọc lệch hình.

Kết quả extract lại: 86 dòng thô → 24 câu, 0 câu dính 元, max 4 mảnh/câu. Job đã
tự process lại + render (theo quy trình [[auto-reprocess-then-notify]]).

---

## 2026-07-05 (2) — Desktop (F:\MyProject\vietsubvideo)

### Fix: phụ đề XEM TRƯỚC trong editor hiện nguyên câu gộp dài (sub thật đã tách)

User soi ảnh: sub gốc 1 dòng ngắn (吴经理负责二楼) mà overlay editor lòi cả câu gộp
5 dòng. `sub_vi.srt`/final.mp4 THẬT đã tách đúng (91 block) — chỉ overlay preview
(`edHighlight`) hiển thị nguyên textarea, không qua logic tách nhịp.

- server `get_segments` trả thêm `pieces` (trước bị strip).
- JS port `edSplitText()` = `s8_render._split_text` (cùng regex dấu câu, cùng tỉ
  trọng, cùng điều kiện ≥2 từ/mảnh) + `edSubAt(idx,t)` chọn đúng mảnh theo nhịp;
  overlay cập nhật theo TỪNG mảnh (mỗi timeupdate), tôn trọng select "sspl".
- Verify parity trên seg 4 job 40de66: JS tách y hệt Python từng ký tự; t=24.3s
  hiện đúng "Quản lý Ngô phụ trách tầng hai mà," khớp sub gốc trong ảnh user.

---

## 2026-07-05 (1) — Desktop (F:\MyProject\vietsubvideo)

### Fix 3 vấn đề user nghe/thấy trên video dọc Douyin (job 40de66)

**#1 "1 giọng mà nghe ra nhiều giọng"** — TTS đúng là chỉ dùng NamMinh (30/30 .sig)
nhưng PROSODY ép PITCH theo cao độ giọng GỐC từng câu (baseline chung khi không
diarize; video có cả diễn viên nam+nữ) → pitch bị bẻ −19..+23Hz → nghe như người
khác. Fix: `prosody.pitch_hz(seg)` = 0 khi `TTS_SINGLE_VOICE` (gate lúc ĐỌC —
sig_tag/edge_kwargs/emotion đi qua đây) → .sig tự đổi, chỉ câu bị ảnh hưởng đọc
lại; nhãn pitch vẫn đo/lưu nên tắt 1-giọng là dùng lại ngay. Rate/volume + pitch
CẢM XÚC nhỏ vẫn giữ (diễn cảm, không đổi danh tính giọng). Verify: sig tags còn
đúng `p0` toàn bộ.

**#2 "SUB_SPLIT không tách"** — KHÔNG phải bug: user xem output của bản OCR hỏng cũ
(2 câu khổng lồ, không có nhịp để tách). Data mới: `pieces` sống đủ 23/30 segment,
make_srt tách 30 câu → **101 dòng hiển thị** đúng nhịp sub gốc. Re-render là thấy.

**#3 "giọng đọc lê sang câu sau"** (24/30 câu tràn, max 5715ms) — fix 3 lớp:
1. S4: payload dịch thêm `max_s` (giây slot) + prompt "≈4 âm tiết/giây, thà ngắn
   hơn"; review không được kéo dài câu. Bản dịch job này ngắn đi 31% (5731→3937 ký tự).
2. S5: `_fit_slot()` — đọc xong đo mp3, dài quá slot (tới start câu kế) → đọc lại
   MỘT lần với edge rate cộng đúng phần vượt (trần tổng +50%; rate TTS tự nhiên
   hơn atempo). Chỉ nhánh edge; slot gắn `_slot_s` in-RAM, không vào transcript.
3. S7: `_trim_silence()` cắt khoảng lặng 2 đầu file TTS (edge đệm ~0.3–0.7s câm ở
   đuôi = "tràn giả") + fix bug file `_sped.wav` cũ bị tái dùng sai tốc độ.

Kết quả job thật: tràn 24→16 câu, trong đó 13 câu ≤282ms (không nghe ra); 3 câu
còn tràn nặng là **đoạn QUẢNG CÁO app thuê nhà chèn giữa video** — chữ UI app dày
đặc bị OCR coi là thoại (60–76 chữ Hán/slot 1.5–5s, vật lý không đọc kịp) → đúng
chỗ user Mute trong editor. 27 câu được S5 tự fit rate.

---

## 2026-07-04 (12) — Desktop (F:\MyProject\vietsubvideo)

### Fix BUG: video DỌC (Douyin/Shorts) OCR chỉ ra 2 câu (đáng lẽ ~100)

Triệu chứng user: video 9:16 xuất ra chỉ 2 dòng sub dù "quét OCR ra 300+".
Chẩn đoán: "300+" là số KHUNG (2fps×158s≈316), không phải dòng. Thật ra OCR chỉ
bắt chữ ở 8/316 khung → 2 câu.

**Nguyên nhân gốc:** `OCR_CROP_TOP=0.70` (cứng) chỉ quét dải 70%→đáy — hợp phim
ngang 16:9 (sub sát đáy). Video DỌC Douyin đặt sub ở **~65%** → NẰM TRÊN vùng quét
→ bị crop cắt mất trước khi OCR đọc. Đo thực tế (t=30/55/80/110): sub ở y=0.64–0.69,
OCR đọc rõ (conf 0.77–0.89) nhưng bị bỏ vì ngoài crop.

**Fix:** `OCR_CROP_TOP="auto"` (mặc định mới) → `ocr_subs._auto_crop_top()` quét thử
~16 khung TOÀN màn hình, đo mép trên dải phụ đề, đặt crop ôm đúng dải (trừ lề). Video
này tự chọn 0.583 → **OCR ra 101 câu** (từ 2). Phim ngang vẫn tự ra ~0.80 như cũ.
Vẫn đặt số tay được (Cấu hình → Nhận dạng thoại → "Vùng quét phụ đề": auto/0.5–0.8).

Liên quan [[app-scope-multi-genre-language]] — app giờ nhận cả video dọc, đừng giả
định layout phim ngang. Job cũ user (chỉ 2 câu) đã reset để OCR lại từ đầu.

### Máy khác pull về: `.env` thêm `OCR_CROP_TOP=auto` (xem .env.example).

---

## 2026-07-04 (11) — Desktop (F:\MyProject\vietsubvideo)

### Gom mọi khóa API/token/mã vào 1 nhóm "🔑 Khóa API & Token" (đầu trang Cấu hình)

Trước đây key rải rác: Gemini ở nhóm Dịch, HF ở Diarization, ElevenLabs/VBee/FPT ở
Lồng tiếng, Telegram ở nhóm riêng. Giờ gộp hết vào MỘT card đầu trang:
Claude, Gemini, ElevenLabs, VBee token + App ID, FPT, HuggingFace, Telegram bot token
+ Chat ID. Các nhóm cũ chỉ còn dòng nhắc "nhập ở nhóm 🔑".

- **Claude API key giờ NHẬP ĐƯỢC trong UI** (thêm `ANTHROPIC_API_KEY` vào
  `SECRET_ENV_KEYS`; `api_key_set` cũng xét `config.ANTHROPIC_API_KEY`). Trước chỉ
  hiện trạng thái ở footer + bắt sửa tay `.env`.
- Ô mật khẩu, đã đặt = placeholder `••••`, để trống khi lưu = giữ khóa cũ (secret
  không bao giờ trả giá trị về). Bỏ nhóm "Thông báo Telegram" (2 field đã dời qua 🔑).
- Verify sống: nhóm 🔑 đứng đầu, đủ 9 ô, không trùng/không thiếu field, lưu 1 khóa
  vô hại KHÔNG xoá secret cũ (api_key_set/gemini_key_set giữ True), không lỗi console.

---

## 2026-07-04 (10) — Desktop (F:\MyProject\vietsubvideo)

### Đại tu UX trang Cấu hình (6 yêu cầu) + chế độ 1 giọng + tab Nghe thử

1. **Bớt rối mắt**: mọi đoạn mô tả dài (luôn hiện) → thu vào icon **ⓘ** cạnh nhãn,
   hover/focus mới bung tooltip. `row()/textrow()` sinh `hint(help)` thay cho `.fhelp`;
   các dòng key (Gemini/HF/ElevenLabs/VBee/FPT/Telegram) cũng chuyển sang ⓘ.
2. **Ẩn Model Claude khi nhà cung cấp = Gemini** (bọc `#claude-cfg`, `applyProviderUI`
   toggle) — Claude vẫn là fallback ngầm, chỉ giấu dòng chọn cho đỡ nhầm.
3. **Thêm model Gemini**: bổ sung `gemini-2.0-flash`, `gemini-2.0-flash-lite`
   (quota free rộng hơn 2.5) — giờ 5 lựa chọn.
4. (Giải đáp) **Kiểu nội dung ≠ Phong cách dịch riêng**: CONTENT_STYLE là preset
   khung dịch (donghua Hán-Việt / chung hiện đại); TRANSLATE_STYLE_EXTRA là chữ tự do
   cộng THÊM lên trên. Đã ghi rõ trong tooltip.
5. **Chế độ 1 giọng** (`TTS_SINGLE_VOICE`, mặc định **1** theo ý user): bỏ phân biệt
   nam/nữ, cả video đọc một giọng; dropdown "Số giọng đọc" (1|2). Chọn 1 → ẩn mọi ô
   "giọng nữ", nhãn ô chính "…nam" → "…". Áp cho MỌI engine qua `s5_tts._seg_nu()`
   (1 choke point → sig cache tự đọc lại đúng); `emotion.vixtts_sample` cũng ép clip
   NAM khi 1 giọng. **Casting nhân vật (voice_ref/Series) vẫn thắng** ở cả 2 chế độ.
6. **Tách "🔊 Nghe thử"** thành tab riêng (cạnh Series): danh sách clip `voices/` +
   nghe/mở thư mục/tải lại chuyển khỏi trang Cấu hình sang `loadPreviewTab()`.

Verify sống trong Claude_Preview: 5 model Gemini, 58 tooltip ẩn mặc định, Claude row
ẩn khi Gemini, 5 ô "giọng nữ" ẩn khi 1 giọng + nhãn đổi đúng, tab Nghe thử 12 clip,
không tràn ngang, không lỗi console; `_seg_nu` đúng cả 2 chiều.

### Máy khác pull về: `.env` thêm `TTS_SINGLE_VOICE=1` (xem .env.example) — mặc định 1 giọng.

---

## 2026-07-04 (9) — Desktop (F:\MyProject\vietsubvideo)

### Fix: video CÂM (không có track tiếng) báo lỗi rõ ràng thay vì dump ffmpeg

User upload file Douyin tải bằng extension web → chỉ có track HÌNH (web Douyin phát
hình/tiếng tách rời) → S2 chết "Output file does not contain any stream" khó hiểu.
`s2_extract` giờ chặn sớm bằng `brand._has_audio()`: báo tiếng Việt rõ nguyên nhân
+ cách sửa (dán LINK để app tự tải đủ, hoặc tải lại bằng tool gộp audio). Verify
end-to-end trên đúng job lỗi; video có tiếng không bị chặn nhầm.

---

## 2026-07-04 (8) — Desktop (F:\MyProject\vietsubvideo)

### Học 2 ý hay từ combo tool "Gemini Auto Translator Pro + Auto CapCut" (bỏ #1 CapCut export theo ý user; KHÔNG copy phần lách bản quyền)

**#2 — Gemini làm engine dịch bên cạnh Claude** (`core/llm.py` mới):
- `structured_json(system,user,schema)` điều phối Claude/Gemini, GIỮ NGUYÊN schema
  → nhãn giọng/cảm xúc/nhân vật y hệt. Gemini gọi bằng urllib (không thêm lib),
  tự chuyển JSON-Schema → responseSchema (type HOA, strip additionalProperties,
  propertyOrdering, giữ description/min/max).
- **Tự fallback về Claude** khi Gemini lỗi/hết quota/timeout → job không chết vì
  rate limit. Test thật: key giả → HTTP 400 (format request ĐÚNG) → fallback Claude ok.
- "Gem" phong cách tùy biến `TRANSLATE_STYLE_EXTRA` chèn vào prompt dịch+soát.
- UI: dropdown Nhà cung cấp (khối Gemini ẩn/hiện), key che như bot token, chọn
  model + giãn nhịp free tier (~10 req/phút). Config: TRANSLATE_PROVIDER,
  GEMINI_API_KEY (secret), GEMINI_MODEL, GEMINI_MIN_INTERVAL.
- **Cần key Gemini THẬT của user để test call thành công** (mình chỉ verify được
  tới bước 400 "thiếu key").

**#3 — Phơi rõ "Đồng bộ khớp thoại"**: `MAX_SPEEDUP` từ hằng số cứng → tùy chọn
Cấu hình (1.0×–2.0×, atempo giữ cao độ; 1.0× = không tăng tốc, chấp nhận tràn).

**Review đối kháng (6 agent) → sửa:** review_pass chịu được JSON hỏng/cắt của Gemini
(bỏ qua thay vì chết job); max_tokens 8000→16000 (Gemini decode tốn token hơn);
TRANSLATE_STYLE_EXTRA + vài text field XÓA được (thêm _EMPTY_OK); lock init
anthropic client; giữ description trong schema; bỏ tham số model chết ở auto_extract.

### Máy khác pull về: `.env` thêm TRANSLATE_PROVIDER=claude + GEMINI_* (xem .env.example).

---

## 2026-07-04 (7) — Desktop (F:\MyProject\vietsubvideo)

### Trang Cấu hình làm lại: full width + helptext từng tùy chọn + rà default

- **Full width, bố cục 2 cột**: mỗi nhóm cấu hình là 1 CARD gập/mở được (CSS
  columns masonry — màn hẹp tự về 1 cột). Nhóm chính mở sẵn (Dịch/Transcript/
  TTS/Thương hiệu), nhóm phụ gập (tự mở nếu tính năng đó đang bật). Nút 💾 Lưu
  thành thanh DÍNH ĐÁY (cuộn tới đâu cũng lưu được) kèm trạng thái API key.
- **Helptext chi tiết cho TẤT CẢ ~40 tùy chọn** (class .fhelp dưới từng dòng):
  mô tả nó làm gì, từng option khác nhau thế nào, khi nào nên chỉnh, đánh đổi
  (vd subtitle_mode giải thích đủ 4 chế độ + lưu ý tự ép burn; TTS engine nói
  rõ license kiếm tiền; KEEP_BGM nói rõ cần GPU + chậm thêm ~¼ thời lượng...).
- **Rà default**: đổi duy nhất `MASTER 0→1` (-14 LUFS chuẩn YouTube — các tập
  đều tiếng, gần như luôn có lợi; đã flip luôn trong .env máy này vì giá trị 0
  cũ là do bulk-save chứ không phải chủ ý). Các default khác giữ nguyên có chủ
  đích (haiku=rẻ, whisper small=an toàn CPU, PROSODY/EMOTION bật, transfer tắt
  chờ thẩm định...) — nay đều có "(khuyên dùng)" trong label + help giải thích.
- Verify: 51 fhelp render, 9 section đúng trạng thái gập/mở, không thiếu field
  nào của saveConfig, engine toggle chạy, 2 cột ở ≥1000px / 1 cột màn hẹp
  (screenshot cả hai), console sạch.

---

## 2026-07-04 (6) — Desktop (F:\MyProject\vietsubvideo)

### Đại tu UX/UI dashboard (mục 5 kế hoạch review — chỉ giao diện, không đổi API)

- **Theme mới**: nền sâu hơn + gradient nhẹ, card có chiều sâu (gradient + hover
  nổi), nút có transition/focus-ring, scrollbar tối, nav STICKY mờ nền (cuộn
  danh sách dài không mất tab), logo chữ gradient, max-width 1560px căn giữa.
- **Thẻ job gọn hẳn**: danh sách stage DỌC 10 dòng → **dải chấm ngang** (1 chấm
  = 1 bước; xanh = xong, xanh dương nhấp nháy = đang chạy, ĐỎ = bước lỗi — job
  failed tự suy bước gãy = bước đầu chưa hoàn thành, kèm nhãn "lỗi ở: …"; rê
  chuột lên chấm xem tên bước). Title kẹp 2 dòng, job id font mono.
- **Toast thay alert()**: 31 chỗ alert chặn màn hình → toast góc phải dưới,
  tự tắt 6s, bấm để đóng, màu theo loại (xanh/đỏ/trung tính) tự nhận diện.
- **Hộp "Thêm video"**: form + upload + series + glossary + cắt video gom vào
  1 khối addbox có viền — hết cảm giác rời rạc.
- **Empty state**: lưới job trống → chỉ dẫn thân thiện thay vì trang trắng.
- Verify bằng screenshot thật từng tab (Jobs/Cấu hình/Series) + DOM inspect
  toast/chấm stage; node --check sạch; console sạch.

---

## 2026-07-04 (5) — Desktop (F:\MyProject\vietsubvideo)

### PLAN 12 #4 — Shorts tự động (`core/shorts.py`) + note phần chưa làm

- Nút **🎬 Tạo Shorts cao trào** (menu 📤 của job đã render): chấm điểm từng câu
  bằng nhãn cảm xúc (gấp/giận +2) + tông giọng đo audio (to/cao/dồn) + mật độ
  thoại → trượt cửa sổ SHORTS_LEN giây, chọn SHORTS_COUNT cửa sổ điểm cao nhất
  không chồng lấn (cách ≥15s), mép cắt bám mép câu. Job cũ không nhãn → vẫn chạy
  bằng mật độ thoại.
- Xuất `<job>/shorts/short_N.mp4` + `info.txt` (mốc thời gian + caption gợi ý
  kèm #Shorts). Kiểu **dọc 9:16** (video thu giữa, nền tự phóng to làm mờ) hoặc
  giữ khung gốc. Cắt từ final.mp4 → sẵn lồng tiếng + phụ đề. Chạy nền, xong tự
  mở thư mục. Config: SHORTS_COUNT/LEN/STYLE (group gập trong tab Cấu hình).
- Test: unit chọn cửa sổ trúng đúng 2 vùng nóng cảm xúc trên timeline 40 câu;
  end-to-end video tổng hợp 120s → 2 clip 1080x1920 ≤60s + info.txt.
- **PLAN 12 cập nhật trạng thái**: còn CHƯA làm #1 bot Telegram 2 chiều,
  #2 auto-pilot theo dõi kênh, #3 đăng theo lịch, #5 playlist series, #6 bảng
  hiệu suất, #7 A/B thumbnail, #9 upload FB/TikTok (chờ duyệt API), #10 brand
  kit. Việc dở khác: VBee chưa test đầu-cuối (cần token); PROSODY_TRANSFER chờ
  nghe thẩm định; GC tự động output/ chưa có.

### Máy khác pull về: `.env` thêm SHORTS_COUNT=2 / SHORTS_LEN=45 / SHORTS_STYLE=vertical.

---

## 2026-07-04 (4) — Desktop (F:\MyProject\vietsubvideo)

### PLAN 11 C/D — TTS trả phí tích hợp trong app (`core/paid_tts.py`)

- Engine mới trong dropdown "Giọng đọc": **elevenlabs** (~$22/th, giống người
  nhất, đa ngôn ngữ — dùng cả khi TARGET_LANG ≠ vi) · **vbee** · **fpt** (VN,
  chỉ tiếng Việt — đích khác tự về edge). Đây là các engine AN TOÀN BẢN QUYỀN
  để kiếm tiền (edge/viXTTS thì không).
- Key/token nhập tab Cấu hình (input password, CHE như bot token — server chỉ
  báo đã-đặt-hay-chưa, đã test không lộ qua API). Giọng nam/nữ từng dịch vụ
  cấu hình được; mặc định sẵn (Adam/Rachel, mạnh dung/ngọc huyền, leminh/banmai).
- Ăn khớp hệ thống: câu cast voice_ref vẫn đọc viXTTS (casting thắng); prosody
  transfer mức 3 vẫn áp lên output; .sig có engine+giọng → đổi là tự đọc lại;
  nghe thử editor dùng CHÍNH engine trả phí (tốn phí ~1 câu); S5 in tổng ký tự
  TRƯỚC khi gửi (các dịch vụ tính phí theo ký tự). Thiếu key → job fail với
  message rõ (không âm thầm rơi về edge).
- Test: ElevenLabs + FPT xác nhận format request qua đường lỗi 401 thật (key
  giả); VBee viết theo docs công khai — CẦN TOKEN THẬT test đầu-cuối, sai
  schema thì message lỗi sẽ in nguyên phản hồi server để sửa nhanh.

### Máy khác pull về: `.env` thêm các khóa ELEVENLABS_*/VBEE_*/FPT_* (xem .env.example).

---

## 2026-07-04 (3) — Desktop (F:\MyProject\vietsubvideo)

### PLAN 11 MỨC 3 — Prosody transfer (`core/prosody_transfer.py`, PROSODY_TRANSFER=0 mặc định)

- Ép DÁNG đường ngữ điệu câu GỐC lên giọng đọc bằng **Praat PSOLA**
  (praat-parselmouth — CPU, chạy cả 2 máy, không cần model GPU): trích F0 câu
  gốc (ưu tiên vocals.wav demucs) → dáng 24 điểm chuẩn hóa semitone → ép quanh
  trung vị giọng đọc (w=0.7, kẹp ±7 semitone), NEO vào khoảng có tiếng của TTS.
  PSOLA giữ nguyên độ dài → không ảnh hưởng atempo S7. Áp cho cả edge lẫn viXTTS,
  chạy ngay sau synth trong S5; cờ :pt1 vào .sig → bật/tắt là tự xử lý lại.
- **Đo thật**: tương quan dáng F0 với nguồn +0.38 → **+0.66** (nguồn = giọng
  người thật truyền cảm, TTS = edge trung tính). Bug đầu tiên tự bắt được khi
  đo: trải dáng lên cả file (dạt vào khoảng lặng đầu/cuối) → sửa neo theo
  khoảng có tiếng.
- Vì sao KHÔNG dùng OpenVoice/RVC như phác thảo: RVC giữ âm vị nguồn (ra tiếng
  Trung giọng mới), OpenVoice chuyển timbre (viXTTS đã làm) — cái cần là ngữ
  điệu → PSOLA đúng công cụ. Mặc định TẮT (thử nghiệm) — bật trong tab Cấu hình
  rồi nghe thử job thật để thẩm định chất lượng.

### Máy khác pull về: `pip install praat-parselmouth` + `.env` thêm `PROSODY_TRANSFER=0`.

---

## 2026-07-04 (2) — Desktop (F:\MyProject\vietsubvideo)

### PLAN 11 MỨC 2 — Nhãn cảm xúc A+B chung một mạch (`core/emotion.py`, EMOTION=1)

- **A**: Claude gắn nhãn cảm xúc từng câu khi dịch (S4, field "emotion":
  binhthuong|gap|gian|buon|thitham — chỉ gắn khi RÕ RÀNG, lưu trên segment khi
  khác bình thường). Giữ nhãn qua fix_leaks (cùng bài học với character).
- **B**: S5 map nhãn theo engine — edge-tts: offset rate/pitch/volume CỘNG vào
  prosody mức 1 (đo audio), kẹp trần ±25%/±30Hz/±25%; viXTTS: chọn clip mẫu
  voices/ hợp cảm xúc (giận→mau-*-nhanh, buồn→mau-*-cham/nhe-nhang; casting
  voice_ref vẫn thắng — danh tính > cảm xúc). Nhãn vào .sig → đổi nhãn/bật tắt
  là câu bị ảnh hưởng tự đọc lại đúng.
- Nghe thử editor giờ áp CÙNG nhãn cảm xúc + đúng giọng TARGET_LANG (trước là
  giọng vi cứng, không sắc thái — nghe khác render).
- Hai tầng bổ trợ: prosody = đo audio khách quan; nhãn = ngữ nghĩa lời thoại
  (bắt được mỉa mai/đe dọa-nói-nhỏ mà audio không lộ). Config UI cạnh PROSODY.
- Test: unit (clamp/mapping ra file mẫu thật/schema/cache), edge synth thật với
  kwargs giận, tts-preview 2 đường. Review đối kháng: 1 lỗi thật (preview thiếu
  cảm xúc) đã sửa; 2 "CRITICAL" là false positive (sig lệch fallback là thiết kế
  cũ có chủ đích, không do emotion).

### Máy khác pull về: `.env` thêm `EMOTION=1` (xem `.env.example`). Không gói pip mới.

---

## 2026-07-04 — Desktop (F:\MyProject\vietsubvideo)

### Đợt dọn dẹp + tối ưu theo review tổng thể (5 mục, user duyệt)

**1. Dọn rác:** XÓA worker.py, bot/ (aiogram stub), uploaders/ (Phase-3 stub),
_azure_tts.html — tất cả đã bị thay bởi worker thread trong server.py,
core/notify.py, core/youtube_upload.py, không ai import. Gỡ field chết
Job.platforms + Job.chat_id (state.json cũ vẫn nạp được — Job.load lọc key lạ).
Gỡ aiogram khỏi requirements; PIN yt-dlp==2026.6.9 (bản mới vỡ Douyin).
KHÔNG xoá output/*.mp4 cũ — sau khi dọn data/jobs, đó là bản duy nhất còn lại.

**2. Series đồng bộ 2 máy (sửa lỗ thiết kế):** kho series chuyển
data/series (gitignore — mỗi máy một bản!) → **series/ trong repo** (git theo
dõi, push/pull là casting+glossary nhất quán xuyên máy). Glossary mặc định
cũng chuyển → series/_glossary_default.txt. Tự DI TRÚ 1 lần khi chạy.

**3. Log per-job:** worker ghi toàn bộ stdout/stderr của cli.py vào
<job>/run.log (append + header mỗi lượt) → job lỗi lúc vắng mặt vẫn còn vết.
Endpoint GET /api/jobs/{id}/log (đọc 256KB cuối); UI: nút 📜 Log trong menu
Soát. Bonus: hết luôn rủi ro crash in tiếng Việt ra console cp1258.

**4. Đĩa + hiệu năng poll:** nút 🧹 Dọn file tạm (job DONE): xoá wav trung
gian (audio_16k/full, vocals, ducked, dubbed...) + *_sped.wav, GỠ
extracting/bgm/mixing khỏi completed_stages → "Sửa lời thoại" sau đó tự tách
audio lại từ source (đã trace: extracting đứng trước tts nên an toàn).
_job_summary cache seg_total/tts_done theo mtime (hết đọc cả transcript mỗi
3 giây); progress chỉ đọc khi job đang chạy. Vá vận hành: rerender gate khoá
file như save_segments; .env ghi nguyên tử; atexit kill job mồ côi khi server tắt.

**5. UX + hàng đợi:** thẻ job gom 9 nút → 2 nút chính + 2 menu (🔎 Soát ▾ /
📤 Xuất bản ▾). Tab Cấu hình gập 4 nhóm ít dùng (diarization/khử ồn/YouTube/
Telegram — tự mở nếu đã bật). Hàng đợi: nút **⬆ Ưu tiên** (job chờ nhảy lên
đầu) + **⏸ Tạm dừng hàng đợi** (job đang chạy chạy nốt, job kế chờ mở lại).

Review đối kháng (2 vòng, 29 agent tổng): 0 lỗi CRITICAL/HIGH xác nhận.

### Máy khác pull về cần làm

1. Sau pull, series ở máy đó (data/series) sẽ TỰ di trú sang series/ khi chạy
   lần đầu — nếu 2 máy có series TRÙNG TÊN khác nội dung, bản trong repo thắng,
   bản local giữ nguyên ở data/series (không đè) → tự xử lý tay nếu cần.
2. `pip uninstall aiogram` (tuỳ, không bắt buộc); yt-dlp giữ 2026.6.9.

---

## 2026-07-03 (đêm) — Desktop (F:\MyProject\vietsubvideo)

### Tính năng mới — chốt nốt #15 + #16 (hết sạch danh sách #1–18)

- **#15 UI duyệt glossary gợi ý** (`core/glossary.py`, `webui/server.py`, UI):
  nút **📒 Tên riêng** trên thẻ job (sau bước transcript) → modal hiện bảng tên
  riêng hiện tại + danh sách Claude trích từ chính video (S4 giờ LƯU cache
  `glossary_auto.json`; chưa có cache thì trích live 1 call). Bấm ➕ từng mục /
  ➕ tất cả; checkbox **lưu thêm vào series** (chỉ THÊM tên chưa có, không đè);
  **💾 Lưu & dịch lại** = reset job về sau transcript (xoá transcript_vi/tts/
  final/metadata) rồi tự resume — dịch lại với glossary mới.
  `auto_extract` có bản generic (mọi ngôn ngữ nguồn, không CJK gate) khi không
  phải donghua-tiếng-Việt. Endpoint: GET `.../glossary-suggest`, POST `.../glossary`.
- **#16 Lồng tiếng đa ngôn ngữ ĐÍCH** (`core/langs.py`, `TARGET_LANG` trong
  Cấu hình): vi|en|zh|ja|ko|es|fr|id|th|pt. Khác vi → S4 dùng prompt dịch/review
  theo ngôn ngữ đó (bỏ Hán-Việt/donghua), S5 đọc bằng cặp giọng edge-tts của
  ngôn ngữ (tên giọng đã verify `--list-voices`; đổi TARGET_LANG là .sig lệch →
  tự đọc lại), S9 metadata viết cùng ngôn ngữ. Đích zh/ja: TẮT leak-check chữ
  Hán (hợp lệ) + review cho phép CJK; `_CLAUSE_SPLIT` (sub_split) thêm dấu câu
  CJK 。？！、；：. **Giới hạn**: viXTTS/casting clone là finetune tiếng Việt →
  đích ≠ vi thì mọi câu (kể cả voice_ref) đọc edge, có log nhắc.

### Ghi chú kỹ thuật

- Job thật chạy tối nay đã đi qua s4 mới → `glossary_auto.json` sinh tự nhiên
  (5 tên: Đường Tam, Đấu La Đại Lục...) — cache suggest hoạt động ngay.
- Test: reset "dịch lại" đúng stage/file; series merge dedupe; edge en-US OK;
  clause-split CJK/VI đúng; JS node --check sạch.

### Máy khác pull về cần làm

1. `.env` thêm `TARGET_LANG=vi` (xem `.env.example`) — không có gói pip mới.
2. Job cũ muốn thấy gợi ý glossary: bấm 📒 Tên riêng (lần đầu trích live 1 call
   Haiku rồi cache).

---

## 2026-07-03 — Laptop (C:\MyProject\FlowApp)

### Tính năng mới

- **Khung viền nâng cấp** (`69943b3`): khung PNG dựng bằng **9-slice** (góc giữ tỉ
  lệ, cạnh kéo 1 chiều — không méo ở mọi tỉ lệ kể cả video dọc 9:16); phụ đề **tự
  né khung** (đo bề dày khung ở đáy → cộng margin, PNG đo bằng kênh alpha); chế độ
  **"khung ngoài" (pad)** — thu hình vào trong, khung không che nội dung; preview
  "Xem thử" giờ vẽ cả khung.
- **#8 Nhận diện NGƯỜI NÓI — diarization pyannote** (`0a72d77`, `core/speakers.py`):
  nhãn cụm S1/S2… vào batch dịch (Claude gán nhân vật nhất quán), giới tính theo
  CỤM (trung vị F0), engine viXTTS tự chia mỗi cụm một clip `voices/` riêng.
  Casting series/chỉnh tay luôn thắng. Kết quả sửa được trong `speakers.json`.
  Bật: DIARIZE=1 + HF_TOKEN (cần `pip install pyannote.audio` + chấp nhận điều
  khoản 2 model pyannote trên HuggingFace — chỉ desktop GPU; laptop tắt mặc định).
- **Xóa/che watermark kênh gốc** (`072495e`, `core/watermark.py`): 4 cách theo
  vùng vẽ trên editor (khung đỏ) — **delogo** (nội suy, sạch nhất cho watermark
  tĩnh), **blur**, **dải đen**, **đè logo kênh mình**; + **cắt mép** (crop tối đa
  20%/cạnh rồi phóng lại, khung xanh = phần giữ). Crop tự quy đổi tọa độ băng
  che/box sub/vùng wm vẽ sau nó. Test thật: xóa sạch logo 斗罗大陆 góc phải-dưới.
- **Tông giọng theo audio gốc — PLAN 11 mức 1** (`83add51`, `core/prosody.py`):
  đo F0 + tốc độ nói + RMS từng câu so với MỨC NỀN TỪNG NGƯỜI NÓI → chỉnh
  rate/pitch/volume edge-tts. Test job Douyin: 6/21 câu chỉnh; câu hét tên chiêu
  nhận r-12%/p+25Hz/v+10%. Bật tắt: PROSODY (mặc định 1). Đo trên vocals.wav
  (demucs) nếu có — desktop bật KEEP_BGM sẽ chính xác hơn.
- **Nhịp phụ đề (sub_split)** (`169f4f0` + chốt an toàn `04fc5f0`): segtools giờ
  GIỮ mốc thời gian từng dòng gốc khi gộp (`pieces`); render tách câu Việt hiển
  thị theo đúng nhịp sub gốc (cắt tại dấu câu) — GIỌNG vẫn đọc câu gộp liền mạch.
  Option per-job "Nhịp" trong editor + SUB_SPLIT mặc định (=1). Job Douyin:
  21 → 104 block, khớp ~1:1 nhịp gốc. Job cũ thiếu pieces → tự về cả câu.
  Chốt an toàn: <2 từ/mảnh không tách (tránh bổ đôi tên riêng khi mốc nhiễu).

### Sửa lỗi

- **OCR làm MỌI job mới chết ở transcribing** (`524bc07`): code tiến độ (desktop
  #9) gọi `pool.imap` — ProcessPoolExecutor không có imap, đổi `.map`. Lỗi chỉ lộ
  khi chạy job mới đầu tiên sau merge desktop.
- **Khôi phục mode `cover_only`** (trong `69943b3`): bị MẤT khi desktop dựng lại
  cây mã (thư mục không còn .git). Che sub gốc nhưng không in sub Việt — để
  upload sub_vi.srt riêng lên YouTube, viewer bật/tắt không chồng sub.
- **Server in tiếng Việt có thể 500** (trong `072495e`): uvicorn console cp1258 —
  ép stdout/stderr UTF-8 như cli.py.
- **launch.json** (`63737a0`): đường dẫn tuyệt đối F:\ của desktop → `.venv`
  tương đối, chạy được cả hai máy.

### Kết quả test đáng nhớ

- **Bilibili**: API bảng xếp hạng (tab Phim hot) chạy KHÔNG cần đăng nhập (quét
  được 197 video); nhưng TẢI video bị 412 — cần cookie đăng nhập
  (YTDLP_COOKIES_FILE). Chưa test tải vì chưa có cookie Bilibili.
- **Douyin**: yt-dlp KHÔNG tải được kể cả có cookie tươi, kể cả bản nightly —
  extractor thiếu chữ ký `a_bogus` (TODO trong source yt-dlp). Thông báo "Fresh
  cookies needed" gây hiểu lầm. **Đường vòng hoạt động tốt**: tải qua SaveTik →
  nút "📁 Upload video từ máy". yt-dlp giữ bản stable 2026.06.09.
- Job Douyin đầu tiên hoàn chỉnh (2.4 phút, 21 câu, HD 1080p) — dùng làm chuẩn
  test cho prosody + sub_split.
- Video dọc 9:16 chạy trọn pipeline; lưu ý OCR_CROP_TOP nếu sub nằm giữa màn hình.

### Máy khác pull về cần làm

1. `git pull` (không có gói pip mới BẮT BUỘC; pyannote là tùy chọn).
2. Bổ sung khóa mới vào `.env` (xem `.env.example`): `PROSODY=1`, `SUB_SPLIT=1`,
   `DIARIZE=0`, `HF_TOKEN=`, `DIARIZE_MAX_SPK=0`.
3. Desktop muốn dùng diarization: `pip install pyannote.audio` + tạo HF token +
   bấm đồng ý điều khoản `pyannote/segmentation-3.0` và
   `pyannote/speaker-diarization-3.1` trên huggingface.co → DIARIZE=1.
4. PLAN.md: mục 11 (giọng cảm xúc — mức 1 đã làm, A/B/C/D để dành) + mục 12
   (backlog 10 ý tưởng, #8 đã xong) là danh sách việc tương lai.
