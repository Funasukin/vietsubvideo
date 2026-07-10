# Tổng hợp 3 phía — panel "⚙️ Tùy chọn video này" (chốt để user duyệt)

> Claude đối chiếu `AUDIT_GIONG_TUYCHON_CODEX.md` + `AUDIT_GIONG_TUYCHON_GEMINI.md`
> với code thật (2026-07-11). Trạng thái: KẾ HOẠCH CHỐT — chưa code, user duyệt
> theo đợt ở mục 4.

## 1. Phân xử các điểm 2 bên nói khác nhau / khác tôi

1. **U1 (đếm chi phí):** Gemini nói "sig viXTTS/paid không chứa `:f`" — **SAI
   một nửa**: từ đợt B, `vix:ref` và `vix:def` ĐỀU có `:f{budget}`
   (`s5_tts.py:_voice_sig`); chỉ PAID là không. Codex nói đúng. Hệ quả giữ
   nguyên tinh thần cả hai: bộ đếm dry-run phải tính THEO SIG THẬT — edge +
   viXTTS re-TTS, paid = 0 call API (chỉ trộn lại).
2. **U2 (gộp knob giọng):** nhận phản biện của Codex, RÚT bản 3-option cứng
   của tôi (trộn "chế độ" với "danh tính giọng", vỡ với viXTTS/paid/đa ngôn
   ngữ, ghim override làm mất kế thừa). Chốt bản Codex: dropdown **"Chế độ
   giọng"** (Theo cấu hình chung / 1 giọng / 2 giọng tự gán) + "Giọng
   chính/phụ" chỉ hiện khi engine hiệu lực là edge (đa ngôn ngữ lấy cặp
   `langs.py`; viXTTS/paid hiện tên cặp global dạng chỉ-đọc). Bản dropdown
   động của Gemini khả thi về render nhưng vẫn ghim giá trị cụ thể vào job.
3. **U4 (PROSODY):** Codex bắt đúng tôi 1 lỗi: mô tả "đo trên audio lẫn nhạc"
   đã LỖI THỜI — `prosody._audio_path` ưu tiên `vocals.wav` (tồn tại từ V14
   khi KEEP_BGM=1 đã chạy). Sửa mô tả thành "ưu tiên vocals đã tách; chưa
   tách thì đo trên audio gốc, có thể nhiễu nhạc". KHÔNG ẩn khi TARGET_LANG≠vi
   (đích khác vẫn đọc edge → prosody có tác dụng).
4. **U11 (OCR_FPS + WHISPER_MODEL):** 2 phiếu ngược nhau — Gemini bỏ, Codex
   giữ. Tôi theo **Codex**: lý do per-video là thật (sub nháy nhanh cần 2fps
   dù global 1fps; audio khó cần model to; auto-gate chỉ chọn OCR-hay-Whisper
   chứ không chọn model). Chốt: GIỮ trong Nâng cao, hiện theo
   TRANSCRIPT_SOURCE, nhãn thân thiện ("Whisper: Nhanh/Cân bằng/Chính xác",
   "OCR: Nhanh/Kỹ").
5. **U12 (dry-run):** thiết kế Gemini (áp override lên "dict config giả lập"
   trong tiến trình server) **không an toàn** — `_voice_sig` đọc module
   `config` toàn cục, server nhiều luồng → race (Codex chỉ đúng chỗ worker
   phải né bằng subprocess + env). Chốt kiến trúc Codex: **tách resolver
   thuần dữ liệu** (`TtsSettings` + `voice_signature(seg, settings)`), S5 và
   endpoint cùng gọi — tiện thể trả nợ kiến trúc "sig phụ thuộc module state"
   (finding 11 audit gốc). Schema response lấy bản Codex (thêm
   `paid_tts_chars`, `manual_edits_at_risk`, `estimated_seconds` là KHOẢNG).
   Với depth translate/transcript: báo "toàn bộ output sau stage bị vô hiệu"
   chứ không giả vờ đếm được.
6. **U13 (Âm nền):** cả hai đồng ý không thêm knob trùng; Codex phát hiện
   thêm **bug thật**: thanh Âm nền chỉ hiện khi KEEP_BGM=flat
   (`index.html:2594`) trong khi S6 áp `bed_gain_db` ở CẢ 3 mode
   (`s6_bgm.py:24,51-75`) → sửa: luôn hiện, mô tả đổi theo mode.
7. **U15 (bố cục):** nhận điểm của Codex — CONTENT_STYLE, TRANSCRIPT_SOURCE là
   knob PHÁ DỮ LIỆU (dịch lại/làm lại transcript, mất chỉnh tay) → không thuộc
   "Thường dùng" của luồng sửa nhanh; Gemini xếp chúng ở thường dùng là kém an
   toàn. Panel nhớ trạng thái đóng/mở.

## 2. Các điểm đồng thuận 3/3 (chốt luôn, không cần bàn thêm)

- **U3** EMOTION: disable-kèm-lý-do khi transcript không có nhãn hợp lệ
  (≠ binhthuong — Codex), kèm nút hành động riêng "Dịch lại để tạo nhãn" có
  cảnh báo mất chỉnh tay + phí. Không chuyển cả knob sang depth translate.
- **U5** Preset khớp thoại: segmented control ĐỘC LẬP đầu phần Thường dùng
  (không nằm dưới nhãn nhóm Trộn vì nó đụng 2 depth), dùng CHUNG mapping với
  preset tab Cấu hình, hiện "có thể đọc lại N câu" từ resolver U12.
- **U6** Nút "↺ Về cấu hình chung": payload `{}` server đã hỗ trợ; phạm vi CHỈ
  env override (không đụng Âm nền/render); dialog nói rõ vẫn chạy lại stage.
- **U7** Engine thiếu key: `/api/config` đã có trạng thái key → editor nhận
  capability object (không lộ secret); disable option + nếu job ĐANG override
  engine mất key thì vẫn hiện giá trị kèm cảnh báo (Codex).
- **U8** VOICE_FX chuyển sang panel render + option 3 trạng thái "Theo cấu
  hình chung" (chỉ lưu key `fx` khi user thật sự override) — fix hẳn bug #12c.
- **U9** Bỏ PROSODY_TRANSFER khỏi per-job. **U10** bỏ 2 danh sách model khỏi
  per-job (tuỳ chọn thêm sau: 1 control "Chất lượng dịch: Tiết kiệm/Cân
  bằng/Tốt nhất" trong Nâng cao — chờ user muốn thì làm).
- **U14** Nghe thử 10s in-timeline: làm SAU khi có primitive mix dùng chung
  với S6/S7 (không viết bản "gần giống" ở endpoint — mất lòng tin như preview
  cũ); v1 chỉ nhận thay đổi mix rẻ (gain/mode/stretch), không nhận đổi
  engine/MAX_SPEEDUP.
- **U16 (MỚI — cả 2 agent đề xuất)** DENOISE per-job: nhận, NHƯNG theo phân
  tích Codex nó đụng S2 → cần **depth mới "extract"** (xoá audio_16k.wav,
  chạy lại từ S3), không được nhét vào nhóm transcript. Đặt ở Nâng cao +
  dry-run cảnh báo rõ.
- Cảnh báo mất-chỉnh-tay của Gemini cho CONTENT_STYLE/STYLE_EXTRA: đã cover
  bằng `manual_edits_at_risk` trong dry-run U12 + confirm đỏ.

## 3. Bố cục chốt

**Thường dùng (6):** Nhạc/SFX gốc · Âm nền (dB, luôn hiện — U13) · Preset khớp
thoại · Engine giọng (kèm capability U7) · Chế độ giọng (U2 bản Codex) · Giọng
tất cả câu / Đổi toàn bộ.
**Nâng cao (gập, nhớ trạng thái):** MAX_SPEEDUP + STRETCH_SHORT (hiện khi
preset = Tùy chỉnh) · Giọng chính/phụ (chỉ edge) · PROSODY (chỉ edge, mô tả
mới) · EMOTION (disable có lý do) · Nhà cung cấp dịch · Ngôn ngữ lồng tiếng ·
Kiểu nội dung · Phong cách dịch riêng · Nguồn transcript · Whisper
(Nhanh/Cân bằng/Chính xác) · OCR (Nhanh/Kỹ) · Vùng quét phụ đề · DENOISE (U16).
**Panel render (🎨):** nhận thêm VOICE_FX (U8) cạnh subtitle/cover/frame.
**Bỏ hẳn khỏi per-job:** PROSODY_TRANSFER, Model Claude, Model Gemini.

## 4. Thứ tự thi công đề xuất (chờ user chốt theo đợt)

- **Đợt U-1 — Trung thực (rẻ, sửa knob nói dối):** U3 (disable EMOTION +
  action), U4 (ẩn PROSODY theo engine + mô tả mới), U7 (capability engine),
  U8 (VOICE_FX sang render + 3 trạng thái), U13 (Âm nền hiện mọi mode).
- **Đợt U-2 — Hạ tầng tác động:** tách resolver `voice_signature(seg,
  settings)` + endpoint `/override-impact` (U12) → nối vào cảnh báo U1,
  preset U5, nút reset U6.
- **Đợt U-3 — Bố cục:** U15 (Thường dùng/Nâng cao/nhớ trạng thái) + U2 bản
  Codex + gỡ U9/U10, nhãn thân thiện U11.
- **Đợt U-4 — Tính năng mới:** U14 (nghe thử 10s, sau khi có primitive mix
  chung), U16 (DENOISE + depth extract).

## 5. Ba câu hỏi còn mở cho user — ĐÃ CHỐT (2026-07-11)

1. U10 mở rộng: **CÓ** — thêm "Chất lượng dịch: Tiết kiệm/Cân bằng/Tốt nhất"
   trong Nâng cao (làm ở đợt U-3).
2. U11: **theo Codex** — giữ Whisper/OCR trong Nâng cao, hiện theo ngữ cảnh.
3. Thứ tự: **U-1 + U-2 trước**, xem thử rồi mới U-3/U-4.

## 6. Trạng thái thi công

- **Đợt U-1 + U-2: ĐÃ LÀM (2026-07-11)** — U3 (làm theo biến thể "leo thang":
  bật EMOTION khi chưa có nhãn → server tự nâng depth lên DỊCH, cảnh báo tại chỗ
  + confirm có số — thay vì disable cứng, vẫn đúng tinh thần "không no-op, hành
  động rõ giá"), U4, U7, U8 (+fx 3 trạng thái, fix bug ghim), U13, resolver
  `core/voicesig.py` (parity 65/65 với .sig thật), endpoint
  `/api/jobs/{id}/override-impact`, confirm có số liệu, nút ↺ Về cấu hình chung.
- **Đợt U-3 + U-4: ĐÃ LÀM (2026-07-11, user gọi "làm U-3 và U-4")** — panel chia
  🧰 Thường dùng (Âm nền · Nhạc/SFX · Preset · Engine · Chế độ giọng · Giọng tất
  cả câu · Nghe thử 10s) + 🛠 Nâng cao gập (nhớ localStorage); U2 bản Codex
  (Chế độ giọng + Giọng chính/phụ chỉ hiện edge); ⭐ Chất lượng dịch (1 núm →
  2 model key, suy ngược từ override cũ); nhãn Whisper/OCR thân thiện; RÚT
  PROSODY_TRANSFER + 2 danh sách model khỏi per-job; U14 `/mix-preview` dựng
  bằng đúng primitive S6/S7 (refactor `apply_duck` + `render_voice`, parity
  md5/field bằng nhau 100%); U16 DENOISE depth "extract" mới (xoá audio_16k,
  chạy lại từ S3). Toàn bộ kế hoạch U1–U16 hoàn tất.
