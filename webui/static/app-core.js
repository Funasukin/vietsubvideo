// #17 tách monolith — NỘI DUNG: helpers chung (esc/toast/fmt), tab, form thêm job/upload, danh sách job, thanh tiến độ, Tổng quan/stats.
// Tab Cấu hình tách tiếp sang app-config.js (đợt G) — file đó nạp NGAY SAU file này.
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
// app-visual.js gắn listener change/input trên #cfgform gọi hàm này cho MỌI control;
// scheduleCfgDiff (app-config.js) gom lại 1 lần quét diff/chấm/đếm mỗi frame.
function markCfgDirty() {
  cfgDirty = true;
  if (typeof scheduleCfgDiff === "function") scheduleCfgDiff();
}
// V12/U5: MỘT nguồn mapping preset khớp thoại — tab Cấu hình (cfg-*) và panel ⚙️
// per-job (ov-*) cùng dùng, khỏi lệch nhau về sau (điểm Codex).
// đợt T: STRETCH_SHORT đã gỡ khỏi app (nhịp đồng đều) — preset chỉ còn MAX_SPEEDUP
const SYNC_PRESETS = {
  tight: { MAX_SPEEDUP: "2.0" },
  natural: { MAX_SPEEDUP: "1.2" },
};
function applySyncPreset(kind, prefix) {
  const p = SYNC_PRESETS[kind] || {};
  for (const [k, v] of Object.entries(p)) {
    const el = document.getElementById(prefix + k);
    if (el) el.value = v;
  }
  toast(kind === "tight" ? "Preset: khớp môi chặt (nén tối đa 2.0×)"
                         : "Preset: tự nhiên (nén tối đa 1.2×)");
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

