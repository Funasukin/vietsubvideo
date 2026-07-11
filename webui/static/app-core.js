// #17 tách monolith — NỘI DUNG: helpers chung (esc/toast/fmt), tab, form thêm job/upload, danh sách job, thanh tiến độ, Tổng quan/stats, Cấu hình (loadConfig/saveConfig/preset).
// đúng thứ tự cũ (classic script — cùng global scope, hành vi không đổi).
const STAGES = [
  ["downloading",  "Tải video"],
  ["extracting",   "Tách audio"],
  ["transcribing", "Transcript (OCR/Whisper)"],
  ["translating",  "Dịch tiếng Việt"],
  ["tts",          "Đọc giọng (TTS 2 giọng)"],
  ["bgm",          "Xử lý nhạc nền"],
  ["mixing",       "Mix audio"],
  ["rendering",    "Render video"],
  ["metadata",     "Metadata"],
];
const FONTS = ["Arial", "Tahoma", "Verdana", "Segoe UI", "Calibri", "Times New Roman"];
let FONT_LIST = FONTS.map(n => ({ name: n, file: null }));  // nạp lại từ /api/fonts
const CFG_FIELDS = [
  ["CLAUDE_MODEL", "Model dịch", ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]],
  ["TRANSLATE_PROVIDER", "Nhà cung cấp dịch", ["claude", "gemini"]],
  ["GEMINI_MODEL", "Model Gemini", ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"]],
  ["GEMINI_MIN_INTERVAL", "Giãn nhịp Gemini (giây)", ["0", "6", "7", "10"]],
  ["TRANSLATE_STYLE_EXTRA", "Phong cách dịch riêng", []],
  ["MAX_SPEEDUP", "Đồng bộ khớp thoại (tăng tốc tối đa)", ["1.0", "1.2", "1.4", "1.6", "1.8", "2.0"]],
  ["STRETCH_SHORT", "Kéo giãn câu đọc xong sớm", ["0", "1"]],
  ["DUCK_GAIN_DB", "Âm nền gốc dưới thoại", ["-14", "-17", "-20", "-23", "-26"]],
  ["CONTENT_STYLE", "Kiểu nội dung", ["donghua", "general"]],
  ["TARGET_LANG", "Ngôn ngữ lồng tiếng", ["vi", "en", "zh", "ja", "ko", "es", "fr", "id", "th", "pt"]],
  ["TTS_ENGINE", "Giọng đọc (engine)", ["edge", "vixtts", "elevenlabs", "vbee", "fpt"]],
  ["TTS_SINGLE_VOICE", "Số giọng đọc", ["1", "0"]],
  ["ELEVENLABS_VOICE_NAM", "Voice ID nam ElevenLabs", []],
  ["ELEVENLABS_VOICE_NU", "Voice ID nữ ElevenLabs", []],
  ["VBEE_APP_ID", "VBee App ID", []],
  ["VBEE_VOICE_NAM", "Voice code nam VBee", []],
  ["VBEE_VOICE_NU", "Voice code nữ VBee", []],
  ["FPT_VOICE_NAM", "Giọng nam FPT", []],
  ["FPT_VOICE_NU", "Giọng nữ FPT", []],
  ["KEEP_BGM", "Giữ nhạc/SFX gốc", ["0", "flat", "1"]],
  ["VOICE_FX", "Xử lý giọng", ["off", "canbang", "amday", "rosang", "dienanh", "toithieu"]],
  ["PROSODY", "Tông giọng theo audio gốc", ["1", "0"]],
  ["EMOTION", "Nhãn cảm xúc khi dịch", ["1", "0"]],
  ["PROSODY_TRANSFER", "Chuyển ngữ điệu gốc", ["0", "1"]],
  ["TTS_VOICE", "Giọng nam (mặc định)", ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"]],
  ["TTS_VOICE_NU", "Giọng nữ", ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]],
  ["WHISPER_MODEL", "Model whisper", ["tiny", "base", "small", "medium", "large-v3"]],
  ["TRANSCRIPT_SOURCE", "Nguồn transcript", ["auto", "ocr", "whisper"]],
  ["SUBTITLE_MODE", "Phụ đề mặc định", ["soft", "cover_only", "burn", "none"]],
  ["SUB_SPLIT", "Nhịp phụ đề", ["1", "0"]],
  ["OCR_WORKERS", "Số worker OCR", ["2", "4", "6", "8"]],
  ["OCR_FPS", "Tốc độ OCR", ["1.0", "1.5", "2.0"]],
  ["OCR_CROP_TOP", "Vùng quét phụ đề", ["auto", "0.50", "0.60", "0.70", "0.80"]],
  ["AUTO_RETRY", "Tự chạy lại khi lỗi", ["0", "1", "2", "3"]],
  ["DIARIZE", "Nhận diện người nói", ["0", "1"]],
  ["DIARIZE_MAX_SPK", "Số người nói tối đa", ["0", "2", "3", "4", "5", "6", "8"]],
  ["MUSIC", "Nhạc nền", []], ["MUSIC_VOL", "Âm lượng nhạc", []],
  ["LOGO", "Logo", []], ["LOGO_POS", "Vị trí logo", []],
  ["LOGO_SCALE", "Cỡ logo", []], ["LOGO_OPACITY", "Độ mờ logo", []],
  ["INTRO", "Intro", []], ["OUTRO", "Outro", []], ["MASTER", "Master độ to", []],
  ["SHORTS_COUNT", "Số short mỗi lần", ["1", "2", "3", "4", "5"]],
  ["SHORTS_LEN", "Độ dài Shorts", ["30", "45", "60"]],
  ["SHORTS_STYLE", "Khung hình Shorts", ["vertical", "original"]],
  ["DENOISE", "Khử ồn trước Whisper", ["0", "1"]],
  ["SUBSCRIBE", "Nhắc Like/Đăng ký", ["off", "on"]],
  ["SUBSCRIBE_TEXT", "Chữ nhắc", []],
  ["TELEGRAM_CHAT_ID", "Telegram Chat ID", []],
  ["YOUTUBE_CLIENT_SECRETS", "YouTube OAuth client (.json)", []],
  ["YOUTUBE_PRIVACY", "Quyền riêng tư khi đăng", ["private", "unlisted", "public"]],
];
// Tùy chọn "Xử lý giọng" (hậu kỳ) — dùng chung cho dropdown trong editor
const FX_OPTS = [["off", "Tắt (giữ nguyên)"], ["canbang", "Cân bằng"], ["amday", "Ấm / dày"],
  ["rosang", "Rõ / sáng"], ["dienanh", "Điện ảnh"], ["toithieu", "Tối thiểu"]];
function fxOptionsHtml(sel) {
  return FX_OPTS.map(([v, l]) => `<option value="${v}" ${sel === v ? "selected" : ""}>${l}</option>`).join("");
}
let lastJson = {};

// Chống XSS: mọi chuỗi từ YouTube (tiêu đề/kênh) hay Claude đều phải escape
// trước khi nhét vào innerHTML — uploader có thể đặt tên video chứa HTML/script.
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

// Toast góc phải dưới thay alert() (không chặn màn hình, tự tắt sau 6s, bấm để đóng).
// Màu tự nhận diện theo nội dung: ✅/Đã... = xanh, Lỗi/Không... = đỏ, còn lại trung tính.
function toast(msg, kind) {
  msg = String(msg ?? "");
  if (!kind) {
    if (/^(✅|✓|🧹|📦|🎬|đã |Đã )/u.test(msg)) kind = "ok";
    else if (/lỗi|không |chưa |bị chặn|thiếu|error|fail/iu.test(msg)) kind = "err";
    else kind = "";
  }
  const box = document.getElementById("toasts");
  if (!box) return;
  const t = document.createElement("div");
  t.className = "toast" + (kind ? " " + kind : "");
  t.textContent = msg;
  t.onclick = () => t.remove();
  box.appendChild(t);
  while (box.children.length > 5) box.firstChild.remove();   // đừng chất đống
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, 6000);
}
function safeUrl(u) {
  try {
    const p = new URL(u);
    return (p.protocol === "http:" || p.protocol === "https:") ? u : "#";
  } catch { return "#"; }
}

/* ---------- Font tùy biến ---------- */
function cssEsc(s) {
  // bo ky tu dieu khien (U+0000..U+001F) lam vo @font-face; escape quote va backslash
  var t = "";
  for (var i = 0; i < s.length; i++) {
    if (s.charCodeAt(i) >= 32) t += s[i];
  }
  return t.replace(/["\\]/g, "\\$&");
}

async function loadFonts() {
  try {
    const r = await (await fetch("/api/fonts")).json();
    if (r.fonts && r.fonts.length) FONT_LIST = r.fonts;
  } catch (e) { return; }
  // @font-face cho font tùy biến — trình duyệt chỉ tải khi preview thật sự dùng
  const css = FONT_LIST.filter(f => f.file).map(f =>
    `@font-face{font-family:"${cssEsc(f.name)}";`
    + `src:url("/api/fonts/file/${encodeURIComponent(f.file)}");font-display:swap;}`
  ).join("\n");
  let st = document.getElementById("customfonts");
  if (!st) { st = document.createElement("style"); st.id = "customfonts"; document.head.appendChild(st); }
  st.textContent = css;
}

function fontOptions(sel) {
  return FONT_LIST.map(f =>
    `<option ${f.name === sel ? "selected" : ""}>${esc(f.name)}</option>`).join("");
}

function updateFontPreview(id) {
  const fp = document.getElementById("fp-" + id);
  if (!fp) return;
  fp.style.fontFamily = '"' + document.getElementById("ft-" + id).value + '"';
  const c = document.getElementById("fc-" + id);
  if (c) fp.style.color = c.value;
}

/* ---------- Glossary (bảng tên riêng) ---------- */
async function loadGlossDefault() {
  try {
    const r = await (await fetch("/api/glossary-default")).json();
    const el = document.getElementById("gloss");
    if (el && r.glossary && !el.value) el.value = r.glossary;
  } catch (e) {}
}
async function saveGlossDefault() {
  const g = document.getElementById("gloss").value;
  const msg = document.getElementById("glossmsg");
  try {
    const r = await fetch("/api/glossary-default", { method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({glossary: g}) });
    msg.textContent = r.ok ? "✓ Đã lưu mặc định" : "Lỗi lưu";
  } catch (e) { msg.textContent = "Lỗi: " + e; }
  setTimeout(() => { msg.textContent = ""; }, 4000);
}

let cfgDirty = false;
let _pendingTab = null;
function markCfgDirty() { cfgDirty = true; }
// V12/U5: MỘT nguồn mapping preset khớp thoại — tab Cấu hình (cfg-*) và panel ⚙️
// per-job (ov-*) cùng dùng, khỏi lệch nhau về sau (điểm Codex).
const SYNC_PRESETS = {
  tight: { MAX_SPEEDUP: "2.0", STRETCH_SHORT: "1" },
  natural: { MAX_SPEEDUP: "1.2", STRETCH_SHORT: "0" },
};
function applySyncPreset(kind, prefix) {
  const p = SYNC_PRESETS[kind] || {};
  for (const [k, v] of Object.entries(p)) {
    const el = document.getElementById(prefix + k);
    if (el) el.value = v;
  }
  toast(kind === "tight" ? "Preset: khớp môi chặt (2.0× + kéo giãn câu ngắn)"
                         : "Preset: tự nhiên (1.2×, không kéo giãn)");
}
function cfgPreset(kind) { applySyncPreset(kind, "cfg-"); markCfgDirty(); }
function edOvPreset(kind) { applySyncPreset(kind, "ov-"); applyOvDeps(); }
// U10 mở rộng: 1 núm "Chất lượng dịch" per-job thay 2 danh sách model — map model
// theo CẢ 2 provider (provider nào hiệu lực thì model đó được dùng; Gemini fallback
// Claude cũng ăn đúng model Claude tương ứng).
const QUALITY_MODELS = {
  eco: { CLAUDE_MODEL: "claude-haiku-4-5-20251001", GEMINI_MODEL: "gemini-2.5-flash-lite" },
  balanced: { CLAUDE_MODEL: "claude-haiku-4-5-20251001", GEMINI_MODEL: "gemini-2.5-flash" },
  best: { CLAUDE_MODEL: "claude-sonnet-4-6", GEMINI_MODEL: "gemini-2.5-pro" },
};
function qualityFromOv(ov) {   // suy ngược giá trị núm từ override đang lưu (job cũ)
  const c = ov.CLAUDE_MODEL || "", g = ov.GEMINI_MODEL || "";
  if (!c && !g) return "";
  if (c.includes("sonnet") || g.includes("pro")) return "best";
  if (g.includes("lite")) return "eco";
  return "balanced";
}

function showTab(name) {
  // Rời tab Cấu hình khi còn thay đổi chưa lưu → nhắc bằng popup trước khi chuyển.
  const leavingCfg = document.getElementById("tab-cfg").classList.contains("active") && name !== "cfg";
  if (leavingCfg && cfgDirty) {
    _pendingTab = name;
    document.getElementById("cfg-modal").style.display = "flex";
    return;
  }
  _doShowTab(name);
}

function _doShowTab(name) {
  const pe = document.getElementById("pane-edit");
  if (pe && pe.style.display !== "none") {  // đang mở editor → đóng sạch
    _teardownEditorMedia();
    pe.style.display = "none"; pe.innerHTML = "";
    // xoá luôn state editor: tránh refresh() tự mở lại editor (render-watch) khi đã sang tab khác
    edJobId = null; edSegs = []; edDirty = new Set(); edRenderWatch = null;
  }
  const pve = document.getElementById("pane-visual-edit");
  if (pve && pve.style.display !== "none") {   // đang mở editor "Chỉnh giao diện" → đóng sạch
    _teardownVisualMedia();
    pve.style.display = "none"; pve.innerHTML = "";
    visJobId = null; visRenderWatch = null;
  }
  for (const t of ["over", "jobs", "visual", "cfg", "trend", "series", "preview"]) {
    document.getElementById("pane-" + t).style.display = t === name ? "" : "none";
    document.getElementById("tab-" + t).classList.toggle("active", t === name);
  }
  if (name === "over") refreshStats();
  if (name === "cfg") loadConfig();
  if (name === "trend") renderTrending();
  if (name === "series") loadSeriesTab();
  if (name === "preview") loadPreviewTab();
  if (name === "visual") loadVisualTab();
}

function _leavePendingTab() {
  document.getElementById("cfg-modal").style.display = "none";
  const t = _pendingTab; _pendingTab = null;
  if (t) _doShowTab(t);
}
async function cfgModalSave() {
  const ok = await saveConfig();   // saveConfig đặt cfgDirty=false khi lưu thành công
  if (!ok) {  // lưu lỗi → đóng popup, ở lại tab Cấu hình để xem báo lỗi
    document.getElementById("cfg-modal").style.display = "none";
    _pendingTab = null;
    return;
  }
  _leavePendingTab();
}
function cfgModalDiscard() { cfgDirty = false; _leavePendingTab(); }
function cfgModalCancel() {
  _pendingTab = null;
  document.getElementById("cfg-modal").style.display = "none";
}

/* ---------- Tổng quan ---------- */
async function refreshStats() {
  if (document.getElementById("pane-over").style.display === "none") return;
  let s;
  try { s = await (await fetch("/api/stats")).json(); } catch (e) { return; }
  const lowDisk = s.disk_free_gb < 20;
  const cards = [
    [s.jobs_total, "Tổng job"],
    [s.jobs_done, "Hoàn thành"],
    [s.jobs_failed, "Lỗi"],
    [s.jobs_active, "Đang chạy / chờ"],
    [s.video_minutes + "′", "Phút video đã xử lý"],
    [s.segments_translated.toLocaleString(), "Câu đã dịch"],
    ["$" + s.est_cost_usd, "Chi phí dịch (ước tính)"],
    [s.jobs_size_gb + " GB", "Dung lượng data/jobs"],
    [s.disk_free_gb + " GB", "Ổ đĩa còn trống", lowDisk],
  ];
  document.getElementById("stats").innerHTML = cards.map(([n, l, warn]) =>
    `<div class="stat${warn ? " warn" : ""}"><div class="num">${n}</div><div class="lbl">${l}</div></div>`
  ).join("");
}

/* ---------- Cấu hình ---------- */
async function loadConfig() {
  const c = await (await fetch("/api/config")).json();
  const V = c.values || {};
  // KEEP_BGM về từ config có thể là "False"/"True" (bool) — chuẩn hoá về "0"/"1"
  // để khớp option, khỏi lòi thêm dòng "False" vào dropdown.
  V.KEEP_BGM = V.KEEP_BGM === "flat" ? "flat"
    : (V.KEEP_BGM === "1" || /^true$/i.test(V.KEEP_BGM || "")) ? "1" : "0";
  V.DENOISE = (V.DENOISE === "1" || /^true$/i.test(V.DENOISE || "")) ? "1" : "0";
  V.TTS_SINGLE_VOICE = (V.TTS_SINGLE_VOICE === "1" || /^true$/i.test(V.TTS_SINGLE_VOICE || "")) ? "1" : "0";
  V.STRETCH_SHORT = (V.STRETCH_SHORT === "1" || /^true$/i.test(V.STRETCH_SHORT || "")) ? "1" : "0";
  V.DUCK_GAIN_DB = String(parseInt(V.DUCK_GAIN_DB || "-20", 10) || -20);   // "-20.0" → "-20"
  V.SHORTS_LEN = String(parseInt(V.SHORTS_LEN || "45", 10) || 45);   // "45.0" → "45"
  V.GEMINI_MIN_INTERVAL = String(parseInt(V.GEMINI_MIN_INTERVAL || "0", 10) || 0);   // "0.0" → "0"
  let v = { voices: [], nam: "", nu: "" };
  try { v = await (await fetch("/api/voices")).json(); } catch (e) {}
  VOICE_LIST = v.voices || [];
  const eng = V.TTS_ENGINE || "edge";

  // ⓘ nhỏ cạnh nhãn: mô tả chi tiết nằm trong tooltip (hover/focus mới hiện) — đỡ rối mắt
  const hint = (h) => h ? ` <span class="finfo" tabindex="0">i<span class="ftip">${h}</span></span>` : "";
  // dựng 1 dòng select; labels map giá trị -> chữ dễ hiểu; help = tooltip ⓘ cạnh nhãn
  const row = (key, label, options, labels, attrs, help) => {
    const val = V[key] || "";
    const opts = options.includes(val) ? options : [val, ...options];
    const body = opts.map(o =>
      `<option value="${esc(o)}" ${o === val ? "selected" : ""}>${
        esc(labels && labels[o] != null ? labels[o] : o)}</option>`).join("");
    return `<div class="frow"><label>${esc(label)}${hint(help)}</label>
      <select id="cfg-${key}" ${attrs || ""}>${body}</select></div>`;
  };
  // ô nhập chữ tự do (khác select) — dùng cho chữ nhắc / chat id / đường dẫn file
  const textrow = (key, label, ph, help) =>
    `<div class="frow"><label>${esc(label)}${hint(help)}</label>
      <input id="cfg-${key}" type="text" value="${esc(V[key] || "")}" placeholder="${esc(ph || "")}"
        style="flex:1;min-width:180px;background:var(--bg2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font:inherit"></div>`;
  // 1 nhóm cấu hình = 1 card gập/mở được (bố cục 2 cột kiểu masonry)
  const sec = (title, open, body) =>
    `<details class="cfgsec"${open ? " open" : ""}><summary><h4>${title}</h4></summary>
     <div class="secbody">${body}</div></details>`;

  // ---- Từng nhóm là 1 card (sec) — bố cục 2 cột, mỗi dòng có help mô tả chi tiết ----

  const sDich = row("TRANSLATE_PROVIDER", "Nhà cung cấp dịch", ["claude", "gemini"],
      {claude: "Claude (Anthropic) — mặc định, ổn định", gemini: "Gemini (Google) — free tier rẻ"},
      'onchange="applyProviderUI()"',
      "LLM dùng để dịch/soát/trích tên riêng. <b>Claude</b> ổn định, có bộ nhớ cache prompt. <b>Gemini</b> free tier gần như $0 nhưng giới hạn ~10 request/phút — <b>lỗi hoặc hết quota giữa chừng sẽ TỰ chuyển về Claude</b> nên job không chết. Giữ nhãn giọng/cảm xúc/nhân vật y như nhau (dùng structured output cả hai).")
    + `<div id="gemini-cfg">`
    + `<div class="fhelp">API key Gemini nhập ở nhóm <b>🔑 Khóa API &amp; Token</b>. ${c.gemini_key_set ? "✓ Đã có key." : "Chưa có key — chọn Gemini mà thiếu key sẽ tự về Claude."}</div>`
    + row("GEMINI_MODEL", "Model Gemini",
      ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"],
      {"gemini-2.5-flash": "2.5 Flash — cân bằng (khuyên dùng)", "gemini-2.5-flash-lite": "2.5 Flash-Lite — nhanh/rẻ nhất",
       "gemini-2.5-pro": "2.5 Pro — mạnh nhất, quota chặt", "gemini-2.0-flash": "2.0 Flash — ổn định, quota rộng",
       "gemini-2.0-flash-lite": "2.0 Flash-Lite — nhẹ nhất"},
      "", "<b>2.5 Flash</b> cân bằng chất lượng/tốc độ (khuyên dùng). <b>2.5 Flash-Lite</b> rẻ nhất. <b>2.5 Pro</b> dịch mượt nhất nhưng free tier siết chặt. <b>2.0 Flash / Flash-Lite</b> đời trước, quota free rộng hơn — chọn khi hay đụng giới hạn 2.5.")
    + row("GEMINI_MIN_INTERVAL", "Giãn nhịp Gemini (giây)", ["0", "6", "7", "10"],
      {"0": "0 — không giãn (gặp 429 thì tự về Claude)", "6": "6 giây", "7": "7 giây (an toàn free tier)", "10": "10 giây"},
      "", "Chờ tối thiểu bấy nhiêu giây giữa 2 lần gọi Gemini để né trần ~10 req/phút của free tier. Trả phí thì để 0.")
    + `</div>`
    + `<div id="claude-cfg">`
    + row("CLAUDE_MODEL", "Model Claude", ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
      {"claude-haiku-4-5-20251001": "Haiku 4.5 — rẻ, nhanh", "claude-sonnet-4-6": "Sonnet 4.6 — dịch mượt hơn"},
      "", "Model Claude khi nhà cung cấp = Claude. <b>Haiku</b> rẻ (~$0.001/câu), đủ tốt; <b>Sonnet</b> mượt hơn với thoại dày/thuật ngữ, phí ~10 lần. (Khi chọn Gemini, dòng này ẩn đi — lúc Gemini lỗi vẫn tự về Claude Haiku dịch tiếp.)")
    + `</div>`
    + textrow("TRANSLATE_STYLE_EXTRA", "Phong cách dịch riêng", "vd: giọng hài hước, dùng teencode",
      "«Gem» tùy biến: mô tả tự do được chèn vào prompt dịch + soát (cộng thêm với Kiểu nội dung). Để trống = theo Kiểu nội dung bên dưới.")
    + row("CONTENT_STYLE", "Kiểu nội dung", ["donghua", "general"],
      {donghua: "Donghua/cổ trang Trung — Hán-Việt, xưng hô cổ", general: "Chung — mọi thể loại/ngôn ngữ, dịch tự nhiên"},
      "", "Văn phong bản dịch. <b>Donghua</b>: tên riêng ép Hán-Việt (叶凡→Diệp Phàm), xưng hô cổ trang (ngươi/ta/tại hạ). <b>Chung</b>: xưng hô hiện đại, giữ tên gốc — chọn khi làm vlog/tài liệu/phim không phải cổ trang Trung.")
    + row("TARGET_LANG", "Ngôn ngữ lồng tiếng", ["vi", "en", "zh", "ja", "ko", "es", "fr", "id", "th", "pt"],
      {vi: "Tiếng Việt (mặc định)", en: "English", zh: "中文 — Tiếng Trung", ja: "日本語 — Tiếng Nhật",
       ko: "한국어 — Tiếng Hàn", es: "Español — Tây Ban Nha", fr: "Français — Pháp",
       id: "Bahasa Indonesia", th: "ไทย — Tiếng Thái", pt: "Português — Brazil"},
      "", "Ngôn ngữ ĐÍCH của bản dịch + giọng đọc + phụ đề + metadata. Khác Tiếng Việt: đọc bằng cặp giọng edge của ngôn ngữ đó; viXTTS/casting clone không áp dụng (ElevenLabs thì vẫn dùng được vì đa ngôn ngữ).")
    + row("SUBTITLE_MODE", "Phụ đề mặc định", ["soft", "cover_only", "burn", "none"],
      {soft: "soft — track bật/tắt (nhanh)", cover_only: "cover_only — chỉ che sub gốc, upload .srt riêng",
       burn: "burn — vẽ cứng vào hình", none: "none — không phụ đề"},
      "", "Cách gắn phụ đề khi render. <b>soft</b>: track bật/tắt được, render nhanh nhất (không re-encode). <b>cover_only</b>: chỉ che sub gốc, KHÔNG in sub Việt — dành cho kiểu upload file .srt riêng lên YouTube để người xem tự bật. <b>burn</b>: vẽ cứng vào hình (re-encode, chậm, không tắt được). Lưu ý: bật che sub gốc / khung viền / logo sẽ tự ép burn.")
    + row("SUB_SPLIT", "Nhịp phụ đề", ["1", "0"],
      {"1": "Tách theo nhịp sub gốc", "0": "Hiện cả câu gộp"},
      "", "Câu bị GỘP từ nhiều dòng sub gốc (cho giọng đọc liền mạch) được tách hiển thị lại đúng nhịp từng dòng như bản gốc. Tắt nếu muốn phụ đề khớp 1:1 với câu giọng đọc (block dài hơn).");

  const sTrans = row("TRANSCRIPT_SOURCE", "Nguồn transcript", ["auto", "ocr", "whisper"],
      {auto: "auto — tự chọn (khuyên dùng)", ocr: "ocr — đọc hardsub có sẵn", whisper: "whisper — nghe tiếng"},
      "", "Cách lấy lời thoại gốc. <b>auto</b>: video ≤20 phút thử OCR đọc sub cứng trước (chính xác nhất với donghua), dài hơn hoặc không có sub cứng → Whisper nghe tiếng. Ép <b>ocr</b> khi chắc chắn video có hardsub; <b>whisper</b> khi video không có sub.")
    + row("WHISPER_MODEL", "Model whisper", ["tiny", "base", "small", "medium", "large-v3"], null,
      "", "Model nghe tiếng khi không có hardsub, to hơn = chính xác hơn + chậm hơn. Máy CPU: <b>small</b> là điểm cân bằng. Máy GPU (đặt WHISPER_DEVICE=cuda trong .env): <b>large-v3</b> chính xác nhất, ~8× realtime trên RTX 3070.")
    + row("OCR_WORKERS", "Số worker OCR", ["2", "4", "6", "8"], null,
      "", "Số tiến trình OCR chạy song song — đặt xấp xỉ số nhân CPU (6 hợp máy 8 nhân). Tăng quá số nhân không nhanh thêm.")
    + row("OCR_FPS", "Tốc độ OCR (frame/giây)", ["1.0", "1.5", "2.0"],
      {"1.0": "1 fps — nhanh gấp đôi", "1.5": "1.5 fps", "2.0": "2 fps — kỹ nhất"},
      "", "Số khung hình quét chữ mỗi giây. 2 fps bắt được cả sub hiện cực ngắn; 1 fps nhanh gấp đôi và vẫn đủ cho sub ≥2 giây (đa số phim). Video dài OCR chậm → giảm xuống 1.")
    + row("OCR_CROP_TOP", "Vùng quét phụ đề", ["auto", "0.50", "0.60", "0.70", "0.80"],
      {auto: "auto — tự đo dải phụ đề (khuyên dùng)", "0.50": "Từ 50% xuống đáy (nửa dưới)",
       "0.60": "Từ 60% xuống đáy", "0.70": "Từ 70% xuống đáy", "0.80": "Từ 80% xuống đáy (chỉ đáy)"},
      "", "OCR chỉ quét dải này (theo chiều cao) để tìm phụ đề. <b>auto</b> tự đo vị trí sub cho từng video — QUAN TRỌNG với video DỌC (Douyin/Shorts) vì sub thường ở ~65% chứ không sát đáy, số cứng sẽ CẮT MẤT sub. Đặt số nhỏ = quét cao hơn (bắt sub ở giữa) nhưng chậm hơn; số lớn = chỉ quét đáy, nhanh, hợp phim ngang 16:9.")
    + row("AUTO_RETRY", "Tự chạy lại khi lỗi", ["0", "1", "2", "3"],
      {"0": "Tắt — lỗi thì dừng", "1": "1 lần (khuyên dùng)", "2": "2 lần", "3": "3 lần"},
      "", "Job lỗi tự xếp lại cuối hàng chạy tiếp từ checkpoint — cứu được lỗi TẠM THỜI (mạng chập chờn, API quá tải). Lỗi cố định (video hỏng, hết quota) vẫn sẽ lỗi lại rồi dừng hẳn.");

  const sDiar = row("DIARIZE", "Nhận diện người nói", ["0", "1"],
      {"0": "Tắt", "1": "Bật — phân cụm giọng thật trong audio"},
      "", "Phân cụm NGƯỜI NÓI thật từ audio (pyannote): Claude gán nhân vật nhất quán hơn, engine viXTTS tự chia mỗi người một giọng riêng (sửa được trong speakers.json của job). Cần: <b>pip install pyannote.audio</b> + HF token + bấm đồng ý điều khoản 2 model <b>pyannote/segmentation-3.0</b> và <b>speaker-diarization-3.1</b> trên huggingface.co. Khuyến nghị máy GPU.")
    + row("DIARIZE_MAX_SPK", "Số người nói tối đa", ["0", "2", "3", "4", "5", "6", "8"],
      {"0": "0 — tự đoán"},
      "", "Biết trước video có mấy người nói thì đặt đúng số đó — phân cụm chính xác hơn hẳn để máy tự đoán.")
    + `<div class="fhelp">HuggingFace token nhập ở nhóm <b>🔑 Khóa API &amp; Token</b>. ${c.hf_token_set ? "✓ Đã có token." : "Chưa lưu token — diarization sẽ không chạy được."}</div>`;

  // Bộ giọng edge (chỉ hiện khi engine = edge)
  const vopt = (sel) => `<option value="">(giọng mặc định model)</option>` + VOICE_LIST.map(x =>
    `<option value="${esc(x.file)}" ${x.file === sel ? "selected" : ""}>${esc(x.name)}</option>`).join("");
  const keyInput = (id, isSet, ph) =>
    `<input id="cfg-${id}" type="password" autocomplete="off"
      placeholder="${isSet ? '•••• đã đặt (để trống = giữ nguyên)' : esc(ph)}"
      style="flex:1;min-width:180px;background:var(--bg2);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font:inherit">`;

  const sTts = row("TTS_ENGINE", "Giọng đọc (engine)", ["edge", "vixtts", "elevenlabs", "vbee", "fpt"],
      {edge: "edge — miễn phí, online (Microsoft) · KHÔNG kiếm tiền được",
       vixtts: "vixtts — nhân bản giọng, GPU · KHÔNG kiếm tiền được",
       elevenlabs: "ElevenLabs — trả phí (~$22/th), giống người nhất ✓ kiếm tiền",
       vbee: "VBee — trả phí (VN), giọng đọc truyện chuẩn ✓ kiếm tiền",
       fpt: "FPT.AI — trả phí (VN), rẻ ✓ kiếm tiền"},
      'onchange="applyEngineUI()"',
      "Bộ máy đọc giọng. <b>edge/vixtts miễn phí nhưng license KHÔNG cho dùng trong video bật kiếm tiền</b>; 3 engine trả phí license thương mại rõ ràng — chọn engine nào thì khối cấu hình key của nó hiện bên dưới. Câu đã cast giọng nhân vật (Series) luôn đọc bằng viXTTS clone bất kể engine.")
    + row("TTS_SINGLE_VOICE", "Số giọng đọc", ["1", "0"],
      {"1": "1 giọng — cả video một giọng", "0": "2 giọng — nam & nữ riêng"},
      'onchange="applySingleVoiceUI()"',
      "<b>1 giọng</b>: bỏ phân biệt nam/nữ, mọi câu đọc cùng một giọng (bên dưới chỉ cần chọn 1 giọng). <b>2 giọng</b>: câu của nhân vật nam đọc giọng nam, nữ đọc giọng nữ (Claude + đo audio tự gán nhãn nam/nữ từng câu). Nhân vật đã cast riêng trong Series vẫn giữ giọng của mình dù chọn kiểu nào.")
    + row("KEEP_BGM", "Giữ nhạc/SFX gốc", ["0", "flat", "1"],
      {"0": "Hạ audio gốc KHI CÓ thoại (duck)", "flat": "Hạ audio gốc ĐỀU suốt video",
       "1": "Tách giọng gốc bằng demucs (GPU)"},
      "", "Cách xử lý audio gốc dưới giọng đọc. <b>Khi có thoại</b>: chỉ hạ lúc có lồng tiếng, chỗ trống giữ nguyên — nền to nhỏ theo thoại (có người thấy 'bơm' khó chịu). <b>Đều suốt video</b>: âm gốc nhỏ ổn định từ đầu tới cuối, dễ nghe, khỏi render lại vì bơm nền. <b>demucs</b>: tách hẳn giọng nói gốc khỏi nhạc/hiệu ứng (GPU, chậm thêm ~¼ thời lượng) — nền giữ trọn vẹn nhất. Mức hạ chỉnh tiếp được trong Chỉnh sửa (🎚 Âm nền gốc).")
    + row("DUCK_GAIN_DB", "Âm nền gốc dưới thoại", ["-14", "-17", "-20", "-23", "-26"],
      {"-14": "-14dB — nền còn rõ (dễ át thoại)", "-17": "-17dB",
       "-20": "-20dB — thoại nổi rõ (khuyên dùng)", "-23": "-23dB", "-26": "-26dB — nền rất nhỏ"},
      "", "Hạ audio gốc (nhạc + giọng Trung) bao nhiêu khi có thoại Việt. Đo thật: -14dB giọng chỉ nổi ~+6dB → bị át; -20dB nổi ~+12dB nghe rõ lời. Giọng đọc cũng được tự chuẩn hoá âm lượng đều nhau từng câu. Chỉnh riêng từng video: thanh 🎚 trong editor.")
    + row("VOICE_FX", "Xử lý giọng",
      ["off", "canbang", "amday", "rosang", "dienanh", "toithieu"],
      {off: "Tắt (giữ nguyên)", canbang: "Cân bằng", amday: "Ấm / dày",
       rosang: "Rõ / sáng", dienanh: "Điện ảnh", toithieu: "Tối thiểu"},
      "", "EQ + nén + chuẩn độ to cho giọng đọc, áp ngay khi render. <b>Cân bằng</b> là khởi đầu tốt; <b>Điện ảnh</b> dày và kịch tính; <b>Rõ/sáng</b> cho giọng bị tối. Áp cho mọi engine.")
    + row("PROSODY", "Tông giọng theo audio gốc", ["1", "0"],
      {"1": "Bật (khuyên dùng)", "0": "Tắt — giọng đọc trung tính"},
      "", "Đo cao độ / tốc độ / độ to từng câu GỐC so với mức nền của người nói → chỉnh giọng đọc theo (câu quát → đọc dồn cao giọng, câu trầm → chậm lại). Đo bảo thủ: mơ hồ (nhạc nền lấn) thì giữ trung tính.")
    + row("EMOTION", "Nhãn cảm xúc khi dịch", ["1", "0"],
      {"1": "Bật (khuyên dùng)", "0": "Tắt"},
      "", "Claude gắn nhãn cảm xúc từng câu (gấp/giận/buồn/thì thầm) ngay khi dịch → giọng edge chỉnh thêm nhịp/cao độ/âm lượng, viXTTS chọn clip mẫu hợp cảm xúc. Bổ trợ cho «Tông giọng»: bắt được sắc thái audio không lộ (mỉa mai, đe dọa nói nhỏ...).")
    + row("PROSODY_TRANSFER", "Chuyển ngữ điệu gốc", ["0", "1"],
      {"0": "Tắt (mặc định — thử nghiệm)", "1": "Bật — ép dáng ngữ điệu gốc lên giọng đọc"},
      "", "Thử nghiệm: ép cả DÁNG đường lên-xuống giọng của câu gốc lên giọng đọc (Praat PSOLA) — câu gốc lên giọng cuối câu thì bản đọc cũng vậy. Bật rồi chạy thử 1 job để nghe thẩm định; đổi lại chỉ những câu bị ảnh hưởng phải đọc lại.")
    + row("MAX_SPEEDUP", "Đồng bộ khớp thoại", ["1.0", "1.2", "1.4", "1.6", "1.8", "2.0"],
      {"1.0": "1.0× — KHÔNG tăng tốc (chấp nhận tràn)", "1.2": "1.2× — nhẹ nhàng",
       "1.4": "1.4× — cân bằng (khuyên dùng)", "1.6": "1.6×", "1.8": "1.8×", "2.0": "2.0× — khớp gắt"},
      "", "Trần NHÂN tổng của mọi lớp tăng tốc vì khớp thoại (engine đọc nhanh × atempo hậu kỳ ≤ mức này — trọng tài thời lượng bảo đảm, không cộng chồng như trước). Câu hết ngân sách mà vẫn dài thì fade + cắt ở biên slot, KHÔNG đè sang câu kế. <b>1.0× = KHÔNG ép nhanh chút nào</b> (tự nhiên nhất, câu dài bị cắt sớm); <b>2.0×</b> = bám hình gắt nhất nhưng câu dài đọc dồn rõ.")
    + row("STRETCH_SHORT", "Kéo giãn câu đọc xong sớm", ["0", "1"],
      {"0": "Tắt (mặc định)", "1": "Bật — chậm lại nhẹ tối đa 8%"},
      "", "Câu đọc xong QUÁ SỚM so với miệng nhân vật → kéo chậm nhẹ (0.92–1.0×, giữ cao độ) cho đỡ hụt. Chỉ kéo về độ dài MIỆNG, không lấp khoảng lặng tự nhiên của phim. Đổi xong chỉ cần render lại (không đọc lại giọng).")
    + `<div class="frow"><label>Preset nhanh</label><span>
        <button class="ghost" onclick="cfgPreset('tight')" title="MAX_SPEEDUP 2.0 + kéo giãn câu ngắn — bám khẩu hình sát nhất">🎯 Khớp môi chặt</button>
        <button class="ghost" onclick="cfgPreset('natural')" title="MAX_SPEEDUP 1.2, không kéo giãn — giọng đều, ưu tiên nghe tự nhiên">🌿 Tự nhiên</button>
        <span class="meta">đặt sẵn 2 núm trên — bấm xong nhớ Lưu</span></span></div>`
    + `<div id="edge-voices">`
    + row("TTS_VOICE", "Giọng nam (edge-tts)", ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"], null,
      "", "Giọng đọc các câu gắn nhãn NAM khi engine = edge (nhãn nam/nữ do Claude + đo audio gán từng câu). Chế độ 1 giọng thì đây là giọng cho cả video.")
    + `<div class="nu-only">` + row("TTS_VOICE_NU", "Giọng nữ (edge-tts)", ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"], null,
      "", "Giọng đọc các câu gắn nhãn NỮ khi engine = edge.") + `</div>`
    + `</div>`
    + `<div id="vixtts-voices">
      <div class="frow"><label>Giọng nam (viXTTS)${hint("Clip 6–10s trong voices/ dùng để nhân bản giọng — nghe thử &amp; quản lý ở tab 🔊 Nghe thử. Câu nhãn NAM (và mọi câu khi bật chế độ 1 giọng) đọc bằng giọng này.")}</label><select id="cfg-VIXTTS_VOICE_NAM">${vopt(v.nam)}</select></div>
      <div class="frow nu-only"><label>Giọng nữ (viXTTS)</label><select id="cfg-VIXTTS_VOICE_NU">${vopt(v.nu)}</select></div>
      <div class="fhelp">Thả clip 6–10 giây (.wav/.mp3) vào thư mục <code>voices/</code> làm giọng mẫu; nghe thử &amp; mở thư mục ở tab <b>🔊 Nghe thử</b>.</div>
    </div>`
    + `<div id="elevenlabs-voices">
      <div class="fhelp">~$22/tháng, giống người nhất, đa ngôn ngữ. API key nhập ở nhóm <b>🔑 Khóa API &amp; Token</b>. ${c.elevenlabs_key_set ? "✓ Đã có key." : "Chưa có key."}</div>`
    + textrow("ELEVENLABS_VOICE_NAM", "Voice ID nam", "vd pNInz6obpgDQGcFmaJgB (Adam)",
      "Voice ID lấy ở elevenlabs.io → Voices (mặc định sẵn Adam). Chế độ 1 giọng dùng voice này cho cả video.")
    + `<div class="nu-only">` + textrow("ELEVENLABS_VOICE_NU", "Voice ID nữ", "vd 21m00Tcm4TlvDq8ikWAM (Rachel)",
      "Mặc định sẵn Rachel — đổi voice id bất kỳ trong tài khoản của bạn.") + `</div>`
    + `</div>`
    + `<div id="vbee-voices">
      <div class="fhelp">Dịch vụ VN chuyên giọng đọc truyện/thuyết minh (chỉ tiếng Việt). VBee token + App ID nhập ở nhóm <b>🔑 Khóa API &amp; Token</b>. ${c.vbee_token_set ? "✓ Đã có token." : "Chưa có token."}</div>`
    + textrow("VBEE_VOICE_NAM", "Voice code nam", "vd hn_male_manhdung_news_48k-fhg", "Mã giọng nam — xem danh sách giọng trong tài liệu VBee. Chế độ 1 giọng dùng mã này cho cả video.")
    + `<div class="nu-only">` + textrow("VBEE_VOICE_NU", "Voice code nữ", "vd hn_female_ngochuyen_full_48k-fhg", "Mã giọng nữ VBee.") + `</div>`
    + `</div>`
    + `<div id="fpt-voices">
      <div class="fhelp">Rẻ nhất nhóm trả phí (chỉ tiếng Việt). API key nhập ở nhóm <b>🔑 Khóa API &amp; Token</b>. ${c.fpt_key_set ? "✓ Đã có key." : "Chưa có key."}</div>`
    + textrow("FPT_VOICE_NAM", "Giọng nam", "leminh | minhquang | thanhtung", "Các giọng nam FPT: leminh, minhquang, thanhtung. Chế độ 1 giọng dùng giọng này cho cả video.")
    + `<div class="nu-only">` + textrow("FPT_VOICE_NU", "Giọng nữ", "banmai | thuminh | myan | giahuy...", "Các giọng nữ FPT: banmai, thuminh, myan, ngoclam, lannhi...") + `</div>`
    + `</div>`;

  const noneL = {none: "— Không —"};
  const musicOpts = ["none", ...(c.music_files || [])];
  const logoOpts = ["none", ...(c.logo_files || [])];
  const clipOpts = ["none", ...(c.clip_files || [])];
  const sBrand = row("MUSIC", "Nhạc nền (.mp3/.wav)", musicOpts, noneL,
      "", "Nhạc nền phủ toàn video, TỰ HẠ NHỎ khi có thoại (ducking). Thả file vào thư mục <code>music/</code> cạnh app rồi chọn ở đây. Nhớ dùng nhạc royalty-free.")
    + row("MUSIC_VOL", "Âm lượng nhạc", ["0.08", "0.12", "0.15", "0.20", "0.30"],
      {"0.08": "8%", "0.12": "12%", "0.15": "15% (khuyên dùng)", "0.20": "20%", "0.30": "30%"},
      "", "Âm lượng nhạc nền so với giọng đọc — 12–15% là mức nghe nền dễ chịu, trên 20% dễ lấn thoại.")
    + row("LOGO", "Logo watermark (.png)", logoOpts, noneL,
      "", "Logo kênh đóng ở góc video (PNG nền trong suốt, thả vào <code>logo/</code>). Bật logo sẽ ép render burn (chậm hơn chút).")
    + row("LOGO_POS", "Vị trí logo", ["tl", "tr", "bl", "br"],
      {tl: "Trên-trái", tr: "Trên-phải", bl: "Dưới-trái", br: "Dưới-phải"},
      "", "Góc đặt logo. Mẹo: nếu video nguồn có watermark của kênh gốc, dùng tính năng che watermark trong editor rồi đặt logo mình đè đúng góc đó.")
    + row("LOGO_SCALE", "Cỡ logo", ["0.08", "0.12", "0.16", "0.20"],
      {"0.08": "Nhỏ (8%)", "0.12": "Vừa (12%)", "0.16": "Lớn (16%)", "0.20": "Rất lớn (20%)"},
      "", "Bề rộng logo theo % bề rộng video.")
    + row("LOGO_OPACITY", "Độ mờ logo", ["0.5", "0.7", "0.85", "1.0"],
      {"0.5": "50%", "0.7": "70%", "0.85": "85% (khuyên dùng)", "1.0": "100% (đặc)"},
      "", "85% đủ rõ nhận diện mà không che nội dung.")
    + row("INTRO", "Clip Intro (đầu video)", clipOpts, noneL,
      "", "Clip chào đầu video — tự ghép + khớp kích thước/fps với video chính. Thả vào <code>clips/</code>.")
    + row("OUTRO", "Clip Outro (cuối video)", clipOpts, noneL,
      "", "Clip kết video (kêu gọi đăng ký, giới thiệu tập sau...).")
    + row("MASTER", "Master độ to (LUFS)", ["1", "0"],
      {"1": "Bật — chuẩn -14 LUFS YouTube (khuyên dùng)", "0": "Tắt"},
      "", "Chuẩn hóa độ to CẢ video về -14 LUFS đúng chuẩn YouTube → các tập đều tiếng như nhau, không tập to tập nhỏ. Nên bật khi đăng YouTube.");

  const sShorts = row("SHORTS_COUNT", "Số short mỗi lần", ["1", "2", "3", "4", "5"], null,
      "", "Số clip Shorts cắt ra mỗi lần bấm 🎬 Tạo Shorts (menu 📤 của job đã render).")
    + row("SHORTS_LEN", "Độ dài mục tiêu", ["30", "45", "60"],
      {"30": "30 giây", "45": "45 giây (khuyên dùng)", "60": "60 giây (trần Shorts)"},
      "", "Độ dài mỗi short. Máy tự chọn các đoạn CAO TRÀO: chấm điểm bằng nhãn cảm xúc + tông giọng + mật độ thoại, mép cắt bám mép câu.")
    + row("SHORTS_STYLE", "Khung hình", ["vertical", "original"],
      {vertical: "Dọc 9:16 — chuẩn Shorts (khuyên dùng)", original: "Giữ nguyên khung gốc"},
      "", "Dọc 9:16: video thu vào giữa, nền là chính nó phóng to làm mờ (kiểu Shorts phổ biến). Clip ra ở thư mục <code>shorts/</code> của job kèm caption gợi ý #Shorts.");

  const sMisc = row("DENOISE", "Khử ồn trước Whisper", ["0", "1"],
      {"0": "Tắt", "1": "Bật — lọc ồn cho ASR nghe rõ"},
      "", "Lọc ồn bản audio đưa vào Whisper (KHÔNG đụng audio của video final). Bật khi video nguồn ồn/nhạc to làm nghe sai lời; nguồn sạch thì để tắt.")
    + row("SUBSCRIBE", "Nhắc Like/Đăng ký", ["off", "on"],
      {off: "Tắt", on: "Bật — banner vài giây đầu video"},
      "", "Hiện banner nhắc Like/Đăng ký trong ~6 giây đầu video (ép render burn).")
    + textrow("SUBSCRIBE_TEXT", "Chữ nhắc", "Nhớ Like & Đăng ký kênh nhé!",
      "Nội dung chữ trên banner.");

  const sYt = textrow("YOUTUBE_CLIENT_SECRETS", "File OAuth client (.json)", "vd D:\\keys\\client_secret.json",
      "Đường dẫn file OAuth client bạn tạo ở Google Cloud (bật YouTube Data API v3). "
      + (c.youtube_ready ? "✓ Sẵn sàng đăng thẳng." : "Chưa đủ điều kiện đăng thẳng — vẫn dùng được 📦 Gói đăng kéo-thả."))
    + row("YOUTUBE_PRIVACY", "Quyền riêng tư khi đăng", ["private", "unlisted", "public"],
      {private: "Riêng tư (an toàn nhất)", unlisted: "Không công khai (chỉ ai có link)", public: "Công khai"},
      "", "Trạng thái video khi đăng thẳng bằng nút ▶ Đăng YouTube. Để <b>Riêng tư</b> rồi tự công khai sau khi duyệt là an toàn nhất.");

  // 1 dòng khóa bí mật (ô mật khẩu). Trạng thái đã-đặt hiện ở placeholder ••••; mô tả trong ⓘ.
  const keyrow = (id, label, isSet, ph, help) =>
    `<div class="frow"><label>${esc(label)}${hint((isSet ? "✓ Đã lưu. " : "Chưa lưu. ") + help)}</label>${keyInput(id, isSet, ph)}</div>`;
  // #Gom mọi khóa/token/mã vào 1 nhóm — chỉ điền dịch vụ nào bạn dùng.
  const sKeys = `<div class="fhelp">Chỉ điền khóa của dịch vụ bạn dùng — để trống = không dùng. Khóa lưu trong <code>.env</code>, KHÔNG hiện lại (đã đặt = ô ghi <b>••••</b>; để trống khi lưu = giữ khóa cũ).</div>`
    + keyrow("ANTHROPIC_API_KEY", "Claude API key", c.api_key_set, "sk-ant-… (console.anthropic.com)",
      "Bắt buộc để dịch bằng Claude, và cho fallback khi Gemini lỗi. Lấy ở console.anthropic.com → API Keys.")
    + keyrow("GEMINI_API_KEY", "Gemini API key", c.gemini_key_set, "lấy free ở aistudio.google.com/apikey",
      "Miễn phí ở Google AI Studio. Cần khi nhà cung cấp dịch = Gemini.")
    + keyrow("ELEVENLABS_API_KEY", "ElevenLabs API key", c.elevenlabs_key_set, "xi-api-key từ elevenlabs.io",
      "Cho engine đọc ElevenLabs (trả phí, giống người nhất).")
    + keyrow("VBEE_TOKEN", "VBee token", c.vbee_token_set, "Bearer token từ vbee.vn/console",
      "Cho engine đọc VBee (trả phí, tiếng Việt).")
    + textrow("VBEE_APP_ID", "VBee App ID", "app id trong console VBee",
      "Mã ứng dụng VBee — đi kèm token để xác thực (cùng chỗ với token trong console vbee.vn).")
    + keyrow("FPT_TTS_API_KEY", "FPT.AI API key", c.fpt_key_set, "api-key từ fpt.ai (TTS)",
      "Cho engine đọc FPT.AI (trả phí, tiếng Việt, rẻ nhất).")
    + keyrow("HF_TOKEN", "HuggingFace token", c.hf_token_set, "hf_… (huggingface.co/settings/tokens)",
      "Để tải model pyannote cho Nhận diện người nói (diarization).")
    + keyrow("TELEGRAM_BOT_TOKEN", "Telegram bot token", c.telegram_token_set, "token từ @BotFather",
      "Bot báo job xong/lỗi (kèm thông báo desktop 🔔). Tạo bot với @BotFather để lấy token.")
    + textrow("TELEGRAM_CHAT_ID", "Telegram Chat ID", "vd 123456789",
      "ID cuộc trò chuyện nhận thông báo — nhắn bot 1 tin rồi mở api.telegram.org/bot&lt;token&gt;/getUpdates để thấy.");

  let html = `<h3 style="margin-bottom:2px">⚙️ Cấu hình <span class="meta" style="font-weight:400">(.env) — áp dụng cho job chạy mới; bấm tiêu đề nhóm để gập/mở</span></h3>`;
  html += `<div class="cfgcols">`;
  html += sec("🔑 Khóa API &amp; Token", true, sKeys);
  html += sec("Dịch &amp; phụ đề", true, sDich);
  html += sec("Nhận dạng thoại (transcript)", true, sTrans);
  html += sec("Lồng tiếng (TTS)", true, sTts);
  html += sec("Thương hiệu / xuất bản", true, sBrand);
  html += sec("Nhận diện người nói (diarization)", V.DIARIZE === "1", sDiar);
  html += sec("Shorts tự động", false, sShorts);
  html += sec("Khử ồn &amp; Nhắc Đăng ký", V.DENOISE === "1" || V.SUBSCRIBE === "on", sMisc);
  html += sec("Đăng YouTube", !!c.youtube_ready, sYt);
  html += `</div>`;
  html += `<div class="cfgfoot"><button onclick="saveConfig()">💾 Lưu cấu hình</button>
    <span id="cfgmsg"></span>
    <span class="meta" style="margin-left:auto">Khóa/token nhập ở nhóm 🔑 đầu trang · lưu vào .env</span></div>`;
  document.getElementById("cfgform").innerHTML = html;
  applyEngineUI();
  applyProviderUI();
  applySingleVoiceUI();
  cfgDirty = false;   // vừa nạp từ .env = sạch, chưa có thay đổi
}

// #5 Nhãn ô giọng chính theo từng engine: [khi 1 giọng, khi 2 giọng]. Relabel giữ
// nguyên icon ⓘ (chỉ đổi text node đầu của nhãn).
const MAIN_VOICE_LABELS = {
  TTS_VOICE:            ["Giọng (edge-tts)",  "Giọng nam (edge-tts)"],
  VIXTTS_VOICE_NAM:     ["Giọng (viXTTS)",    "Giọng nam (viXTTS)"],
  ELEVENLABS_VOICE_NAM: ["Voice ID",          "Voice ID nam"],
  VBEE_VOICE_NAM:       ["Voice code",        "Voice code nam"],
  FPT_VOICE_NAM:        ["Giọng",             "Giọng nam"],
};
// Chế độ 1 giọng: ẩn mọi ô "giọng nữ", đổi nhãn ô chính "…nam" → bỏ chữ "nam".
function applySingleVoiceUI() {
  const sel = document.getElementById("cfg-TTS_SINGLE_VOICE");
  const single = !sel || sel.value === "1";
  document.querySelectorAll("#pane-cfg .nu-only").forEach(e => { e.style.display = single ? "none" : ""; });
  for (const [key, pair] of Object.entries(MAIN_VOICE_LABELS)) {
    const el = document.getElementById("cfg-" + key);
    const lab = el && el.closest(".frow") && el.closest(".frow").querySelector("label");
    if (!lab) continue;
    const txt = (single ? pair[0] : pair[1]) + " ";
    if (lab.firstChild && lab.firstChild.nodeType === 3) lab.firstChild.nodeValue = txt;
    else lab.insertBefore(document.createTextNode(txt), lab.firstChild);
  }
}

// Nhà cung cấp = gemini → hiện khối Gemini, ẩn dòng Model Claude (Claude chỉ còn là
// fallback ngầm); = claude → ngược lại.
function applyProviderUI() {
  const sel = document.getElementById("cfg-TRANSLATE_PROVIDER");
  const gem = sel && sel.value === "gemini";
  const box = document.getElementById("gemini-cfg");
  if (box) box.style.display = gem ? "" : "none";
  const cbox = document.getElementById("claude-cfg");
  if (cbox) cbox.style.display = gem ? "none" : "";
}

// Nút "↻ Tải lại" nạp lại form từ .env → sẽ mất thay đổi chưa lưu; hỏi trước.
function reloadConfig() {
  if (cfgDirty && !confirm("Bỏ thay đổi cấu hình chưa lưu và tải lại?")) return;
  loadConfig();
}

let VOICE_LIST = [];
let _vaudio = null;
function playVoice(i) {
  const x = VOICE_LIST[i];
  if (!x) return;
  stopVoice();
  _vaudio = new Audio("/api/voices/file/" + encodeURIComponent(x.file));
  _vaudio.play();
}
function stopVoice() {
  if (_vaudio) { _vaudio.pause(); _vaudio.currentTime = 0; _vaudio = null; }
}
function openVoices() { fetch("/api/voices/open", { method: "POST" }); }

// Tab 🔊 Nghe thử: nghe & quản lý các clip giọng mẫu trong voices/ (tách khỏi Cấu hình).
async function loadPreviewTab() {
  let v = { voices: [] };
  try { v = await (await fetch("/api/voices")).json(); } catch (e) {}
  VOICE_LIST = v.voices || [];
  const rows = VOICE_LIST.length
    ? VOICE_LIST.map((x, i) => `<div class="vrow"><span>${esc(x.name)}</span>
        <button class="ghost" type="button" onclick="playVoice(${i})">🔊 Nghe</button></div>`).join("")
    : '<span class="meta">Chưa có giọng nào trong voices/ — thả clip 6–10s (.wav/.mp3) vào rồi bấm ↻ Tải lại.</span>';
  document.getElementById("previewview").innerHTML =
    `<h3 style="margin-top:0">🔊 Nghe thử giọng</h3>
     <div class="meta" style="margin-bottom:12px">Các clip mẫu trong thư mục <code>voices/</code> — dùng để nhân bản giọng (viXTTS) hoặc casting nhân vật (Series). Bấm 🔊 nghe thử, rồi vào ⚙️ Cấu hình → Lồng tiếng để chọn làm giọng mặc định.</div>
     <div class="vlist">${rows}</div>
     <div class="row" style="margin-top:10px">
       <button class="ghost" type="button" onclick="stopVoice()">⏹ Ngừng đọc</button>
       <button class="ghost" type="button" onclick="openVoices()">📂 Mở thư mục voices</button>
       <button class="ghost" type="button" onclick="loadPreviewTab()">↻ Tải lại</button></div>`;
}

// Chỉ hiện bộ giọng của engine đang chọn — gọn gàng, đỡ nhầm 2 bộ nam/nữ.
function applyEngineUI() {
  const sel = document.getElementById("cfg-TTS_ENGINE");
  const eng = sel ? sel.value : "edge";
  for (const [id, match] of [["edge-voices", "edge"], ["vixtts-voices", "vixtts"],
      ["elevenlabs-voices", "elevenlabs"], ["vbee-voices", "vbee"], ["fpt-voices", "fpt"]]) {
    const el = document.getElementById(id);
    if (el) el.style.display = eng === match ? "" : "none";
  }
  applySingleVoiceUI();   // block vừa hiện cần đúng trạng thái ẩn/hiện ô giọng nữ
}

async function saveConfig() {
  const body = {};
  for (const [key] of CFG_FIELDS)
    body[key] = document.getElementById("cfg-" + key).value;
  for (const key of ["VIXTTS_VOICE_NAM", "VIXTTS_VOICE_NU"]) {
    const el = document.getElementById("cfg-" + key);
    if (el) body[key] = el.value;
  }
  // token bí mật: chỉ gửi khi người dùng thực sự nhập (để trống = giữ token cũ)
  for (const key of ["ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "HF_TOKEN", "GEMINI_API_KEY",
                     "ELEVENLABS_API_KEY", "VBEE_TOKEN", "FPT_TTS_API_KEY"]) {
    const el = document.getElementById("cfg-" + key);
    if (el && el.value.trim()) body[key] = el.value.trim();
  }
  let ok = false;
  try {
    const res = await fetch("/api/config", { method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
    ok = res.ok;
  } catch (e) { ok = false; }   // server tắt/mất kết nối → fetch ném lỗi, đừng để treo
  if (ok) cfgDirty = false;
  document.getElementById("cfgmsg").textContent =
    ok ? "✓ Đã lưu — job mới sẽ dùng cấu hình này" : "Lỗi khi lưu (kiểm tra server còn chạy không)";
  setTimeout(() => document.getElementById("cfgmsg").textContent = "", 4000);
  return ok;
}

/* ---------- Jobs ---------- */
// Tên thân thiện cho từng stage trong pipeline (khớp key stage server trả về)
const STAGE_LABEL = {
  downloading: "Đang tải video", extracting: "Đang tách âm thanh",
  transcribing: "Đang nhận dạng thoại", translating: "Đang dịch sang tiếng Việt",
  tts: "Đang đọc lồng tiếng", bgm: "Đang xử lý nhạc nền", mixing: "Đang trộn lồng tiếng",
  rendering: "Đang render video", metadata: "Đang tạo metadata", uploading: "Đang đăng tải",
};
// Thanh tiến độ cho 1 job đang chạy/chờ. TTS có số câu → thanh chính xác (%); các stage
// khác chưa có % chi tiết → thanh chạy vô định (animate) cho biết đang xử lý.
// base = số câu ĐÃ có sẵn mp3 khi bắt đầu lần đọc lại này (chỉ dùng cho editor render-watch):
// re-render chỉ đọc lại câu đã đổi → trừ base để thanh đi từ 0% theo SỐ CÂU PHẢI ĐỌC LẠI,
// không nhảy ngay lên ~95% (các câu không đổi vẫn còn mp3). base=0 ở thẻ job → giữ nguyên.
function jobProgressHTML(j, base = 0) {
  if (!j) return "";
  if (j.queued && !j.running)
    return '<div class="prog"><div class="prog-lbl">⏳ Trong hàng đợi — chờ job phía trước xong…</div>'
         + '<div class="bar indet"><span></span></div></div>';
  if (!j.running) return "";
  let lbl = STAGE_LABEL[j.stage] || j.stage || "Đang xử lý";
  let pct = null;
  if (j.stage === "tts" && j.seg_total) {
    const total = j.seg_total - base, done = j.tts_done - base;
    if (total > 0) {   // có câu phải đọc lại → thanh chính xác theo phần còn lại
      pct = Math.max(0, Math.min(100, Math.round(done / total * 100)));
      lbl += ` — ${Math.max(0, done)}/${total} câu`;
    }   // total<=0 (chỉ đổi cài đặt, không đổi câu) → để indeterminate
  } else if (j.prog_total) {   // OCR/Whisper/dịch: tiến độ trong-stage
    pct = Math.max(0, Math.min(100, Math.round(j.prog_done / j.prog_total * 100)));
    lbl += ` — ${j.prog_done}/${j.prog_total}`;
  }
  const bar = pct === null
    ? '<div class="bar indet"><span></span></div>'
    : `<div class="bar"><span style="width:${pct}%"></span></div>`;
  return `<div class="prog"><div class="prog-lbl">▶ ${esc(lbl)}${pct !== null ? ` · ${pct}%` : ""}</div>${bar}</div>`;
}

// #11 Thông báo desktop khi job chuyển sang Xong / Lỗi (so với lần refresh trước).
const _prevStage = {};
function notifyJob(j) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const done = j.stage === "done";
  const title = done ? "✅ Job hoàn thành" : "⚠️ Job lỗi";
  const name = j.yt_title || j.url || j.id;
  const body = name + (!done && j.error ? "\n" + j.error : "");
  try { new Notification(title, { body, tag: j.id, requireInteraction: !done }); } catch (e) {}
}
function checkJobNotifications(jobs) {
  for (const j of jobs) {
    const prev = _prevStage[j.id];
    if (prev && prev !== j.stage && (j.stage === "done" || j.stage === "failed")) notifyJob(j);
    _prevStage[j.id] = j.stage;
  }
}
function _notifBtnLabel() {
  const b = document.getElementById("notifbtn");
  if (!b) return;
  const ok = ("Notification" in window) && Notification.permission === "granted";
  b.textContent = ok ? "🔔 Đã bật thông báo" : "🔔 Bật thông báo";
}
function enableNotif() {
  if (!("Notification" in window)) { toast("Trình duyệt không hỗ trợ thông báo."); return; }
  Notification.requestPermission().then(p => {
    _notifBtnLabel();
    if (p !== "granted") toast("Thông báo đang bị chặn — bật lại trong cài đặt trình duyệt cho trang này.");
  });
}

function badge(j) {
  if (j.stage === "done")   return '<span class="badge done">✅ Hoàn thành</span>';
  if (j.stage === "failed") return '<span class="badge fail">⚠️ Lỗi</span>';
  if (j.stage === "paused") return '<span class="badge wait">⏸ Chờ xem thử trước render</span>';
  if (j.running)            return '<span class="badge run">▶ Đang chạy</span>';
  if (j.queued)             return '<span class="badge wait">⏸ Trong hàng đợi</span>';
  if (j.stage === "pending") return '<span class="badge wait">🕒 Chờ chạy</span>';
  return '<span class="badge wait">' + j.stage + '</span>';
}

function stageList(j) {
  // Dải chấm NGANG (1 chấm = 1 bước) thay danh sách dọc 10 dòng — thẻ job gọn hẳn.
  // Chi tiết từng bước vẫn xem được bằng cách rê chuột lên chấm (title).
  const done = new Set(j.completed_stages);
  // job failed: state.stage="failed" (không phải tên bước) → bước LỖI = bước đầu
  // tiên chưa hoàn thành (pipeline chạy tuần tự nên chính nó là chỗ gãy)
  const failKey = j.stage === "failed"
    ? (STAGES.find(([k]) => !done.has(k)) || [""])[0] : "";
  let dots = "", curLbl = "";
  for (const [key, label] of STAGES) {
    let cls = "todo";
    if (done.has(key)) cls = "ok";
    else if (key === failKey) { cls = "bad"; curLbl = label; }
    else if (j.stage === key) { cls = j.error ? "bad" : "cur"; curLbl = label; }
    let tip = label;
    if (key === "tts" && j.seg_total && !done.has("tts")) tip += ` (${j.tts_done}/${j.seg_total})`;
    dots += `<span class="stg ${cls}" title="${esc(tip)}"></span>`;
  }
  const nDone = STAGES.filter(([k]) => done.has(k)).length;
  let lbl;
  if (j.stage === "done") lbl = "";                       // badge ✅ đã nói đủ
  else if ((j.error || failKey) && curLbl) lbl = "lỗi ở: " + curLbl;
  else if (curLbl) lbl = `${curLbl} · ${nDone}/${STAGES.length}`;
  else lbl = nDone ? `${nDone}/${STAGES.length} bước` : "chưa chạy";
  return `<div class="stgbar"><div class="stgdots">${dots}</div>`
       + (lbl ? `<span class="stglbl">${esc(lbl)}</span>` : "") + `</div>`;
}

function cardHtml(j) {
  // j.url do người dùng dán, j.yt_title/j.error chứa dữ liệu từ YouTube → escape
  let html = `<h3>${esc(j.url)}</h3><div class="jobid">${esc(j.id)}</div>`;
  html += badge(j) + stageList(j);
  if (j.running || j.queued) html += jobProgressHTML(j);
  if (j.error) html += `<div class="err">${esc(j.error)}</div>`;
  if (j.series) html += `<div class="meta">📚 ${esc(j.series)}</div>`;
  if (j.yt_title) html += `<div class="meta">📺 ${esc(j.yt_title)}</div>`;
  if (j.seg_total) html += `<div class="meta">${j.seg_total} câu thoại`
      + (j.overflow !== undefined ? ` · ${j.overflow} cảnh báo timing` : "") + `</div>`;
  if (j.has_thumb)
    html += `<img class="preview" src="/api/jobs/${j.id}/thumb?v=${Date.now() % 1e7}" alt="thumbnail">`;
  if (j.has_final)
    html += `<video controls preload="none" src="/api/jobs/${j.id}/video?v=${j.created_at}"></video>`;
  html += '<div class="row">';
  if (j.stage !== "done" && !j.queued && !j.running) {
    // chưa chạy lần nào (pending, chưa có stage hoàn thành) → nút ▶ Chạy nổi bật;
    // còn lại (dở dang / lỗi) → ↻ Chạy tiếp. Cả hai dùng chung endpoint resume.
    const fresh = j.stage === "pending" && !(j.completed_stages && j.completed_stages.length);
    html += fresh
      ? `<button onclick="resumeJob('${j.id}')">▶ Chạy</button>`
      : `<button class="ghost" onclick="resumeJob('${j.id}')">↻ Chạy tiếp</button>`;
  }
  if (j.queued && !j.running)   // đang chờ → cho nhảy lên đầu hàng
    html += `<button class="ghost" onclick="prioritizeJob('${j.id}')" title="Chạy ngay sau job hiện tại">⬆ Ưu tiên</button>`;
  if (j.seg_total && !j.queued && !j.running)
    html += `<button class="ghost" onclick="openEditor('${j.id}')">✏️ Chỉnh sửa</button>`;

  // Cụm "🔎 Soát ▾": QC + tên riêng + log — gọn thẻ job (9 nút → 2 menu + nút chính)
  const soat = [];
  if (j.seg_total && !j.queued && !j.running)
    soat.push(`<button class="ghost" onclick="qcJob('${j.id}')">🔍 QC dịch/timing</button>`);
  if (j.completed_stages.includes("transcribing") && !j.queued && !j.running)
    soat.push(`<button class="ghost" onclick="openGloss('${j.id}')">📒 Tên riêng</button>`);
  if (j.has_log)
    soat.push(`<button class="ghost" onclick="openLog('${j.id}')">📜 Log chạy</button>`);
  if (soat.length)
    html += `<details class="btnmenu"><summary class="ghost" role="button"><button class="ghost" type="button" tabindex="-1" style="pointer-events:none">🔎 Soát ▾</button></summary><div class="menu" onclick="this.closest('details').removeAttribute('open')">${soat.join("")}</div></details>`;

  // Cụm "📤 Xuất bản ▾": thumbnail + gói đăng + YouTube + thư mục + srt + dọn
  const xb = [];
  if (j.seg_total && (j.stage === "done" || j.completed_stages.includes("translating")))
    xb.push(`<button class="ghost" id="thumb-${j.id}" onclick="regenThumb('${j.id}')">🖼 ${j.has_thumb ? "Thumbnail mới" : "Tạo thumbnail"}</button>`);
  if (j.has_final) {
    xb.push(`<button class="ghost" onclick="makePackage('${j.id}')">📦 Gói đăng (kéo-thả)</button>`);
    xb.push(`<button class="ghost" onclick="uploadYT('${j.id}')">▶ Đăng YouTube</button>`);
    xb.push(`<button class="ghost" onclick="makeShorts('${j.id}')">🎬 Tạo Shorts cao trào</button>`);
  }
  if (j.has_srt) xb.push(`<a href="/api/jobs/${j.id}/srt">⬇ Tải sub_vi.srt</a>`);
  xb.push(`<button class="ghost" onclick="openJob('${j.id}')">📂 Mở thư mục</button>`);
  if (j.stage === "done" && !j.queued && !j.running)
    xb.push(`<button class="ghost" onclick="cleanJob('${j.id}')" title="Xoá file âm thanh trung gian (giữ video, phụ đề, bản dịch)">🧹 Dọn file tạm</button>`);
  html += `<details class="btnmenu"><summary role="button"><button class="ghost" type="button" tabindex="-1" style="pointer-events:none">📤 Xuất bản ▾</button></summary><div class="menu" onclick="this.closest('details').removeAttribute('open')">${xb.join("")}</div></details>`;

  if (j.queued || j.running)   // #12 đang chạy/chờ → cho hủy (dừng giữa chừng, chạy tiếp sau)
    html += `<button class="danger" onclick="cancelJob('${j.id}')">⏹ Hủy</button>`;
  else
    html += `<button class="danger" onclick="deleteJob('${j.id}')">🗑 Xóa</button>`;
  html += '</div>';
  return html;   // cài đặt phụ đề/che giờ nằm TRONG "Sửa lời thoại" (không lặp ngoài thẻ job)
}

let refreshGen = 0;   // tem thứ tự: phân biệt refresh có snapshot CŨ HƠN lúc edSave enqueue
let _refreshIdleTick = 0;
async function refresh() {
  // Audit #8: tab Jobs ẩn + không có editor/render đang theo dõi → giãn nhịp poll
  // 3s→15s (chạy 1/5 tick) thay vì tắt hẳn — notification "job xong" vẫn tới, chỉ
  // trễ tối đa ~15s; đỡ 80% fetch + stringify khi ngồi ở tab khác.
  const jobsHidden = document.getElementById("pane-jobs").style.display === "none";
  if (jobsHidden && !edJobId && !edRenderWatch) {
    if ((_refreshIdleTick = (_refreshIdleTick + 1) % 5) !== 0) return;
  } else {
    _refreshIdleTick = 0;
  }
  const myGen = ++refreshGen;   // chụp trước khi fetch (sống qua await)
  let jobs;
  try { jobs = await (await fetch("/api/jobs")).json(); }
  catch (e) { return; }
  checkJobNotifications(jobs);   // #11 báo desktop khi job Xong/Lỗi
  const grid = document.getElementById("jobs");
  const seen = new Set();
  if (!jobs.length) {          // trống → chỉ dẫn thân thiện thay vì lưới trắng
    seen.add("jobs-empty");
    if (!document.getElementById("jobs-empty")) {
      const d = document.createElement("div");
      d.id = "jobs-empty"; d.className = "empty";
      d.innerHTML = "🎬<div><b>Chưa có job nào</b></div>"
        + "<div class='meta'>Dán link video (hoặc playlist) vào ô phía trên rồi bấm ＋ Thêm job — hoặc 📁 Upload video từ máy.</div>";
      grid.appendChild(d);
    }
  }
  for (const j of jobs) {
    seen.add("card-" + j.id);
    let card = document.getElementById("card-" + j.id);
    if (!card) {
      card = document.createElement("div");
      card.className = "card";
      card.id = "card-" + j.id;
      grid.appendChild(card);
    }
    const json = JSON.stringify(j);
    if (lastJson[j.id] === json) continue;
    if (card.querySelector("details[open]")) continue;
    card.innerHTML = cardHtml(j);
    lastJson[j.id] = json;
  }
  for (const card of [...grid.children])
    if (!seen.has(card.id)) card.remove();

  // Editor đang mở → cập nhật thanh tiến độ của job đó (rỗng khi job không chạy → ẩn)
  if (edJobId) {
    const ej = jobs.find(x => x.id === edJobId);
    const watching = !!(edRenderWatch && edRenderWatch.id === edJobId);
    // BỎ QUA refresh có snapshot chụp TRƯỚC lúc edSave enqueue (myGen <= armGen): nó thấy job
    // chưa chạy → sẽ báo "xong" GIẢ. Chỉ refresh bắt đầu SAU enqueue mới được xét hoàn tất.
    const stale = watching && myGen <= edRenderWatch.armGen;
    const box = document.getElementById("edprogress");
    if (box && !stale) box.innerHTML = jobProgressHTML(ej, watching ? (edRenderWatch.ttsBase || 0) : 0);
    // job RỜI trạng thái chạy (xong/lỗi/biến mất) → coi là hoàn tất. Không cần cờ "seen":
    // refresh hậu-enqueue luôn thấy job trong _active (đồng bộ) tới khi worker xong thật.
    if (watching && !stale && !(ej && (ej.running || ej.queued))) {
      edRenderWatch = null;
      const m = document.getElementById("edmsg"), b = document.getElementById("edsavebtn");
      const reEnable = () => { if (b) { b.disabled = false; b.textContent = "💾 Lưu & render lại"; } };
      if (!ej) { if (m) m.textContent = "Job không còn — kiểm tra tab Jobs."; reEnable(); }
      else if (ej.stage === "failed") { if (m) m.textContent = "Render lỗi: " + (ej.error || "(xem tab Jobs)"); reEnable(); }
      else if (edDirty.size) {
        // sửa thêm trong lúc render → đừng tự mở lại kẻo mất sửa đổi chưa lưu
        if (m) m.textContent = "✓ Render xong. Có câu sửa mới chưa lưu — bấm 💾 để render lại.";
        reEnable();
      } else {
        reEnable();          // nhả nút TRƯỚC: nếu openEditor refetch lỗi (early-return) vẫn còn nút dùng được
        openEditor(edJobId); // mở lại với bản final mới (video + lồng tiếng mới)
      }
    }
  }

  // Thanh "Chạy tất cả" + điều khiển hàng đợi — hiện khi có job chờ chạy/đang xếp hàng.
  const pend = jobs.filter(j => j.stage === "pending"
    && !(j.completed_stages && j.completed_stages.length) && !j.queued && !j.running).length;
  const nQueued = jobs.filter(j => j.queued).length;
  const bar = document.getElementById("pending-bar");
  let bh = "";
  if (pend > 0)
    bh += `<button onclick="runAllPending()">▶ Chạy tất cả (${pend})</button>`;
  if (nQueued > 0 || _queuePaused)   // có hàng đợi (hoặc đang pause) → nút tạm dừng/mở
    bh += _queuePaused
      ? `<button onclick="queuePause(false)">▶ Mở lại hàng đợi</button><span class="meta" style="color:var(--warn)">⏸ Hàng đợi đang TẠM DỪNG — job đang chạy chạy nốt, job kế chờ.</span>`
      : `<button class="ghost" onclick="queuePause(true)">⏸ Tạm dừng hàng đợi</button>`;
  if (pend > 0 && !bh.includes("TẠM DỪNG"))
    bh += `<span class="meta">Job mới thêm KHÔNG tự chạy — bấm ▶ Chạy ở từng job, hoặc nút này để chạy hết.</span>`;
  bar.style.display = bh ? "" : "none";
  bar.innerHTML = bh;
}

