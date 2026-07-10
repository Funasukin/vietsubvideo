# Phản biện panel "Tùy chọn video này" — Codex

> Kiểm tra trên commit `d8006af`, ngày 2026-07-11. Phạm vi chỉ đọc code và
> phản biện `AUDIT_GIONG_TUYCHON_JOB.md`; không sửa pipeline/UI/cấu hình.

## 0. Kết luận ngắn

Hướng giảm số knob và làm rõ chi phí là đúng. Tôi đồng ý mạnh với U1, U6, U7,
U8, U9, U12, U13; đồng ý có điều kiện với U3, U4, U5, U10, U14, U15; không
đồng ý U2 và U11 theo dạng đang đề xuất.

Ba điều nên sửa trước khi chốt thiết kế:

1. Không gộp cứng chế độ và danh tính giọng thành ba lựa chọn NamMinh/HoaiMy.
   Cách đó chỉ mô tả đúng edge tiếng Việt, không mô tả đúng viXTTS, paid engine,
   giọng tùy biến, ngôn ngữ khác và trạng thái "theo cấu hình chung".
2. `bed_gain_db` đang bị UI ẩn sai ngữ cảnh. S6 dùng nó cho cả duck theo thoại,
   flat và nền demucs, không chỉ `KEEP_BGM=flat`.
3. Dry-run phải dùng một bộ tính tác động thuần dữ liệu. Không nên đổi tạm biến
   trong module `config`, vì server có tiến trình dùng chung và dễ tạo race.

## 1. Phản biện U1–U15

### U1 — Đồng ý, nhưng số câu phải tính theo engine

`MAX_SPEEDUP` đúng là nhóm TTS: chữ ký edge, viXTTS và câu cast viXTTS chứa
`:f{budget}` (`core/stages/s5_tts.py:49-64`). Đổi mức có thể làm lệch `.sig` và
đọc lại các câu tương ứng.

Ngoại lệ quan trọng: chữ ký paid engine hiện không chứa `:f`, vì paid TTS chưa
fit ở lúc synth (`s5_tts.py:54-57, 268-301`). Đổi `MAX_SPEEDUP` với job thuần
paid sẽ chạy lại stage TTS nhưng `_seg_ready` giữ toàn bộ MP3, tức số câu gọi API
trả phí có thể là 0. UI nên hiện số thực tế từ chữ ký, không nói mặc định rằng
mọi câu sẽ được đọc lại.

Ước lượng thời gian nên là khoảng, dựa trên engine và lịch sử job nếu có. Chỉ từ
N/M câu thì không đủ để hứa một số phút chính xác.

### U2 — Không đồng ý với dropdown ba lựa chọn hiện tại

`TTS_SINGLE_VOICE` áp cho mọi engine, nhưng `TTS_VOICE`/`TTS_VOICE_NU` chỉ là
giọng edge tiếng Việt. viXTTS dùng `VIXTTS_VOICE_NAM/NU`; paid dùng cặp voice
riêng của provider; ngôn ngữ khác lấy cặp trong `core/langs.py`. Ba lựa chọn
"1 giọng — NamMinh / HoaiMy / 2 giọng — Nam+Nữ" vì vậy trộn hai khái niệm:

- chế độ phân vai: một giọng hay hai giọng;
- danh tính giọng: phụ thuộc engine/ngôn ngữ/provider.

Nó còn ghim override cụ thể vào job, làm mất ý nghĩa kế thừa nếu giọng chung đổi
sau này. Cặp cùng giới, giọng edge tùy biến và voice pair paid cũng không biểu
diễn được.

Đề xuất thay thế: dùng một control tổng hợp nhưng vẫn giữ hai tầng dữ liệu:

- `Chế độ giọng`: Theo cấu hình chung / Một giọng / Hai giọng tự gán;
- `Giọng chính` và `Giọng phụ`: chỉ hiện khi engine hiện tại thực sự cho phép
  chọn per-job. Với viXTTS/paid hiện nay, hiển thị tên cặp global dạng chỉ đọc
  hoặc bổ sung whitelist riêng nếu thật sự muốn override per-job.

Casting Series không bị phá bởi chế độ một giọng vì `voice_ref` thắng nhánh
nam/nữ (`s5_tts.py:28-31, 51-52`). Vấn đề của U2 nằm ở biểu diễn và kế thừa,
không nằm ở casting.

### U3 — Chọn disable, kèm hành động "Dịch lại để tạo nhãn"

Nếu transcript hiện tại không có nhãn cảm xúc hữu ích, bật `EMOTION` ở depth TTS
không thay đổi output: `emotion.label()` trả rỗng và chữ ký cũng không đổi
(`core/emotion.py:45-60`). Nhận định no-op là đúng với job đó.

Không nên âm thầm chuyển toàn bộ knob sang depth translate. Với job đã có nhãn,
bật/tắt EMOTION chỉ cần TTS; ép dịch lại sẽ tốn phí và làm mất chỉnh tay vô ích.
Thiết kế đúng là:

- có nhãn: cho bật/tắt ở nhóm TTS;
- không có nhãn: disable, giải thích lý do và có lệnh riêng "Dịch lại để tạo nhãn";
- lệnh riêng phải xác nhận rõ mất bản sửa tay và chi phí.

Nên kiểm tra nhãn hợp lệ khác `binhthuong`, không chỉ kiểm tra field tồn tại.

### U4 — Đồng ý ẩn theo engine, sửa lại mô tả nguồn audio

Prosody mức 1 chỉ tác động tham số edge; chữ ký viXTTS/paid không chứa prosody.
Ẩn khi engine hiệu lực không phải edge là đúng.

Tuy nhiên ghi chú "đo trên audio lẫn nhạc nền" không còn luôn đúng. Hàm
`_audio_path()` ưu tiên `vocals.wav`, rồi mới fallback `audio_16k.wav` và
`audio_full.wav` (`core/prosody.py:78-83`). UI nên nói nguồn đo thực tế:
"ưu tiên vocals; nếu chưa tách giọng sẽ đo trên audio gốc và có thể nhiễu nhạc".

Khi `TARGET_LANG != vi`, pipeline vẫn dùng edge nên PROSODY có tác dụng; không
nên ẩn chỉ vì ngôn ngữ khác tiếng Việt.

### U5 — Đồng ý có điều kiện

Preset hữu ích, nhưng preset này trải qua hai depth: `MAX_SPEEDUP` là TTS,
`STRETCH_SHORT` là mix. Vì vậy không nên đặt nó dưới nhãn nhóm Trộn. Đặt ở đầu
phần Thường dùng như một segmented control độc lập, đồng thời hiển thị trước
"có thể đọc lại N câu".

Preset chỉ nên điền giá trị vào các control và vẫn cho user xem/chỉnh giá trị
chi tiết. Repo đã có mapping global `tight = 2.0 + stretch`, `natural = 1.2 +
không stretch`; per-job nên dùng cùng một nguồn mapping để tránh lệch về sau.

### U6 — Đồng ý

Nút reset toàn bộ override là cần thiết. Payload `{}` đã có nghĩa xóa toàn bộ
override (`webui/server.py:1270-1273`). Dialog phải liệt kê tác động của việc
quay về default hiện tại, vì reset không đồng nghĩa "không chạy lại".

Không reset chung `bed_gain_db` hay `job.render` nếu nút chỉ mang tên "Về cấu
hình chung" cho env override. Nếu muốn reset mọi thứ, cần tên và phạm vi khác.

### U7 — Đồng ý

Server đã có trạng thái key trong `/api/config`, còn `paid_tts.ready()` đã biết
điều kiện từng engine. Editor nên nhận một object capability đã lọc bí mật,
ví dụ `{elevenlabs:{ready:false,reason:"Thiếu API key"}}`.

VBee phải kiểm tra cả token và app id. Disable option chưa đủ nếu job cũ đang
override engine nay bị mất key: vẫn phải hiển thị giá trị hiện tại cùng cảnh báo,
để user có thể chuyển đi hoặc sửa credential.

### U8 — Đồng ý mạnh

`VOICE_FX` là render-time processing (`s8_render.py:286, 410`), không phải TTS.
Chuyển nó sang panel render là đúng cả về mô hình và chi phí.

Bug kế thừa là thật: editor dựng select bằng `(data.render || {}).fx || "off"`
và `RenderOptions.fx` mặc định `off`; mỗi lần lưu render có thể ghim `off` vào
job. Cần option ba trạng thái "Theo cấu hình chung" và chỉ lưu key `fx` khi user
thật sự override. S8 hiện đã hỗ trợ fallback nếu thiếu key.

### U9 — Đồng ý

`PROSODY_TRANSFER` là thử nghiệm DSP, áp mọi output TTS và có blast radius toàn
job. Không có bằng chứng nó là quyết định thay đổi thường xuyên theo video.
Global-only là hợp lý cho tới khi tính năng ổn định và có A/B preview đáng tin.

### U10 — Đồng ý có điều kiện

Model là chính sách chất lượng/chi phí và không cần nằm ở phần thường dùng.
Loại khỏi per-job là quyết định UX hợp lý. Lưu ý khi Gemini fallback sang Claude,
model Claude sẽ theo global; cần ghi rõ để user không tưởng provider override là
một cấu hình khép kín.

Nếu nhóm vận hành thực sự có workflow "video khó dùng model mạnh", có thể giữ
một control chung `Chất lượng dịch: Tiết kiệm / Cân bằng / Tốt nhất` trong Nâng
cao, map theo provider. Không nên phơi hai danh sách model độc lập.

### U11 — Không đồng ý bỏ cả hai

`WHISPER_MODEL` thường theo năng lực máy, nhưng cũng thay đổi theo độ khó audio,
ngôn ngữ và nhu cầu sửa một job thất bại. `OCR_FPS` thay đổi theo tốc độ phụ đề:
sub rất ngắn có thể cần 2 fps dù global dùng 1 fps. Đây là hai knob có lý do
per-video rõ ràng.

Đề xuất giữ trong Nâng cao, chỉ hiện theo `TRANSCRIPT_SOURCE`, kèm cảnh báo làm
lại transcript. Có thể đổi nhãn thành preset dễ hiểu thay vì tên kỹ thuật:
"Whisper: Nhanh / Cân bằng / Chính xác" và "OCR: Nhanh / Kỹ".

Auto-gate chỉ chọn OCR hay Whisper; nó không tự chọn model Whisper hoặc sampling
rate tối ưu, nên không thay thế hai control này.

### U12 — Đồng ý mạnh, cần mở rộng estimate

Dry-run nên trả cả chi phí paid TTS, không chỉ dịch. Đổi engine/voice có thể gửi
lại toàn bộ ký tự tới ElevenLabs/VBee/FPT dù không dịch lại.

Thiết kế endpoint đề xuất:

`POST /api/jobs/{job_id}/override-impact`

Payload chứa `env_overrides` dự kiến và, nếu cần, danh sách edit chưa lưu. Response:

```json
{
  "depth": "tts",
  "stages": ["tts", "bgm", "mixing", "rendering"],
  "segments_total": 120,
  "tts_regenerate": 37,
  "paid_tts_chars": 0,
  "translation_segments": 0,
  "translation_chars": 0,
  "manual_edits_at_risk": 0,
  "estimated_seconds": [80, 180],
  "warnings": []
}
```

Không cần load model. Tuy nhiên `_voice_sig` hiện đọc trực tiếp module `config`,
nên gọi nó với override giả bằng cách `setattr(config, ...)` trong server là
không an toàn. Worker đang tránh vấn đề này bằng tiến trình con và biến môi
trường (`webui/server.py:186-199`).

Giải pháp bền là tách resolver thuần dữ liệu, ví dụ `TtsSettings` +
`voice_signature(seg, settings)`, rồi S5 và endpoint cùng gọi. Bản đầu tối thiểu
có thể spawn một subprocess ngắn với `FLOWAPP_JOB_OVERRIDES`; cách đó an toàn
hơn mutation global nhưng chậm hơn và dễ trùng logic response.

Với depth translate/transcript, không thể biết chữ ký tương lai trước khi LLM/
ASR chạy. Khi đó endpoint phải báo toàn bộ output sau stage sẽ bị vô hiệu hóa,
không giả vờ đếm chính xác từ transcript cũ.

### U13 — Đồng ý không thêm knob trùng, nhưng phải sửa visibility

`bed_gain_db` đúng là override của `DUCK_GAIN_DB`; không thêm knob thứ hai.
Nhưng S6 dùng gain này ở cả ba trường hợp: duck theo cửa sổ thoại, hạ đều và nền
demucs (`core/stages/s6_bgm.py:23-27, 40-75`). UI hiện chỉ hiện BEDVOL khi
`KEEP_BGM === "flat"` (`index.html:2593-2594`), làm mất control hợp lệ ở hai mode
còn lại.

Nên luôn hiện "Mức nền khi có thoại" và đổi phần giải thích theo mode. Với flat,
nó là mức toàn video; với duck/demucs, nó là mức trong vùng thoại.

### U14 — Đồng ý có điều kiện

Preview 10 giây quanh câu đang chọn rất đúng nhu cầu chỉnh mix. Phạm vi phiên bản
đầu nên chỉ gồm các thay đổi mix rẻ: gain, duck/flat và `STRETCH_SHORT` trên audio
TTS đã có.

Các giới hạn phải trung thực:

- chọn demucs khi job chưa có stem không thể là preview tức thì;
- thay engine/voice/MAX_SPEEDUP có thể cần synth lại, không thuộc preview mix rẻ;
- đoạn preview phải dùng cùng hàm dựng gain/window/atempo với S6/S7, không tạo
  một implementation gần giống ở endpoint.

Nếu không tái dùng được pipeline cục bộ, nút này dễ thành một preview nghe khác
render và làm giảm lòng tin hơn là tăng.

### U15 — Đồng ý chia tầng, không đồng ý danh sách thường dùng hiện tại

`CONTENT_STYLE` và `TRANSCRIPT_SOURCE` là lựa chọn sâu, phá bản dịch/chỉnh tay khi
đổi trong editor; chúng không phù hợp với luồng "sửa nhanh" dù có thể quan trọng
lúc tạo job.

Đề xuất bố cục:

**Thường dùng**

- Nhạc/SFX gốc;
- Mức nền;
- Preset khớp thoại;
- Engine giọng;
- Chế độ một/hai giọng;
- Giọng tất cả câu / Đổi toàn bộ.

**Nâng cao**

- MAX_SPEEDUP, STRETCH_SHORT;
- PROSODY (chỉ edge), EMOTION theo trạng thái nhãn;
- provider, target language, content/style;
- transcript source, Whisper quality, OCR quality/crop.

**Render**

- VOICE_FX cùng subtitle mode, cover, frame, watermark và `sub_split` hiện có.

Panel nên mặc định nhớ trạng thái đóng/mở của user, thay vì luôn `open`.

## 2. Knob thiếu và knob nửa tác dụng

### DENOISE là ứng viên per-job hợp lý, nhưng cần depth mới

Nhiễu là thuộc tính từng video, nên `DENOISE` hợp per-job hơn `WHISPER_MODEL`.
Nhưng nó tác động S2 (`core/stages/s2_extract.py:40`), sâu hơn nhóm transcript
hiện tại bắt đầu ở S3. Không được chỉ thêm vào `_OV_TRANSCRIPT`: phải có depth
`extract`, xóa/tạo lại `audio_16k.wav`, rồi chạy S3 trở đi. Vì chi phí và nguy cơ
mất chỉnh tay lớn, đặt nó trong Nâng cao với dry-run rõ ràng.

### SUBTITLE_MODE không thiếu

Nó đã nằm trong panel render qua `RenderOptions.subtitle_mode`; `sub_split` cũng
đã là render option. Không thêm bản env-override thứ hai vào panel này.

### Các điểm nửa tác dụng cần sửa

- `bed_gain_db`: có tác dụng nhưng bị ẩn ở hai mode hợp lệ, như U13.
- `PROSODY`: no-op trên viXTTS/paid, như U4.
- `EMOTION`: no-op nếu job không có nhãn hợp lệ, như U3.
- `TTS_VOICE/_NU`: chỉ edge tiếng Việt; panel đã ẩn ngoài ngữ cảnh, nhưng U2
  không được làm mất ranh giới này.
- `MAX_SPEEDUP`: paid engine không re-synth; dry-run phải trả đúng 0 API call
  nếu chữ ký paid không đổi.

## 3. Thứ tự chốt đề xuất

1. Sửa tính trung thực trước: U3, U4, U7, U8 và visibility của U13.
2. Làm resolver tác động + endpoint U12; dùng nó cho cảnh báo U1 và mọi thao tác
   reset/preset.
3. Tổ chức lại U15 và preset U5.
4. Làm U14 sau khi đã có primitive mix dùng chung.
5. Không triển khai U2/U11 nguyên dạng; dùng phương án thay thế ở trên.

Kết luận: mục tiêu từ 23 knob xuống một panel dễ dùng là đúng, nhưng không nên
đạt con số thấp bằng cách gộp các khái niệm không cùng miền hoặc bỏ các control
thật sự thay đổi theo video. Tính trung thực về ngữ cảnh, kế thừa và chi phí quan
trọng hơn số lượng knob tuyệt đối.
