# Phản biện tốc độ giọng đọc đồng đều — Codex

> Kiểm tra trên commit `a183bb9`, ngày 2026-07-12. Đã đọc `CLAUDE.md`, đầu
> `CHANGELOG.md`, code S4/S5/S7, duration, voicesig, paid TTS và settings schema.
> Chỉ phân tích; không sửa code, `.env` hay job.

## 0. Kết luận

Chẩn đoán chính là đúng: với PROSODY/EMOTION/STRETCH tắt, edge synth lần đầu ở
`+0%`; chỉ câu vượt slot mới được synth lại hoặc atempo nhanh hơn. Vì thế câu
ngắn nghe chậm, câu dài lại nhanh, dù hệ thống đang làm đúng governor hiện tại.

Tôi đồng ý thêm một tốc độ nền cho mọi câu, nhưng không triển khai đúng nguyên
dạng đề xuất. Cần sửa năm điểm:

1. Dùng canonical key dạng hệ số, đề xuất `TTS_BASE_SPEED=1.30`, UI hiển thị
   `+30%`. `SPEECH_RATE=30` không tự mô tả đơn vị và khó dùng chung API engine.
2. Tách tốc độ phong cách khỏi nén fit trong cả toán, report và UI. Không được
   nhét tốc độ nền vào `engine_speed` hiện tại.
3. Giữ factory default `1.0`; profile/cấu hình của user chọn `1.30`. Default
   1.30 sẽ âm thầm làm lệch voicesig và có thể gọi lại paid TTS cho job cũ.
4. Chưa scale `SYL_MAX_PER_S` ở vòng đầu. Thay đổi một biến để nghe/đo trước,
   tránh đồng thời nới mật độ bản dịch và che mất nguyên nhân.
5. ElevenLabs hiện có speed native 0.7–1.2; giả định “không có speed API” đã
   lỗi thời. Dùng native trước, atempo chỉ cho phần dư.

`STRETCH_SHORT` mâu thuẫn trực tiếp triết lý mới; nên deprecate khỏi UI và sửa
hai preset đang bật nó.

## 1. Kiểm chứng chẩn đoán trên code

Edge lần đầu gọi:

```text
edge_tts.Communicate(text, voice, **emotion.edge_kwargs(seg))
```

ở `core/stages/s5_tts.py:146-167`. Khi PROSODY và EMOTION tắt,
`emotion.edge_kwargs()` không có `rate`, nên engine dùng `+0%`.

Chỉ khi bản đọc vượt limit, `_fit_slot()` lấy rate hiện tại làm `base`, tính
cross-term và synth lại (`s5_tts.py:96-139`). Nếu vẫn dài, S7 atempo trong phần
MAX_SPEEDUP còn lại rồi fade-cut (`core/stages/s7_mix.py:69-100`). Do đó hiện
tượng “câu dài nhanh hơn câu ngắn” là hệ quả tất yếu của thiết kế deadzone, không
phải bug đo duration.

Một hiệu chỉnh ngôn ngữ: knob tốc độ nền chỉ làm **tempo** đồng đều tương đối.
Nó không tự làm “tông giọng” giống nhau. Pitch, volume, nhịp nghỉ do dấu câu,
voice/model và clip reference vẫn có thể khác. Với yêu cầu hiện tại, PROSODY và
EMOTION đang tắt nên pitch/rate modifier per-câu không can thiệp.

## 2. Trả lời trực tiếp 7 câu hỏi

### 1. Default bao nhiêu?

**Factory default: 1.0 (+0%). Recommended channel setting để thử: 1.30 (+30%).**

Lý do không đặt factory default 1.30 ngay:

- một phép đo 29 âm tiết chưa đại diện câu rất ngắn, số, tên riêng và dấu câu;
- các engine/voice có tốc độ gốc khác nhau;
- job cũ thiếu key sẽ nhận default mới, voicesig lệch và re-TTS;
- với ElevenLabs/VBee/FPT, re-TTS toàn job là chi phí thật.

Tab Cấu hình có thể đánh dấu `1.30 — nhanh tự nhiên (khuyên dùng)`, và user chủ
động lưu 1.30 sau khi nghe preview. Nếu sản phẩm muốn factory default 1.30 cho
cài mới, phải có migration idempotent ghim `1.0` cho cài đặt cũ trước khi đổi
default, tương tự bài học PROSODY/EMOTION.

Tôi đồng ý +30 là mức A/B đầu tiên tốt hơn +40/+50: theo số đo hiện có nó lên
khoảng 4.2 âm tiết/s, đủ khác biệt nhưng còn headroom chất lượng. Chỉ nâng tiếp
sau corpus test.

### 2. Tên khóa và per-job

Đề xuất tên: **`TTS_BASE_SPEED`**, giá trị hệ số:

```text
1.0 / 1.1 / 1.2 / 1.3 / 1.4 / 1.5
```

UI hiển thị `Mặc định / +10% / ... / +50%`. Cách này cùng đơn vị với viXTTS,
ElevenLabs, VBee và MAX_SPEEDUP. Nếu nhất quyết lưu phần trăm, tên phải là
`TTS_BASE_RATE_PCT`, không dùng `SPEECH_RATE` chung chung.

Nên hỗ trợ per-job ngay vì hạ tầng đã có settings schema, `_OV_TTS`, voicesig và
`/override-impact`. Nội dung giáo dục, audiobook và clip hoạt ngôn có nhu cầu
khác nhau. Key thuộc depth **TTS**, không thuộc translate:

- đổi nó re-TTS toàn bộ câu bị ảnh hưởng;
- S4 chỉ dùng giá trị mới nếu sau này job thật sự dịch lại;
- không ép dịch lại job hiện có chỉ vì đổi tốc độ.

### 3. viXTTS và trần 1.25

`VIXTTS_SPEED_MAX=1.25` hiện được chú thích là ngưỡng cao hơn bắt đầu vỡ
prosody. Phải coi đây là **trần chất lượng tuyệt đối của native XTTS** cho tới
khi benchmark chứng minh khác, không phải chỉ là trần chính sách nén.

Không thể nói “1.4 là gu đọc nên không tính” rồi truyền `speed=1.4`; model vẫn
nghe cùng một giá trị vật lý và vẫn có thể vỡ.

Phân tách sạch:

- `desired_style = TTS_BASE_SPEED`;
- `native_style = min(desired_style, VIXTTS_NATIVE_SPEED_MAX)`;
- `style_post = desired_style / native_style`;
- XTTS synth ở `native_style`;
- phần `style_post` nhỏ còn lại dùng atempo, **không tính vào MAX_SPEEDUP**;
- fit thêm vì slot được tính riêng sau baseline.

Ví dụ desired 1.30, native cap 1.25: XTTS 1.25 + style atempo 1.04. Đây hợp lý
hơn XTTS 1.30 hoặc atempo toàn phần 1.30. Nhưng vẫn phải A/B vì clip reference
nhanh/chậm làm XTTS phản ứng khác nhau.

### 4. ElevenLabs và atempo

Đề xuất gốc đã lỗi thời: ElevenLabs có `voice_settings.speed`; tài liệu chính
thức ghi default 1.0 và miền 0.7–1.2. Code hiện chỉ gửi stability/similarity nên
có thể thêm speed vào cùng object. Nguồn:

- [ElevenLabs voice settings API](https://elevenlabs.io/docs/api-reference/voices/settings/get)
- [ElevenLabs speed best practices](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices)

Với desired 1.30: native 1.20 + style atempo khoảng 1.083. Tôi chấp nhận atempo
nhẹ cho phần dư sau khi nghe A/B. Không nên bỏ qua ElevenLabs vì như vậy cùng
một setting nhưng paid engine quan trọng nhất lại no-op.

FPT có header speed rời rạc `-3..+3`, trong đó +3 nhanh nhất, theo
[tài liệu FPT.AI TTS v5](https://docs.fpt.ai/docs/vi/speech/api/text-to-speech.html).
Không được giả định +1 = 10%; cần đo duration từng mức và map mức gần nhất, phần
dư mới atempo.

VBee payload hiện đã có `speed_rate=1.0`. Tài liệu API công khai cho thấy field
này tồn tại trong request/result, nhưng miền hợp lệ và tỷ lệ duration cần test
trên account thật trước khi chốt mapping. Không hardcode theo tài liệu sản phẩm
UI hoặc API AICall khác endpoint.

### 5. Có scale `SYL_MAX_PER_S` không?

**Không ở vòng đầu.** Lý do:

- `4.5` hiện là policy ceiling, không phải phép hiệu chuẩn chính xác cho edge
  +0%; chính số đo đề xuất cho thấy edge +0 chỉ khoảng 3.24 âm tiết/s;
- scale 4.5 × 1.3 thành 5.85, cao hơn cả target tham chiếu 5.4;
- vừa tăng speed vừa nới max_syll làm thay đổi hai biến, khó biết chất lượng đến
  từ đâu;
- user vừa chốt bản dịch ngắn gọn và hoãn vòng rút gọn; chưa có nhu cầu nới để
  LLM được phép viết dày hơn.

Giữ 4.5 không ép câu dài ra; nó chỉ giữ ceiling cũ. Baseline nhanh hơn sẽ tự làm
ít câu overflow hơn.

Sau khi đo 20–30 job, nếu validator đang rút oan nhiều câu vốn đọc tự nhiên ở
1.30, mới hiệu chỉnh theo **tỷ lệ duration đo thật** của engine/voice, có cap,
không mặc định nhân tuyến tính. `SYL_TARGET_PER_S` hiện không còn được S4 dùng
sau bậc 1, nên không cần “scale tương tự”.

### 6. Có bỏ STRETCH_SHORT không?

Có, ít nhất khỏi UI/preset. Nó cố kéo câu ngắn chậm lại về phía thời lượng miệng
(`s7_mix.py:81-90`), trái hẳn yêu cầu “đọc xong sớm là mong muốn”.

Lộ trình tương thích:

1. bỏ khỏi tab Cấu hình, panel per-job và profile mới;
2. sửa preset `tight` vì hiện preset này đặt STRETCH_SHORT=1;
3. nếu `.env`/job cũ đang có 1, hiển thị migration warning và reset về 0;
4. giữ parser/code đọc key một phiên bản để job cũ không crash, rồi xóa sau.

Không chỉ đổi default; nếu setting cũ vẫn là 1 thì triết lý mới vẫn bị phá.

### 7. Rủi ro còn thiếu

Các rủi ro đáng thêm:

- **Tổng tốc độ tuyệt đối quá cao:** baseline 1.5 × fit budget 2.0 có thể thành
  3.0× so với engine normal. Dù baseline không “tiêu” MAX_SPEEDUP, vẫn cần một
  hard quality cap cho `audible_total`.
- **PROSODY/EMOTION bật lại:** edge có modifier rate từ -12% đến +20/+25%; lúc
  đó các câu lại không đồng đều. viXTTS chọn clip cảm xúc nhanh/chậm cũng phá
  tính đồng đều. UI phải nói đây là base speed, hoặc chế độ uniform phải bỏ rate
  modifier nhưng vẫn có thể giữ pitch/volume.
- **Số và tên riêng:** `duration.syllables()` đếm `2026` là một token nhưng TTS
  có thể đọc thành nhiều âm tiết. Dấu chấm, viết tắt và tên Latin cũng tạo pause
  không phản ánh trong count.
- **Câu rất ngắn:** 1–3 từ ở +50% dễ cụt phụ âm và nghe như notification. Không
  nên tự giảm speed per-câu vì trái yêu cầu; thay vào đó corpus test phải có nhóm
  này và giữ pad/fade đủ an toàn.
- **Khác engine/voice/ngôn ngữ:** cùng multiplier không cho cùng số âm tiết/s.
  Setting chỉ đảm bảo tốc độ tương đối so với voice gốc, không đảm bảo 5.4 tuyệt
  đối trên mọi engine.
- **Fallback:** viXTTS/paid lỗi rồi rơi về edge phải áp cùng base speed; nếu
  quên, chỉ các câu fallback lại chậm.
- **Preview branch voice_ref:** route hiện xử lý voice_ref trước khi resolve
  draft settings. Khi thêm speed phải bảo đảm cả nhánh clone/casting preview
  nhận speed, không chỉ nhánh engine phía dưới.
- **Paid cost:** preview có tính phí và đổi speed làm voicesig lệch toàn bộ paid
  output. `/override-impact` phải báo đúng ký tự trước khi áp.
- **Report cũ:** `total_speed` hiện chỉ có nghĩa fit compression ≤ MAX_SPEEDUP.
  Nếu trộn baseline vào field này, dashboard sẽ báo vượt trần giả hoặc mất nghĩa.
- **Perceived pacing:** tempo chữ đều nhưng khoảng nghỉ do dấu câu và khoảng
  trống giữa segment vẫn khác. Đây không phải bug nếu user chấp nhận khoảng lặng.

## 3. Mô hình toán nên chốt

Đặt:

- `B`: tốc độ phong cách mong muốn (`TTS_BASE_SPEED`, ví dụ 1.30);
- `N`: phần style engine làm native;
- `S = B / N`: phần style hậu kỳ còn lại;
- `E`: nén fit engine thêm sau baseline;
- `A`: nén fit atempo thêm ở S7;
- `M = MAX_SPEEDUP`.

Hai bất biến:

```text
E × A ≤ M                         # ngân sách chống tràn, như lời hứa MAX_SPEEDUP
B × E × A ≤ ABS_AUDIBLE_MAX      # trần chất lượng tuyệt đối mới
```

`S` thuộc baseline style nên không nằm trong `E × A`, nhưng có trong tổng nghe
thật. `ABS_AUDIBLE_MAX` là constant kỹ thuật ban đầu, không cần thêm knob. Giá
trị phải A/B; 2.0 là một điểm chặn bảo thủ hơn việc cho phép 3.0.

Nếu PROSODY/EMOTION rate modifier `R` được bật, tổng thực là `B × R × E × A` và
hard cap cũng phải xét R. Vì yêu cầu mới muốn uniform, lựa chọn sạch nhất là:

- uniform mode: emotion/prosody chỉ chỉnh pitch/volume, không chỉnh rate;
- expressive mode tương lai: cho rate modifier và chấp nhận không đều.

Không nên âm thầm cộng phần trăm. Mọi lớp tốc độ dùng hệ số nhân.

## 4. Mapping engine đề xuất

| Engine | Native style | Phần dư style | Fit thêm |
|---|---|---|---|
| edge | rate tổng, cap chất lượng hiện +50% | atempo nếu B vượt native cap | edge resynth rồi S7 |
| viXTTS | `speed`, tạm cap 1.25 | atempo nhẹ | XTTS resynth trong headroom rồi S7 |
| ElevenLabs | `voice_settings.speed`, cap API 1.2 | atempo nhẹ | hiện tại S7 |
| VBee | `speed_rate`, miền cần verify | atempo nhẹ | hiện tại S7 |
| FPT | header speed -3..+3, map bằng đo duration | atempo nhẹ | hiện tại S7 |

Không cần bắt mọi engine thực hiện B hoàn toàn native. Mục tiêu là output cuối
cùng gần B, ưu tiên native trong miền chất lượng rồi dùng một residual atempo
nhỏ. Với +30%, cách này khả thi hơn +50% trên viXTTS/ElevenLabs.

Để tránh encode nhiều lần, S7 có thể hợp nhất style-atempo và fit-atempo thành
một filter execution, nhưng report và budget vẫn phải giữ hai factor riêng.
Quyết định stage cụ thể không được làm thay đổi các bất biến trên.

## 5. Voicesig, report và impact

### Voicesig

Thêm base speed vào `TtsSettings` và mọi signature branch:

- edge;
- viXTTS default;
- viXTTS voice_ref/casting;
- ElevenLabs/VBee/FPT;
- paid vi-only fallback sang edge.

Paid signature hiện không chứa fit budget vì MAX_SPEEDUP không làm paid re-synth;
base speed thì khác: nó được gửi vào API native, nên bắt buộc nằm trong sig.

Có hai nơi phải giữ parity:

- `core/voicesig.voice_signature()`;
- direct edge signature trong `_tts_one()` (`s5_tts.py:172-174`).

Comment trong voicesig đã cảnh báo đúng bẫy này. Cần parity tests cho tất cả
engine/casting/single-voice.

### Fit report

Không overload `engine_speed`. Report nên tách:

```json
{
  "style_requested": 1.3,
  "style_native": 1.2,
  "style_atempo": 1.083,
  "fit_engine": 1.0,
  "fit_atempo": 1.15,
  "audible_total": 1.495
}
```

`budget_left()` dùng `fit_engine`, không dùng style factor. Dashboard có thể
hiện “nhịp nền 1.30×; nén thêm 1.15×; tổng nghe 1.50×”. Đây mới đúng nghĩa với
người dùng.

### Override impact

Thêm key vào `_OV_TTS`, `_JOB_OVERRIDE_KEYS`, preview allowlist và settings
schema/profile. `/override-impact` sẽ so voicesig và báo N/M câu cùng paid chars.

Đổi per-job speed không được leo depth translate chỉ vì S4 có thể tham khảo
speed cho job dịch mới. Job hiện tại giữ nguyên text và đi từ TTS.

## 6. Test trước khi chọn mức 1.30 chính thức

Dùng corpus cố định ít nhất 20 câu cho NamMinh và HoaiMy:

- 5 câu rất ngắn 1–5 âm tiết;
- 5 câu trung bình;
- 5 câu dài;
- 5 câu có số, tên Latin/Hán-Việt, dấu phẩy/chấm hỏi/chấm than.

Mỗi câu synth ở 1.0/1.2/1.3/1.4/1.5. Đo:

- trimmed duration và âm tiết/s;
- median + độ phân tán giữa câu, không chỉ một câu mẫu;
- số câu overflow, fit thêm và clipped_ms trên job test;
- tỷ lệ câu chạm absolute cap;
- nghe mù A/B về tự nhiên, rõ phụ âm, tên/số, pause.

Sau đó chạy đúng một clone job test qua full pipeline, không đụng job thật.
So `mix_report`: clipped count/ms, fit factors, gap và tổng tốc độ. Với paid
engine, dùng câu preview ngắn trước; không chạy cả corpus nếu chưa chốt chi phí.

Tiêu chí chọn 1.30:

- đa số câu ngắn hết cảm giác lê thê;
- câu rất ngắn không bị cụt;
- median gần vùng user muốn;
- variance tempo giảm rõ;
- clipped_ms không tăng bất thường;
- không cần style atempo residual quá lớn trên engine mục tiêu.

## 7. Thứ tự triển khai nếu user chốt

1. Chốt tên/unit/default/migration và mô hình B/N/S/E/A.
2. Thêm schema/config/voicesig/report + tests toán/parity trước.
3. Edge end-to-end + preview draft + per-job impact.
4. Chạy corpus/job test, user nghe 1.20/1.30/1.40 rồi chốt setting kênh.
5. viXTTS với cap native + residual.
6. ElevenLabs/VBee/FPT theo API native đã verify; paid test có giới hạn chi phí.
7. Deprecate STRETCH_SHORT và sửa preset/nhãn MAX_SPEEDUP.
8. Chỉ sau khi có số liệu mới cân nhắc nới `SYL_MAX_PER_S`.

## 8. Quyết định đề xuất

Chọn **tốc độ nền 1.30 cho cấu hình kênh của user**, nhưng giữ **factory default
1.0**. Hỗ trợ per-job ngay. Không scale ngân sách âm tiết trong đợt đầu. Bỏ
STRETCH_SHORT khỏi UX. Dùng native speed của từng engine trong miền an toàn,
atempo chỉ bù phần dư, và thêm hard cap tổng để baseline × fit không trở thành
3× ngoài ý muốn.

Đây giữ đúng yêu cầu mới: mọi câu bắt đầu từ cùng một nhịp nhanh tự nhiên; chỉ
câu thật sự không vừa mới bị nén thêm và cuối cùng fade-cut như cơ chế đã chốt.
