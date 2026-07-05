# Nhật ký làm việc

Mỗi phiên làm việc (bất kể máy nào) ghi một mục vào ĐẦU file này — máy kia pull về
đọc là biết chuyện gì đã xảy ra, không phải lần commit hay lục transcript chat.
Bài học: danh sách đề xuất #1–#18 từng bị mất vì chỉ nằm trong hội thoại một máy.

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
