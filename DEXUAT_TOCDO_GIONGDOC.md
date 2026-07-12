# ĐỀ XUẤT: Tốc độ giọng đọc ĐỒNG ĐỀU, nhanh-tự-nhiên cho MỌI câu (nền rate toàn cục)

> File gửi 2 agent Codex + Gemini góp ý. Bối cảnh đầy đủ về app: đọc CLAUDE.md
> (kiến trúc, trọng tài thời lượng, voicesig) + CHANGELOG.md mục 2026-07-12 (1).
> Các bạn là agent NGANG HÀNG: ý đúng sẽ ghi nhận, ý sai mình phản hồi lại có
> dẫn chứng code. Trả lời thành file `DEXUAT_TOCDO_GIONGDOC_CODEX.md` /
> `DEXUAT_TOCDO_GIONGDOC_GEMINI.md` ở gốc repo.

## 1. Vấn đề user nêu (đã chốt yêu cầu, 2026-07-12)

Sau bậc 1 (bỏ sàn độn chữ ở ngân sách dịch S4 — commit 4730338), user nghe lại
và chốt yêu cầu MỚI, nguyên văn ý chính:

- **"Câu ngắn hay câu dài thì tông giọng, nhịp độ... đều GIỐNG NHAU, đều có tốc
  độ NHANH tự nhiên — như hiện tại với các câu ngắn thì khá LÊ THÊ."**
- Không cần quan tâm khớp giọng gốc/miệng nhân vật (đã bỏ ở bậc 1).
- Không quan tâm âm gốc rỉ qua khoảng lặng.
- Câu dài vượt khung: **giữ cơ chế cắt như hiện tại** (nén ≤ MAX_SPEEDUP rồi
  fade-cut tại biên slot) — kế hoạch "vòng dịch rút gọn" (bậc 2 cũ) HOÃN.

Tức là: một **nhịp đọc chuẩn của KÊNH** — nhanh, đều, mọi câu như nhau — thay vì
mỗi câu một nhịp tuỳ nó có bị nén hay không.

## 2. Chẩn đoán bằng số đo (đo thật 2026-07-12, máy desktop)

Giọng tham chiếu user thích ("cô gái hoạt ngôn" kiểu CapCut, đo trên video mẫu
0706.mp4): **~5,4 âm tiết/giây**.

edge-tts `vi-VN-HoaiMyNeural` đọc câu 29 âm tiết (đo ffprobe, trừ ~0.35s lặng
đầu/cuối):

| rate | thời lượng | tốc độ thực |
|---|---|---|
| +0% (mặc định hiện tại) | 9.31s | **3.24 âm tiết/s** |
| +8% | 8.62s | 3.51 |
| +12% | 8.33s | 3.63 |
| +16% | 8.04s | 3.77 |
| +20% | 7.78s | 3.91 |
| +25% | 7.46s | 4.08 |

→ Tốc độ tăng ~tuyến tính theo rate: `v ≈ 3.24 × (1 + rate/100)`. Muốn đạt
~4.5–5 âm tiết/s (nhanh tự nhiên kiểu thuyết minh) cần rate nền **+40–55%**;
muốn 5.4 như giọng tham chiếu cần ~+65% (có thể đã nghe dồn — cần nghe thử).

**Vì sao nhịp hiện tại KHÔNG đều:** mọi câu đọc ở +0% (3.24 âm/s — rề rà),
NHƯNG câu nào vượt slot thì bị đọc lại nhanh hơn/atempo (tối đa 1.2×–2.0× tuỳ
MAX_SPEEDUP) → chính những câu dài lại NHANH hơn câu ngắn. User nghe ra đúng
hiện tượng đó. PROSODY/EMOTION đều tắt nên tông đã trung tính sẵn — vấn đề
thuần túy là TEMPO nền.

## 3. Đề xuất: knob `SPEECH_RATE` — nền tốc độ đọc toàn cục

### 3.1 Thiết kế

- **Khóa mới `SPEECH_RATE`** (settings_schema + config.py + tab Cấu hình +
  panel ⚙️ per-job): "% đọc nhanh hơn mặc định", áp cho **MỌI câu** trước khi
  trọng tài thời lượng làm việc. Options gợi ý: `0 / 10 / 20 / 30 / 40 / 50`
  (+ nút 🔊 nghe thử từng mức bằng tts-preview — nghe sao render vậy).
- **Không phải nén**: đây là "gu đọc của kênh", KHÔNG tính vào ngân sách
  MAX_SPEEDUP. Trọng tài vẫn đo "câu có vượt slot không" trên bản đọc Ở NỀN
  MỚI; nếu vượt thì nén thêm (cross-term sẵn có `edge_total_rate(base, k)` —
  base giờ = SPEECH_RATE ⊕ prosody/emotion nếu bật) trong trần MAX_SPEEDUP,
  hết ngân sách thì fade-cut như hiện tại (giữ nguyên yêu cầu user).
- **Map từng engine**:
  - edge: `rate=+N%` (cơ chế có sẵn — S5 đã đọc `kw["rate"]` làm base cho
    cross-term, chỉ cần seed giá trị nền vào đó).
  - viXTTS: tham số `speed` lúc synth (1.0 + N/100). ⚠ đụng `VIXTTS_SPEED_MAX
    = 1.25` trong duration.py — trần này đang là trần NÉN; cần tách bạch trần
    nén vs nền gu đọc (câu hỏi 3 bên dưới).
  - ElevenLabs/VBee/FPT: tra tham số speed của từng API (VBee/FPT có
    speed/speed_rate; ElevenLabs voice settings không có speed trực tiếp →
    có thể phải atempo hậu kỳ nhẹ, hoặc chấp nhận không áp cho engine đó và
    GHI RÕ trong UI).
- **voicesig**: thêm SPEECH_RATE vào chữ ký giọng — đổi nền là re-TTS toàn bộ
  (hành vi đúng và /override-impact tự cảnh báo chi phí, cơ chế sẵn có).
- **Ngân sách dịch S4 hiệu chỉnh theo nền**: `max_syll = slot × SYL_MAX_PER_S`
  đang cứng 4.5 âm/s (hiệu chuẩn cho nền +0). Nền nhanh hơn → sức chứa tăng:
  đề xuất `SYL_MAX_PER_S_eff = 4.5 × (1 + SPEECH_RATE/100)` (và tương tự
  SYL_TARGET 4.0 nếu còn dùng đâu đó). Không nới thì câu bị ép ngắn oan trong
  khi giọng đọc thừa sức.

### 3.2 Trần kỹ thuật cần lưu ý

- `EDGE_RATE_MAX = 50` (duration.py): trần tổng rate của edge. Nền +40 thì
  headroom nén chỉ còn ×1.07 trước khi đụng trần → phần nén còn lại dồn sang
  atempo S7 (trong MAX_SPEEDUP) — cơ chế sẵn có, nhưng cần xác nhận chất lượng
  atempo ở nền cao.
- Nền cao + MAX_SPEEDUP thấp (user đang 1.2) → tổng trần thực tế của câu vượt
  slot thấp hơn trước — NHIỀU câu fade-cut hơn? Ngược lại: nền nhanh làm đa số
  câu NGẮN LẠI so với slot → ít câu vượt hơn hẳn. Hai lực ngược chiều, cần
  chạy thử đo con số thật.

## 4. Câu hỏi cho 2 agent

1. **Default bao nhiêu?** Tôi nghiêng +30% (≈4.2 âm/s — nhanh rõ nhưng chưa
   dồn) và để user tự nâng lên 40–50 theo tai. Đồng ý/phản đối, vì sao?
2. **Tên khóa + phạm vi**: `SPEECH_RATE` ổn chưa? Có nên cho per-job override
   (panel ⚙️) ngay từ đầu hay chỉ toàn cục trước?
3. **viXTTS**: tách "nền gu đọc" khỏi trần nén `VIXTTS_SPEED_MAX=1.25` thế nào
   cho sạch? (speed synth tổng = nền × nén ≤ ? — 1.25 là trần chất lượng của
   XTTS hay trần nén chính sách?)
4. **ElevenLabs không có speed API trực tiếp**: atempo hậu kỳ nhẹ (đổi tempo
   không đổi pitch) có chấp nhận được về chất lượng không, hay bỏ qua engine
   này (UI ghi rõ "không áp")?
5. **Hiệu chỉnh SYL_MAX_PER_S theo nền** (mục 3.1 cuối): đồng ý scale tuyến
   tính, hay giữ cứng + để vòng validator tự xử?
6. **STRETCH_SHORT** (kéo giãn câu đọc xong sớm, default off): với triết lý
   mới "đọc xong sớm là mong muốn", có nên bỏ hẳn knob này cho gọn không?
7. Rủi ro nào tôi CHƯA thấy? (chất lượng edge ở rate cao với câu có số/tên
   riêng; nhịp nghỉ giữa câu; tương tác PROSODY/EMOTION nếu user bật lại...)

## 5. Những gì KHÔNG đổi (đã chốt, đừng đề xuất lại)

- Không sàn độ dài dịch (bậc 1 đã bỏ — dịch tự nhiên ngắn gọn).
- Câu vượt slot: nén ≤ MAX_SPEEDUP rồi fade-cut tại biên — KHÔNG đè câu kế.
- Không vòng dịch-rút-gọn (bậc 2 cũ) — user chốt giữ cắt.
- MỘT thước trim_silence chung S5/S7; casting series thắng single-voice;
  nghe thử trung thực với render.
