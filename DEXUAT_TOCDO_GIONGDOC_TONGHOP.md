# TỔNG HỢP 3 phía: Nền tốc độ giọng đọc đồng đều (TTS_BASE_SPEED)

> Tổng hợp từ DEXUAT_TOCDO_GIONGDOC.md (Claude) + _CODEX.md + _GEMINI.md.
> Mọi claim kiểm chứng được đã VERIFY trong code ngày 2026-07-12 (bảng mục 2).
> User chốt theo mục 5.

## 1. Đồng thuận 3 bên (không cần bàn thêm)

- Chẩn đoán đúng: edge synth lần đầu +0% (≈3.24 âm tiết/s — rề rà); chỉ câu
  vượt slot mới bị đọc nhanh lên → câu dài nhanh, câu ngắn lê thê, nhịp không đều.
- Cần MỘT tốc độ nền cho MỌI câu; trọng tài chống tràn + fade-cut giữ nguyên,
  làm việc TRÊN nền mới.
- Hỗ trợ per-job (panel ⚙️, nhóm `_OV_TTS`, depth TTS — đổi là re-TTS, KHÔNG
  leo depth dịch) ngay từ đầu — hạ tầng voicesig//override-impact có sẵn.
- viXTTS: `VIXTTS_SPEED_MAX=1.25` là TRẦN CHẤT LƯỢNG model (verify comment
  duration.py:27 "cao hơn vỡ prosody") — nền vượt trần thì synth ở 1.25 rồi
  bù phần dư bằng atempo nhẹ (cả 2 agent cùng ra một công thức).
- STRETCH_SHORT trái triết lý mới → bỏ khỏi UI (chi tiết mục 3).
- Nghe thử (tts-preview) phải áp nền mới — nghe sao render vậy.

## 2. Bảng verify claim (ý đúng ghi nhận, ý sai phản hồi)

| Claim | Kết quả verify |
|---|---|
| Codex: ElevenLabs CÓ speed native (`voice_settings.speed`, 0.7–1.2) — đề xuất gốc "không có" đã lỗi thời | ✅ code chỉ gửi stability/similarity (paid_tts.py:84) → thêm được; miền 0.7–1.2 theo docs Codex dẫn — RE-VERIFY lúc code |
| Codex: FPT đã gửi header `"speed": "0"`, miền rời rạc −3..+3, phải đo duration để map | ✅ paid_tts.py:101 có sẵn header |
| Codex: VBee payload đã có `speed_rate: "1.0"` | ✅ paid_tts.py:132 |
| Codex: `SYL_TARGET_PER_S` là HẰNG SỐ CHẾT sau bậc 1 | ✅ chỉ còn định nghĩa duration.py:34, 0 nơi dùng |
| Codex: chữ ký giọng 2 NƠI phải parity (voicesig.py + chuỗi tường minh s5_tts.py:172-174) | ✅ CONFIRMED — bẫy thật, thêm base speed phải sửa CẢ HAI |
| Codex: preset `tight` đang bật STRETCH_SHORT=1 | ✅ app-core.js SYNC_PRESETS |
| Codex: edge synth đầu qua `emotion.edge_kwargs` không rate (s5:146-167) | ✅ |
| Gemini: VIXTTS_SPEED_MAX là trần chất lượng model | ✅ |
| Gemini: scale `SYL_TARGET_PER_S` "tương tự" | ❌ vô nghĩa — hằng số chết (Codex đúng) |
| Gemini: đặt default +30 luôn | ❌ bác — default đổi là voicesig lệch toàn bộ install cũ → re-TTS âm thầm (kể cả paid = tốn tiền thật). Đúng bài học PROSODY/EMOTION. Factory 1.0, user tự lưu 1.3 |
| Gemini: rủi ro "bắn chữ rồi khựng" (gap to hơn khi đọc nhanh) | ✅ ghi nhận — là hành vi user ĐÃ chấp nhận, không chữa |
| Gemini: số/viết tắt méo ở rate cao | ✅ trùng Codex — corpus test phải có nhóm câu số/tên |

## 3. Thiết kế CHỐT (sau phản biện)

- **Khóa `TTS_BASE_SPEED`** — HỆ SỐ nhân: options `1.0 / 1.1 / 1.2 / 1.3 / 1.4 / 1.5`,
  UI hiển thị "Mặc định / +10% … +50%". **Factory default 1.0**; option 1.3 gắn
  nhãn "nhanh tự nhiên (khuyên dùng)". (Tên SPEECH_RATE=30 bị loại: không rõ đơn
  vị, lệch với MAX_SPEEDUP/viXTTS speed vốn là hệ số.)
- **Mô hình toán B/N/S/E/A** (Codex, nhận nguyên):
  - `B` = TTS_BASE_SPEED (gu đọc); `N` = phần engine làm native
    (edge: rate; viXTTS: speed ≤1.25; EL: speed ≤1.2; VBee/FPT: tham số riêng);
    `S = B/N` = phần dư style bù bằng atempo; `E×A` = nén chống tràn như cũ.
  - Hai bất biến: `E×A ≤ MAX_SPEEDUP` (lời hứa cũ, KHÔNG đổi nghĩa) và
    `B×E×A ≤ ABS_AUDIBLE_MAX` (trần chất lượng tuyệt đối MỚI, hằng số kỹ thuật
    ~2.0, không thêm knob).
  - PROSODY/EMOTION nếu bật lại: modifier rate per-câu phá đồng đều → đợt này
    chỉ cần ghi chú UI; "uniform mode" (emotion chỉ pitch/volume) để sau.
- **Fit report tách trường** (không nhét nền vào `engine_speed` cũ):
  `style_requested / style_native / style_atempo / fit_engine / fit_atempo /
  audible_total`. Dashboard đọc "nhịp nền 1.30× · nén thêm 1.15× · tổng 1.50×".
- **Voicesig**: thêm base speed vào TtsSettings + MỌI nhánh sig, sửa Ở CẢ HAI
  nơi (voicesig.py + s5 inline sig) + parity test như đợt U-2.
- **KHÔNG scale `SYL_MAX_PER_S` đợt đầu** (đổi 1 biến/lần; 4.5×1.3=5.85 vượt cả
  giọng tham chiếu 5.4; nền nhanh tự làm ít câu tràn hơn). Xóa luôn hằng số chết
  SYL_TARGET_PER_S. Đo 20–30 job rồi mới cân nhắc nới theo duration đo thật.
- **STRETCH_SHORT**: bỏ khỏi UI (Cấu hình + per-job + profile), sửa preset
  `tight` (bỏ vế STRETCH_SHORT=1), .env/job cũ còn bật → cảnh báo + coi như 0;
  giữ code đọc key 1 phiên bản rồi xóa.

## 4. Kế hoạch triển khai (đợt T)

- **T-1 Nền**: settings_schema + config + voicesig 2-nơi + duration
  (ABS_AUDIBLE_MAX, xóa SYL_TARGET_PER_S, field report mới) + parity/math tests.
- **T-2 edge end-to-end**: seed nền vào kwargs trước synth đầu (cross-term sẵn
  có ăn theo); corpus test ~20 câu (ngắn/vừa/dài/số-tên) × 1.0/1.2/1.3/1.4/1.5
  × NamMinh+HoaiMy — đo âm tiết/s, variance, overflow, clipped; job test full
  pipeline; **bộ mẫu cho user NGHE MÙ chọn mức kênh**.
- **T-3 UI**: knob tab Cấu hình (+🔊 nghe từng mức) + panel ⚙️ per-job +
  /override-impact + preview allowlist; gỡ STRETCH_SHORT + sửa preset.
- **T-4 viXTTS**: native ≤1.25 + residual atempo, A/B chất lượng.
- **T-5 paid** (cần key + chi phí nhỏ, làm khi user duyệt): EL
  `voice_settings.speed` (verify miền), VBee test miền `speed_rate`, FPT đo
  duration map −3..+3.

## 5. User chốt theo số

1. **Tên/đơn vị/factory**: `TTS_BASE_SPEED` hệ số, factory 1.0, UI khuyên 1.3 — OK?
2. **Phạm vi đợt này**: T-1→T-3 (edge + UI + per-job) trước, T-4 viXTTS liền sau,
   T-5 paid để đợt riêng — OK?
3. **Mức kênh**: sau T-2 bạn nghe bộ mẫu 1.2/1.3/1.4 rồi chốt số lưu vào .env
   (không ai chọn thay tai bạn) — OK?
4. **Bỏ STRETCH_SHORT khỏi UI + sửa preset tight** — OK?
