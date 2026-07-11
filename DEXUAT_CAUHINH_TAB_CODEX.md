# Phản biện tab Cấu hình — Codex

> Kiểm tra trên commit `2ddf43f`, ngày 2026-07-11. Chỉ đọc code và viết tài
> liệu; không sửa UI, pipeline, `.env` hay dữ liệu job.

## 0. Kết luận ngắn

Hướng tổ chức lại tab theo ngữ cảnh người dùng là đúng. Tôi đồng ý với G1–G4,
G6–G9, G11, G13–G14 sau một số hiệu chỉnh; đồng ý mạnh với mục tiêu G5 nhưng
không nên tạo key chất lượng mới; G10 và G12 cần đổi semantics; G15 phần lớn đã
có trong code hiện tại.

Điều kiện kiến trúc nên làm trước G8/G11 là một **settings schema duy nhất**.
Hiện một setting bị khai báo lặp ở ít nhất ba nơi:

- default/parser trong `config.py`;
- whitelist trong `SAFE_ENV_KEYS`/`SECRET_ENV_KEYS`;
- control/options trong `CFG_FIELDS` và `loadConfig()`.

Nếu tiếp tục thêm reset, profile, capability và validation trên ba danh sách
riêng, chúng sẽ lệch nhau. Ví dụ thực tế: `ELEVENLABS_MODEL` có trong config và
server whitelist nhưng không có control trong `CFG_FIELDS`.

Hai facts trong đề xuất cần sửa:

1. `/api/config` hiện **không trả `defaults`**. Nó tạo biến cục bộ tên
   `defaults` nhưng chỉ trả `values` (`webui/server.py:1149-1168`). Hơn nữa,
   `getattr(config, key)` đã chịu ảnh hưởng `.env`, nên đó không phải factory
   default để dùng cho G8.
2. G15 sticky save và cảnh báo rời tab đã có: `.cfgfoot` đã `position: sticky`
   (`style.css:202-207`), còn `cfgDirty` + modal đã chặn chuyển tab
   (`app-core.js:165-167, 201-207`). Phần thiếu là đếm diff thật, cảnh báo đóng
   browser và hiển thị danh sách key server đã lưu.

## 1. Phản biện G1–G6

### G1 — Đồng ý

`AUTO_RETRY` do `webui/worker.py` đọc tươi và áp cho mọi lỗi pipeline, không liên
quan riêng transcript. Chuyển vào Hệ thống / Hàng đợi là đúng.

### G2 — Đồng ý, chỉnh lại tên nhóm

DENOISE thuộc xử lý đầu vào cho Whisper ở S2; diarization dùng audio để bổ sung
speaker ở S4. Gom cả hai dưới **Nhận dạng & người nói** hợp với mô hình người
dùng hơn việc giữ hai card nhỏ.

`DIARIZE_MAX_SPK` chỉ nên hiện khi DIARIZE bật. DENOISE nên hiện chú thích rằng
nó không có tác dụng nếu job cuối cùng dùng OCR.

SUBSCRIBE và SUBSCRIBE_TEXT là render/publishing nên chuyển sang Xuất bản.

### G3 — Đồng ý, nên chuyển thêm VOICE_FX

`SUBTITLE_MODE` và `SUB_SPLIT` đều được S8 đọc (`core/stages/s8_render.py`), nên
đặt trong Xuất bản / Render là đúng.

`VOICE_FX` cũng chỉ áp lúc S8 qua `brand.build_audio`; audit per-job đã chốt nó
là render option. Để nhất quán, global VOICE_FX cũng nên chuyển sang phần
**Âm thanh xuất bản / Mastering**, không để cạnh engine TTS.

KEEP_BGM, DUCK_GAIN_DB và STRETCH_SHORT là mix chứ không phải engine TTS. Không
nhất thiết tách thêm card, nhưng nên đổi tên nhóm thành **Lồng tiếng & âm thanh**
thay vì “Lồng tiếng TTS” để nhãn nhóm trung thực.

### G4 — Đồng ý có điều kiện

GEMINI_MIN_INTERVAL vào Nâng cao là hợp lý.

OCR_WORKERS nên có option `auto`, nhưng không nên mặc định thẳng bằng
`os.cpu_count()`: mỗi process RapidOCR đang dùng hai thread, nên số worker bằng
số logical CPU có thể oversubscribe gấp đôi và tốn RAM. Runtime resolver nên
dùng một công thức có cap, ví dụ dựa trên `logical_cpu // 2`, rồi benchmark để
chọn trần 4/6. Lưu `.env` là `OCR_WORKERS=auto`, không ghi con số máy hiện tại,
để profile/máy khác vẫn tự thích nghi.

### G5 — Đồng ý với UX, không tạo `QUALITY` key mới

⭐ Chất lượng dịch nên chỉ là một **setter/view** cho hai key thật
`CLAUDE_MODEL` và `GEMINI_MODEL`, giống mapping `QUALITY_MODELS` hiện có:

- chọn Tiết kiệm/Cân bằng/Tốt nhất thì set cả hai model control;
- đổi một model thủ công khiến núm chất lượng hiện `Tùy chỉnh`;
- lưu `.env` chỉ lưu hai model thật;
- profile lưu model thật, có thể kèm nhãn tier chỉ để hiển thị.

Không thêm key `TRANSLATE_QUALITY`. Nếu tier và model cùng tồn tại sẽ phải định
nghĩa precedence mãi mãi, profile cũ phụ thuộc mapping mới và log không cho biết
model thực tế chỉ bằng cách nhìn `.env`.

Khi provider là Gemini, model Claude không nên biến mất hoàn toàn: đó là model
fallback thật. Đưa cả hai vào Nâng cao, ghi rõ `Model chính` và `Model fallback`.
Tooltip hiện nói fallback Haiku nhưng model thật có thể đã là Sonnet.

### G6 — Đồng ý, cần thêm dependency theo engine

Nhãn “Bật (khuyên dùng)” của PROSODY/EMOTION mâu thuẫn default `0` trong
`config.py:163-166`; phải sửa.

Ngoài cảnh báo emotion cần nhãn từ lần dịch, UI nên phản ánh phạm vi thật:

- PROSODY mức 1 chỉ tác động edge; disable/ẩn khi engine viXTTS hoặc paid;
- EMOTION tác động edge và viXTTS, nhưng paid engine hiện bỏ qua;
- PROSODY ưu tiên `vocals.wav`, nếu chưa có mới đo audio gốc có thể lẫn nhạc;
- PROSODY_TRANSFER là thử nghiệm và áp hậu kỳ output của mọi engine.

## 2. Phản biện G7–G12

### G7 — Đồng ý, nên gọi `/api/capabilities`

`/api/health` thường mang nghĩa liveness/readiness của server. Card này là năng
lực máy, nên endpoint rõ nghĩa hơn là:

`GET /api/capabilities`

Response đề xuất:

```json
{
  "generated_at": "2026-07-11T10:00:00+07:00",
  "cpu": {"logical_cores": 16},
  "gpu": {
    "status": "available",
    "name": "NVIDIA GeForce RTX 3070",
    "vram_total_mb": 8192,
    "driver": "..."
  },
  "ffmpeg": {"available": true, "version": "...", "h264_encoder": "h264_nvenc"},
  "packages": {
    "faster_whisper": "installed",
    "demucs": "installed",
    "pyannote": "installed"
  },
  "models": {
    "vixtts": {"status": "files_present", "missing": []}
  },
  "engines": {
    "edge": {"ready": true, "reason": ""},
    "elevenlabs": {"ready": false, "reason": "Thiếu API key"}
  },
  "keys": {"anthropic": true, "gemini": false, "hf": false}
}
```

Các probe rẻ và không load model:

- `os.cpu_count()`;
- `nvidia-smi --query-gpu=...` với timeout 2–3 giây;
- `ffmpeg -version` và encode thử 0.1 giây như `ffmpeg.h264_args()` để xác nhận
  encoder chạy thật, không chỉ có tên trong danh sách;
- `importlib.util.find_spec()` cho package tùy chọn, không import torch/TTS;
- kiểm tra đủ `config.json`, `model.pth`, `vocab.json` của viXTTS;
- key status từ `_read_env()` tươi, không trả giá trị.

`pyannote installed` không có nghĩa đã chấp nhận model HF; `demucs installed`
không có nghĩa checkpoint đã tải. Response phải dùng trạng thái `installed / 
partial / unknown`, không gộp thành boolean “sẵn sàng” gây hiểu lầm.

Cache kết quả 30–60 giây và có nút refresh. Tuyệt đối không gọi
`vixtts.is_available()` vì hàm đó load model lên GPU.

### G8 — Đồng ý mạnh, nhưng cần factory-default thật và API unset

Nên phân biệt ba trạng thái:

1. factory/recommended default của phiên bản app;
2. giá trị đã lưu trong `.env`;
3. giá trị draft chưa lưu trên form.

Indicator “khác mặc định” so sánh 1 với 2 sau khi normalize type (`False`, `0`,
`0.0` không được báo khác giả). Counter “N thay đổi chưa lưu” so sánh 2 với 3;
đây là hai con số khác nhau.

Nút reset nên **xóa key khỏi `.env`**, không chỉ ghi giá trị default hiện tại.
Như vậy default app đổi trong phiên bản sau thì setting chưa ghim sẽ theo đúng
default mới. Server hiện chưa có semantics unset; blank thường bị bỏ qua. Cần
API explicit `unset: [key]` và confirmation riêng nếu xóa secret.

Factory defaults phải nằm trong settings schema, không lấy từ module `config`
đã load `.env`.

### G9 — Đồng ý

Search nên match label, env key, tooltip và alias tiếng Việt; row không khớp nên
ẩn, section có kết quả tự mở. “Làm mờ” hàng chục kết quả không khớp vẫn để trang
dài và khó quét.

Khi xóa search, khôi phục trạng thái mở/gập trước đó. Search trong Nâng cao phải
tự mở đúng details, nếu không user thấy “có kết quả” nhưng không thấy control.

### G10 — Đồng ý cảnh báo, không disable option trong tab global

Per-job nên disable engine thiếu key vì key không được nhập tại đó. Tab Cấu hình
thì khác: user có thể chọn ElevenLabs và nhập key trong cùng một form trước khi
bấm Lưu. Disable option sẽ chặn chính luồng setup này.

Thiết kế phù hợp cho tab global:

- option vẫn chọn được, gắn `thiếu key`;
- hiện lỗi inline và nút nhảy đến field key;
- nếu user vừa nhập secret trong draft, warning cập nhật ngay;
- khi lưu có thể cảnh báo mạnh, không nhất thiết chặn việc lưu cấu hình chuẩn bị
  cho lần sau.

`_engine_caps()` hiện có nhưng dùng `config` của server từ lúc startup qua
`paid_tts.ready()`. Sau khi UI lưu key mới, capability đó có thể stale cho tới
khi restart. Nên tách resolver dùng snapshot `_read_env()` tươi và dùng chung
cho editor, config tab và capability endpoint.

Kiểm tra viXTTS hiện chỉ nhìn `config.json`; cần kiểm tra cả checkpoint/vocab.

### G11 — Đồng ý, không lưu “toàn bộ non-secret” một cách mù quáng

Profile nội dung không nên mang setting phụ thuộc máy hoặc tích hợp cá nhân sang
máy khác. Dùng allowlist `PROFILE_KEYS`, loại:

- mọi secret và trạng thái key;
- path local/cookie/OAuth file;
- OCR worker/device phần cứng;
- Telegram chat id;
- AUTO_RETRY và setting vận hành server.

Schema đề xuất:

```json
{
  "schema_version": 1,
  "id": "uuid",
  "name": "Donghua kiếm hiệp",
  "created_at": "2026-07-11T10:00:00+07:00",
  "app_version": "2ddf43f",
  "values": {
    "CONTENT_STYLE": "donghua",
    "TARGET_LANG": "vi",
    "TTS_ENGINE": "edge",
    "CLAUDE_MODEL": "claude-haiku-4-5-20251001"
  }
}
```

Import/apply phải có preview diff. Key thiếu trong profile cũ nghĩa là **giữ
giá trị hiện tại**, không reset ngầm. Key thừa/không còn hỗ trợ bị bỏ qua và trả
warning. Giá trị phải qua cùng parser/options/range của settings schema; không
cho profile ghi thẳng tùy ý vào `.env`.

Lưu file theo UUID và tên hiển thị ở JSON; không dùng tên người dùng làm path.
Ghi atomic. Export/import không bao giờ chứa secret.

Không kèm `pause_before_render`: đó là preference của UI/workflow, không phải
profile nội dung. Nếu cần nhớ, lưu riêng trong local preference.

Một bug nền cần xử lý cùng profile: `set_config()` hiện ghi raw
`KEY={value}`. Text tự do có `#`, quote hoặc cú pháp dotenv có thể bị parse khác
lần sau. Nên dùng serializer dotenv có quote/escape chuẩn; validation hiện chỉ
chặn newline và độ dài, chưa validate enum/range.

### G12 — Đồng ý với FX sample; TTS preview cần mở rộng API

`voice_samples/` đã có bộ file FX và `core/voice_fx.py` xác nhận filter giống
render. Nút icon nghe sample cạnh VOICE_FX là rẻ và trung thực nếu endpoint file
được allowlist basename.

`/api/tts-preview` hiện không nhận toàn bộ draft setting global. Không có
`job_id`, nó dùng `config` đã load khi server startup; body chỉ có nam/nữ và
voice_ref, không truyền được voice id/engine đang chọn nhưng chưa lưu. Tái dùng
nguyên endpoint sẽ tạo preview “chọn một đằng, nghe một nẻo”.

Nên bổ sung preview settings explicit đã whitelist hoặc endpoint config-preview
riêng. Paid TTS phải ghi rõ “nghe thử có tính phí” và yêu cầu click chủ động.
viXTTS có thể mất thời gian load GPU; UI cần trạng thái loading/cancel. Không tự
preview khi đổi dropdown.

## 3. Phản biện G13–G15

### G13 — Đồng ý có điều kiện

Thứ tự TTS → Dịch → Nhận dạng → Xuất bản phù hợp workflow hiện tại. Tuy nhiên
không nên tách các field phụ thuộc nhau chỉ để ép đúng taxonomy:

- `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` nên ở cùng nhóm Thông báo;
- `VBEE_TOKEN` và `VBEE_APP_ID` nên ở cùng nhóm credential của VBee;
- YouTube OAuth/path/privacy hợp với Xuất bản hoặc Tích hợp hơn Hệ thống.

Keys có thể xuống cuối và gập khi hệ thống đã sẵn sàng. First run hoặc active
provider/engine đang thiếu credential thì card setup phải được đẩy lên đầu hoặc
card Trạng thái máy phải có banner + nút nhảy thẳng tới key thiếu. Chỉ “mở card
ở cuối trang” vẫn là first-run UX kém.

Đề xuất nhóm cuối tên **Tích hợp & khóa truy cập**, chia tiểu mục Dịch, TTS,
Thông báo, YouTube; không gom mọi token thành danh sách phẳng.

### G14 — Đồng ý

Nâng cao trong từng nhóm là đúng. Nên nhớ trạng thái details bằng localStorage.
Dependency UI vẫn thắng trạng thái advanced: field không áp dụng phải ẩn/disable
có lý do dù phần Nâng cao đang mở.

Các ứng viên advanced rõ ràng: model cụ thể, rate-limit, OCR worker/FPS,
DIARIZE_MAX_SPK, PROSODY_TRANSFER, logo scale/opacity, metadata model.

### G15 — Chỉ còn phần nâng cấp, không phải làm mới

Sticky footer và modal rời tab đã tồn tại. Phần còn thiếu:

- counter tính diff draft thật, giảm về 0 nếu user đổi lại giá trị ban đầu;
- `beforeunload` khi đóng/reload browser;
- parse JSON response và toast danh sách `saved` thay vì bỏ response body;
- giữ nút disabled trong lúc request, tránh bấm lưu chồng;
- hiển thị lỗi validation chi tiết từ server.

Secret input trống nghĩa là giữ nguyên nên không được tính dirty chỉ vì form
render lại. Secret chỉ tính thay đổi khi user nhập hoặc bấm lệnh xóa riêng.

## 4. Setting còn thiếu / không nên lộ thô

### Đáng đưa lên UI

- `YOUTUBE_API_KEY`: hiện Trends bảo user sửa `.env` tay nhưng key chưa nằm trong
  `SECRET_ENV_KEYS`/tab. Đây là thiếu sót user-facing rõ nhất.
- `REVIEW_TRANSLATION`: advanced Dịch, vì ảnh hưởng chi phí/chất lượng mỗi job.
- `GLOSSARY_AUTO`: advanced Dịch, vì có thêm API work và thay đổi thuật ngữ.
- `WHISPER_LANGUAGE`: advanced Nhận dạng, mặc định Auto.
- `ELEVENLABS_MODEL`: đã được runtime dùng và server whitelist nhưng UI không có.
- `METADATA_MODEL`: advanced Xuất bản dưới nhãn chất lượng metadata/thumbnail.
- `OCR_MAX_MINUTES`: advanced policy cho auto OCR → Whisper, nếu user thường làm
  video dài có hardsub.
- `BATCH_LIMIT`: advanced Hệ thống như một safety cap.
- `YTDLP_COOKIES_FILE/BROWSER`: chỉ nên lộ trong advanced Tải nguồn với cảnh
  báo quyền riêng tư; hữu ích khi nguồn yêu cầu đăng nhập.

Global `FRAME`, `FRAME_COLOR*`, `FRAME_WIDTH`, `FRAME_PAD` đang được S8 dùng làm
fallback nhưng không có trong SAFE_ENV/UI. Vì tab global được định nghĩa là
chính sách kênh, nên hoặc expose “Khung mặc định” trong Xuất bản/Nâng cao bằng
control dùng chung với editor, hoặc bỏ đường config global này. Trạng thái nửa
lộ nửa ẩn hiện tại khó hiểu.

### Không nên đưa hai knob raw độc lập

`WHISPER_DEVICE` và `WHISPER_COMPUTE` có quan hệ ràng buộc. Phơi hai dropdown sẽ
tạo tổ hợp sai như CPU + float16 và pipeline chỉ âm thầm fallback CPU int8.

Nên có một control high-level:

- Auto (khuyên dùng);
- CPU tương thích (`cpu/int8`);
- NVIDIA GPU (`cuda/float16`);
- Tùy chỉnh chỉ trong expert mode nếu thật sự cần.

Runtime vẫn phải fallback và log cấu hình hiệu lực. `VIXTTS_DEVICE` không nên lộ
như knob thường: viXTTS CPU gần như không thực dụng, và biến này hiện còn được
demucs dùng chung dù tên chỉ viXTTS.

Các biến internal/tuning như `GENDER_DETECT`, `TRENDING_PER_KW`,
`TRENDING_YT_LIMIT`, `COVER_TOP` không nên đưa lên chỉ vì chúng tồn tại. Chỉ lộ
khi có workflow user rõ và validation đầy đủ.

## 5. Settings schema đề xuất

Mỗi setting nên có metadata tập trung:

```text
key, type, factory_default, allowed/range, secret, allow_empty,
category, advanced, profile_scope, restart_effect, dependencies
```

Server dùng schema để:

- tạo SAFE/SECRET allowlist;
- parse và validate `/api/config`;
- trả factory defaults + saved values + normalized effective values;
- reset/unset;
- validate profile import;
- tạo capability/dependency warnings.

Frontend vẫn sở hữu label/help tiếng Việt và layout nếu muốn, nhưng không tự
định nghĩa lại option/default kỹ thuật. Ít nhất server phải là nguồn sự thật cho
type/default/options để G8 và G11 đáng tin.

## 6. Thứ tự triển khai sau khi user chốt

1. Settings schema + dotenv serializer/validation + API unset.
2. Sửa G1–G6 và dependency engine; hoàn thiện G15 đang có.
3. Capability endpoint + G7/G10.
4. G8 diff/reset và G9 search.
5. G13/G14 tái bố cục.
6. Profile G11 sau khi schema ổn định.
7. Preview G12 cuối vì liên quan GPU, paid API và config draft.

Chốt: nên tinh gọn tab, nhưng giá trị lớn nhất không nằm ở việc giảm từ 9 card
xuống 7. Giá trị lớn nhất là biến cấu hình từ ba danh sách rời rạc thành một hệ
thống có default, validation, dependency, reset và profile nhất quán.
