// app-config.js — tab ⚙️ Cấu hình (đợt G, tách khỏi app-core.js).
// Nạp SAU app-core.js (dùng esc/toast/QUALITY_MODELS/applySyncPreset/VOICE_LIST),
// TRƯỚC app-visual.js (file đó gắn listener change/input trên #cfgform → markCfgDirty).
// Bố cục theo DEXUAT_CAUHINH_TAB_TONGHOP.md: card Trạng thái máy + tìm kiếm + profile
// trên đầu; nhóm theo pipeline; khóa/token dồn xuống cuối; mỗi nhóm có "Nâng cao".

let CFG = null;                 // /api/config gần nhất (values đã chuẩn hoá + pinned Set)
let CAPS = null;                // /api/capabilities gần nhất
let _cfgUnset = new Set();      // key chờ ↺ về mặc định (Lưu sẽ XOÁ khỏi .env)
let _cfgInitialWhisper = "auto"; // giá trị núm Whisper lúc nạp (pseudo, ghi 2 key)
let _cfgProfiles = [];

// ---- chuẩn hoá giá trị để SO SÁNH (bool "True"→"1", "-20.0"→"-20", màu về thường) ----
const _CFG_BOOLISH = ["DENOISE", "TTS_SINGLE_VOICE", "DIARIZE", "MASTER",
  "SUB_SPLIT", "PROSODY", "EMOTION", "PROSODY_TRANSFER", "REVIEW_TRANSLATION",
  "GLOSSARY_AUTO", "FRAME_PAD"];
const _CFG_INTISH = ["DUCK_GAIN_DB", "SHORTS_LEN", "GEMINI_MIN_INTERVAL"];
function _cfgNorm(k, v) {
  v = String(v ?? "").trim();
  if (k === "KEEP_BGM") return v === "flat" ? "flat" : (v === "1" || /^true$/i.test(v)) ? "1" : "0";
  if (_CFG_BOOLISH.includes(k)) return (v === "1" || /^true$/i.test(v)) ? "1" : "0";
  if (_CFG_INTISH.includes(k)) return String(parseInt(v || "0", 10) || 0);
  if (k === "FRAME_COLOR" || k === "FRAME_COLOR2") return v.toLowerCase();
  return v;
}

/* ---------- nạp + dựng form ---------- */
async function loadConfig(keepScroll) {
  const box = document.getElementById("cfgform");
  const scrollY = keepScroll ? window.scrollY : null;
  let c, caps;
  try {
    [c, caps] = await Promise.all([
      fetch("/api/config").then(r => r.json()),
      fetch("/api/capabilities").then(r => r.json()),
    ]);
  } catch (e) {
    box.innerHTML = '<div class="fhelp">Không tải được cấu hình — server còn chạy không?</div>';
    return;
  }
  try { _cfgProfiles = await (await fetch("/api/profiles")).json(); } catch (e) { _cfgProfiles = []; }
  let vv = { voices: [] };
  try { vv = await (await fetch("/api/voices")).json(); } catch (e) {}
  VOICE_LIST = vv.voices || [];

  // chuẩn hoá giá trị nạp về dạng canonical ("True"→"1", "-20.0"→"-20") để select
  // khớp option — .env cũ có thể còn kiểu bool/float của bản trước
  const V = c.values || {};
  for (const k of Object.keys(V)) V[k] = _cfgNorm(k, V[k]);
  CFG = { ...c, values: V, pinned: new Set(c.pinned || []) };
  CAPS = caps;
  _cfgUnset = new Set();

  // ---- helper dựng dòng (label + chấm khác-mặc-định + control + nút ↺) ----
  const hint = (h) => h ? ` <span class="finfo" tabindex="0">i<span class="ftip">${h}</span></span>` : "";
  const shell = (key, label, help, control, extra) =>
    `<div class="frow" data-key="${esc(key)}"><label>${esc(label)} <span class="cfgdot" id="dot-${key}" style="display:none"></span>${hint(help)}</label>${control}${extra || ""}<button class="ghost rstbtn" id="rst-${key}" type="button" style="display:none" onclick="cfgReset('${key}')">↺</button></div>`;
  const row = (key, label, options, labels, attrs, help, extra) => {
    const val = V[key] ?? "";
    const opts = options.includes(val) ? options : [val, ...options];
    const body = opts.map(o =>
      `<option value="${esc(o)}" ${o === val ? "selected" : ""}>${
        esc(labels && labels[o] != null ? labels[o] : o)}</option>`).join("");
    return shell(key, label, help, `<select id="cfg-${key}" ${attrs || ""}>${body}</select>`, extra);
  };
  const textrow = (key, label, ph, help, extra) =>
    shell(key, label, help,
      `<input id="cfg-${key}" type="text" value="${esc(V[key] ?? "")}" placeholder="${esc(ph || "")}"
        style="flex:1;min-width:180px;background:var(--bg2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font:inherit">`, extra);
  const colorrow = (key, label, help) =>
    shell(key, label, help, `<input id="cfg-${key}" type="color" value="${esc((V[key] || "#000000").toLowerCase())}" style="flex:0 0 64px;height:32px;padding:2px;background:var(--bg2);border:1px solid var(--border);border-radius:8px">`);
  const keyInput = (id, isSet, ph) =>
    `<input id="cfg-${id}" type="password" autocomplete="off"
      placeholder="${isSet ? '•••• đã đặt (để trống = giữ nguyên)' : esc(ph)}"
      style="flex:1;min-width:180px;background:var(--bg2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font:inherit">`;
  const keyrow = (id, label, isSet, ph, help) =>
    `<div class="frow" data-key="${esc(id)}"><label>${esc(label)}${hint((isSet ? "✓ Đã lưu. " : "Chưa lưu. ") + help)}</label>${keyInput(id, isSet, ph)}</div>`;
  const sec = (id, title, open, body) =>
    `<details class="cfgsec" id="sec-${id}" data-initopen="${open ? 1 : 0}"${open ? " open" : ""}><summary><h4>${title}</h4></summary>
     <div class="secbody">${body}</div></details>`;
  // khối "Nâng cao" trong nhóm — nhớ trạng thái mở theo máy (localStorage)
  const adv = (id, body) => {
    const open = localStorage.getItem("cfgadv:" + id) === "1";
    return `<details class="cfgadv" id="adv-${id}"${open ? " open" : ""} ontoggle="localStorage.setItem('cfgadv:${id}', this.open ? '1' : '0')"><summary>Nâng cao</summary><div class="advbody">${body}</div></details>`;
  };

  /* ---- ⭐ Dịch ---- */
  const qInit = _qualityFromModels(V.CLAUDE_MODEL, V.GEMINI_MODEL);
  const sDich =
    `<div class="frow" data-key="QUALITY"><label>⭐ Chất lượng dịch${hint("Núm gộp: đặt CẶP model Claude + Gemini theo mức chất lượng/chi phí (provider nào đang chọn thì model đó được dùng; provider kia là dự phòng). Chỉnh model lẻ ở Nâng cao → núm tự nhảy về «Tùy chỉnh».")}</label>
      <select id="cfg-QUALITY" onchange="cfgQualityChanged()">
        <option value="" ${qInit === "" ? "selected" : ""}>— Tùy chỉnh (theo 2 model ở Nâng cao) —</option>
        <option value="eco" ${qInit === "eco" ? "selected" : ""}>Tiết kiệm — Haiku + Flash-Lite</option>
        <option value="balanced" ${qInit === "balanced" ? "selected" : ""}>Cân bằng — Haiku + Flash</option>
        <option value="best" ${qInit === "best" ? "selected" : ""}>Cao nhất — Sonnet + Pro</option>
      </select></div>`
    + row("TRANSLATE_PROVIDER", "Nhà cung cấp dịch", ["claude", "gemini"],
      {claude: "Claude (Anthropic) — mặc định, ổn định", gemini: "Gemini (Google) — free tier rẻ"},
      'onchange="applyProviderUI()"',
      "LLM dùng để dịch/soát/trích tên riêng. <b>Claude</b> ổn định, có cache prompt. <b>Gemini</b> free tier gần như $0 nhưng giới hạn ~10 request/phút — <b>lỗi hoặc hết quota giữa chừng sẽ TỰ chuyển về Claude</b> nên job không chết.")
    + row("CONTENT_STYLE", "Kiểu nội dung", ["donghua", "general"],
      {donghua: "Donghua/cổ trang Trung — Hán-Việt, xưng hô cổ", general: "Chung — mọi thể loại/ngôn ngữ, dịch tự nhiên"},
      "", "Văn phong bản dịch. <b>Donghua</b>: tên riêng ép Hán-Việt (叶凡→Diệp Phàm), xưng hô cổ trang (ngươi/ta/tại hạ). <b>Chung</b>: xưng hô hiện đại, giữ tên gốc — chọn khi làm vlog/tài liệu/phim không phải cổ trang Trung.")
    + row("TARGET_LANG", "Ngôn ngữ lồng tiếng", ["vi", "en", "zh", "ja", "ko", "es", "fr", "id", "th", "pt"],
      {vi: "Tiếng Việt (mặc định)", en: "English", zh: "中文 — Tiếng Trung", ja: "日本語 — Tiếng Nhật",
       ko: "한국어 — Tiếng Hàn", es: "Español — Tây Ban Nha", fr: "Français — Pháp",
       id: "Bahasa Indonesia", th: "ไทย — Tiếng Thái", pt: "Português — Brazil"},
      "", "Ngôn ngữ ĐÍCH của bản dịch + giọng đọc + phụ đề + metadata. Khác Tiếng Việt: đọc bằng cặp giọng edge của ngôn ngữ đó; viXTTS/casting clone không áp dụng (ElevenLabs vẫn dùng được vì đa ngôn ngữ).")
    + textrow("TRANSLATE_STYLE_EXTRA", "Phong cách dịch riêng", "vd: giọng hài hước, dùng teencode",
      "«Gu» tùy biến: mô tả tự do được chèn vào prompt dịch + soát (cộng thêm với Kiểu nội dung). Để trống = theo Kiểu nội dung.")
    + adv("dich",
      row("CLAUDE_MODEL", "Model chính (Claude)", ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
        {"claude-haiku-4-5-20251001": "Haiku 4.5 — rẻ, nhanh", "claude-sonnet-4-6": "Sonnet 4.6 — dịch mượt hơn"},
        "", "Model Claude — dùng khi nhà cung cấp = Claude, và là model DỰ PHÒNG khi Gemini lỗi/hết quota (đúng model chọn ở đây, không tự đổi). <b>Haiku</b> ~$0.001/câu, đủ tốt; <b>Sonnet</b> mượt hơn với thoại dày/thuật ngữ, phí ~10 lần.")
      + row("GEMINI_MODEL", "Model Gemini",
        ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"],
        {"gemini-2.5-flash": "2.5 Flash — cân bằng (khuyên dùng)", "gemini-2.5-flash-lite": "2.5 Flash-Lite — nhanh/rẻ nhất",
         "gemini-2.5-pro": "2.5 Pro — mạnh nhất, quota chặt", "gemini-2.0-flash": "2.0 Flash — ổn định, quota rộng",
         "gemini-2.0-flash-lite": "2.0 Flash-Lite — nhẹ nhất"},
        "", "Model khi nhà cung cấp = Gemini. <b>2.5 Flash</b> cân bằng; <b>2.5 Pro</b> mượt nhất nhưng free tier siết chặt; <b>2.0</b> đời trước quota free rộng hơn.")
      + row("GEMINI_MIN_INTERVAL", "Giãn nhịp Gemini (giây)", ["0", "6", "7", "10"],
        {"0": "0 — không giãn (gặp 429 thì tự về Claude)", "6": "6 giây", "7": "7 giây (an toàn free tier)", "10": "10 giây"},
        "", "Chờ tối thiểu bấy nhiêu giây giữa 2 lần gọi Gemini để né trần ~10 req/phút của free tier. Trả phí thì để 0.")
      + row("REVIEW_TRANSLATION", "Soát lại bản dịch (lượt 2)", ["1", "0"],
        {"1": "Bật (mặc định) — dịch xong soát lại 1 lượt", "0": "Tắt — nhanh/rẻ hơn, chất lượng thô hơn"},
        "", "Sau khi dịch xong toàn bộ, chạy thêm 1 lượt soát: sửa câu ngây ngô, thống nhất xưng hô/tên riêng, kiểm tra ngân sách âm tiết. Tốn thêm ~30–50% phí dịch của job.")
      + row("GLOSSARY_AUTO", "Tự trích tên riêng", ["1", "0"],
        {"1": "Bật (mặc định) — Claude tự trích tên từ thoại", "0": "Tắt — chỉ dùng bảng tên bạn nhập"},
        "", "Claude tự trích tên nhân vật/địa danh/chiêu thức từ thoại và thêm vào glossary của job để dịch nhất quán các đoạn sau. Tắt nếu muốn kiểm soát bảng tên 100% thủ công."));

  /* ---- Nhận dạng thoại & người nói ---- */
  const gpuOk = caps && caps.gpu && caps.gpu.status === "available";
  const wInit = _whisperModeInit();
  _cfgInitialWhisper = wInit;
  const sTrans = row("TRANSCRIPT_SOURCE", "Nguồn transcript", ["auto", "ocr", "whisper"],
      {auto: "auto — tự chọn (khuyên dùng)", ocr: "ocr — đọc hardsub có sẵn", whisper: "whisper — nghe tiếng"},
      "", "Cách lấy lời thoại gốc. <b>auto</b>: video ngắn thử OCR đọc sub cứng trước (chính xác nhất với donghua), dài hơn hoặc không có sub cứng → Whisper nghe tiếng. Ép <b>ocr</b> khi chắc chắn video có hardsub; <b>whisper</b> khi video không có sub.")
    + row("OCR_CROP_TOP", "Vùng quét phụ đề", ["auto", "0.50", "0.60", "0.70", "0.80"],
      {auto: "auto — tự đo dải phụ đề (khuyên dùng)", "0.50": "Từ 50% xuống đáy (nửa dưới)",
       "0.60": "Từ 60% xuống đáy", "0.70": "Từ 70% xuống đáy", "0.80": "Từ 80% xuống đáy (chỉ đáy)"},
      "", "OCR chỉ quét dải này (theo chiều cao) để tìm phụ đề. <b>auto</b> tự đo vị trí sub từng video — QUAN TRỌNG với video DỌC (Douyin/Shorts) vì sub thường ở ~65% chứ không sát đáy, số cứng sẽ CẮT MẤT sub.")
    + adv("trans",
      row("WHISPER_MODEL", "Model Whisper", ["tiny", "base", "small", "medium", "large-v3"], null,
        "", "Model nghe tiếng khi không có hardsub — to hơn = chính xác hơn + chậm hơn. CPU: <b>small</b> là điểm cân bằng. Chạy GPU (núm bên dưới): <b>large-v3</b> chính xác nhất.")
      + `<div class="frow" data-key="WHISPER_MODE"><label>Thiết bị Whisper${hint("Núm gộp ghi 2 khóa WHISPER_DEVICE + WHISPER_COMPUTE. <b>Tự động</b> = xoá 2 khóa khỏi .env, chạy theo mặc định app (hiện CPU int8 — an toàn nhất). <b>GPU</b> cần card NVIDIA + CUDA của faster-whisper.")}</label>
        <select id="cfg-WHISPER_MODE">
          <option value="auto" ${wInit === "auto" ? "selected" : ""}>Tự động (mặc định app — CPU int8)</option>
          <option value="cpu" ${wInit === "cpu" ? "selected" : ""}>CPU (int8) — ổn định</option>
          <option value="gpu" ${wInit === "gpu" ? "selected" : ""} ${gpuOk ? "" : "disabled"}>GPU NVIDIA (float16) — nhanh hơn nhiều${gpuOk ? "" : " · máy không có GPU"}</option>
        </select></div>`
      + textrow("WHISPER_LANGUAGE", "Ngôn ngữ audio gốc", "vd zh, en, ja — trống = tự nhận diện",
        "Mã ngôn ngữ của TIẾNG NÓI trong video nguồn cho Whisper. Để trống = tự nhận diện (đúng đa số). Đặt cứng khi video hay bị nhận nhầm (nhạc nền lấn, nói lẫn 2 thứ tiếng).")
      + row("OCR_FPS", "Tốc độ OCR (frame/giây)", ["1.0", "1.5", "2.0"],
        {"1.0": "1 fps — nhanh gấp đôi", "1.5": "1.5 fps", "2.0": "2 fps — kỹ nhất"},
        "", "Số khung hình quét chữ mỗi giây. 2 fps bắt được cả sub hiện cực ngắn; 1 fps nhanh gấp đôi và vẫn đủ cho sub ≥2 giây.")
      + row("OCR_WORKERS", "Số worker OCR", ["auto", "2", "4", "6", "8"],
        {auto: "Tự động (≈ nửa số nhân CPU, tối đa 6)"},
        "", "Số tiến trình OCR chạy song song. <b>Tự động</b> lấy ≈ nửa số nhân CPU của máy — đổi máy không phải chỉnh lại. Tăng quá số nhân không nhanh thêm.")
      + row("OCR_MAX_MINUTES", "Trần OCR (phút)", ["10", "20", "30", "45", "60"], null,
        "", "Video dài hơn ngưỡng này thì chế độ auto bỏ OCR, đi thẳng Whisper (OCR video dài rất chậm). Ép nguồn = ocr thì vẫn OCR bất kể độ dài.")
      + row("DENOISE", "Khử ồn trước Whisper", ["0", "1"],
        {"0": "Tắt", "1": "Bật — lọc ồn cho ASR nghe rõ"},
        "", "Lọc ồn bản audio đưa vào Whisper (KHÔNG đụng audio của video final). Bật khi video nguồn ồn/nhạc to làm nghe sai lời.")
      + row("DIARIZE", "Nhận diện người nói", ["0", "1"],
        {"0": "Tắt", "1": "Bật — phân cụm giọng thật trong audio"},
        "", "Phân cụm NGƯỜI NÓI thật từ audio (pyannote): gán nhân vật nhất quán hơn, viXTTS tự chia mỗi người một giọng. Cần <b>pip install pyannote.audio</b> + HF token (nhóm Tích hợp) + đồng ý điều khoản 2 model pyannote trên huggingface.co. Khuyến nghị máy GPU.")
      + row("DIARIZE_MAX_SPK", "Số người nói tối đa", ["0", "2", "3", "4", "5", "6", "8"],
        {"0": "0 — tự đoán"},
        "", "Biết trước video có mấy người nói thì đặt đúng số — phân cụm chính xác hơn hẳn để máy tự đoán."));

  /* ---- Lồng tiếng & âm thanh ---- */
  const vopt = (sel) => `<option value="">(giọng mặc định model)</option>` + VOICE_LIST.map(x =>
    `<option value="${esc(x.file)}" ${x.file === sel ? "selected" : ""}>${esc(x.name)}</option>`).join("");
  const prevBtn = (id, which) =>
    `<button class="ghost" type="button" id="vprev-${id}" onclick="cfgVoicePreview('${which}', this)" title="Nghe thử giọng đang chọn (theo bản nháp, chưa cần Lưu)">🔊</button>`;
  const sTts = row("TTS_ENGINE", "Giọng đọc (engine)", ["edge", "vixtts", "elevenlabs", "vbee", "fpt"],
      {edge: "edge — miễn phí, online (Microsoft) · KHÔNG kiếm tiền được",
       vixtts: "vixtts — nhân bản giọng, GPU · KHÔNG kiếm tiền được",
       elevenlabs: "ElevenLabs — trả phí (~$22/th), giống người nhất ✓ kiếm tiền",
       vbee: "VBee — trả phí (VN), giọng đọc truyện chuẩn ✓ kiếm tiền",
       fpt: "FPT.AI — trả phí (VN), rẻ ✓ kiếm tiền"},
      'onchange="applyEngineUI()"',
      "Bộ máy đọc giọng. <b>edge/vixtts miễn phí nhưng license KHÔNG cho dùng trong video bật kiếm tiền</b>; 3 engine trả phí license thương mại rõ ràng. Câu đã cast giọng nhân vật (Series) luôn đọc bằng viXTTS clone bất kể engine.")
    + `<div id="engine-capwarn" class="fhelp" style="display:none"></div>`
    + row("TTS_SINGLE_VOICE", "Số giọng đọc", ["1", "0"],
      {"1": "1 giọng — cả video một giọng", "0": "2 giọng — nam & nữ riêng"},
      'onchange="applySingleVoiceUI()"',
      "<b>1 giọng</b>: mọi câu đọc cùng một giọng. <b>2 giọng</b>: câu nhân vật nam đọc giọng nam, nữ đọc giọng nữ (Claude + đo audio gán nhãn từng câu). Nhân vật đã cast trong Series vẫn giữ giọng riêng dù chọn kiểu nào.")
    + `<div id="edge-voices">`
    + row("TTS_VOICE", "Giọng nam (edge-tts)", ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"], null,
      "", "Giọng đọc các câu gắn nhãn NAM khi engine = edge. Chế độ 1 giọng thì đây là giọng cho cả video.", prevBtn("edge-nam", "nam"))
    + `<div class="nu-only">` + row("TTS_VOICE_NU", "Giọng nữ (edge-tts)", ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"], null,
      "", "Giọng đọc các câu gắn nhãn NỮ khi engine = edge.", prevBtn("edge-nu", "nu")) + `</div>`
    + `</div>`
    + `<div id="vixtts-voices">`
    + shell("VIXTTS_VOICE_NAM", "Giọng nam (viXTTS)",
      "Clip 6–10s trong voices/ để nhân bản giọng — nghe thử &amp; quản lý ở tab 🔊 Nghe thử. Câu nhãn NAM (và mọi câu khi 1 giọng) đọc bằng giọng này.",
      `<select id="cfg-VIXTTS_VOICE_NAM">${vopt(V.VIXTTS_VOICE_NAM || "")}</select>`, prevBtn("vix-nam", "nam"))
    + `<div class="nu-only">` + shell("VIXTTS_VOICE_NU", "Giọng nữ (viXTTS)", "",
      `<select id="cfg-VIXTTS_VOICE_NU">${vopt(V.VIXTTS_VOICE_NU || "")}</select>`, prevBtn("vix-nu", "nu")) + `</div>`
    + `<div class="fhelp">Thả clip 6–10 giây (.wav/.mp3) vào thư mục <code>voices/</code> làm giọng mẫu; nghe thử &amp; mở thư mục ở tab <b>🔊 Nghe thử</b>.</div>`
    + `</div>`
    + `<div id="elevenlabs-voices">
      <div class="fhelp">~$22/tháng, giống người nhất, đa ngôn ngữ. ${c.elevenlabs_key_set ? "✓ Đã có key." : "Chưa có key — nhập ở nhóm <b>Tích hợp &amp; khóa truy cập</b>."}</div>`
    + textrow("ELEVENLABS_VOICE_NAM", "Voice ID nam", "vd pNInz6obpgDQGcFmaJgB (Adam)",
      "Voice ID lấy ở elevenlabs.io → Voices. Chế độ 1 giọng dùng voice này cho cả video.")
    + `<div class="nu-only">` + textrow("ELEVENLABS_VOICE_NU", "Voice ID nữ", "vd 21m00Tcm4TlvDq8ikWAM (Rachel)",
      "Đổi voice id bất kỳ trong tài khoản của bạn.") + `</div>`
    + textrow("ELEVENLABS_MODEL", "Model ElevenLabs", "eleven_multilingual_v2",
      "Model tổng hợp giọng của ElevenLabs. <b>eleven_multilingual_v2</b> (mặc định) chất lượng cao; <b>eleven_turbo_v2_5</b> nhanh/rẻ hơn ~50%.")
    + `</div>`
    + `<div id="vbee-voices">
      <div class="fhelp">Dịch vụ VN chuyên giọng đọc truyện/thuyết minh (chỉ tiếng Việt). ${c.vbee_token_set ? "✓ Đã có token." : "Chưa có token — nhập ở nhóm <b>Tích hợp &amp; khóa truy cập</b>."}</div>`
    + textrow("VBEE_VOICE_NAM", "Voice code nam", "vd hn_male_manhdung_news_48k-fhg", "Mã giọng nam — xem danh sách trong tài liệu VBee. Chế độ 1 giọng dùng mã này cho cả video.")
    + `<div class="nu-only">` + textrow("VBEE_VOICE_NU", "Voice code nữ", "vd hn_female_ngochuyen_full_48k-fhg", "Mã giọng nữ VBee.") + `</div>`
    + `</div>`
    + `<div id="fpt-voices">
      <div class="fhelp">Rẻ nhất nhóm trả phí (chỉ tiếng Việt). ${c.fpt_key_set ? "✓ Đã có key." : "Chưa có key — nhập ở nhóm <b>Tích hợp &amp; khóa truy cập</b>."}</div>`
    + textrow("FPT_VOICE_NAM", "Giọng nam", "leminh | minhquang | thanhtung", "Các giọng nam FPT: leminh, minhquang, thanhtung.")
    + `<div class="nu-only">` + textrow("FPT_VOICE_NU", "Giọng nữ", "banmai | thuminh | myan | giahuy...", "Các giọng nữ FPT: banmai, thuminh, myan, ngoclam, lannhi...") + `</div>`
    + `</div>`
    + row("KEEP_BGM", "Giữ nhạc/SFX gốc", ["0", "flat", "1"],
      {"0": "Hạ audio gốc KHI CÓ thoại (duck)", flat: "Hạ audio gốc ĐỀU suốt video",
       "1": "Tách giọng gốc bằng demucs (GPU)"},
      "", "Cách xử lý audio gốc dưới giọng đọc. <b>Khi có thoại</b>: chỉ hạ lúc có lồng tiếng — nền to nhỏ theo thoại. <b>Đều suốt video</b>: âm gốc nhỏ ổn định, dễ nghe. <b>demucs</b>: tách hẳn giọng gốc khỏi nhạc/hiệu ứng (GPU, chậm thêm ~¼ thời lượng) — nền giữ trọn vẹn nhất.")
    + row("DUCK_GAIN_DB", "Âm nền gốc dưới thoại", ["-14", "-17", "-20", "-23", "-26"],
      {"-14": "-14dB — nền còn rõ (dễ át thoại)", "-17": "-17dB",
       "-20": "-20dB — thoại nổi rõ (khuyên dùng)", "-23": "-23dB", "-26": "-26dB — nền rất nhỏ"},
      "", "Hạ audio gốc (nhạc + giọng gốc) bao nhiêu khi có thoại. Đo thật: -14dB giọng chỉ nổi ~+6dB → bị át; -20dB nổi ~+12dB nghe rõ lời. Chỉnh riêng từng video: thanh 🎚 trong editor.")
    + row("TTS_BASE_SPEED", "🚀 Nhịp đọc nền", ["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"],
      {"1.0": "Mặc định (chậm rãi ~4 âm tiết/giây)", "1.1": "+10%", "1.2": "+20%",
       "1.3": "+30% — nhanh tự nhiên (khuyên dùng)", "1.4": "+40%", "1.5": "+50% — dồn dập"},
      "", "Nền tốc độ đọc cho MỌI câu — gu đọc của kênh (đợt T). Câu ngắn hết rề rà, nhịp đều giữa các câu; đo thật: mức +30% ≈ 4.9–5.2 âm tiết/giây (giọng review phim phổ biến ~5.4). KHÔNG tính vào ngân sách khớp thoại — câu vượt khung vẫn nén thêm trong trần rồi mới cắt. Hiện áp engine <b>edge</b>; viXTTS/trả phí theo sau. Đổi xong bấm 🔊 cạnh ô giọng để nghe nhịp mới; job đang có sẽ đọc lại các câu edge khi render lại.",
      `<button class="ghost" type="button" onclick="cfgVoicePreview('nam', this)" title="Nghe thử nhịp đang chọn (giọng chính, theo bản nháp)">🔊</button>`)
    + `<div class="frow"><label>Preset nhanh</label><span>
        <button class="ghost" type="button" onclick="cfgPreset('tight')" title="Nén khớp thoại tối đa 2.0× — bám khẩu hình sát nhất">🎯 Khớp môi chặt</button>
        <button class="ghost" type="button" onclick="cfgPreset('natural')" title="Nén khớp thoại tối đa 1.2× — ưu tiên nghe tự nhiên">🌿 Tự nhiên</button>
        <span class="meta">đặt sẵn núm trong Nâng cao — bấm xong nhớ Lưu</span></span></div>`
    + adv("tts",
      row("MAX_SPEEDUP", "Đồng bộ khớp thoại", ["1.0", "1.2", "1.4", "1.6", "1.8", "2.0"],
        {"1.0": "1.0× — KHÔNG tăng tốc (chấp nhận tràn)", "1.2": "1.2× — nhẹ nhàng",
         "1.4": "1.4× — cân bằng (khuyên dùng)", "1.6": "1.6×", "1.8": "1.8×", "2.0": "2.0× — khớp gắt"},
        "", "Trần NHÂN tổng của mọi lớp tăng tốc VÌ KHỚP THOẠI (engine đọc nhanh × atempo hậu kỳ ≤ mức này — không gồm 🚀 Nhịp đọc nền). Câu hết ngân sách mà vẫn dài thì fade + cắt ở biên slot, KHÔNG đè sang câu kế.")
      + row("PROSODY", "Tông giọng theo audio gốc", ["1", "0"],
        {"1": "Bật — đọc theo tông câu gốc", "0": "Tắt (mặc định) — giọng đọc trung tính"},
        "", "Đo cao độ / tốc độ / độ to từng câu GỐC so với mức nền của người nói → chỉnh giọng đọc theo (câu quát → đọc dồn cao giọng). Đo bảo thủ: mơ hồ (nhạc nền lấn) thì giữ trung tính. Mặc định TẮT — bật rồi chạy thử 1 job để nghe thẩm định.")
      + row("EMOTION", "Nhãn cảm xúc khi dịch", ["1", "0"],
        {"1": "Bật — gắn nhãn cảm xúc từng câu", "0": "Tắt (mặc định)"},
        "", "Claude gắn nhãn cảm xúc từng câu (gấp/giận/buồn/thì thầm) ngay khi dịch → giọng edge chỉnh nhịp/cao độ/âm lượng, viXTTS chọn clip mẫu hợp cảm xúc. Bắt được sắc thái audio không lộ (mỉa mai, đe dọa nói nhỏ...). Mặc định TẮT.")
      + row("PROSODY_TRANSFER", "Chuyển ngữ điệu gốc", ["0", "1"],
        {"0": "Tắt (mặc định — thử nghiệm)", "1": "Bật — ép dáng ngữ điệu gốc lên giọng đọc"},
        "", "Thử nghiệm: ép cả DÁNG đường lên-xuống giọng của câu gốc lên giọng đọc (Praat PSOLA). Bật rồi chạy thử 1 job để nghe thẩm định.")
      + textrow("FFMPEG_SHARED_BIN", "Thư mục ffmpeg shared (DLL)", "vd C:\\ffmpeg-shared\\...\\bin",
        "Đường dẫn thư mục <code>bin</code> của bản ffmpeg SHARED (có DLL) — cần cho torchcodec/viXTTS trên Windows. Máy không dùng viXTTS thì bỏ qua."));

  /* ---- Xuất bản / thương hiệu ---- */
  const noneL = {none: "— Không —"};
  const musicOpts = ["none", ...(c.music_files || [])];
  const logoOpts = ["none", ...(c.logo_files || [])];
  const clipOpts = ["none", ...(c.clip_files || [])];
  const frameLbls = {none: "Không khung", solid: "Viền đơn", double: "Viền đôi",
    twocolor: "Viền 2 màu", corner: "4 góc kiểu ngoặc"};
  const frameOpts = ["none", "solid", "double", "twocolor", "corner",
    ...(c.frame_files || []).map(n => "png:" + n)];
  (c.frame_files || []).forEach(n => { frameLbls["png:" + n] = "🖼 " + n; });
  const sBrand = row("SUBTITLE_MODE", "Phụ đề mặc định", ["soft", "cover_only", "burn", "none"],
      {soft: "soft — track bật/tắt (nhanh)", cover_only: "cover_only — chỉ che sub gốc, upload .srt riêng",
       burn: "burn — vẽ cứng vào hình", none: "none — không phụ đề"},
      "", "Cách gắn phụ đề khi render. <b>soft</b>: track bật/tắt được, render nhanh nhất. <b>cover_only</b>: chỉ che sub gốc, upload file .srt riêng lên YouTube. <b>burn</b>: vẽ cứng vào hình (re-encode, chậm). Bật che sub gốc / khung viền / logo sẽ tự ép burn.")
    + row("VOICE_FX", "Xử lý giọng (hậu kỳ)",
      ["off", "canbang", "amday", "rosang", "dienanh", "toithieu"],
      {off: "Tắt (giữ nguyên)", canbang: "Cân bằng", amday: "Ấm / dày",
       rosang: "Rõ / sáng", dienanh: "Điện ảnh", toithieu: "Tối thiểu"},
      "", "EQ + nén + chuẩn độ to cho giọng đọc, áp ngay khi render. <b>Cân bằng</b> là khởi đầu tốt; <b>Điện ảnh</b> dày và kịch tính. Bấm 🔊 nghe mẫu từng kiểu (cùng một câu, đúng chuỗi filter sẽ render).",
      `<button class="ghost" type="button" onclick="playFxSample()" title="Nghe mẫu kiểu đang chọn — cùng một câu thu sẵn, đúng chuỗi filter sẽ render">🔊</button>`)
    + row("MUSIC", "Nhạc nền (.mp3/.wav)", musicOpts, noneL,
      "", "Nhạc nền phủ toàn video, TỰ HẠ NHỎ khi có thoại. Thả file vào thư mục <code>music/</code> cạnh app. Nhớ dùng nhạc royalty-free.")
    + row("MUSIC_VOL", "Âm lượng nhạc", ["0.08", "0.12", "0.15", "0.20", "0.30"],
      {"0.08": "8%", "0.12": "12%", "0.15": "15% (khuyên dùng)", "0.20": "20%", "0.30": "30%"},
      "", "Âm lượng nhạc nền so với giọng đọc — 12–15% là mức nghe nền dễ chịu, trên 20% dễ lấn thoại.")
    + row("LOGO", "Logo watermark (.png)", logoOpts, noneL,
      "", "Logo kênh đóng ở góc video (PNG nền trong suốt, thả vào <code>logo/</code>). Bật logo sẽ ép render burn.")
    + row("MASTER", "Master độ to (LUFS)", ["1", "0"],
      {"1": "Bật — chuẩn -14 LUFS YouTube (khuyên dùng)", "0": "Tắt"},
      "", "Chuẩn hóa độ to CẢ video về -14 LUFS đúng chuẩn YouTube → các tập đều tiếng như nhau.")
    + row("SUBSCRIBE", "Nhắc Like/Đăng ký", ["off", "on"],
      {off: "Tắt", on: "Bật — banner vài giây đầu video"},
      "", "Hiện banner nhắc Like/Đăng ký trong ~6 giây đầu video (ép render burn).")
    + textrow("SUBSCRIBE_TEXT", "Chữ nhắc", "Nhớ Like & Đăng ký kênh nhé!", "Nội dung chữ trên banner.")
    + adv("brand",
      row("SUB_SPLIT", "Nhịp phụ đề", ["1", "0"],
        {"1": "Tách theo nhịp sub gốc", "0": "Hiện cả câu gộp"},
        "", "Câu bị GỘP từ nhiều dòng sub gốc được tách hiển thị lại đúng nhịp từng dòng như bản gốc.")
      + row("LOGO_POS", "Vị trí logo", ["tl", "tr", "bl", "br"],
        {tl: "Trên-trái", tr: "Trên-phải", bl: "Dưới-trái", br: "Dưới-phải"},
        "", "Góc đặt logo. Mẹo: video nguồn có watermark kênh gốc → che watermark trong editor rồi đặt logo mình đè đúng góc.")
      + row("LOGO_SCALE", "Cỡ logo", ["0.08", "0.12", "0.16", "0.20"],
        {"0.08": "Nhỏ (8%)", "0.12": "Vừa (12%)", "0.16": "Lớn (16%)", "0.20": "Rất lớn (20%)"},
        "", "Bề rộng logo theo % bề rộng video.")
      + row("LOGO_OPACITY", "Độ mờ logo", ["0.5", "0.7", "0.85", "1.0"],
        {"0.5": "50%", "0.7": "70%", "0.85": "85% (khuyên dùng)", "1.0": "100% (đặc)"},
        "", "85% đủ rõ nhận diện mà không che nội dung.")
      + row("INTRO", "Clip Intro (đầu video)", clipOpts, noneL,
        "", "Clip chào đầu video — tự ghép + khớp kích thước/fps. Thả vào <code>clips/</code>.")
      + row("OUTRO", "Clip Outro (cuối video)", clipOpts, noneL,
        "", "Clip kết video (kêu gọi đăng ký, giới thiệu tập sau...).")
      + row("FRAME", "Khung viền mặc định", frameOpts, frameLbls,
        "", "Khung viền đóng lên MỌI video render (không phải chỉnh tay từng job trong editor nữa). Kiểu vẽ (viền đơn/đôi/2 màu/4 góc) hoặc khung PNG trong thư mục <code>frames/</code>. Job chỉnh khung riêng trong editor 🎨 vẫn thắng giá trị này.")
      + colorrow("FRAME_COLOR", "Màu khung",
        "Màu viền chính của khung vẽ (không áp cho khung PNG).")
      + colorrow("FRAME_COLOR2", "Màu khung phụ",
        "Màu viền TRONG — chỉ dùng cho kiểu «Viền 2 màu».")
      + row("FRAME_WIDTH", "Độ dày khung", ["0.005", "0.01", "0.02", "0.03", "0.04", "0.06"],
        {"0.005": "Mảnh (0.5%)", "0.01": "1%", "0.02": "2% (mặc định)", "0.03": "3%", "0.04": "4%", "0.06": "Dày (6%)"},
        "", "Bề dày viền theo % chiều cao video.")
      + row("FRAME_PAD", "Khung ngoài video", ["0", "1"],
        {"0": "Khung đè lên mép video (mặc định)", "1": "Video thu nhỏ vào trong khung (không che hình)"},
        "", "<b>Đè lên mép</b>: giữ nguyên cỡ hình, viền che một dải mép. <b>Thu nhỏ vào trong</b>: video co lại để khung nằm NGOÀI hình — không mất nội dung, có lề.")
      + row("METADATA_MODEL", "Model viết metadata", ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        {"claude-sonnet-4-6": "Sonnet — tiêu đề/mô tả hay hơn (mặc định)", "claude-haiku-4-5-20251001": "Haiku — rẻ hơn"},
        "", "Model viết tiêu đề + mô tả + tag YouTube (1 lần gọi mỗi video — phí không đáng kể, nên để Sonnet)."));

  /* ---- Shorts ---- */
  const sShorts = row("SHORTS_COUNT", "Số short mỗi lần", ["1", "2", "3", "4", "5"], null,
      "", "Số clip Shorts cắt ra mỗi lần bấm 🎬 Tạo Shorts (menu 📤 của job đã render).")
    + row("SHORTS_LEN", "Độ dài mục tiêu", ["30", "45", "60"],
      {"30": "30 giây", "45": "45 giây (khuyên dùng)", "60": "60 giây (trần Shorts)"},
      "", "Độ dài mỗi short. Máy tự chọn đoạn CAO TRÀO: chấm điểm bằng nhãn cảm xúc + tông giọng + mật độ thoại.")
    + row("SHORTS_STYLE", "Khung hình", ["vertical", "original"],
      {vertical: "Dọc 9:16 — chuẩn Shorts (khuyên dùng)", original: "Giữ nguyên khung gốc"},
      "", "Dọc 9:16: video thu vào giữa, nền là chính nó phóng to làm mờ. Clip ra ở thư mục <code>shorts/</code> của job.");

  /* ---- Hệ thống & tự động hóa ---- */
  const sSys = row("AUTO_RETRY", "Tự chạy lại khi lỗi", ["0", "1", "2", "3"],
      {"0": "Tắt — lỗi thì dừng", "1": "1 lần (khuyên dùng)", "2": "2 lần", "3": "3 lần"},
      "", "Job lỗi tự xếp lại cuối hàng chạy tiếp từ checkpoint — cứu lỗi TẠM THỜI (mạng chập chờn, API quá tải). Lỗi cố định vẫn dừng hẳn.")
    + row("BATCH_LIMIT", "Trần video mỗi lần thêm", ["20", "50", "100"], null,
      "", "Dán link playlist/kênh thì lấy tối đa bấy nhiêu video một lần — chặn lỡ tay dán kênh 2000 video.")
    + adv("sys",
      `<div class="fhelp">⚠️ <b>Cookies = phiên đăng nhập của bạn.</b> Ai có file cookies là dùng được tài khoản trang video của bạn — chỉ trỏ tới file trên máy mình, KHÔNG chia sẻ/commit. App chỉ đọc khi tải video cần đăng nhập (giới hạn tuổi, membership).</div>`
      + textrow("YTDLP_COOKIES_FILE", "File cookies (yt-dlp)", "vd C:\\keys\\cookies.txt",
        "File cookies định dạng Netscape xuất từ tiện ích trình duyệt (Get cookies.txt). Dùng khi video đòi đăng nhập.")
      + row("YTDLP_COOKIES_BROWSER", "Lấy cookies từ trình duyệt", ["", "edge", "chrome", "firefox"],
        {"": "— Không —", edge: "Edge", chrome: "Chrome", firefox: "Firefox"},
        "", "yt-dlp đọc thẳng cookies từ trình duyệt đã đăng nhập trên máy này (--cookies-from-browser) — khỏi xuất file. Chọn MỘT trong hai cách (file hoặc trình duyệt)."));

  /* ---- Tích hợp & khóa truy cập ---- */
  const sub = (title, body) => `<div class="cfgsub"><h5>${title}</h5>${body}</div>`;
  const firstRun = !c.api_key_set && !c.gemini_key_set;
  const sKeys = `<div class="fhelp">Chỉ điền khóa của dịch vụ bạn dùng. Khóa lưu trong <code>.env</code>, KHÔNG hiện lại (đã đặt = ô ghi <b>••••</b>; để trống khi lưu = giữ khóa cũ).</div>`
    + sub("Dịch",
      keyrow("ANTHROPIC_API_KEY", "Claude API key", c.api_key_set, "sk-ant-… (console.anthropic.com)",
        "Bắt buộc để dịch bằng Claude, và cho dự phòng khi Gemini lỗi. Lấy ở console.anthropic.com → API Keys.")
      + keyrow("GEMINI_API_KEY", "Gemini API key", c.gemini_key_set, "lấy free ở aistudio.google.com/apikey",
        "Miễn phí ở Google AI Studio. Cần khi nhà cung cấp dịch = Gemini."))
    + sub("Lồng tiếng (engine trả phí)",
      keyrow("ELEVENLABS_API_KEY", "ElevenLabs API key", c.elevenlabs_key_set, "xi-api-key từ elevenlabs.io",
        "Cho engine đọc ElevenLabs (trả phí, giống người nhất).")
      + keyrow("VBEE_TOKEN", "VBee token", c.vbee_token_set, "Bearer token từ vbee.vn/console",
        "Cho engine đọc VBee (trả phí, tiếng Việt).")
      + textrow("VBEE_APP_ID", "VBee App ID", "app id trong console VBee",
        "Mã ứng dụng VBee — đi kèm token để xác thực.")
      + keyrow("FPT_TTS_API_KEY", "FPT.AI API key", c.fpt_key_set, "api-key từ fpt.ai (TTS)",
        "Cho engine đọc FPT.AI (trả phí, tiếng Việt, rẻ nhất)."))
    + sub("Thông báo",
      keyrow("TELEGRAM_BOT_TOKEN", "Telegram bot token", c.telegram_token_set, "token từ @BotFather",
        "Bot báo job xong/lỗi (kèm thông báo desktop 🔔). Tạo bot với @BotFather.")
      + textrow("TELEGRAM_CHAT_ID", "Telegram Chat ID", "vd 123456789",
        "ID cuộc trò chuyện nhận thông báo — nhắn bot 1 tin rồi mở api.telegram.org/bot&lt;token&gt;/getUpdates để thấy."))
    + sub("YouTube",
      keyrow("YOUTUBE_API_KEY", "YouTube Data API key", c.youtube_api_key_set, "AIza… (console.cloud.google.com)",
        "Cho nút 🔎 «Kiểm tra đã có bản Việt» và cột YouTube ở tab Phim hot. Bật YouTube Data API v3 trong Google Cloud rồi tạo API key.")
      + textrow("YOUTUBE_CLIENT_SECRETS", "File OAuth client (.json)", "vd D:\\keys\\client_secret.json",
        "Đường dẫn file OAuth client tạo ở Google Cloud (YouTube Data API v3) — để ĐĂNG video thẳng. "
        + (c.youtube_ready ? "✓ Sẵn sàng đăng thẳng." : "Chưa đủ điều kiện — vẫn dùng được 📦 Gói đăng kéo-thả."))
      + row("YOUTUBE_PRIVACY", "Quyền riêng tư khi đăng", ["private", "unlisted", "public"],
        {private: "Riêng tư (an toàn nhất)", unlisted: "Không công khai (ai có link)", public: "Công khai"},
        "", "Trạng thái video khi đăng thẳng bằng ▶ Đăng YouTube. Để <b>Riêng tư</b> rồi tự công khai sau khi duyệt."))
    + sub("Khác",
      keyrow("HF_TOKEN", "HuggingFace token", c.hf_token_set, "hf_… (huggingface.co/settings/tokens)",
        "Để tải model pyannote cho Nhận diện người nói (nhóm Nhận dạng thoại)."));

  /* ---- ráp trang ---- */
  const profOpts = _cfgProfiles.map(p =>
    `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  let html = `<h3 style="margin-bottom:2px">⚙️ Cấu hình <span class="meta" style="font-weight:400">(.env) — áp dụng cho job chạy mới; bấm tiêu đề nhóm để gập/mở</span></h3>`;
  html += `<div class="cfgtop">
    <input type="search" id="cfgsearch" placeholder="🔎 Tìm cấu hình… (vd: giọng, khung, cookies)" oninput="cfgSearch(this.value)">
    <span class="cfgprof">
      <select id="cfgprofile" title="Profile cấu hình đã lưu (bộ nội dung: dịch/giọng/khung...)"><option value="">— Profile —</option>${profOpts}</select>
      <button class="ghost" type="button" onclick="cfgProfileSave()" title="Chụp cấu hình hiện tại thành profile có tên">💾</button>
      <button class="ghost" type="button" onclick="cfgProfileApply()" title="Áp profile đang chọn (xem trước thay đổi)">▶</button>
      <button class="ghost" type="button" onclick="cfgProfileExport()" title="Xuất profile ra file JSON (mang sang máy khác)">⬇</button>
      <button class="ghost" type="button" onclick="document.getElementById('cfgimport').click()" title="Nhập profile từ file JSON">⬆</button>
      <button class="ghost" type="button" onclick="cfgProfileDelete()" title="Xóa profile đang chọn">🗑</button>
      <input type="file" id="cfgimport" accept=".json" style="display:none" onchange="cfgProfileImportFile(this)">
    </span></div>`;
  html += _capsCardHtml(caps);
  if (firstRun)
    html += `<div class="cfgbanner">🔑 <b>Chưa có khóa dịch.</b> Dán <b>Claude API key</b> hoặc <b>Gemini API key</b> (miễn phí ở aistudio.google.com) là chạy được job đầu tiên.
      <button class="ghost" type="button" onclick="cfgJumpToKey('ANTHROPIC_API_KEY')">→ Nhập key</button></div>`;
  html += `<div class="cfgcols">`;
  html += sec("dich", "⭐ Dịch &amp; nội dung", true, sDich);
  html += sec("trans", "Nhận dạng thoại &amp; người nói", true, sTrans);
  html += sec("tts", "Lồng tiếng &amp; âm thanh", true, sTts);
  html += sec("brand", "Xuất bản / thương hiệu", true, sBrand);
  html += sec("shorts", "Shorts tự động", false, sShorts);
  html += sec("sys", "Hệ thống &amp; tự động hóa", false, sSys);
  html += sec("keys", "🔑 Tích hợp &amp; khóa truy cập", firstRun, sKeys);
  html += `</div>`;
  html += `<div class="cfgfoot"><button id="cfgsavebtn" onclick="saveConfig()">💾 Lưu cấu hình</button>
    <span id="cfgdiff" class="meta"></span><span id="cfgmsg"></span>
    <button class="ghost" type="button" onclick="reloadConfig()" style="margin-left:auto">↻ Tải lại</button></div>`;
  box.innerHTML = html;

  applyEngineUI();
  applyProviderUI();
  applySingleVoiceUI();
  updateEngineWarn();
  updateCfgDiff();
  cfgDirty = false;   // vừa nạp từ .env = sạch
  if (scrollY != null) window.scrollTo(0, scrollY);
}

/* ---------- card Trạng thái máy (G7) ---------- */
function _capsCardHtml(caps) {
  if (!caps) return "";
  const chip = (ok, label, tip) =>
    `<span class="capchip ${ok === true ? "ok" : ok === false ? "bad" : "warn"}" title="${esc(tip || "")}">${label}</span>`;
  const g = caps.gpu || {};
  const ff = caps.ffmpeg || {};
  const pk = caps.packages || {};
  const vix = (caps.models || {}).vixtts || {};
  const chips = [
    g.status === "available"
      ? chip(true, `🎮 GPU: ${esc(g.name || "NVIDIA")} · ${esc(g.vram_total || "")}`, "Driver " + (g.driver || ""))
      : chip(false, "🎮 GPU: không có", "viXTTS/demucs/Whisper-GPU sẽ rất chậm hoặc không chạy"),
    ff.available
      ? chip(ff.h264_encoder && ff.h264_encoder.includes("nvenc"), `🎬 ffmpeg · ${esc(ff.h264_encoder || "?")}`,
          (ff.version || "") + (ff.h264_encoder && ff.h264_encoder.includes("nvenc") ? " — render bằng GPU" : " — render bằng CPU (chậm hơn)"))
      : chip(false, "🎬 ffmpeg: THIẾU", "Không render được — cài ffmpeg vào PATH"),
    chip(pk.faster_whisper === "installed", "🗣 whisper", pk.faster_whisper === "installed" ? "faster-whisper đã cài" : "pip install faster-whisper"),
    pk.vixtts_stack === "installed"
      ? chip(vix.status === "files_present", "🎙 viXTTS" + (vix.status === "files_present" ? "" : " (thiếu model)"),
          vix.status === "files_present" ? "Stack TTS + đủ file model" : "Thiếu file: " + (vix.missing || []).join(", "))
      : chip(false, "🎙 viXTTS: chưa cài", "Cần stack TTS (coqui) + GPU"),
    chip(pk.demucs === "installed", "🎵 demucs", pk.demucs === "installed" ? "Tách giọng gốc dùng được (Giữ nhạc/SFX = demucs)" : "pip install demucs — cần cho chế độ tách giọng gốc"),
    chip(pk.pyannote === "installed", "👥 pyannote", pk.pyannote === "installed" ? "Đã cài — còn cần HF token + accept model" : "pip install pyannote.audio — cho Nhận diện người nói"),
    chip(pk.rapidocr === "installed", "🔡 OCR", pk.rapidocr === "installed" ? "RapidOCR sẵn sàng (đọc hardsub)" : "pip install rapidocr-onnxruntime"),
    caps.disk_free_gb != null
      ? chip(caps.disk_free_gb >= 20, `💾 Trống ${caps.disk_free_gb} GB`, caps.disk_free_gb < 20 ? "Sắp đầy ổ — dọn tab Tổng quan" : "Ổ chứa data/jobs")
      : "",
  ].join("");
  return `<div class="capscard" id="capscard">${chips}
    <button class="ghost" type="button" onclick="cfgRefreshCaps()" title="Đo lại (GPU/ffmpeg/package/đĩa) — cache 60 giây">↻</button></div>`;
}
async function cfgRefreshCaps() {
  try { CAPS = await (await fetch("/api/capabilities?refresh=1")).json(); } catch (e) { return; }
  const el = document.getElementById("capscard");
  if (el) el.outerHTML = _capsCardHtml(CAPS);
  updateEngineWarn();
}

/* ---------- ⭐ Chất lượng dịch (G5 — setter 2 model, không phải khóa riêng) ---------- */
function _qualityFromModels(cm, gm) {
  for (const [tier, m] of Object.entries(QUALITY_MODELS))
    if (m.CLAUDE_MODEL === cm && m.GEMINI_MODEL === gm) return tier;
  return "";
}
function applyQualityUI() {
  const q = document.getElementById("cfg-QUALITY");
  const cm = document.getElementById("cfg-CLAUDE_MODEL"), gm = document.getElementById("cfg-GEMINI_MODEL");
  if (q && cm && gm) q.value = _qualityFromModels(cm.value, gm.value);
}
function cfgQualityChanged() {
  const t = document.getElementById("cfg-QUALITY").value;
  if (!t || !QUALITY_MODELS[t]) return;   // «Tùy chỉnh» — không đổi model
  const m = QUALITY_MODELS[t];
  const cm = document.getElementById("cfg-CLAUDE_MODEL"), gm = document.getElementById("cfg-GEMINI_MODEL");
  if (cm) cm.value = m.CLAUDE_MODEL;
  if (gm) gm.value = m.GEMINI_MODEL;
}

/* ---------- Whisper CPU/GPU (pseudo — ghi WHISPER_DEVICE + WHISPER_COMPUTE) ---------- */
function _whisperModeInit() {
  if (!CFG) return "auto";
  if ((CFG.values.WHISPER_DEVICE || "cpu") === "cuda") return "gpu";
  if (CFG.pinned.has("WHISPER_DEVICE") || CFG.pinned.has("WHISPER_COMPUTE")) return "cpu";
  return "auto";
}

/* ---------- nhãn động theo provider / engine / số giọng ---------- */
function _setRowLabel(key, txt) {
  const el = document.getElementById("cfg-" + key);
  const lab = el && el.closest(".frow") && el.closest(".frow").querySelector("label");
  if (!lab) return;
  if (lab.firstChild && lab.firstChild.nodeType === 3) lab.firstChild.nodeValue = txt + " ";
  else lab.insertBefore(document.createTextNode(txt + " "), lab.firstChild);
}
function applyProviderUI() {
  const sel = document.getElementById("cfg-TRANSLATE_PROVIDER");
  const gem = sel && sel.value === "gemini";
  _setRowLabel("CLAUDE_MODEL", gem ? "Model dự phòng (Claude)" : "Model chính (Claude)");
  _setRowLabel("GEMINI_MODEL", gem ? "Model chính (Gemini)" : "Model Gemini (chỉ dùng khi chọn Gemini)");
  const gi = document.getElementById("cfg-GEMINI_MIN_INTERVAL");
  const girow = gi && gi.closest(".frow");
  if (girow) girow.style.opacity = gem ? "" : ".55";
}
const MAIN_VOICE_LABELS = {
  TTS_VOICE:            ["Giọng (edge-tts)",  "Giọng nam (edge-tts)"],
  VIXTTS_VOICE_NAM:     ["Giọng (viXTTS)",    "Giọng nam (viXTTS)"],
  ELEVENLABS_VOICE_NAM: ["Voice ID",          "Voice ID nam"],
  VBEE_VOICE_NAM:       ["Voice code",        "Voice code nam"],
  FPT_VOICE_NAM:        ["Giọng",             "Giọng nam"],
};
function applySingleVoiceUI() {
  const sel = document.getElementById("cfg-TTS_SINGLE_VOICE");
  const single = !sel || sel.value === "1";
  document.querySelectorAll("#pane-cfg .nu-only").forEach(e => { e.style.display = single ? "none" : ""; });
  for (const [key, pair] of Object.entries(MAIN_VOICE_LABELS))
    _setRowLabel(key, single ? pair[0] : pair[1]);
}
function applyEngineUI() {
  const sel = document.getElementById("cfg-TTS_ENGINE");
  const eng = sel ? sel.value : "edge";
  for (const [id, match] of [["edge-voices", "edge"], ["vixtts-voices", "vixtts"],
      ["elevenlabs-voices", "elevenlabs"], ["vbee-voices", "vbee"], ["fpt-voices", "fpt"]]) {
    const el = document.getElementById(id);
    if (el) el.style.display = eng === match ? "" : "none";
  }
  applySingleVoiceUI();
  updateEngineWarn();
}

/* ---------- G10: cảnh báo engine thiếu điều kiện + nhảy tới ô key ---------- */
const _ENGINE_KEYS = { elevenlabs: ["ELEVENLABS_API_KEY"], vbee: ["VBEE_TOKEN", "VBEE_APP_ID"], fpt: ["FPT_TTS_API_KEY"] };
function _keyPresent(k) {
  const el = document.getElementById("cfg-" + k);
  if (el && el.value.trim()) return true;                       // đang gõ trong form
  if (el && el.type !== "password") return false;               // khóa thường: chỉ tính ô nhập
  return !!(CAPS && CAPS.keys && CAPS.keys[k.toLowerCase()]);   // secret đã lưu server-side
}
function updateEngineWarn() {
  const box = document.getElementById("engine-capwarn");
  if (!box || !CAPS) return;
  const eng = (document.getElementById("cfg-TTS_ENGINE") || {}).value || "edge";
  const cap = (CAPS.engines || {})[eng];
  if (!cap || cap.ready) { box.style.display = "none"; box.innerHTML = ""; return; }
  const keys = _ENGINE_KEYS[eng] || [];
  const typed = keys.length && keys.every(_keyPresent);
  box.style.display = "";
  box.innerHTML = typed
    ? `ℹ️ Key đã nhập trong form — bấm <b>💾 Lưu</b> là engine này sẵn sàng.`
    : `⚠️ ${esc(cap.reason || "Engine chưa sẵn sàng")}. Job chạy với engine thiếu điều kiện sẽ LỖI ở bước đọc giọng.`
      + (keys.length ? ` <button class="ghost" type="button" onclick="cfgJumpToKey('${keys[0]}')">→ Nhập key</button>` : "");
}
function cfgJumpToKey(key) {
  const rowEl = document.querySelector(`#cfgform .frow[data-key="${key}"]`);
  if (!rowEl) return;
  let p = rowEl.parentElement;
  while (p && p.id !== "cfgform") { if (p.tagName === "DETAILS") p.open = true; p = p.parentElement; }
  rowEl.scrollIntoView({behavior: "smooth", block: "center"});
  const inp = rowEl.querySelector("input,select");
  if (inp) { inp.focus({preventScroll: true}); }
  rowEl.classList.add("flash");
  setTimeout(() => rowEl.classList.remove("flash"), 2000);
}

/* ---------- G8/G15: diff với .env + factory, chấm, nút ↺, đếm thay đổi ---------- */
function collectCfgDraft() {
  const out = {};
  document.querySelectorAll('#cfgform [id^="cfg-"]').forEach(el => {
    const k = el.id.slice(4);
    if (k === "QUALITY" || k === "WHISPER_MODE") return;   // pseudo — xử lý riêng
    if (el.type === "password" || el.type === "file") return;
    out[k] = el.value;
  });
  return out;
}
function cfgReset(key) {
  if (!CFG) return;
  const el = document.getElementById("cfg-" + key);
  if (!el) return;
  const fac = (CFG.factory || {})[key] ?? "";
  el.value = el.type === "color" ? (fac || "#000000").toLowerCase() : fac;
  if (CFG.pinned.has(key)) _cfgUnset.add(key);
  markCfgDirty();
}
function updateCfgDiff() {
  if (!CFG || !document.getElementById("cfgform").innerHTML) return;
  const draft = collectCfgDraft();
  let changes = 0;
  for (const [k, val] of Object.entries(draft)) {
    const cur = _cfgNorm(k, val);
    const loaded = _cfgNorm(k, CFG.values[k] ?? "");
    const fac = _cfgNorm(k, (CFG.factory || {})[k] ?? "");
    const pinned = CFG.pinned.has(k);
    if (cur !== loaded) changes++;
    else if (_cfgUnset.has(k) && pinned) changes++;   // chỉ gỡ ghim (giá trị không đổi)
    // chấm + ↺ chỉ khi GIÁ TRỊ khác mặc định gốc. Key ghim trong .env nhưng bằng
    // factory (di sản saveConfig cũ ghi cả 60 key) thì im lặng — 55 chấm là nhiễu.
    const show = cur !== fac;
    const dot = document.getElementById("dot-" + k);
    if (dot) {
      dot.style.display = show ? "" : "none";
      dot.title = `Khác mặc định gốc (${(CFG.factory || {})[k] || "(trống)"})${pinned ? " — đang ghim trong .env" : " — Lưu sẽ ghim vào .env"}`;
    }
    const rst = document.getElementById("rst-" + k);
    if (rst) {
      rst.style.display = show ? "" : "none";
      rst.title = `↺ Về mặc định gốc: ${(CFG.factory || {})[k] || "(trống)"} (Lưu sẽ xoá khóa khỏi .env)`;
    }
  }
  document.querySelectorAll('#cfgform input[type="password"][id^="cfg-"]').forEach(el => {
    if (el.value.trim()) changes++;
  });
  const wm = document.getElementById("cfg-WHISPER_MODE");
  if (wm && wm.value !== _cfgInitialWhisper) changes++;
  cfgDirty = changes > 0;
  const d = document.getElementById("cfgdiff");
  if (d) d.textContent = changes ? `● ${changes} thay đổi chưa lưu` : "";
  const b = document.getElementById("cfgsavebtn");
  if (b && !b.disabled) b.textContent = changes ? `💾 Lưu (${changes})` : "💾 Lưu cấu hình";
}
// markCfgDirty (app-core) gọi hook này — gom nhiều event input liên tiếp thành 1 lần
// quét. setTimeout chứ KHÔNG requestAnimationFrame: tab nền bị trình duyệt ngừng vẽ
// thì rAF không bao giờ chạy → đếm diff đứng im.
let _cfgDiffQueued = false;
function scheduleCfgDiff() {
  if (_cfgDiffQueued || !CFG) return;
  _cfgDiffQueued = true;
  setTimeout(() => {
    _cfgDiffQueued = false;
    try { applyQualityUI(); updateEngineWarn(); updateCfgDiff(); } catch (e) {}
  }, 60);
}

/* ---------- lưu ---------- */
async function saveConfig() {
  if (!CFG) return false;
  const draft = collectCfgDraft();
  const body = {};
  const unset = new Set();
  for (const k of _cfgUnset) {   // ↺ rồi lại đổi sang giá trị khác → thành update thường
    if (_cfgNorm(k, draft[k] ?? "") === _cfgNorm(k, (CFG.factory || {})[k] ?? "")) unset.add(k);
  }
  for (const [k, val] of Object.entries(draft)) {
    if (unset.has(k)) continue;
    if (_cfgNorm(k, val) !== _cfgNorm(k, CFG.values[k] ?? "")) body[k] = String(val).trim();
  }
  document.querySelectorAll('#cfgform input[type="password"][id^="cfg-"]').forEach(el => {
    const v = el.value.trim();
    if (v) body[el.id.slice(4)] = v;
  });
  const wm = document.getElementById("cfg-WHISPER_MODE");
  if (wm && wm.value !== _cfgInitialWhisper) {
    if (wm.value === "auto") { unset.add("WHISPER_DEVICE"); unset.add("WHISPER_COMPUTE"); delete body.WHISPER_DEVICE; delete body.WHISPER_COMPUTE; }
    else if (wm.value === "gpu") { body.WHISPER_DEVICE = "cuda"; body.WHISPER_COMPUTE = "float16"; }
    else { body.WHISPER_DEVICE = "cpu"; body.WHISPER_COMPUTE = "int8"; }
  }
  if (!Object.keys(body).length && !unset.size) {
    cfgDirty = false;
    updateCfgDiff();
    toast("Không có thay đổi nào để lưu");
    return true;
  }
  if (unset.size) body._unset = [...unset];
  const btn = document.getElementById("cfgsavebtn");
  if (btn) { btn.disabled = true; btn.textContent = "Đang lưu…"; }
  let ok = false, err = "";
  try {
    const res = await fetch("/api/config", { method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
    ok = res.ok;
    if (ok) {
      const r = await res.json();
      const n = (r.saved || []).length + (r.unset || []).length;
      toast(`✅ Đã lưu ${n} thay đổi — job mới sẽ dùng cấu hình này`);
    } else {
      try { err = (await res.json()).detail || ""; } catch (e) {}
    }
  } catch (e) { err = "server không phản hồi"; }
  if (btn) { btn.disabled = false; btn.textContent = "💾 Lưu cấu hình"; }
  if (ok) {
    cfgDirty = false;
    await loadConfig(true);   // nạp lại: pinned/dot/chỗ hiển thị "đã đặt" cập nhật đúng
  } else {
    const msg = document.getElementById("cfgmsg");
    if (msg) {
      msg.textContent = "Lỗi khi lưu" + (err ? ": " + err : " (server còn chạy không?)");
      msg.style.color = "var(--err)";
      setTimeout(() => { msg.textContent = ""; msg.style.color = ""; }, 8000);
    }
  }
  return ok;
}
function reloadConfig() {
  if (cfgDirty && !confirm("Bỏ thay đổi cấu hình chưa lưu và tải lại?")) return;
  cfgDirty = false;
  loadConfig();
}
// G15: đóng/refresh cả TRANG khi còn thay đổi chưa lưu → trình duyệt hỏi lại
window.addEventListener("beforeunload", (e) => {
  if (cfgDirty) { e.preventDefault(); e.returnValue = ""; }
});

/* ---------- G9: tìm kiếm cấu hình ---------- */
function cfgSearch(q) {
  q = (q || "").trim().toLowerCase();
  const secs = document.querySelectorAll("#cfgform details.cfgsec");
  if (!q) {
    document.querySelectorAll("#cfgform .frow").forEach(r => { r.style.display = ""; });
    secs.forEach(s => { s.style.display = ""; s.open = s.dataset.initopen === "1"; });
    document.querySelectorAll("#cfgform details.cfgadv").forEach(d => {
      d.open = localStorage.getItem("cfgadv:" + d.id.slice(4)) === "1";
    });
    applyEngineUI();   // khôi phục ẩn/hiện block engine + nu-only sau khi bung tất cả
    return;
  }
  // row nằm trong block đang ẩn (bộ giọng engine KHÁC, ô nữ khi 1 giọng) thì coi
  // như không khớp — kẻo "section bung ra mà chẳng thấy dòng nào" (review F5)
  const blocked = (r) => {
    for (let p = r.parentElement; p && !p.classList.contains("secbody"); p = p.parentElement)
      if (p.style && p.style.display === "none") return true;
    return false;
  };
  secs.forEach(s => {
    let any = false;
    s.querySelectorAll(".frow").forEach(r => {
      const hit = !blocked(r) && (r.textContent.toLowerCase().includes(q)
        || (r.dataset.key || "").toLowerCase().includes(q));
      r.style.display = hit ? "" : "none";
      if (hit) any = true;
    });
    s.style.display = any ? "" : "none";
    if (any) {
      s.open = true;
      s.querySelectorAll("details.cfgadv").forEach(d => {
        if ([...d.querySelectorAll(".frow")].some(r => r.style.display !== "none")) d.open = true;
      });
    }
  });
}

/* ---------- G11: profile cấu hình ---------- */
async function _cfgReloadProfiles(selectId) {
  try { _cfgProfiles = await (await fetch("/api/profiles")).json(); } catch (e) { return; }
  const sel = document.getElementById("cfgprofile");
  if (!sel) return;
  sel.innerHTML = `<option value="">— Profile —</option>` + _cfgProfiles.map(p =>
    `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  if (selectId) sel.value = selectId;
}
async function cfgProfileSave() {
  if (cfgDirty && !confirm("Bạn còn thay đổi CHƯA LƯU — profile chụp theo bản ĐÃ LƯU trong .env. Tiếp tục?")) return;
  const name = prompt("Tên profile (chụp cấu hình nội dung hiện tại — không gồm khóa API/cài đặt máy):");
  if (!name || !name.trim()) return;
  try {
    const res = await fetch("/api/profiles", { method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({name: name.trim()}) });
    if (!res.ok) { toast("Lỗi lưu profile", "err"); return; }
    const r = await res.json();
    toast(`✅ Đã lưu profile «${r.name}»`);
    await _cfgReloadProfiles(r.id);
  } catch (e) { toast("Lỗi lưu profile: " + e, "err"); }
}
async function _cfgGetSelectedProfile() {
  const sel = document.getElementById("cfgprofile");
  if (!sel || !sel.value) { toast("Chọn một profile trước đã"); return null; }
  try {
    const res = await fetch("/api/profiles/" + sel.value);
    if (!res.ok) { toast("Không tải được profile", "err"); return null; }
    return await res.json();
  } catch (e) { return null; }
}
async function cfgProfileApply() {
  const p = await _cfgGetSelectedProfile();
  if (!p || !CFG) return;
  // chỉ xét khóa còn tồn tại trong schema hiện tại (profile cũ có thể chứa khóa đã bỏ)
  const diff = Object.entries(p.values || {}).filter(([k, v]) =>
    (k in (CFG.factory || {})) && _cfgNorm(k, v) !== _cfgNorm(k, CFG.values[k] ?? ""));
  if (!diff.length) { toast("Profile giống hệt cấu hình hiện tại — không có gì để áp"); return; }
  const lines = diff.slice(0, 15).map(([k, v]) => `• ${k}: ${CFG.values[k] || "(mặc định)"} → ${v || "(trống)"}`);
  if (diff.length > 15) lines.push(`… và ${diff.length - 15} thay đổi nữa`);
  if (!confirm(`Áp profile «${p.name}» — đổi ${diff.length} cấu hình:\n\n${lines.join("\n")}\n\nÁp dụng cho job chạy mới. Tiếp tục?`)) return;
  try {
    // gửi giá trị ĐÃ chuẩn hoá — profile chụp từ .env di sản có thể chứa
    // "True"/"-20.0", validate options phía server sẽ 400 nếu gửi thô
    const res = await fetch("/api/config", { method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.fromEntries(diff.map(([k, v]) => [k, _cfgNorm(k, v)]))) });
    if (!res.ok) { toast("Lỗi áp profile", "err"); return; }
    toast(`✅ Đã áp profile «${p.name}» (${diff.length} thay đổi)`);
    await loadConfig(true);
  } catch (e) { toast("Lỗi áp profile: " + e, "err"); }
}
async function cfgProfileExport() {
  const p = await _cfgGetSelectedProfile();
  if (!p) return;
  const blob = new Blob([JSON.stringify(p, null, 2)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = (p.name || "profile").replace(/[^\w\-. ]+/g, "_") + ".flowapp-profile.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
async function cfgProfileImportFile(input) {
  const f = input.files && input.files[0];
  input.value = "";
  if (!f) return;
  let data;
  try { data = JSON.parse(await f.text()); }
  catch (e) { toast("File không phải JSON hợp lệ", "err"); return; }
  const values = data.values || data;   // nhận cả file export lẫn JSON {KEY: value} trần
  if (typeof values !== "object" || Array.isArray(values)) { toast("File không đúng định dạng profile", "err"); return; }
  const name = String(data.name || f.name.replace(/\.[^.]*$/, "")).slice(0, 80);
  try {
    const res = await fetch("/api/profiles", { method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, values}) });
    if (!res.ok) {
      let d = ""; try { d = (await res.json()).detail || ""; } catch (e) {}
      toast("Lỗi nhập profile" + (d ? ": " + d : ""), "err");
      return;
    }
    const r = await res.json();
    toast(`✅ Đã nhập profile «${r.name}»` + (r.skipped && r.skipped.length ? ` — bỏ qua ${r.skipped.length} khóa lạ/không hợp lệ` : ""));
    await _cfgReloadProfiles(r.id);
  } catch (e) { toast("Lỗi nhập profile: " + e, "err"); }
}
async function cfgProfileDelete() {
  const sel = document.getElementById("cfgprofile");
  if (!sel || !sel.value) { toast("Chọn một profile trước đã"); return; }
  const name = sel.options[sel.selectedIndex].textContent;
  if (!confirm(`Xóa profile «${name}»? (không đụng cấu hình đang dùng)`)) return;
  try {
    const res = await fetch("/api/profiles/" + sel.value, { method: "DELETE" });
    if (res.ok) { toast(`🧹 Đã xóa profile «${name}»`); await _cfgReloadProfiles(""); }
  } catch (e) {}
}

/* ---------- G12: nghe mẫu VOICE_FX + nghe thử giọng theo bản nháp ---------- */
let _cfgAudio = null;
function _cfgPlayBlobUrl(url) {
  if (_cfgAudio) { _cfgAudio.pause(); _cfgAudio = null; }
  _cfgAudio = new Audio(url);
  _cfgAudio.play().catch(() => toast("Không phát được âm thanh", "err"));
}
function playFxSample() {
  const v = (document.getElementById("cfg-VOICE_FX") || {}).value || "off";
  if (_cfgAudio) { _cfgAudio.pause(); _cfgAudio = null; }
  _cfgAudio = new Audio("/api/fx-sample/" + encodeURIComponent(v));
  _cfgAudio.play().catch(() => toast("Chưa có file mẫu cho kiểu này"));
}
async function cfgVoicePreview(which, btn) {
  const draft = collectCfgDraft();
  const st = {};
  for (const k of ["TTS_ENGINE", "TTS_SINGLE_VOICE", "TARGET_LANG",
                   "TTS_VOICE", "TTS_VOICE_NU", "VIXTTS_VOICE_NAM", "VIXTTS_VOICE_NU",
                   "TTS_BASE_SPEED"])
    if (draft[k] != null) st[k] = draft[k];
  const eng = st.TTS_ENGINE || "edge";
  if (["elevenlabs", "vbee", "fpt"].includes(eng)
      && !confirm(`Nghe thử bằng ${eng} sẽ gọi API TRẢ PHÍ (~1 câu). Tiếp tục?`)) return;
  const old = btn ? btn.textContent : "";
  if (btn) { btn.disabled = true; btn.textContent = "…"; }
  try {
    const res = await fetch("/api/tts-preview", { method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text: "Xin chào, đây là giọng đọc thử của FlowApp.",
                            voice: which, settings: st}) });
    if (!res.ok) {
      let d = ""; try { d = (await res.json()).detail || ""; } catch (e) {}
      toast("Nghe thử lỗi" + (d ? ": " + d : ""), "err");
      return;
    }
    _cfgPlayBlobUrl(URL.createObjectURL(await res.blob()));
  } catch (e) { toast("Nghe thử lỗi: " + e, "err"); }
  finally { if (btn) { btn.disabled = false; btn.textContent = old || "🔊"; } }
}
