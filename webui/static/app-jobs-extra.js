// #17 tách monolith — NỘI DUNG: hàng đợi (pause/prioritize), Series + casting, QC, log/dọn file per-job, glossary theo job, đăng YouTube, cắt video dài.
// đúng thứ tự cũ (classic script — cùng global scope, hành vi không đổi).
// ---------- Hàng đợi: tạm dừng + trạng thái (đồng bộ mỗi 10s qua refreshStats) ----------
let _queuePaused = false;
async function queuePause(paused) {
  try {
    const r = await fetch("/api/queue/pause", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paused }) });
    if (r.ok) _queuePaused = paused;
  } catch (e) {}
  refresh();
}
async function syncQueueState() {
  try { _queuePaused = !!(await (await fetch("/api/queue")).json()).paused; } catch (e) {}
}

// ---------- Series (#7/#8): glossary + casting giọng dùng chung nhiều tập ----------
let _seriesList = [], _seriesVoices = [], _seriesCasting = [];

async function refreshSeriesDatalist() {   // đổ tên series vào ô "Series" của form thêm job
  try { _seriesList = (await (await fetch("/api/series")).json()).series || []; }
  catch (e) { return; }
  const dl = document.getElementById("series-list");
  if (dl) dl.innerHTML = _seriesList.map(s => `<option value="${esc(s.name)}">`).join("");
}

async function loadSeriesTab() {
  const [sl, vl] = await Promise.all([
    fetch("/api/series").then(r => r.json()).catch(() => ({ series: [] })),
    fetch("/api/voices").then(r => r.json()).catch(() => ({ voices: [] })),
  ]);
  _seriesList = sl.series || [];
  _seriesVoices = vl.voices || [];
  let h = `<h3 style="margin-top:0">📚 Series — glossary & casting giọng dùng chung nhiều tập</h3>`;
  h += `<div class="meta" style="margin-bottom:12px;line-height:1.6">Gán mỗi <b>nhân vật</b> một <b>giọng mẫu</b> (clip trong <code>voices/</code>): mọi tập thuộc series sẽ đọc nhân vật đó bằng đúng giọng — Claude tự nhận diện câu theo tên. <b>Glossary</b> của series gộp với glossary từng tập (tập thắng khi trùng). Áp dụng cho tập <b>thêm mới</b> hoặc <b>chạy lại từ bước dịch</b>.</div>`;
  h += `<div class="row" style="margin-bottom:6px">`;
  h += `<input id="sv-name" list="sv-names" autocomplete="off" placeholder="Chọn series có sẵn hoặc gõ tên series mới" style="flex:1;min-width:240px;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font:inherit">`;
  h += `<datalist id="sv-names">` + _seriesList.map(s => `<option value="${esc(s.name)}">`).join("") + `</datalist>`;
  h += `<button type="button" onclick="seriesOpen()">📂 Mở / Tạo</button></div>`;
  if (_seriesList.length)
    h += `<div class="meta" style="margin-bottom:10px">Đã có ${_seriesList.length} series: ` +
      _seriesList.map((s, i) => `<a href="#" onclick="seriesOpenIdx(${i});return false">${esc(s.name)}</a> <span style="opacity:.7">(${s.cast_count} vai · ${s.gloss_lines} tên)</span>`).join(" · ") + `</div>`;
  if (!_seriesVoices.length)
    h += `<div class="err">Chưa có clip giọng nào trong voices/. Thêm file .wav giọng mẫu để cast được nhân vật.</div>`;
  h += `<div id="sv-editor" style="margin-top:14px"></div>`;
  document.getElementById("seriesview").innerHTML = h;
}

function seriesOpenIdx(i) { document.getElementById("sv-name").value = _seriesList[i].name; seriesOpen(); }

async function seriesOpen() {
  const name = document.getElementById("sv-name").value.trim();
  if (!name) { toast("Nhập tên series."); return; }
  let s;
  try { s = await (await fetch("/api/series/one?name=" + encodeURIComponent(name))).json(); }
  catch (e) { toast("Lỗi tải series."); return; }
  _seriesCasting = Object.entries(s.casting || {}).map(([char, voice]) => ({ char, voice }));
  if (!_seriesCasting.length) _seriesCasting.push({ char: "", voice: "" });
  renderSeriesEditor(s.name, s.glossary || "", s.exists);
}

function _voiceOptions(sel) {
  let o = `<option value="">— chọn giọng —</option>`;
  o += _seriesVoices.map(v => `<option value="${esc(v.file)}"${v.file === sel ? " selected" : ""}>${esc(v.name)}</option>`).join("");
  if (sel && !_seriesVoices.some(v => v.file === sel))   // giọng đã lưu nhưng mất file → vẫn giữ
    o += `<option value="${esc(sel)}" selected>${esc(sel)} (thiếu file)</option>`;
  return o;
}

function renderSeriesEditor(name, glossary, exists) {
  const inp = "background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font:inherit;font-size:13px";
  let h = `<div class="card" style="background:var(--bg)">`;
  h += `<h4 style="margin:0 0 4px">${exists ? "✏️ Sửa" : "🆕 Tạo"} series: ${esc(name)}</h4>`;
  h += `<label class="meta">Glossary dùng chung (mỗi dòng: tên gốc=Hán-Việt / nghĩa Việt)</label>`;
  h += `<textarea id="sv-gloss" rows="4" style="width:100%;box-sizing:border-box;${inp};margin:4px 0 12px;resize:vertical">${esc(glossary)}</textarea>`;
  h += `<label class="meta">Casting: nhân vật → giọng mẫu</label>`;
  h += `<div id="sv-cast" style="margin:6px 0"></div>`;
  h += `<button type="button" class="ghost" onclick="seriesAddRow()">＋ Thêm nhân vật</button>`;
  h += `<div class="row" style="margin-top:14px"><button type="button" onclick="seriesSave()">💾 Lưu series</button>`;
  h += `<span class="meta" id="sv-msg"></span></div></div>`;
  const box = document.getElementById("sv-editor");
  box.innerHTML = h;
  box.dataset.name = name;
  renderCastRows();
}

function renderCastRows() {
  const cell = "background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font:inherit;font-size:13px";
  document.getElementById("sv-cast").innerHTML = _seriesCasting.map((c, i) => {
    let r = `<div class="row" style="margin-bottom:6px" data-i="${i}">`;
    r += `<input class="sv-char" placeholder="Tên nhân vật (vd Đường Tam)" value="${esc(c.char)}" style="flex:1;min-width:140px;${cell}">`;
    r += `<select class="sv-voice" style="flex:1;min-width:140px;${cell}">${_voiceOptions(c.voice)}</select>`;
    r += `<button type="button" class="ghost" onclick="seriesPlayRow(${i})">▶</button>`;
    r += `<button type="button" class="danger" onclick="seriesDelRow(${i})">🗑</button></div>`;
    return r;
  }).join("");
}

function _collectCast() {
  _seriesCasting = [...document.querySelectorAll("#sv-cast .row")].map(r => ({
    char: r.querySelector(".sv-char").value,
    voice: r.querySelector(".sv-voice").value,
  }));
}
function seriesAddRow() { _collectCast(); _seriesCasting.push({ char: "", voice: "" }); renderCastRows(); }
function seriesDelRow(i) { _collectCast(); _seriesCasting.splice(i, 1); if (!_seriesCasting.length) _seriesCasting.push({ char: "", voice: "" }); renderCastRows(); }
function seriesPlayRow(i) {
  const sel = document.querySelector(`#sv-cast .row[data-i="${i}"] .sv-voice`);
  if (sel && sel.value) { stopVoice(); _vaudio = new Audio("/api/voices/file/" + encodeURIComponent(sel.value)); _vaudio.play(); }
}

async function seriesSave() {
  const name = document.getElementById("sv-editor").dataset.name;
  _collectCast();
  const casting = {};
  for (const c of _seriesCasting) { const ch = c.char.trim(); if (ch && c.voice) casting[ch] = c.voice; }
  const msg = document.getElementById("sv-msg");
  try {
    const r = await fetch("/api/series", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, glossary: document.getElementById("sv-gloss").value, casting }) });
    if (!r.ok) { msg.style.color = "var(--err)"; msg.textContent = "Lỗi: " + (await r.text()); return; }
    msg.style.color = "var(--ok)";
    msg.textContent = `Đã lưu (${Object.keys(casting).length} vai).`;
    refreshSeriesDatalist();
  } catch (e) { msg.style.color = "var(--err)"; msg.textContent = "Lỗi mạng."; }
}

// ---------- #13 QC: soát lỗi dịch + timing ----------
function _mmss(sec) { sec = Math.max(0, Math.floor(sec)); return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); }
// ---------- Log per-job + dọn file tạm + ưu tiên hàng đợi ----------
let _logJobId = null;
function closeLog() { document.getElementById("log-modal").style.display = "none"; }
async function openLog(id) {
  _logJobId = id;
  const body = document.getElementById("log-body");
  body.textContent = "Đang tải log…";
  document.getElementById("log-modal").style.display = "flex";
  try {
    const r = await fetch(`/api/jobs/${id}/log?lines=300`);
    const d = await r.json().catch(() => ({}));
    body.textContent = r.ok ? (d.log || "(log rỗng)") : ("Lỗi: " + (d.detail || r.status));
    body.scrollTop = body.scrollHeight;   // nhảy xuống cuối — dòng lỗi mới nhất
  } catch (e) { body.textContent = "Lỗi mạng khi tải log."; }
}

async function cleanJob(id) {
  if (!confirm("Dọn file âm thanh trung gian của job này?\n\nGiữ nguyên: video final, phụ đề, bản dịch, giọng đã đọc, video nguồn.\nSau này nếu 'Chỉnh sửa', app sẽ tự tách audio lại từ nguồn (chậm hơn một chút)."))
    return;
  try {
    const r = await fetch(`/api/jobs/${id}/clean`, { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast("Không dọn được: " + (d.detail || r.status)); return; }
    toast(`🧹 Đã dọn ${d.freed_mb} MB file trung gian.`);
  } catch (e) { toast("Lỗi mạng khi dọn."); }
  refresh();
}

async function prioritizeJob(id) {
  try {
    const r = await fetch(`/api/jobs/${id}/prioritize`, { method: "POST" });
    if (!r.ok) { const d = await r.json().catch(() => ({})); toast(d.detail || "Không đổi được thứ tự."); }
  } catch (e) { toast("Lỗi mạng."); }
  delete lastJson[id];
  refresh();
}

// ---------- #15 Glossary theo job: xem/duyệt tên riêng Claude gợi ý ----------
let _glJobId = null, _glSuggest = [];
function closeGloss() { document.getElementById("gloss-modal").style.display = "none"; }

async function openGloss(id) {
  _glJobId = id;
  const jobs = await (await fetch("/api/jobs")).json().catch(() => []);
  const j = (jobs || []).find(x => x.id === id) || {};
  document.getElementById("gl-text").value = j.glossary || "";
  const sw = document.getElementById("gl-series-wrap");
  if (j.series) {
    sw.style.display = "";
    document.getElementById("gl-series-name").textContent = j.series;
  } else sw.style.display = "none";
  document.getElementById("gl-msg").textContent = "";
  document.getElementById("gl-suggest").innerHTML = "⏳ Đang trích tên riêng từ video…";
  document.getElementById("gloss-modal").style.display = "flex";
  try {
    const r = await fetch(`/api/jobs/${id}/glossary-suggest`);
    const d = await r.json().catch(() => ({}));
    if (!r.ok) {
      document.getElementById("gl-suggest").innerHTML =
        `<span class="err">${esc(d.detail || "Không trích được gợi ý")}</span>`;
      return;
    }
    _glSuggest = d.pairs || [];
    renderGlossSuggest();
  } catch (e) {
    document.getElementById("gl-suggest").innerHTML = '<span class="err">Lỗi mạng khi trích gợi ý.</span>';
  }
}

function _glHave() {   // các tên gốc đã có trong textarea (để đánh dấu ✓)
  const have = new Set();
  for (const line of document.getElementById("gl-text").value.split("\n")) {
    const z = line.split("=")[0].trim();
    if (z && !z.startsWith("#")) have.add(z);
  }
  return have;
}

function renderGlossSuggest() {
  const box = document.getElementById("gl-suggest");
  if (!_glSuggest.length) { box.innerHTML = '<span class="meta">Không trích được tên riêng nào từ video này.</span>'; return; }
  const have = _glHave();
  let h = `<div class="row" style="justify-content:space-between;margin-bottom:4px">
    <b>Gợi ý từ video (${_glSuggest.length})</b>
    <button class="ghost" type="button" onclick="glossAddAll()">➕ Thêm tất cả</button></div>`;
  h += _glSuggest.map((p, i) => {
    const got = have.has(p.zh);
    return `<div class="row" style="padding:3px 0;border-bottom:1px solid var(--border)">
      <span style="flex:1">${esc(p.zh)} = ${esc(p.vi)}</span>
      ${got ? '<span style="color:var(--ok)">✓ đã có</span>'
            : `<button class="ghost" type="button" onclick="glossAdd(${i})">➕</button>`}</div>`;
  }).join("");
  box.innerHTML = h;
}

function glossAdd(i) {
  const p = _glSuggest[i];
  if (!p || _glHave().has(p.zh)) return renderGlossSuggest();
  const ta = document.getElementById("gl-text");
  ta.value = (ta.value.trimEnd() + `\n${p.zh}=${p.vi}`).trim();
  renderGlossSuggest();
}
function glossAddAll() {
  const ta = document.getElementById("gl-text");
  const have = _glHave();
  const lines = _glSuggest.filter(p => !have.has(p.zh)).map(p => `${p.zh}=${p.vi}`);
  if (lines.length) ta.value = (ta.value.trimEnd() + "\n" + lines.join("\n")).trim();
  renderGlossSuggest();
}

async function glossSave(retranslate) {
  if (retranslate && !confirm("Dịch lại với glossary mới?\n\nBản dịch + lồng tiếng + video final hiện tại sẽ bị xoá và job chạy lại từ bước dịch (tốn thời gian + phí dịch)."))
    return;
  const msg = document.getElementById("gl-msg");
  msg.style.color = "var(--dim)"; msg.textContent = "Đang lưu…";
  try {
    const r = await fetch(`/api/jobs/${_glJobId}/glossary`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ glossary: document.getElementById("gl-text").value,
        save_series: !!document.getElementById("gl-series")?.checked && document.getElementById("gl-series-wrap").style.display !== "none",
        retranslate }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { msg.style.color = "var(--err)"; msg.textContent = "Lỗi: " + (d.detail || r.status); return; }
    msg.style.color = "var(--ok)";
    msg.textContent = "✓ Đã lưu" + (d.series_added ? ` (+${d.series_added} tên vào series)` : "");
    if (retranslate && d.reset) {
      closeGloss();
      await fetch(`/api/jobs/${_glJobId}/resume`, { method: "POST" });  // chạy lại từ bước dịch
      delete lastJson[_glJobId];
      refresh();
    }
  } catch (e) { msg.style.color = "var(--err)"; msg.textContent = "Lỗi mạng."; }
}

function closeQc() { document.getElementById("qc-modal").style.display = "none"; }
async function qcJob(id) {
  const body = document.getElementById("qc-body");
  body.innerHTML = "Đang tải…";
  document.getElementById("qc-modal").style.display = "flex";
  let d;
  try { d = await (await fetch(`/api/jobs/${id}/qc`)).json(); }
  catch (e) { body.innerHTML = '<div class="err">Không tải được QC.</div>'; return; }
  const item = "padding:6px 0;border-bottom:1px solid var(--border);font-size:13px";
  let h = `<div class="meta" style="margin:6px 0">${d.total} câu · <b>${d.suspects.length}</b> câu nghi ngờ · <b>${d.overflow.length}</b> câu tràn timing</div>`;
  if (!d.suspects.length && !d.overflow.length)
    h += `<div style="color:var(--ok)">✓ Không phát hiện lỗi rõ ràng. Vẫn nên xem qua bằng "Sửa lời thoại".</div>`;
  if (d.suspects.length) {
    h += `<h4>Câu dịch nghi ngờ</h4>`;
    h += d.suspects.slice(0, 150).map(s =>
      `<div style="${item}"><b>${_mmss(s.start)}</b> <span class="badge fail">${esc(s.reason)}</span>`
      + (s.text ? `<br><span class="ed-zh">${esc(s.text)}</span>` : "")
      + `<br>${s.text_vi ? esc(s.text_vi) : "<i>(rỗng)</i>"}</div>`).join("");
  }
  if (d.overflow.length) {
    h += `<h4>Timing tràn (giọng Việt dài hơn khoảng trống)</h4>`;
    h += d.overflow.slice(0, 150).map(w =>
      `<div style="${item}"><span class="badge wait">+${w.overflow_ms} ms</span> ${esc(w.text_vi)}</div>`).join("");
  }
  h += `<div class="row" style="margin-top:12px"><button onclick="closeQc();openEditor('${id}')">✏️ Mở Sửa lời thoại</button>`
     + `<button class="ghost" onclick="closeQc()">Đóng</button></div>`;
  body.innerHTML = h;
}

// ---------- #1 Đăng YouTube: gói kéo-thả + đăng thẳng OAuth ----------
async function makePackage(id) {
  try {
    const r = await fetch(`/api/jobs/${id}/package`, { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast("Lỗi tạo gói: " + (d.detail || r.status)); return; }
    toast("📦 Đã tạo gói đăng (đã mở thư mục):\n" + d.folder
      + "\n\nKéo video.mp4 + thumbnail.jpg lên YouTube Studio; tiêu đề/mô tả/tags nằm trong upload_info.txt.");
  } catch (e) { toast("Lỗi mạng khi tạo gói."); }
}
async function makeShorts(id) {   // PLAN 12 #4: cắt đoạn cao trào từ final.mp4
  try {
    const r = await fetch(`/api/jobs/${id}/shorts`, { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast("Không tạo được Shorts: " + (d.detail || r.status)); return; }
    toast("🎬 " + (d.note || "Đang cắt Shorts — xong sẽ tự mở thư mục."));
  } catch (e) { toast("Lỗi mạng khi tạo Shorts."); }
}

async function uploadYT(id) {
  if (!confirm("Đăng video này thẳng lên YouTube?\n\nLần đầu sẽ mở trình duyệt để bạn cho phép. "
    + "Mặc định quyền RIÊNG TƯ (đổi công khai sau trong Cấu hình/YouTube). Quá trình có thể mất vài phút.")) return;
  const msg = document.getElementById("cfgmsg");
  try {
    const r = await fetch(`/api/jobs/${id}/upload-youtube`, { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast("Đăng lỗi: " + (d.detail || r.status)); return; }
    toast("✅ Đã đăng lên YouTube:\n" + d.url + "\n(quyền: " + d.privacy + ")");
  } catch (e) { toast("Lỗi mạng/timeout khi đăng (upload dài — kiểm tra YouTube Studio)."); }
}

// ---------- #17 Cắt video dài thành nhiều phần ----------
function spMode() {
  const m = document.getElementById("sp-mode").value;
  document.getElementById("sp-parts-wrap").style.display = m === "parts" ? "" : "none";
  document.getElementById("sp-cuts-wrap").style.display = m === "cuts" ? "" : "none";
}
async function splitVideo() {
  const url = document.getElementById("sp-url").value.trim();
  const file = document.getElementById("sp-file").files[0];
  const mode = document.getElementById("sp-mode").value;
  const msg = document.getElementById("sp-msg");
  if (!url && !file) { msg.style.color = "var(--err)"; msg.textContent = "Nhập link hoặc chọn file."; return; }
  if (mode === "cuts" && !document.getElementById("sp-cuts").value.trim()) {
    msg.style.color = "var(--err)"; msg.textContent = "Nhập ít nhất 1 mốc cắt."; return;
  }
  const fd = new FormData();
  if (file) fd.append("file", file);
  fd.append("url", url);
  fd.append("mode", mode);
  fd.append("parts", document.getElementById("sp-parts").value || "3");
  fd.append("cuts", document.getElementById("sp-cuts").value || "");
  fd.append("pause_before_render", document.getElementById("pbr").checked ? "true" : "false");
  fd.append("glossary", document.getElementById("gloss").value || "");
  fd.append("series", document.getElementById("series").value.trim() || "");
  msg.style.color = "var(--dim)"; msg.textContent = "Đang gửi…";
  try {
    const r = await fetch("/api/jobs/split", { method: "POST", body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { msg.style.color = "var(--err)"; msg.textContent = "Lỗi: " + (d.detail || r.status); return; }
    msg.style.color = "var(--ok)"; msg.textContent = d.note || "Đang cắt…";
    document.getElementById("sp-url").value = ""; document.getElementById("sp-file").value = "";
    setTimeout(refresh, 1500);
  } catch (e) { msg.style.color = "var(--err)"; msg.textContent = "Lỗi mạng."; }
}

document.getElementById("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = document.getElementById("url").value.trim();
  if (!text) return;
  const btn = document.getElementById("addbtn");
  const single = !/\s/.test(text) && !/[?&]list=|\/playlist|\/@|\/channel\//.test(text);

  const pbr = document.getElementById("pbr").checked;
  const gloss = document.getElementById("gloss").value;
  const series = document.getElementById("series").value.trim();
  if (single) {
    await fetch("/api/jobs", { method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: text, pause_before_render: pbr, glossary: gloss, series}) });
  } else {
    btn.disabled = true;
    btn.textContent = "⏳ Đang đọc danh sách...";
    try {
      const res = await fetch("/api/expand", { method: "POST",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify({text}) });
      if (!res.ok) { toast((await res.json()).detail || "Không đọc được danh sách"); return; }
      const { entries, new: nNew } = await res.json();
      const dup = entries.length - nNew;
      if (!nNew) { toast(`Cả ${entries.length} video đều đã có job — không thêm gì.`); return; }
      const names = entries.filter(e => !e.duplicate).slice(0, 10)
        .map(e => "• " + e.title).join("\n");
      if (!confirm(`Tìm thấy ${entries.length} video` +
          (dup ? ` (${dup} trùng job cũ, bỏ qua)` : "") +
          `.\nThêm ${nNew} video? (sẽ ở trạng thái "Chờ chạy" — bấm ▶ Chạy để bắt đầu)\n\n${names}${nNew > 10 ? "\n..." : ""}`))
        return;
      await fetch("/api/jobs/batch", { method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({urls: entries.filter(e => !e.duplicate).map(e => e.url), pause_before_render: pbr, glossary: gloss, series}) });
    } finally {
      btn.disabled = false;
      btn.textContent = "＋ Thêm job";
    }
  }
  document.getElementById("url").value = "";
  refresh();
});

const DUP_TYPE = {vietsub: "vietsub", long_tieng: "lồng tiếng/thuyết minh", khong_ro: "không rõ loại"};
const DUP_COV = {vietsub: "đã có VIETSUB", long_tieng: "đã có LỒNG TIẾNG",
                 ca_hai: "đã có CẢ vietsub LẪN lồng tiếng", khong_ro: "có bản Việt nhưng không rõ loại",
                 khong_co: "chưa thấy bản Việt"};
const DUP_CONF = {cao: "cao", trung_binh: "trung bình", thap: "thấp"};

async function checkDup() {
  const text = document.getElementById("url").value.trim();
  const box = document.getElementById("dupresult");
  box.style.display = "block";
  if (!text || /\s/.test(text)) {
    box.innerHTML = "⚠️ Dán đúng MỘT link video (không phải nhiều link/playlist) để kiểm tra.";
    return;
  }
  const btn = document.getElementById("dupbtn");
  btn.disabled = true; btn.textContent = "⏳ Đang tra YouTube (~15s)...";
  box.innerHTML = "Đang lấy thông tin video và tìm trên YouTube...";
  try {
    const res = await fetch("/api/check-dup", { method: "POST",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({url: text}) });
    box.innerHTML = renderDup(await res.json());
  } catch (e) {
    box.innerHTML = "Lỗi khi kiểm tra: " + e;
  } finally {
    btn.disabled = false; btn.textContent = "🔎 Kiểm tra đã có bản Việt?";
  }
}

function renderDup(r) {
  if (r.status === "no_api_key")
    return "⚠️ Chưa có ANTHROPIC_API_KEY trong .env nên không phân tích được. Hãy điền key rồi thử lại.";
  if (r.status === "no_title") return "⚠️ Không lấy được tiêu đề video — kiểm tra lại link.";
  if (r.status === "error") return "❌ Lỗi: " + (r.error || "không rõ");

  const n = r.normalized || {}, v = r.verdict || {};
  const matches = v.matches || [];
  let html = `<b>Nhận diện:</b> ${esc(n.series_vi || "?")}`
    + (n.episode != null ? ` — tập ${esc(n.episode)}` : (n.kind === "tron_bo" ? " — bản tổng hợp" : ""))
    + `<br>`;
  if (!v.already_exists) {
    html += `✅ <b>Có vẻ CHƯA có bản Việt</b> trong ${r.candidate_count || 0} kết quả tìm được `
      + `(độ tin cậy: ${DUP_CONF[v.confidence] || "?"}).<br>`
      + `<span class="meta">Lưu ý: "không thấy" KHÔNG chắc chắn 100% là chưa ai làm — chỉ là không có trong top kết quả.</span>`;
  } else {
    html += `⚠️ <b>Có thể ĐÃ CÓ bản Việt</b> — ${DUP_COV[v.coverage] || "?"} `
      + `(tin cậy: ${DUP_CONF[v.confidence] || "?"}).<br>`;
    if (!matches.length)
      html += `<span class="meta">(không trích được link cụ thể từ kết quả)</span><br>`;
    for (const m of matches) {
      const views = m.views != null ? ` · ${(+m.views).toLocaleString()} views` : "";
      const label = esc(m.title || "(không tên)");
      const link = m.url
        ? `<a href="${esc(safeUrl(m.url))}" target="_blank" rel="noopener">${label}</a>`
        : label;
      html += `&nbsp;&nbsp;• ${link}`
        + ` <span class="meta">— ${esc(m.channel || "")}${views} · ${DUP_TYPE[m.type] || "không rõ"}</span><br>`;
    }
  }
  if (v.reason) html += `<span class="meta">${esc(v.reason)}</span>`;
  return html;
}

function toggleCoverSliders(id) {
  const auto = document.getElementById("cv-" + id).value === "auto";
  for (const p of ["ct", "cb", "cw"])
    document.getElementById(p + "-" + id).disabled = auto;
}

// Hai cạnh băng che đẩy nhau, giữ khoảng hở tối thiểu 5% (từ < đến)
function syncBand(id, which) {
  const ct = document.getElementById("ct-" + id);
  const cb = document.getElementById("cb-" + id);
  if (which === "ct" && +ct.value > +cb.value - 5) cb.value = Math.min(100, +ct.value + 5);
  if (which === "cb" && +cb.value < +ct.value + 5) ct.value = Math.max(0, +cb.value - 5);
  document.getElementById("pct-" + id).textContent = ct.value + "%";
  document.getElementById("cbp-" + id).textContent = cb.value + "%";
}

function readOpts(id) {
  const g = (p) => document.getElementById(p + "-" + id);
  return {
    subtitle_mode: g("sm").value,
    cover: g("cv").value,
    cover_top: parseInt(g("ct").value) / 100,
    cover_bottom: parseInt(g("cb").value) / 100,
    cover_width: parseInt(g("cw").value) / 100,
    fx: (g("fx") && g("fx").value) || "",   // "" = theo cấu hình chung (server không lưu key)
    frame: (g("frm") && g("frm").value) || "none",
    frame_color: (g("frmc") && g("frmc").value) || "#FFD700",
    frame_color2: (g("frmc2") && g("frmc2").value) || "#FFFFFF",
    frame_width: (g("frmw") ? parseFloat(g("frmw").value) : 2) / 100,
    frame_pad: !!(g("frmp") && g("frmp").checked),
    sub_split: g("sspl") ? g("sspl").value === "1" : true,
    wm_method: (g("wmm") && g("wmm").value) || "none",
    wm_box: g("wmx") ? (() => {
      const x = (+g("wmx").value || 0) / 100, y = (+g("wmy").value || 0) / 100;
      const w = (+g("wmw").value || 0) / 100, h = (+g("wmh").value || 0) / 100;
      return [x, y, Math.min(1, x + w), Math.min(1, y + h)];
    })() : [],
    crop: g("crl") ? [(+g("crl").value || 0) / 100, (+g("crt").value || 0) / 100,
                      (+g("crr").value || 0) / 100, (+g("crb").value || 0) / 100] : [],
    style: {
      font: g("ft").value,
      size: parseInt(g("fs").value),
      color: g("fc").value,
      outline_color: g("oc").value,
      outline: parseInt(g("ow").value),
      back: g("bk").checked,
      back_color: g("bc").value,
      back_opacity: parseInt(g("bo").value) / 100,
      margin_v: parseInt(g("mv").value),
    },
  };
}

async function resumeJob(id) {
  await fetch(`/api/jobs/${id}/resume`, { method: "POST" });
  // ép thẻ vẽ lại dù panel cài đặt đang mở (refresh() bỏ qua card có details[open])
  document.querySelector(`#card-${id} details`)?.removeAttribute("open");
  delete lastJson[id];
  refresh();
}

async function runAllPending() {
  await fetch("/api/jobs/run-all", { method: "POST" });
  refresh();
}

async function cancelJob(id) {   // #12 dừng job đang chạy/chờ (checkpoint vẫn còn → chạy tiếp sau)
  if (!confirm("Dừng job này? Có thể bấm 'Chạy tiếp' sau để chạy nốt từ chỗ dừng.")) return;
  try {
    const r = await fetch(`/api/jobs/${id}/cancel`, { method: "POST" });
    // 409 = job vừa chạy xong/không còn trong hàng → không phải lỗi, chỉ cần làm mới
    if (!r.ok && r.status !== 409) toast("Không hủy được: " + (await r.text()));
  } catch (e) { toast("Lỗi mạng khi hủy."); }
  delete lastJson[id];
  refresh();
}

// Upload video từ máy → tạo job (xử lý y như link). Dùng XHR để có thanh % upload.
function uploadVideo() {
  const inp = document.getElementById("upfile");
  const f = inp.files && inp.files[0];
  if (!f) { toast("Chọn 1 file video trước đã."); return; }
  const fd = new FormData();
  fd.append("file", f);
  fd.append("pause_before_render", document.getElementById("pbr").checked ? "true" : "false");
  fd.append("glossary", document.getElementById("gloss").value || "");
  fd.append("series", document.getElementById("series").value.trim() || "");
  const btn = document.getElementById("upbtn");
  const box = document.getElementById("upprogress");
  const setBar = (pct, label) => {
    box.innerHTML = `<div class="prog"><div class="prog-lbl">${esc(label)}</div>`
      + `<div class="bar"><span style="width:${pct}%"></span></div></div>`;
  };
  const done = () => { btn.disabled = false; btn.textContent = "📁 Upload video từ máy"; };
  btn.disabled = true; btn.textContent = "⏳ Đang tải lên...";
  setBar(0, "Đang tải lên: " + f.name);
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/jobs/upload");
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round(e.loaded / e.total * 100);
    const mb = (n) => (n / 1048576).toFixed(0);
    if (pct >= 100) setBar(100, "Đã tải xong — server đang lưu file…");
    else setBar(pct, `Đang tải lên ${f.name} · ${pct}% (${mb(e.loaded)}/${mb(e.total)} MB)`);
  };
  xhr.onload = () => {
    done(); box.innerHTML = "";
    if (xhr.status >= 200 && xhr.status < 300) { inp.value = ""; refresh(); }
    else toast("Upload lỗi: " + _errDetail(xhr.responseText, xhr.status));
  };
  xhr.onerror = () => { done(); box.innerHTML = ""; toast("Upload lỗi mạng / đứt kết nối."); };
  try { xhr.send(fd); } catch (e) { done(); box.innerHTML = ""; toast("Không gửi được: " + e); }
}

