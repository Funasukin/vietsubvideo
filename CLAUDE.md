# FlowApp — CLAUDE.md (hồ sơ bàn giao đa máy)

File này để agent trên BẤT KỲ máy nào đọc là hiểu dự án và làm việc tiếp được ngay.
Claude Code tự nạp file này mỗi phiên. Nhật ký chi tiết từng đợt: [CHANGELOG.md](CHANGELOG.md)
— **ĐỌC các mục đầu CHANGELOG trước khi làm gì** (biết máy kia vừa làm gì), và
**GHI 1 mục mới lên ĐẦU CHANGELOG cuối mỗi phiên**.

## App là gì

Dashboard FastAPI chạy local trên Windows, tự động hoá toàn bộ: tải video
(YouTube/Bilibili/Douyin/upload) → transcript (OCR hardsub RapidOCR, fallback
Whisper) → dịch bằng LLM (Claude, fallback/chọn Gemini) → TTS tiếng Việt
(edge/viXTTS clone/ElevenLabs/VBee/FPT) → xử lý nhạc nền (duck/demucs) → mix →
render (NVENC) → metadata YouTube. Mục tiêu: kênh YouTube **kiếm tiền** (mọi
quyết định giọng đọc/nhạc phải xét license thương mại).

KHÔNG còn chỉ donghua: `CONTENT_STYLE=donghua|general`, `TARGET_LANG` 10 ngôn
ngữ, `WHISPER_LANGUAGE` rỗng = tự nhận diện. Tính năng mới đừng giả định video
là phim Trung.

## Chạy app + checklist máy mới

```powershell
# chạy server (KHÔNG --reload — sửa .py là PHẢI restart; sửa static/*.js|html chỉ cần F5)
.venv\Scripts\python.exe -m uvicorn webui.server:app --host 127.0.0.1 --port 8790
# hoặc run.bat (tự tạo venv + cài lib). Script lẻ: .venv\Scripts\python.exe -X utf8 ...
```

`.claude/launch.json` có sẵn cấu hình tên **"flowapp"** — agent dùng preview
tool để mở/restart server thay vì Bash.

**KHÔNG đi theo git — máy mới phải copy tay từ máy cũ (hoặc tạo lại):**

| Thứ | Vì sao | Cách có lại |
|---|---|---|
| `.env` | chứa API key (secrets) | copy tay MỘT LẦN qua USB/khác — TUYỆT ĐỐI không commit |
| `models/viXTTS/` (~1.8GB) | model clone giọng | tải từ HuggingFace `capleaf/viXTTS` (cần đủ config.json + model.pth + vocab.json) |
| `voices/` | clip giọng mẫu clone/casting | copy tay |
| `music/`, `logo/`, `clips/` | asset thương hiệu | copy tay |
| `voice_samples/` | file mẫu VOICE_FX (nút 🔊 tab Cấu hình) | copy tay hoặc chạy `voice_samples/_gen_fx_demo.py` |
| `data/` | jobs đã xử lý | thường KHÔNG cần mang theo — job làm mới ở máy mới |

Máy không có các thứ trên vẫn chạy được: tab Cấu hình có **card Trạng thái máy**
(`/api/capabilities`) báo thiếu gì (GPU/ffmpeg/package/model/key). Máy không GPU:
viXTTS/demucs không chạy, Whisper để chế độ Tự động (CPU int8), render dùng CPU.

## Bản đồ kiến trúc

```
cli.py                  # chạy 1 job: cli.py --resume <job_id> (worker spawn subprocess này)
config.py               # đọc .env → hằng số runtime; FLOWAPP_JOB_OVERRIDES (JSON) per-job thắng .env
core/
  job.py                # Job/state.json, checkpoint qua completed_stages
  pipeline.py           # chạy tuần tự s1→s9, telemetry "STAGE name=.. seconds=.." vào run.log
  stages/s1_download → s9_metadata   # các bước; s5_tts._seg_nu là choke point chọn giọng
  duration.py           # TRỌNG TÀI thời lượng (một thước đo trim chung S5/S7) — xem "Thiết kế đã chốt"
  voicesig.py           # chữ ký giọng thuần dữ liệu — S5 và /override-impact dùng CHUNG
  paid_tts.py           # ElevenLabs/VBee/FPT
  frames.py, brand.py, prosody.py, emotion.py, vixtts.py, langs.py, segtools.py ...
webui/
  server.py             # routes chung + /api/config (settings schema) + /api/capabilities + /api/profiles
  worker.py             # queue + process lifecycle. Biến vô hướng (_running_id, _current_proc,
                        #   _queue_paused) PHẢI truy cập qua "worker.X" — from-import là dính bản cũ
  routes_editor.py      # APIRouter cụm editor (segments/override-impact/mix-preview/tts-preview)
  common.py             # helper chung (+ engine_caps(env) — tính từ env TƯƠI)
  envfile.py            # đọc/GHI .env chuẩn dotenv (quote/escape); write_env(updates, unset)
  settings_schema.py    # NGUỒN SỰ THẬT config: 81 khóa, validate, factory default, profile allowlist
                        #   ⚠ đổi default = sửa CẢ schema lẫn config.py (2 mặt của 1 setting)
  static/               # classic scripts CÙNG global scope, THỨ TỰ NẠP quan trọng:
                        #   app-core.js → app-config.js → app-jobs-extra.js → app-trending.js
                        #   → app-editor.js → app-visual.js  (+ style.css, index.html 208 dòng)
scripts/bench_models.py # benchmark model load (JSONL)
```

## Quy ước làm việc với chủ dự án (QUAN TRỌNG — làm sai là hỏng lòng tin)

1. **Hỏi thì CHỈ TRẢ LỜI; user CONFIRM thì mới code.** Đề xuất xong phải chờ chốt.
2. **Sửa pipeline → TỰ chạy lại video test** (reset đúng stage, chờ chạy xong)
   rồi mới báo "**vào test**". Không đụng pipeline thì nói rõ "test ngay được".
3. **CHANGELOG.md**: đọc đầu phiên, ghi mục mới ĐẦU file cuối phiên (định dạng
   `## YYYY-MM-DD (n) — Desktop/Laptop`). Đây là kênh đồng bộ 2 máy duy nhất.
4. **Git**: KHÔNG BAO GIỜ commit `.env`/`data/`/`output/`/secrets. Leak-scan
   diff trước commit (sk-ant-, AIza, hf_...). Giá trị secret không bao giờ echo
   ra chat/log — chỉ báo "đã đặt/chưa đặt". Commit message tiếng Việt, kết thúc
   bằng `Co-Authored-By: Claude <model> <noreply@anthropic.com>`. Push lên
   `github.com/Funasukin/vietsubvideo` (nhánh main). Nếu init lại repo thì
   rebase lên lịch sử remote, ĐỪNG force push.
5. **Job thật của user không được đụng** (xoá/reset/chạy lại) — chỉ thao tác
   trên job test do agent tự tạo (đặt id kiểu aaa001... cho dễ nhận).
6. **Workflow 3 agent** (khi user muốn lấy thêm ý kiến): viết đề xuất
   `DEXUAT_<chủđề>.md` ở gốc repo → user đưa cho Codex + Gemini trả lời thành
   `*_CODEX.md`/`*_GEMINI.md` → mình VERIFY TỪNG CLAIM của họ trong code (họ
   ngang hàng: ý đúng ghi nhận, sai phản hồi lại có dẫn chứng) → viết
   `*_TONGHOP.md` → user chốt theo số. Các file AUDIT_*/DEXUAT_* hiện có là hồ
   sơ các vòng đã xong.
7. **Review đối kháng trước khi commit đợt lớn**: spawn agent riêng soát diff
   tìm bug thật (đã nhiều lần bắt được lỗi nghiêm trọng).
8. **Sau khi Edit file HTML/JS**: scan ký tự điều khiển literal
   (`ord(c) < 32` ngoài \n\r\t) — Edit tool từng làm hỏng U+0000 vào source
   khiến toàn bộ JS chết. `node --check` cho JS, `py_compile` cho Python.

## Gotchas kỹ thuật (đã trả giá mới biết)

- **uvicorn không --reload**: sửa .py xong phải restart server (dùng preview
  tool stop/start "flowapp"). Port 8790 kẹt tiến trình mồ côi →
  `Get-NetTCPConnection -LocalPort 8790` + `Stop-Process`.
- **Windows khoá file media đang phát**: browser đang phát `dubbed_audio.wav`/
  `final.mp4` thì ghi đè/xoá sẽ fail âm thầm (WinError 32) — nhả file trước,
  endpoint trả 409 khi khoá (`_unlink_quiet` trong common.py).
- **Norton TLS interception** (máy desktop): HTTPS bị chặn → đã sửa bằng
  `truststore` trong config.py. Máy khác có antivirus chặn tương tự thì nhớ vụ này.
- **Preview browser của Claude Code không có codec H.264** — final.mp4 không
  phát được trong preview pane; verify playback bằng cách khác (ffprobe, mở tay).
- **PROSODY/EMOTION migration marker**: config.py có block migration ghi
  `# flowapp-migrated: prosody-emotion-default-2026-07-10` vào .env — idempotent
  bằng marker, ĐỪNG đổi thành "thiếu key thì thêm" (sẽ phá nút ↺ unset).
- **`/api/config` unset semantics**: reset = XOÁ key khỏi .env (về factory
  default của schema), không phải ghi lại giá trị default.
- Model load đo được (W-0): Whisper small CPU ~24s, viXTTS ~26s (cold 84s),
  demucs 0.2s — worker thường trú (W-2) đã bàn và HOÃN, chỉ làm khi telemetry
  chứng minh tiết kiệm ≥20-30s/job.

## Thiết kế đã chốt (đừng phá khi sửa vùng lân cận)

- **Trọng tài thời lượng** (`core/duration.py`): `MAX_SPEEDUP` là trần **NHÂN
  tổng** mọi lớp tăng tốc (engine đọc nhanh × atempo hậu kỳ ≤ trần). MỘT thước
  đo trim_silence chung cho S5/S7. Câu hết ngân sách → fade + cắt tại biên slot,
  KHÔNG BAO GIỜ đè sang câu kế. Đệm hơi thở BREATH_S 0.25, guard fade 0.10,
  deadzone TOL 1.02. edge cross-term: `ceil(round(((1+base/100)*k−1)*100, 6))`.
- **Ngân sách dịch kép** (S4): target theo miệng + trần theo slot + trần âm tiết
  (vi ~4.5 âm tiết/giây); 1 vòng dịch lại cho câu vượt; review guard.
- **TTS 1 giọng mặc định** (`TTS_SINGLE_VOICE=1`): mọi câu một giọng, nhưng
  **casting series luôn thắng** — character gán trên segment + bảng casting của
  series điền voice_ref ở S5. Build lại bản dịch KHÔNG được làm rớt `character`.
- **voicesig**: đổi cài đặt giọng nào cần đọc lại câu nào là do
  `voice_signature(seg, settings)` quyết — sửa logic giọng thì sửa Ở ĐÓ để
  UI dự đoán (/override-impact) và S5 không lệch nhau.
- **OCR_CROP_TOP=auto**: tự đo dải phụ đề từng video — quan trọng với video DỌC
  (sub ở ~65%, crop cứng 0.70 sẽ cắt mất).
- **settings_schema.py là nguồn sự thật config**: thêm/sửa setting = sửa schema
  (+ default khớp config.py). UI tab Cấu hình (app-config.js) tự ăn theo:
  validate, chấm ●, nút ↺, profile.
- **Nghe thử phải TRUNG THỰC với render**: tts-preview áp override job/draft
  settings, đúng engine đúng giọng sẽ render — đừng "demo tạm" bằng giọng khác.

## License TTS (ràng buộc kinh doanh — kênh BẬT KIẾM TIỀN)

- ❌ KHÔNG monetize: **viXTTS/XTTS (CPML), F5-TTS, VietTTS, edge-tts** (ToS),
  StyleTTS2-vi, Fish/Spark (weights NC). Dùng thử nghiệm nội bộ thì được.
- ✅ Free + monetize: tự thu giọng mình (sở hữu 100%); Piper `vi_VN-vais1000`
  (MIT, nhưng giọng phẳng); voice-conversion MIT (OpenVoice v2 + MeloTTS-VN,
  RVC) với điều kiện **giọng ĐÍCH cũng của mình/free** (giọng mình làm nguồn
  KHÔNG "rửa sạch" giọng đích có bản quyền).
- ✅ Trả phí có license: **ElevenLabs / VBee / FPT đã tích hợp trong app**
  (core/paid_tts.py, key nhập tab Cấu hình). Ứng viên CHƯA làm: MiniMax
  speech-02 (giọng VN energetic, ~$50/1M ký tự), BytePlus (cùng engine Doubao
  với CapCut, tiếng Việt chưa xác nhận).
- 🚫 **KHÔNG clone giọng người khác/giọng TTS thương mại** (CapCut/FPT/VBee...)
  — right of publicity + ToS. CapCut không có API chính thức; license CapCut
  Pro KHÔNG phủ việc rút giọng ra pipeline ngoài; các "CapCut TTS API" trên
  GitHub là reverse-engineer, cấm dùng cho sản phẩm này.
- ⚠ YouTube demonetize nội dung TTS "xài chung giọng" sản xuất hàng loạt
  (chính sách inauthentic content 7/2025) — thêm lý do làm giọng riêng.

## Trạng thái hiện tại (2026-07-11)

- Roadmap gốc #1–#18: **XONG toàn bộ**. Các đợt lớn sau đó cũng xong: audit
  giọng (A/B/C/D), panel ⚙️ per-job (U-1→U-4), tách monolith (#16 worker +
  routes_editor, #17 static), **đợt G làm lại tab Cấu hình trên settings
  schema** (commit e7b01ec).
- **Đang MỞ, chờ user chốt**: (a) tối ưu source V-1/V-2/V-3 — danh sách ở
  DEXUAT_TOIUU_SOURCE.md, THI CÔNG THEO HUONGDAN_TOIUU_CHITIET.md (playbook
  từng bước cho mọi model, có parity test + bản đồ rủi ro RM-1..17);
  (b) user bật TTS_BASE_SPEED (đang 1.0 — DEXUAT_TANGTOC_GIONGDOC.md) + T-6
  mở trần nếu 1.5 chưa đủ; (c) T-4 viXTTS/T-5 paid honor nhịp nền; (d) chế độ
  lai OCR+Whisper cho thoại không sub; (e) engine TTS "hoạt ngôn" monetize
  (MiniMax/BytePlus/RVC); (f) W-2 model-host thường trú (HOÃN); (g) tab
  phối/test giọng (ý tưởng).
- Chi tiết từng đợt + quyết định thiết kế: đọc CHANGELOG.md từ trên xuống.
