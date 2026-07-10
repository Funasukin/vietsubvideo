# Bàn giao audit chuỗi xử lý GIỌNG — FlowApp (cho agent phân tích độc lập)

> Tài liệu này do Claude (Claude Code) soạn 2026-07-10 để bàn giao cho các agent
> khác (Codex, Gemini) **cùng vai trò kỹ sư trên repo này** phân tích, phản biện
> và bổ sung. Mọi trích dẫn `file:dòng` là trạng thái tại commit `0c43a2e` —
> hãy tự mở code kiểm chứng, đừng tin lời tài liệu.

## 0. Đề bài từ user (chủ dự án)

Nguyên văn: *"kiểm tra lại toàn bộ xử lý giọng voice xem có bị lồng ghép chồng
chéo quá nhiều config, setting, tinh chỉnh ko. tôi thấy âm thanh hiện tại lúc
ngắn, lúc dài, đọc không tự nhiên cả về tốc độ lẫn âm điệu. Đưa ra đề xuất giải
quyết."*

Ba triệu chứng cần giải thích: (a) độ dài tiếng đọc lệch slot lúc thiếu lúc
thừa; (b) tốc độ đọc không tự nhiên; (c) âm điệu (intonation) không tự nhiên.

**Luật làm việc của dự án (áp dụng cho cả bạn):** user hỏi thì CHỈ phân tích/trả
lời, user confirm mục cụ thể mới được code. KHÔNG commit `.env`, `data/`,
`output/`. Phân tích này cũng vậy: chỉ đọc, không sửa.

## 1. Tổng quan hệ thống

FlowApp = dashboard FastAPI chạy local Windows (uvicorn 127.0.0.1:8790, không
`--reload`) tự dịch + lồng tiếng + phụ đề video (gốc thường là donghua Trung
Quốc) sang tiếng Việt để đăng YouTube kiếm tiền.

- `webui/server.py` (~2050 dòng): toàn bộ API + worker. Worker spawn subprocess
  `cli.py --resume <job_id>` cho mỗi job; stage checkpoint qua
  `job.completed_stages` (`data/jobs/<id>/state.json`).
- `webui/static/index.html` (~3500 dòng): toàn bộ UI 1 file (tab Jobs, editor
  segment, Cấu hình, Tổng quan, Chỉnh giao diện...).
- Pipeline (`core/pipeline.py`, stages trong `core/stages/`):
  - **s1_download** → tải/copy video nguồn
  - **s2_extract** → `audio_16k.wav` (ASR) + `audio_full.wav` (nền mix)
  - **s3_transcript** → OCR hardsub (RapidOCR) hoặc Whisper → `transcript_zh.json`
    (mốc `start`/`end` từng câu — MỌI tầng sau tin vào mốc này);
    `core/segtools.py` gộp câu (gap ≤ 0.35s, trần 8s/80 chữ)
  - **s4_translate** → Claude/Gemini dịch → `transcript_vi.json` (kèm nhãn
    `voice`, `emotion`, `character` per-segment)
  - **s5_tts** → tổng hợp giọng từng câu → `tts/seg_NNNN.mp3` (+ cache `.sig`)
  - **s6_bgm** → nền bed: demucs tách nhạc (KEEP_BGM=1) hoặc audio gốc hạ
    −14dB (KEEP_BGM=0/flat) → `ducked.wav`
  - **s7_mix** → đặt từng câu TTS lên bed theo timeline → `dubbed_audio.wav`
    (+ `mix_report.json`)
  - **s8_render** → ffmpeg vẽ sub/khung/logo + `brand.build_audio` (loudnorm
    master) → `final.mp4`
  - **s9_metadata** → tiêu đề/mô tả/thumbnail
- Config 3 tầng: `.env` (global, `load_dotenv(override=True)` trong `config.py`)
  → `FLOWAPP_JOB_OVERRIDES` (JSON env per-job, panel ⚙️ trong UI, 19 tùy chọn)
  → per-segment trong `transcript_vi.json` (voice/voice_ref/mute qua editor)
  → casting series (`core/series.py`, thắng tất cả khi segment có `character`).

### Cấu hình THẬT trên máy user lúc audit (.env — file không commit)

```
TTS_ENGINE=vixtts            VIXTTS_VOICE_NAM=rieng-nam-review.wav
TTS_SINGLE_VOICE=1           PROSODY=0
EMOTION=0                    PROSODY_TRANSFER=0
VOICE_FX=off                 MAX_SPEEDUP=2.0     (mặc định code là 1.4)
KEEP_BGM=flat                MASTER=1    MUSIC=none
SUB_SPLIT=1                  DIARIZE=0   TARGET_LANG=vi
GENDER_DETECT (không đặt → mặc định BẬT, config.py:101)
```

Nghĩa là: mọi câu không casting đều clone viXTTS từ MỘT clip
`voices/rieng-nam-review.wav` (giọng chính user); toàn bộ tầng prosody/emotion/
PSOLA/voice_fx đang TẮT.

## 2. Chuỗi xử lý giọng — dòng chảy một segment

1. **S3/segtools chốt mốc** `start`/`end` (`core/segtools.py:74-95`).
2. **S4 dịch** (`core/stages/s4_translate.py`): gửi LLM
   `max_s = round(max(0.5, end−start), 1)` (dòng 152) — ràng buộc độ dài **chỉ
   là lời dặn trong prompt** ("≈3–4 âm tiết/giây"), không có kiểm tra đếm âm
   tiết nào trong code; review pass (dòng 251-277) được viết lại text mà không
   nhận `max_s`, không so độ dài. LLM cũng sinh nhãn `voice` (nam/nữ) và
   `emotion`. `TRANSLATE_STYLE_EXTRA` chèn SAU rule độ dài (dòng 370-374).
3. **S5 TTS** (`core/stages/s5_tts.py`):
   - Khi bật: `prosody.measure` đo audio gốc → `rate −12..+20%`, pitch ±25Hz,
     vol ±15% (`core/prosody.py:33-35,100-178`); `emotion` cộng thêm offset
     (±12% rate...), kẹp tổng ±25% (`core/emotion.py:22-29,63-88`).
     `TTS_SINGLE_VOICE=1` ép mọi pitch = 0 (`prosody.py:53-54`,
     `emotion.py:74-77`).
   - **Nhánh edge**: đọc với rate/pitch/volume; `_fit_slot` (dòng 107-141):
     slot = `max(0.3, start_câu_kế − start)` (dòng 291-294); đo bằng ffprobe
     trên **FULL mp3 gồm đuôi lặng 0.3–0.9s edge tự đệm** (dòng 115); vượt
     slot×1.02 → đọc lại ĐÚNG 1 LẦN, rate mới = base +
     `min(50−base, (MAX_SPEEDUP−1)×100, ceil((dur/slot−1)×100))` (dòng
     123-126) — công thức thiếu số hạng chéo nên thường vẫn hụt mục tiêu.
   - **Nhánh viXTTS** (đang dùng): `_tts_vixtts` (dòng 227-234) →
     `core/vixtts.py:144-145` gọi `model.inference(..., temperature=0.7,
     enable_text_splitting=True)` — **KHÔNG truyền tham số `speed`** (XTTS có
     hỗ trợ, xem `.venv/.../TTS/tts/models/xtts.py:462` `speed=1.0` →
     `length_scale`), **KHÔNG đo, KHÔNG fit**. Không seed → nondeterministic.
     Lỗi bất kỳ → fallback cả nhóm sang edge (dòng 329-334).
   - **Nhánh paid** (ElevenLabs/VBee/FPT): speed cứng (`core/paid_tts.py:101,132`).
   - Cache `.sig` per-segment = engine:giọng:r/p/v:emotion:`:f{budget}`:pt —
     KHÔNG chứa slot lẫn rate fit thực áp (dòng 62-63, 170-172).
4. **S7 mix** (`core/stages/s7_mix.py`): nạp mp3, **CẮT im lặng 2 đầu** (dòng
   22-38 — thước đo KHÁC với thước S5 dùng); slot = `next.start − start` (dòng
   55-67, cùng công thức S5 nhưng lệch thước vì trim); dài hơn slot → `atempo =
   min(MAX_SPEEDUP, len/slot)` (dòng 69-76) — **chồng NHÂN lên rate fit đã
   nướng ở S5**; vẫn dài → chấp nhận TRÀN đè sang câu kế, chỉ ghi
   `mix_report.json` (dòng 77-88); ngắn hơn slot → KHÔNG làm gì (không có chiều
   kéo chậm — bản 2 chiều commit `a613cbc` đã bị revert ở `30e285c` vì làm khi
   user chưa confirm).
5. **S6 duck window** = [start−120ms, end+120ms] theo `seg.end`
   (`core/stages/s6_bgm.py:67-68`) ≠ vùng S7 thực đặt giọng
   [start, start+len] (có thể vượt `seg.end`) → giọng Việt tràn đè lên thoại
   gốc CHƯA hạ ở mode flat/0.
6. **S8 render**: `voice_fx` (off) + loudnorm master — chỉ volume, không đổi
   duration.

Nút 🔊 nghe thử per-câu (`webui/server.py:1450-1562`) dựng đường xử lý RIÊNG:
với config hiện tại nó đọc bằng **edge** trong khi render bằng **viXTTS**, bỏ
qua prosody đo audio, fit, atempo, voice_fx và mọi override per-job.

## 3. Số liệu đo trên job thật (data/jobs/, đo lại được bằng script)

Cách đo: decode `tts/seg_*.mp3` + `_sped.wav`, cắt lặng 2 đầu y hệt
`s7_mix._load_voice`, slot đúng công thức S7. 4 job: `20260706_212330_a20f78`
(viXTTS, 23 câu), `20260705_212220_8691dd` (viXTTS, 22), `20260705_201942_292928`
(edge, 22), `20260704_124056_40de66` (edge, 27).

| Chỉ số | a20f78 (viXTTS) | 8691dd (viXTTS) | 292928 (edge) | 40de66 (edge) |
|---|---|---|---|---|
| TTS-raw / thoại gốc (end−start), median | **2.49×** | 2.51× | — | — |
| ... max | **14.62×** | 12.02× | — | — |
| Câu bị S7 atempo | 12/23 = 52% | 50% | **20/22 = 91%** | 48% |
| Hệ số atempo median / max | 1.41 / 2.00 (kẹp trần) | 1.60 / — | 1.39 / 2.28 | 1.29 / 1.47 |
| Câu hụt slot (<70%, gap>0.7s) | 6/23 = 26% | 32% | — | 19% |
| Tổng im lặng sau câu | **35.2s / video 102.9s** | 35.1s | — | 12.4s |
| Tràn SAU atempo (mix_report) | 10 câu, max 826ms | 12 câu, max 156ms | 20 câu, **max 2233ms** | 13 câu, max 338ms |

Ví dụ đắt giá:
- a20f78 #8: 「念宝」thoại gốc 0.25s → "Niệm Bảo" viXTTS ngân **3.56s** (14.2×),
  slot 1.0s → atempo kẹp 2.0× còn 1.83s, **vẫn tràn 826ms** đè câu kế.
- a20f78 #4: slot 17.5s, thoại gốc 4.25s, TTS 5.03s → **12.47s im lặng** liền sau.
- 292928 #1 (edge, chạy lúc MAX_SPEEDUP=1.4): câu gộp 34 chữ Hán, edge đã đọc
  +20% rate mà raw 7.99s / slot 3.5s → tràn **2233ms**.
- Job edge cũ: sig ghi rate −12..+20% đổi zigzag từng câu (prosody+emotion bật
  thời đó) rồi 91% câu vẫn bị atempo thêm — 2–3 tầng tốc độ trên cùng 1 câu.

Lưu ý nhiễu: một phần "im lặng" là gap TỰ NHIÊN của video gốc (nhân vật cũng
ngừng nói); so sánh đúng phải theo cả hai mốc: miệng (end−start) VÀ slot.

## 4. Kết luận audit (12 phát hiện sau vòng phản biện: 4 CONFIRMED, 8 PARTIAL, 0 REFUTED)

**CONFIRMED (chỉ được đúng dòng code):**
1. **MAX_SPEEDUP tiêu 2 lần độc lập** (S5 fit budget + S7 atempo trần; không nơi
   nào kẹp TÍCH → tới 1.5×2.0 = 3.0×) trong khi UI mô tả là "núm TỔNG"
   (`index.html:895`). Công thức fit thiếu số hạng chéo → S7 atempo lần 2 là
   MẶC ĐỊNH với edge (91% câu job 292928). Override per-job MAX_SPEEDUP xếp
   nhóm `_OV_MIX` → chạy lại từ mixing, phần fit nướng trong mp3 giữ tốc độ núm
   CŨ (knob nửa tác dụng). [`s5_tts.py:110-126`, `s7_mix.py:70`, `server.py:1267`]
2. **Độ dài bản dịch chỉ ràng bằng lời dặn prompt** — không đếm âm tiết/CPS
   programmatic, không vòng dịch-lại-cho-ngắn; review có thể nới dài không ai
   chặn; temperature Gemini 0.7 hardcode. [`s4_translate.py:32,47,63,150-154,251-277`]
3. **S5 và S7 đo bằng 2 thước khác nhau** (full mp3 gồm đuôi lặng vs đã cắt
   lặng) → "tràn giả": 7/27 câu job 40de66 bị cộng oan tới +26% rate dù tiếng
   thật vừa slot; đuôi lặng edge đo được 0.51–0.93s. [`s5_tts.py:115`, `s7_mix.py:22-38`]
4. **Tràn sau atempo không bị cắt** → giọng câu trước đè giọng câu kế (cộng
   int32 clip int16) + ở KEEP_BGM=flat/0 bed còn nguyên thoại gốc hạ −14dB →
   giọng Việt tràn đè lên thoại gốc chưa duck (cửa sổ duck theo seg.end, vùng
   đặt giọng theo slot). [`s7_mix.py:69-88`, `s6_bgm.py:47-49,64-68`]

**PARTIAL nặng (đúng cơ chế chính, sai/thu hẹp vài tiểu tiết):**
5. Nhánh viXTTS không có tầng kiểm soát độ dài nào ở S5 + không seed + 1 clip
   mẫu cho mọi câu → nguồn lệch số 1 với config hiện tại (median 2.5× thoại
   gốc; sàn ~2.27s cả với câu 1 từ). Fallback lỗi → đổi cả loạt sang edge (sig
   cố tình lệch để lần sau thử lại viXTTS) → chạy lại đổi engine/màu giọng.
6. Hệ khớp slot lệch ngân sách kép: S4 cấp chữ theo end−start (sàn 0.5s), S5/S7
   nén theo next.start−start (sàn 0.3s) — và cả hệ CHỈ nén, không kéo. (Điểm
   claim sai: trên 5 job không có cặp segment chồng lấn nên vế "max_s > slot"
   chưa xảy ra thực tế.)
7. TTS_SINGLE_VOICE=1 cắt chiều pitch của prosody/emotion (khi bật) và làm
   dropdown Nam/Nữ per-câu thành knob chết; hiện tại đóng góp qua đường khác:
   mọi câu 1 clip nam duy nhất → một màu ngữ điệu.
8. Khi PROSODY/EMOTION bật (nhánh edge): 4 nguồn rate độc lập không trọng tài
   (prosody đo audio ±12..20% + emotion ±12% + fit tới 50% + atempo ×2) — thủ
   phạm các job edge cũ, bẫy tái phát nếu bật lại. Prosody còn đo trên audio
   TRỘN NHẠC (vocals.wav không tồn tại lúc S5 chạy) → số đo nhiễm nhạc nền.
9. Bề mặt config "nói dối": preview 🔊 khác đường render (điểm 2 ở mục 2);
   EMOTION per-job là no-op nếu lúc dịch EMOTION=0 (nhãn chỉ sinh ở S4 mà
   override chỉ chạy lại từ S5); `render.fx` đã lưu làm knob VOICE_FX global
   chết vĩnh viễn cho job đó.
10. PROSODY_TRANSFER (PSOLA) khi bật thay TOÀN BỘ đường F0 của TTS bằng dáng 24
    điểm từ câu Trung → nguy cơ bẻ thanh điệu tiếng Việt + re-encode mp3 48k
    lần 2; hiện tắt, không đóng góp vào triệu chứng hiện tại.
11. Sig thiếu slot → claim "sửa editor làm hàng xóm stale" bị BÁC phần lõi
    (editor không đổi được start nên slot bất biến), nhưng sig thiếu rate-fit
    thực áp vẫn là nợ kiến trúc khi sau này cho sửa timing.
12. Bất ổn run-to-run: temperature 0.7 không seed (viXTTS), 4 writer tuần tự
    ghi đè `seg.voice` (LLM → review → GENDER_DETECT → user), mix_report không
    log hệ số đã áp → khó tái hiện lỗi.

## 5. Đề xuất V1–V13 (CHƯA code — user chọn theo số mới làm)

**GÓI 1 — "Một trọng tài thời lượng"** (khuyên làm trước, sửa gốc):
- **V1** Cắt đuôi lặng NGAY sau synth (mọi engine, trước khi đo/ghi sig) → S5
  và S7 nhìn cùng một thước, hết "tràn giả".
- **V2** viXTTS: truyền tham số `speed` của XTTS + một vòng fit như edge (đo
  sau synth, vượt slot → synth lại với speed tính được).
- **V3** Tốc độ quyết định MỘT nơi duy nhất; MAX_SPEEDUP = trần TÍCH thật
  (đúng lời hứa UI); bỏ nén 2 tầng chồng nhân.
- **V4** Tràn sau trần → cắt/fade ~100ms thay vì đè câu kế.

**GÓI 2 — Khớp từ tầng dịch:**
- **V5** S4 nhận ngân sách = slot thật (next.start − start, trừ đệm thở ~0.25s).
- **V6** Đếm âm tiết programmatic sau dịch; câu > ~4.3 âm tiết/giây-slot → dịch
  lại NGẮN riêng câu đó (1 vòng, gom batch) — vòng phản hồi đang thiếu.
- **V7** Review pass nhận max_s, không cho kết quả dài hơn ngân sách.

**GÓI 3 — Tự nhiên hoá:**
- **V8** Mục tiêu duration = MIỆNG (end−start), trần = slot (đọc xong gần
  seg.end thay vì trườn hết slot).
- **V9** Kéo chậm NHẸ có trần (atempo 0.92–1.0) chỉ khi hụt >30% slot.
- **V10** segtools: nhập câu 1-từ vào câu bên cạnh (né sàn ~2.3s viXTTS), tách
  câu gộp quá dài (34 chữ Hán/3.5s là vô vọng).

**GÓI 4 — Dọn bề mặt config:**
- **V11** Nghe thử 🔊 dùng ĐÚNG engine + đường xử lý render (kể cả override
  per-job).
- **V12** Gom PROSODY/EMOTION/PROSODY_TRANSFER/VOICE_FX/MAX_SPEEDUP thành 3
  preset (Khớp môi chặt / Tự nhiên / Tùy chỉnh); ẩn knob chết theo ngữ cảnh.
- **V13** mix_report ghi hệ số từng câu (fit rate, atempo, hụt/tràn) + editor
  tô đỏ câu nén >1.3× hoặc hụt >30%.

Ngoài code: cắt 3–4 clip mẫu từ 10 phút giọng user đã tách demucs (bình thường /
nhấn mạnh / trầm) — viXTTS bắt chước ngữ điệu clip mẫu, là cách chỉnh âm điệu
tự nhiên nhất.

## 6. Nhờ bạn (Codex / Gemini) phân tích thêm

1. **Phản biện 12 kết luận** ở mục 4: mở đúng file:dòng, tìm chỗ tôi đọc sai
   hoặc kết luận quá tay. Đặc biệt soi các phát hiện PARTIAL.
2. **Tìm cái tôi BỎ SÓT** trong chuỗi giọng (s3→s8): còn tầng nào đụng
   duration/rate/pitch chưa được kể? (gợi ý chỗ tôi chưa đào sâu: `SUB_SPLIT`,
   `core/langs.py` khi TARGET_LANG≠vi, `core/splitter.py`/`shorts.py` cắt
   video có làm lệch timing không, đường resume/checkpoint khi job chạy lại
   nửa chừng.)
3. **Đánh giá V1–V13**: cái nào sai hướng? thứ tự ưu tiên khác? rủi ro kỹ
   thuật (vd XTTS `speed`/length_scale chất lượng ra sao ở 0.8–1.3? có nên
   synth-lại thay vì atempo?)? Có giải pháp tốt hơn không (forced alignment,
   chọn-best-of-N lần synth viXTTS theo độ dài, VAD-trim, thay đổi cách gộp
   segment...)?
4. **Thiết kế "một trọng tài thời lượng"**: nên đặt ở S5 (fit lúc synth) hay S7
   (một atempo duy nhất) hay tách thành module riêng? Đề xuất kiến trúc cụ thể.
5. Ghi kết quả phân tích của bạn vào file mới cạnh file này
   (`AUDIT_GIONG_CODEX.md` / `AUDIT_GIONG_GEMINI.md`) — KHÔNG sửa code, không
   sửa file này.
