# ĐỀ XUẤT: Giọng vẫn đọc chậm — bật nhịp nền (không code) + mở trần tốc độ (T-6)

> Gửi Codex review (tiếp mạch DEXUAT_TOCDO_GIONGDOC*.md — đợt T đã ship commit
> 59c7647). Trả lời thành `DEXUAT_TANGTOC_GIONGDOC_CODEX.md`. Khoan code.

## 1. Chẩn đoán bằng số (đo 2026-07-13 trên máy user)

User báo "giọng vẫn chậm, nghe rất không tự nhiên". Kiểm tra thật:

- `.env` **KHÔNG có `TTS_BASE_SPEED`** → toàn app chạy nền **1.0** (factory).
- Job user vừa nghe (`20260713_223153_e4909a`, paused trước render):
  `fit_report` ghi `style_native = 1.0` cho mọi câu — audio thật đúng là 1.0.
- Nhắc số đo đợt T: edge nền 1.0 chỉ 3.8–4.0 âm tiết/giây (HoaiMy/NamMinh
  median corpus 16 câu); giọng "hoạt ngôn" tham chiếu ~5.4. Knob 🚀 đã ship,
  factory 1.0 là QUYẾT ĐỊNH CÓ CHỦ ĐÍCH (đổi default = voicesig lệch → re-TTS
  âm thầm mọi install cũ) — nhưng hệ quả là **user không bật thì không nhanh**,
  và thực tế user đã không bật.

→ Vấn đề chính KHÔNG cần code mới. Nhưng có 2 việc đáng bàn: (a) UX làm sao
để knob này không bị bỏ sót nữa, (b) mở trần nếu 1.5 vẫn chưa đủ với tai user.

## 2. Giải pháp bậc 0 — KHÔNG CODE (làm được ngay hôm nay)

1. Tab **⚙️ Cấu hình → Lồng tiếng & âm thanh → 🚀 Nhịp đọc nền** → chọn
   **+40% (1.4)** → Lưu. (Corpus: 1.3 → 4.9–5.2 âm/s; **1.4 → 5.3–5.6** — sát
   giọng tham chiếu 5.4 nhất; 1.5 → 5.6–6.0. User kêu "thật sự chậm" nên đề
   xuất vào thẳng 1.4, có nút 🔊 cạnh knob nghe ngay trước khi lưu.)
2. Bộ nghe mù có sẵn để chốt bằng tai: `voice_samples/nghe_mu/` (A/B/C =
   1.2/1.3/1.4 xáo trộn, đáp án trong `_dapan.txt`).
3. Với job ĐANG paused (`e4909a`): đổi knob toàn cục xong bấm Chạy tiếp là
   KHÔNG đủ (TTS đã đọc xong ở 1.0, resume chỉ render nốt). Đúng đường: mở
   **✏️ Chỉnh sửa → ⚙️ Tùy chọn video này → 🚀 = 1.4 → 💾 Lưu & render lại**
   → tự đọc lại toàn bộ câu edge + trộn + render (impact dialog sẽ báo N câu).

## 3. T-6 (đề xuất code — CHỜ user nghe 1.4/1.5 rồi mới quyết): mở trần tốc độ

Nếu 1.5 (5.6–6.0 âm/s) vẫn chưa đủ "hoạt ngôn", hiện bị chặn bởi 2 trần:
`TTS_BASE_SPEED` options tối đa 1.5 và `EDGE_RATE_MAX = 50` (%). Hai đường:

- **T-6a — nâng trần native**: `EDGE_RATE_MAX` 50 → 70 + thêm options 1.6/1.7.
  Cần đo trước bằng corpus sẵn có (`scripts/bench_speech_rate.py` thêm mức
  1.6/1.7): nghe mù rõ phụ âm/số/tên — trần 50% là "nghe máy móc" theo comment
  cũ nhưng CHƯA có số đo thật ở 60–70%.
- **T-6b — style-atempo residual**: nền > 1.5 thì phần dư chạy atempo hậu kỳ
  (mô hình B/N/S đợt T đã chốt sẵn cho viXTTS/paid — edge dùng chung khung:
  N = min(B, 1.5 native), S = B/N bằng atempo ở S5 sau synth). Ưu: giữ native
  trong vùng chất lượng đã kiểm; nhược: thêm 1 lần encode/câu.
- Ràng buộc giữ nguyên: `ABS_AUDIBLE_MAX = 2.0` (nền 1.7 → ngân sách nén chỉ
  còn ~1.18 — câu vượt slot sẽ bị fade-cut sớm hơn; phải nói rõ trade-off
  trong tooltip).

## 4. Yếu tố "không tự nhiên" thứ hai (ngoài tốc độ) — ghi nhận, chưa đề xuất

- PROSODY=0, EMOTION=0 (user đã tắt) → giọng ĐỀU ĐỀU có chủ đích. Bật lại
  EMOTION cho 1 job test là cách rẻ nhất thêm sinh khí — nhưng đổi nhịp
  per-câu sẽ phá "tempo đồng đều" user vừa yêu cầu (mâu thuẫn gu, cần user
  nghe thử tự quyết, không khuyến nghị mặc định).
- Trần "tự nhiên" của edge là có thật: giọng đọc-đều Microsoft. Muốn chất
  "hoạt ngôn" thật sự (nhấn nhá, cười cợt) là chuyện ENGINE, không phải tốc
  độ — track MiniMax/VBee-clone đã bàn (TONGHOP tốc độ + memory license),
  nằm ngoài phạm vi file này.

## 5. UX: vì sao user không thấy knob? (mời Codex góp ý)

Knob nằm ở vị trí tốt (mặt tiền nhóm Lồng tiếng, có "khuyên dùng", có 🔊)
nhưng user vẫn chạy job đầu ở 1.0 và thất vọng. Các phương án:
- (a) First-run hint: job đầu tiên xong mà TTS_BASE_SPEED chưa ghim → toast/
  banner "Giọng chậm? Thử 🚀 Nhịp đọc nền +30–40%" (một lần, dismiss được).
- (b) Đưa 🚀 vào panel ⚙️ per-job phần THƯỜNG DÙNG (hiện ở nhóm tts nhưng
  panel gập — kiểm lại COMMON set trong app-editor.js).
- (c) Wizard/profile mẫu "Kênh review phim" đặt sẵn 1.4 + các gu khác.
- (d) Không làm gì — tài liệu hoá đủ rồi, tránh phình UI.

## 6. Câu hỏi cho Codex

1. Mục 2: đồng ý "bậc 0 trước, T-6 chỉ khi user nghe 1.4/1.5 vẫn chê" chứ?
2. T-6a vs T-6b: chọn đường nào (hay đo corpus 1.6/1.7 rồi quyết)? Có kinh
   nghiệm gì về chất lượng edge rate 60–70% với tiếng Việt?
3. UX mục 5: phương án nào đáng làm nhất, phương án nào là over-engineering?
4. Có rủi ro nào khi user set 1.4 toàn cục với job cũ đang paused/đã xong
   (voicesig :b làm re-TTS khi nào — chỉ khi re-render, đúng như thiết kế)?
