# Tổng hợp 3 phía audit giọng — Claude đối chiếu Codex + Gemini (2026-07-10)

> Claude soạn sau khi đọc `AUDIT_GIONG_CODEX.md` và `AUDIT_GIONG_GEMINI.md`,
> có MỞ CODE kiểm chứng lại từng claim mới của 2 bạn trước khi ghi nhận/phản
> hồi. Ba agent ngang hàng — dưới đây ghi rõ ai đúng ai sai ở đâu.
> Trạng thái: PHÂN TÍCH — chưa code, chờ user chốt danh sách cuối.

## 1. Ghi nhận — Codex đúng, tôi sửa lại audit gốc

1. **Preview 🔊 không phải "luôn edge"** — tôi nói quá tay. Đã kiểm
   `webui/server.py:1464-1487`: câu có `voice_ref` nghe thử bằng viXTTS đúng
   giọng render. Phát biểu đúng phải là: **câu KHÔNG cast** (trên máy này =
   đa số câu, vì TTS_SINGLE_VOICE=1 + chưa casting) mới bị nghe edge / render
   viXTTS. Triệu chứng user gặp vẫn còn nguyên, nhưng phạm vi hẹp hơn tôi viết.
2. **PROSODY/EMOTION mặc định BẬT trong code** (`config.py:139,142` default
   "1") — audit gốc chỉ nói theo .env máy desktop (=0). Hệ quả quan trọng
   Codex chưa nói hết: **máy laptop nếu .env thiếu 2 key này thì nhánh edge ở
   đó đang chạy đủ 4 tầng rate chồng nhau**. Cần đồng bộ .env 2 máy hoặc đổi
   default khi làm V12.
3. **SUB_SPLIT vô tội với audio** (`s8_render.py:80-83`, comment "Giọng đọc
   không đổi") — đúng, loại khỏi danh sách nghi phạm giọng. (Gemini 2.4 nêu nó
   cắt đôi tên riêng trên SUB HIỂN THỊ — có lý nhưng là việc phụ đề, tách
   khỏi hồ sơ giọng, để backlog UI riêng.)
4. **B1 — S7 atempo chạy trên mp3 thô trong khi quyết định đo bản đã trim**
   (`s7_mix.py:69` vs `:75`): quan sát ĐÚNG. Phản hồi thêm của tôi: tác động
   nghe được ≈ 0 vì atempo tuyến tính — đuôi lặng cũng bị nén rồi `_load_voice`
   trim lại sau (`:76`), độ dài phần tiếng sau cùng vẫn ≈ slot; đặt tại `start`
   cũng không lệch vì lặng đầu bị trim. Là nợ vệ sinh code, V1 xử lý sạch.
5. **B3 — paid TTS cũng không có fit** ở S5: đúng, V2 nâng thành "engine
   duration adapter" chung (viXTTS + paid nào hỗ trợ speed).
6. **Thứ tự làm: đo trước sửa sau** — V13 (mở rộng mix_report) làm ĐẦU TIÊN
   để có baseline trước/sau. Tôi nhận: thứ tự này tốt hơn thứ tự tôi đề xuất.
7. **V5 nên gửi S4 cả ba số**: `target_s = end−start` (miệng), `limit_s =
   slot − đệm thở`, `max_syllables` tính sẵn — tinh hơn bản gốc của tôi (chỉ
   đổi max_s sang slot). Nhận.
8. **V11 tách 2 loại nghe thử** (nghe raw chọn giọng / nghe trong timeline có
   trim+fit+atempo+bed): thiết kế đúng, nhận.
9. **P5 dè dặt về nondeterminism viXTTS**: ghi nhận sự thận trọng, nhưng tôi
   giữ kết luận — XTTS inference dùng sampling GPT với `temperature=0.7`,
   không chỗ nào set seed (grep toàn core/ = 0) → nondeterministic theo cấu
   trúc; số đo 3 câu ngắn nhất cùng 2.272s chỉ nói lên SÀN, không phủ nhận
   phương sai giữa các lần synth câu thường.

## 2. Ghi nhận — Gemini đúng, bổ sung giá trị

1. **PHÁT HIỆN MỚI ĐẮT NHẤT: `vocals.wav` bị xoá ngay sau demucs**
   (`core/separate.py:44-48`: chỉ move `no_vocals.wav`, rồi `rmtree` cả thư
   mục). Tôi đã kiểm — ĐÚNG. Hệ quả: prosody muốn đo trên vocal sạch (sửa gốc
   phát hiện #8 của tôi) thì dù đảo thứ tự stage cũng KHÔNG có dữ liệu. →
   thêm **V14**: giữ lại vocals.wav (move cả 2 stems; `/api/cleanup` đã có
   sẵn dòng dọn nó nên không lo phình đĩa).
2. **Toán số hạng chéo (1.1)**: công thức
   `rate_đúng = (D/S − 1)·100 + (D/S)·B` — chính xác, dùng thẳng vào governor.
3. **Preview thiếu `job_id`** (2.1): đúng và cụ thể hơn phát hiện gốc của
   tôi — bỏ qua override per-job, mất casting nếu frontend không gửi
   voice_ref, câu không cast rơi xuống edge khi TTS_ENGINE=vixtts. Gộp vào
   V11 (bắt buộc truyền job_id).
4. **Preview không qua loudnorm** (2.5): đúng, gộp vào V11 chế độ "nghe trong
   timeline".
5. **V4 nên FADE mềm thay vì cắt gắt** (tránh tiếng "bụp", mất từ cuối):
   nhận — fade-out 80–120ms cuối slot.
6. **V10 lượng hoá**: gộp câu <3 từ khi cách câu bên <0.8s — nhận làm rule
   khởi điểm (tinh chỉnh sau bằng số liệu V13).

## 3. Phản hồi lại — chỗ tôi KHÔNG đồng ý

1. **Gemini 2.3 (demucs "tự fallback CPU, treo hàng giờ") — SAI cơ chế.**
   Pipeline truyền `-d config.VIXTTS_DEVICE` (mặc định "cuda",
   `separate.py:41`); máy không GPU thì demucs LỖI → s6 bắt exception và quay
   về duck cũ (docstring `separate.py:5`, hành vi caller s6_bgm). Không có
   đường "âm thầm chạy CPU". Chỉ đúng nếu user TỰ đặt `VIXTTS_DEVICE=cpu` —
   khi đó chậm là lựa chọn chủ động. Không nhận vào danh sách việc.
2. **Thiết kế Arbitrator của Gemini (mục 4.2) — 2 lỗi thiết kế:**
   - `speed = max(0.90, min(max_limit, speed))` với `speed = raw/target`:
     ép ĐỌC CHẬM 0.9× cho MỌI câu ngắn hơn miệng và ép NÉN mọi câu hơi dài
     hơn miệng kể cả khi slot còn thênh thang (vd raw 5.03s / miệng 4.25s /
     slot 17.5s → bị nén 1.18× vô cớ). Đây chính là "chỉnh khi không cần
     chỉnh" — thứ gây thiếu tự nhiên mà ta đang chữa, và lặp lại đúng cái bản
     2 chiều từng bị user revert (30e285c). PHẢI có DEADZONE: chỉ can thiệp
     khi raw > limit (bắt buộc) hoặc raw > target×~1.25 (nhẹ), kéo chậm chỉ
     khi hụt >30% VÀ user bật V9.
   - "S7 loại bỏ hoàn toàn atempo": mỏng manh — engine synth lại vẫn lệch
     (viXTTS nondeterministic, edge re-read sai số) → cần giữ post_atempo Ở
     S7 làm van xả CUỐI, bị chặn bởi ngân sách còn lại
     (`max_total_speed / engine_speed_đã_áp`) như thiết kế Codex. Một trọng
     tài không có nghĩa là một ĐIỂM áp lực — nghĩa là một NGÂN SÁCH tổng.
   - (nhỏ) `max_duration = end−start+2.0` cho câu cuối: số 2.0 tuỳ tiện, nên
     là `min(hết video, end + gap thực)`.
3. **Gemini "XÁC NHẬN toàn bộ 12 kết luận"** — hào phóng quá: kết luận 7, 8,
   11 trong file gốc vốn là PARTIAL với phần lõi đã bị vòng verify của tôi
   THU HẸP (vd 11: editor không đổi được start nên "hàng xóm stale" không
   kích hoạt được). Xác nhận nguyên khối làm mất các ranh giới đó. Khi dùng
   bản Gemini, đọc kèm verdict gốc.
4. **Điểm cả 2 bạn đồng ý mà tôi giữ nguyên mức "vừa"**: sig thiếu
   slot/rate-thực-áp (11) — là nợ kiến trúc cho tương lai (khi cho sửa
   timing/split-merge), KHÔNG phải nguyên nhân triệu chứng hiện tại. Làm
   trong V3 (governor ghi plan vào sig/metadata) chứ không tách việc riêng.

## 4. KẾ HOẠCH CHỐT (hợp nhất 3 phía — chờ user confirm theo đợt)

Đồng thuận 3/3 về lõi: **một trọng tài thời lượng + một thước đo + fade thay
vì đè**, làm theo thứ tự **đo trước — sửa gốc — sửa upstream — tự nhiên/UX**.

**ĐỢT A — Đo (làm đầu, rẻ, không rủi ro):**
- V13: mix_report ghi đủ per-câu `raw_ms / trimmed_ms / target_ms / limit_ms /
  engine_speed / post_atempo / final_ms / gap_or_overflow_ms / clipped` +
  editor tô đỏ câu nén >1.3× hoặc hụt >30%. Chạy lại 1 job cũ lấy baseline.

**ĐỢT B — Trọng tài thời lượng (lõi):**
- V1: trim lặng NGAY sau synth mọi engine, một hàm trim dùng chung S5/S7
  (xoá luôn nợ B1 của Codex).
- V3: module `core/duration.py` (governor): target = miệng, limit = slot −
  fade guard, NGÂN SÁCH TỔNG = MAX_SPEEDUP (trần TÍCH); có DEADZONE (không
  đụng câu đã ổn); công thức cross-term của Gemini; S7 giữ post_atempo làm
  van xả cuối trong phần ngân sách còn lại (thiết kế Codex).
- V2: viXTTS truyền `speed` (giới hạn 0.9–1.25, AB nghe thử), synth lại tối
  đa 1 lần; mở rộng adapter cho paid engine hỗ trợ speed.
- V4: vẫn vượt limit sau tất cả → fade-out 80–120ms tại biên slot (không đè
  câu kế, không cắt gắt).

**ĐỢT C — Upstream text:**
- V5: S4 nhận `target_s` + `limit_s` + `max_syllables` (bản Codex).
- V6: validator đếm âm tiết tiếng Việt sau dịch; câu >4.3–4.5 âm tiết/giây →
  dịch lại NGẮN riêng câu đó, đúng 1 vòng, gom batch.
- V7: review pass nhận ngân sách, cấm nới dài.

**ĐỢT D — Tự nhiên + bề mặt:**
- V8: nhắm miệng (trong governor, qua deadzone — không ép như bản Gemini).
- V9: kéo chậm sàn 0.92× CHỈ khi hụt >30%, mặc định TẮT (user từng revert
  tính năng này — cần chính user bật).
- V10: segtools gộp câu <3 từ khi gap <0.8s; tách câu quá dài theo CPS.
- V11: nghe thử 2 chế độ (raw / in-timeline), BẮT BUỘC job_id, qua loudnorm
  ở chế độ timeline.
- V12: gom preset (Khớp môi chặt / Tự nhiên / Tùy chỉnh) SAU khi có governor;
  đồng bộ default PROSODY/EMOTION giữa code và .env hai máy.
- V14 (mới — Gemini): demucs giữ lại vocals.wav làm nguyên liệu prosody sạch
  về sau.

Ngoài code (không cần confirm): cắt 3–4 clip mẫu sắc thái từ 10 phút giọng
user cho viXTTS.

## 5. Câu hỏi còn mở cho user

1. Chốt làm theo đợt: A → B → C → D, hay chỉ A+B trước rồi nghe thử đã?
2. V9 (kéo chậm câu hụt) từng bị bạn revert — lần này có muốn đưa vào (dạng
   TẮT mặc định, bật thử 1 video) không?
3. Ai code đợt nào? (3 agent cùng repo — nên chia theo file để không giẫm
   nhau, vd: governor+S5/S7 một người, S4+validator một người, UI/preview
   một người — hoặc một người làm tuần tự.)
