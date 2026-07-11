// #17 tách monolith — NỘI DUNG: tab Chỉnh giao diện (job visual) + editor khung/logo/watermark/crop + khởi động app (refresh đầu + interval).
// đúng thứ tự cũ (classic script — cùng global scope, hành vi không đổi).
// ========== #task "Chỉnh giao diện" (job.mode=="visual"): chỉ tải video về rồi áp
// khung viền/logo/watermark/crop/che sub gốc — KHÔNG dịch/lồng tiếng, không tốn phí
// AI. Dùng lại tối đa hạ tầng job/pipeline/render sẵn có (xem server: list_jobs mode=,
// rerender/preview endpoint y hệt editor lồng tiếng, chỉ khác payload). ==========
let visJobId = null;       // id job đang mở trong editor; null = đang ở danh sách
let visRenderWatch = null; // job đang render (đợi qua visWaitRender) — chặn thao tác chồng chéo
let _visJobsSeen = {};      // diff thẻ như lastJson, tránh vẽ lại thẻ không đổi

async function loadVisualTab() {
  if (visJobId) return;   // đang mở editor 1 job → danh sách khỏi vẽ lại
  if (document.getElementById("pane-visual").style.display === "none") return;  // tab khác → khỏi poll phí
  let jobs;
  try { jobs = await (await fetch("/api/jobs?mode=visual")).json(); }
  catch (e) { return; }
  const grid = document.getElementById("vis-jobs");
  const seen = new Set();
  if (!jobs.length) {
    seen.add("vis-empty");
    if (!document.getElementById("vis-empty")) {
      const d = document.createElement("div");
      d.id = "vis-empty"; d.className = "empty";
      d.innerHTML = "🎨<div><b>Chưa có video nào</b></div>"
        + "<div class='meta'>Dán link hoặc 📁 Upload video ở trên — chỉ tải về để chỉnh khung viền/logo/watermark, không dịch/lồng tiếng, gần như tức thời.</div>";
      grid.appendChild(d);
    }
  } else {
    document.getElementById("vis-empty")?.remove();
  }
  for (const j of jobs) {
    seen.add("vcard-" + j.id);
    let card = document.getElementById("vcard-" + j.id);
    if (!card) {
      card = document.createElement("div");
      card.className = "card"; card.id = "vcard-" + j.id;
      grid.appendChild(card);
    }
    const json = JSON.stringify(j);
    if (_visJobsSeen[j.id] === json) continue;
    _visJobsSeen[j.id] = json;
    card.innerHTML = visCardHtml(j);
  }
  for (const card of [...grid.children]) {
    if (seen.has(card.id)) continue;
    card.remove();
    delete _visJobsSeen[card.id.replace("vcard-", "")];
  }
}

function visCardHtml(j) {
  const ready = j.stage === "paused" || j.stage === "done" || j.has_final;
  let body = `<h3 style="margin:0 0 6px;font-size:14px;word-break:break-all">${esc(j.url)}</h3>`;
  body += jobProgressHTML(j);
  if (j.stage === "failed") body += `<div class="err">${esc(j.error || "Lỗi không rõ")}</div>`;
  body += `<div class="row" style="margin-top:8px">`;
  if (ready) body += `<button onclick="openVisualEditor('${j.id}')">🎨 Chỉnh sửa</button>`;
  else if (!j.running && !j.queued && j.stage !== "failed")
    body += `<button onclick="resumeJob('${j.id}').then(loadVisualTab)">▶ Chạy</button>`;
  if (j.has_final)
    body += `<a class="ghost" href="/api/jobs/${j.id}/video" download title="Tải video đã render"`
          + ` style="display:inline-flex;align-items:center;padding:0 12px;border-radius:8px;text-decoration:none">⬇ Tải video</a>`;
  body += `<button class="ghost" type="button" onclick="openJob('${j.id}')" title="Mở thư mục job">📂</button>`;
  body += `<button class="ghost" type="button" onclick="deleteVisualJob('${j.id}')" title="Xóa job">🗑</button>`;
  body += `</div>`;
  return body;
}

async function deleteVisualJob(id) {
  if (!confirm(`Xóa job ${id}?\nVideo đã tải/render của job này sẽ bị xóa khỏi ổ đĩa.`)) return;
  const res = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  if (!res.ok) toast((await res.json()).detail || "Không xóa được");
  delete _visJobsSeen[id];
  loadVisualTab();
}

async function addVisualJob() {
  const ta = document.getElementById("vis-url");
  const lines = ta.value.split("\n").map(s => s.trim()).filter(Boolean);
  if (!lines.length) { toast("Dán link video trước đã."); return; }
  const btn = document.getElementById("visaddbtn");
  btn.disabled = true;
  try {
    for (const line of lines) {
      const res = await fetch("/api/jobs", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: line, mode: "visual" }) });
      if (!res.ok) toast("Lỗi thêm '" + line + "': " + _errDetail(await res.text(), res.status));
    }
    ta.value = "";
    loadVisualTab();
  } finally { btn.disabled = false; }
}

function uploadVisualVideo() {
  const inp = document.getElementById("vis-upfile");
  const f = inp.files && inp.files[0];
  if (!f) { toast("Chọn 1 file video trước đã."); return; }
  const fd = new FormData();
  fd.append("file", f);
  fd.append("mode", "visual");
  const btn = document.getElementById("visupbtn");
  const box = document.getElementById("vis-upprogress");
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
    if (xhr.status >= 200 && xhr.status < 300) { inp.value = ""; loadVisualTab(); }
    else toast("Upload lỗi: " + _errDetail(xhr.responseText, xhr.status));
  };
  xhr.onerror = () => { done(); box.innerHTML = ""; toast("Upload lỗi mạng / đứt kết nối."); };
  try { xhr.send(fd); } catch (e) { done(); box.innerHTML = ""; toast("Không gửi được: " + e); }
}

// ---------- Editor "Chỉnh giao diện" cho 1 job ----------
async function openVisualEditor(id) {
  let data;
  try { data = await (await fetch(`/api/jobs/${id}/visual`)).json(); }
  catch (e) { toast("Không mở được: " + e); return; }
  visJobId = id;
  const vsrc = data.has_final ? `/api/jobs/${id}/video` : `/api/jobs/${id}/source`;
  document.getElementById("pane-visual").style.display = "none";
  const pane = document.getElementById("pane-visual-edit");
  pane.innerHTML = `
    <div class="ed-top">
      <button class="ghost" onclick="closeVisualEditor()">← Quay lại</button>
      <b>Chỉnh giao diện</b>
      <span class="meta" id="vismsg"></span>
    </div>
    <div style="max-width:640px">
      <div id="vis-stage">
        <div class="ed-vwrap" id="vis-vwrap">
          <video id="visvideo" preload="metadata" src="${vsrc}"></video>
          <div class="ed-cover-ov" id="vis-cover-ov"></div>
          <div class="ed-frame-ov" id="vis-frame-ov"></div>
          <div class="wm-ov" id="vis-wm-ov"></div>
          <div class="crop-ov" id="vis-crop-ov"></div>
        </div>
        <div class="ed-player">
          <button class="ghost" id="visplay" onclick="visTogglePlay()" title="Phát / Dừng">▶</button>
          <input type="range" id="visseek" min="0" max="1000" value="0" step="1" oninput="visSeekBar(this.value)" title="Tua">
          <span class="meta" id="vistime">0:00 / 0:00</span>
          <button class="ghost" id="vismutebtn" onclick="visToggleMute()" title="Tắt / bật tiếng">🔊</button>
          <input type="range" id="visvol" min="0" max="100" value="100" oninput="visSetVol(this.value)" title="Âm lượng">
          <button class="ghost" onclick="visFullscreen()" title="Toàn màn hình">⛶</button>
        </div>
      </div>
      <div class="meta" style="margin:6px 0 0">${data.has_final ? "Đang xem BẢN ĐÃ RENDER." : "Đang xem video GỐC — khung/che/watermark bên dưới là xem trước gần đúng (bản chính xác sau khi bấm 🎨 Xuất video)."}${data.has_audio ? "" : " Video này KHÔNG có âm thanh."}</div>
    </div>
    ${visSettingsPanel(data)}
    <div class="ed-actionbar">
      <button onclick="visSaveRender()" id="vissavebtn">🎨 Xuất video</button>
      <span class="meta" id="vismsg2"></span>
    </div>`;
  pane.style.display = "";
  const v = document.getElementById("visvideo");
  v.addEventListener("loadedmetadata", () => { visUpdateOverlay(); visUpdatePlayer(); });
  v.addEventListener("timeupdate", visUpdatePlayer);
  v.addEventListener("play", () => { document.getElementById("visplay").textContent = "⏸"; });
  v.addEventListener("pause", () => { document.getElementById("visplay").textContent = "▶"; });
  visUpdateOverlay();
}

function closeVisualEditor() {
  _teardownVisualMedia();
  const pane = document.getElementById("pane-visual-edit");
  pane.style.display = "none"; pane.innerHTML = "";
  visJobId = null; visRenderWatch = null;
  document.getElementById("pane-visual").style.display = "";
  loadVisualTab();
}

function _teardownVisualMedia() {
  const v = document.getElementById("visvideo"); if (v) v.pause();
  const img = document.getElementById("vis-preview-frame");
  if (img && img.src && img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
}

function visTogglePlay() {
  const v = document.getElementById("visvideo");
  if (v.paused) v.play().catch(() => {}); else v.pause();
}
function visToggleMute() {
  const v = document.getElementById("visvideo");
  v.muted = !v.muted;
  document.getElementById("vismutebtn").textContent = v.muted ? "🔇" : "🔊";
}
function visSetVol(val) { document.getElementById("visvideo").volume = val / 100; }
function visSeekBar(val) {
  const v = document.getElementById("visvideo");
  if (v.duration) v.currentTime = (val / 1000) * v.duration;
}
function visUpdatePlayer() {
  const v = document.getElementById("visvideo");
  if (!v.duration) return;
  document.getElementById("visseek").value = Math.round((v.currentTime / v.duration) * 1000);
  const fmt = (s) => { s = Math.floor(s); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
  document.getElementById("vistime").textContent = fmt(v.currentTime) + " / " + fmt(v.duration);
}
function visFullscreen() {
  const el = document.getElementById("vis-stage");
  if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
}

function visSettingsPanel(data) {
  const r = data.render || {};
  const cv = r.cover || "none";
  const ct = Math.round((r.cover_top ?? 0.78) * 100), cb = Math.round((r.cover_bottom ?? 1.0) * 100), cw = Math.round((r.cover_width ?? 1.0) * 100);
  const frame = r.frame || "none";
  const frameColor = r.frame_color || "#FFD700";
  const frameColor2 = r.frame_color2 || "#FFFFFF";
  const frameW = Math.round((r.frame_width ?? 0.02) * 1000) / 10;
  const framePad = r.frame_pad ? "checked" : "";
  const wmM = r.wm_method || "none";
  const wb = (r.wm_box && r.wm_box.length === 4) ? r.wm_box : [0.80, 0.03, 0.97, 0.12];
  const wmX = Math.round(wb[0] * 100), wmY = Math.round(wb[1] * 100);
  const wmW = Math.max(1, Math.round((wb[2] - wb[0]) * 100));
  const wmH = Math.max(1, Math.round((wb[3] - wb[1]) * 100));
  const cr = (r.crop && r.crop.length === 4) ? r.crop : [0, 0, 0, 0];
  const crL = Math.round(cr[0] * 100), crT = Math.round(cr[1] * 100);
  const crR = Math.round(cr[2] * 100), crB = Math.round(cr[3] * 100);
  const FRAME_PRESETS = [["none", "Không khung"], ["solid", "Viền đơn"], ["double", "Viền đôi"],
    ["twocolor", "Viền 2 màu"], ["corner", "Bo góc / 4 góc"]];
  const pngFrames = data.frames || [];
  const frameOptsHtml = FRAME_PRESETS.map(([v, l]) => `<option value="${v}" ${frame === v ? "selected" : ""}>${l}</option>`).join("")
    + pngFrames.map(n => `<option value="png:${esc(n)}" ${frame === "png:" + n ? "selected" : ""}>🖼 ${esc(n)}</option>`).join("");
  return `<details class="ed-settings" open>
    <summary>🎨 Khung viền / logo / watermark / che sub gốc</summary>
    <div oninput="visUpdateOverlay()" onchange="visUpdateOverlay()">
    <div class="opts">🖼 Khung viền: <select id="frm-vis" onchange="visToggleFrameCtl()">${frameOptsHtml}</select>
      Màu: <input type="color" id="frmc-vis" value="${esc(frameColor)}">
      <span id="frmc2-wrap-vis">Màu 2: <input type="color" id="frmc2-vis" value="${esc(frameColor2)}"></span>
      Độ dày: <input type="range" id="frmw-vis" min="0.5" max="6" step="0.1" value="${frameW}"
             oninput="document.getElementById('frmwp-vis').textContent=this.value+'%'">
      <span class="pct" id="frmwp-vis">${frameW}%</span>
      <label><input type="checkbox" id="frmp-vis" ${framePad}> Khung ngoài (thu hình vào trong — khung không che mép video)</label>
      <span class="meta">Khung PNG: thả file .png (nền giữa trong suốt) vào thư mục frames/ — tự co giãn 9-slice, không méo hoa văn. Logo kênh đặt trong Cấu hình → Thương hiệu (áp mọi video, kể cả video chỉnh ở đây).</span></div>
    <div class="opts">🚿 Watermark kênh gốc:
      <select id="wmm-vis">
        <option value="none" ${wmM === "none" ? "selected" : ""}>Không xử lý</option>
        <option value="delogo" ${wmM === "delogo" ? "selected" : ""}>Xóa (delogo — vệt mờ nhẹ)</option>
        <option value="blur" ${wmM === "blur" ? "selected" : ""}>Làm mờ vùng</option>
        <option value="black" ${wmM === "black" ? "selected" : ""}>Dải đen</option>
        <option value="logo" ${wmM === "logo" ? "selected" : ""}>Đè logo kênh mình</option>
      </select>
      Vùng: X <input type="number" id="wmx-vis" min="0" max="99" value="${wmX}" style="width:52px">%
      Y <input type="number" id="wmy-vis" min="0" max="99" value="${wmY}" style="width:52px">%
      Rộng <input type="number" id="wmw-vis" min="1" max="100" value="${wmW}" style="width:52px">%
      Cao <input type="number" id="wmh-vis" min="1" max="100" value="${wmH}" style="width:52px">%
      <span class="meta">Khung đỏ trên video = vùng sẽ xử lý (suốt thời lượng). "Xóa" hợp watermark TĨNH ở góc; "Đè logo" dùng logo trong thư mục logo/ (tab Cấu hình).</span></div>
    <div class="opts">✂ Cắt mép:
      Trên <input type="number" id="crt-vis" min="0" max="20" value="${crT}" style="width:52px">%
      Dưới <input type="number" id="crb-vis" min="0" max="20" value="${crB}" style="width:52px">%
      Trái <input type="number" id="crl-vis" min="0" max="20" value="${crL}" style="width:52px">%
      Phải <input type="number" id="crr-vis" min="0" max="20" value="${crR}" style="width:52px">%
      <span class="meta">Cắt dải watermark sát rìa rồi phóng lại đúng cỡ — sạch tuyệt đối, mất một dải hình (khung xanh = phần GIỮ LẠI).</span></div>
    <div class="opts">
      Che sub gốc: <select id="cv-vis" onchange="visToggleCoverSliders()">
        <option value="none" ${cv === "none" ? "selected" : ""}>Không che</option>
        <option value="blur" ${cv === "blur" ? "selected" : ""}>Làm mờ</option>
        <option value="black" ${cv === "black" ? "selected" : ""}>Dải đen</option></select>
      <span class="meta">(Không có "tự động" — video này chưa từng OCR nên chỉnh tay dải che bên dưới.)</span>
    </div>
    <div class="opts">
      Vùng che từ: <input type="range" id="ct-vis" min="0" max="97" value="${ct}" ${cv === "none" ? "disabled" : ""} oninput="syncBand('vis','ct')">
      <span class="pct" id="pct-vis">${ct}%</span>
      đến: <input type="range" id="cb-vis" min="3" max="100" value="${cb}" ${cv === "none" ? "disabled" : ""} oninput="syncBand('vis','cb')">
      <span class="pct" id="cbp-vis">${cb}%</span>
      Rộng: <input type="range" id="cw-vis" min="20" max="100" value="${cw}" ${cv === "none" ? "disabled" : ""} oninput="document.getElementById('cwp-vis').textContent=this.value+'%'">
      <span class="pct" id="cwp-vis">${cw}%</span>
    </div>
    <div class="meta">Xem trước ở trên là gần đúng (CSS). Bấm 👁 bên dưới để dựng thử 1 khung bằng FFmpeg — chính xác 100%. Bấm 🎨 Xuất video (thanh dưới cùng) để render thật.</div>
    <div class="row">
      <button class="ghost" id="vispvbtn" onclick="visPreviewFrame()" title="Dựng thử 1 khung bằng FFmpeg — chính xác hơn xem trước trực tiếp">👁 Xem trước 1 khung (chính xác)</button>
    </div>
    <img class="preview" id="vis-preview-frame" style="display:none">
    </div>
  </details>`;
}

function visToggleCoverSliders() {
  const off = document.getElementById("cv-vis").value === "none";
  for (const p of ["ct", "cb", "cw"]) document.getElementById(p + "-vis").disabled = off;
}

function visReadOpts() {
  const g = (p) => document.getElementById(p + "-vis");
  const wx = (+g("wmx").value || 0) / 100, wy = (+g("wmy").value || 0) / 100;
  const ww = (+g("wmw").value || 0) / 100, wh = (+g("wmh").value || 0) / 100;
  return {
    subtitle_mode: "cover_only",   // #task: không bao giờ vẽ phụ đề MỚI (không có bản dịch)
    cover: g("cv").value,
    cover_top: parseInt(g("ct").value) / 100,
    cover_bottom: parseInt(g("cb").value) / 100,
    cover_width: parseInt(g("cw").value) / 100,
    frame: g("frm").value,
    frame_color: g("frmc").value,
    frame_color2: g("frmc2").value,
    frame_width: parseFloat(g("frmw").value) / 100,
    frame_pad: g("frmp").checked,
    wm_method: g("wmm").value,
    wm_box: [wx, wy, Math.min(1, wx + ww), Math.min(1, wy + wh)],
    crop: [(+g("crl").value || 0) / 100, (+g("crt").value || 0) / 100,
           (+g("crr").value || 0) / 100, (+g("crb").value || 0) / 100],
  };
}

function visUpdateOverlay() {
  if (!document.getElementById("cv-vis")) return;
  const o = visReadOpts();
  const cov = document.getElementById("vis-cover-ov");
  if (cov) {
    if (o.cover === "none") { cov.style.display = "none"; }
    else {
      const top = o.cover_top * 100, bot = o.cover_bottom * 100, w = o.cover_width * 100;
      cov.style.display = "block";
      cov.style.top = top + "%"; cov.style.height = Math.max(0, bot - top) + "%";
      cov.style.left = ((100 - w) / 2) + "%"; cov.style.width = w + "%";
      if (o.cover === "black") { cov.style.background = "#000"; cov.style.backdropFilter = cov.style.webkitBackdropFilter = "none"; }
      else { cov.style.background = "rgba(0,0,0,.04)"; cov.style.backdropFilter = cov.style.webkitBackdropFilter = "blur(7px)"; }
    }
  }
  const fov = document.getElementById("vis-frame-ov");
  if (fov) {
    const v = document.getElementById("visvideo");
    if (!o.frame || o.frame === "none") {
      fov.style.display = "none";
    } else if (o.frame.startsWith("png:")) {
      fov.style.display = "block"; fov.style.border = "none"; fov.style.boxShadow = "none";
      fov.style.backgroundImage = `url(/api/frames/${encodeURIComponent(o.frame.slice(4))})`;
    } else {
      fov.style.display = "block"; fov.style.backgroundImage = "none";
      const px = Math.max(1, Math.round(o.frame_width * (v && v.clientHeight ? v.clientHeight : 360)));
      fov.style.border = `${px}px ${o.frame === "double" ? "double" : "solid"} ${o.frame_color}`;
      fov.style.boxShadow = (o.frame === "twocolor") ? `inset 0 0 0 ${2 * px}px ${o.frame_color2}` : "none";
      if (o.frame === "corner") fov.style.borderStyle = "dashed";
    }
  }
  const wmo = document.getElementById("vis-wm-ov");
  if (wmo) {
    const on = o.wm_method && o.wm_method !== "none" && o.wm_box.length === 4;
    wmo.style.display = on ? "block" : "none";
    if (on) {
      wmo.style.left = (o.wm_box[0] * 100) + "%"; wmo.style.top = (o.wm_box[1] * 100) + "%";
      wmo.style.width = ((o.wm_box[2] - o.wm_box[0]) * 100) + "%";
      wmo.style.height = ((o.wm_box[3] - o.wm_box[1]) * 100) + "%";
    }
  }
  const cro = document.getElementById("vis-crop-ov");
  if (cro) {
    const c = o.crop || [];
    const on = c.some(v => v > 0.001);
    cro.style.display = on ? "block" : "none";
    if (on) cro.style.inset = `${c[1] * 100}% ${c[2] * 100}% ${c[3] * 100}% ${c[0] * 100}%`;
  }
}

function visToggleFrameCtl() {
  const sel = document.getElementById("frm-vis"); if (!sel) return;
  const f = sel.value;
  const proc = (f === "solid" || f === "double" || f === "twocolor" || f === "corner");
  const c = document.getElementById("frmc-vis"), w = document.getElementById("frmw-vis");
  if (c) c.disabled = !proc;
  if (w) w.disabled = !proc;
  const c2w = document.getElementById("frmc2-wrap-vis");
  if (c2w) c2w.style.display = (f === "twocolor") ? "" : "none";
  visUpdateOverlay();
}

async function visPreviewFrame() {
  if (!visJobId) return;
  const img = document.getElementById("vis-preview-frame");
  const btn = document.getElementById("vispvbtn");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Đang dựng khung..."; }
  if (img) { img.style.display = "block"; img.style.opacity = 0.4; }
  try {
    const res = await fetch(`/api/jobs/${visJobId}/preview`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(visReadOpts()) });
    if (res.ok) {
      if (img && img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
      if (img) img.src = URL.createObjectURL(await res.blob());
    } else {
      const m = document.getElementById("vismsg");
      if (m) m.textContent = "Xem trước lỗi: " + _errDetail(await res.text(), res.status);
    }
  } catch (e) {
    const m = document.getElementById("vismsg"); if (m) m.textContent = "Xem trước lỗi: " + e;
  } finally {
    if (img) img.style.opacity = 1;
    if (btn) { btn.disabled = false; btn.textContent = "👁 Xem trước 1 khung (chính xác)"; }
  }
}

async function visWaitRender(id, onTick) {
  for (let i = 0; i < 200; i++) {   // tối đa ~6-7 phút — render visual (không LLM/TTS) luôn nhanh hơn nhiều
    await new Promise(r => setTimeout(r, 2000));
    let jobs;
    try { jobs = await (await fetch("/api/jobs?mode=visual")).json(); } catch (e) { continue; }
    const j = jobs.find(x => x.id === id);
    if (!j) return null;
    if (!j.running && !j.queued) return j;
    if (onTick) onTick(j);
  }
  return null;
}

async function visSaveRender() {
  if (!visJobId) return;
  const jid = visJobId;
  const btn = document.getElementById("vissavebtn");
  const msg = document.getElementById("vismsg2");
  btn.disabled = true; btn.textContent = "⏳ Đang render...";
  msg.textContent = "";
  const v = document.getElementById("visvideo");
  if (v) { v.pause(); v.removeAttribute("src"); try { v.load(); } catch (e) {} }
  let res, raw;
  try {
    res = await fetch(`/api/jobs/${jid}/rerender`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(visReadOpts()) });
    raw = await res.text();
  } catch (e) {
    msg.textContent = "Lỗi: " + e; btn.disabled = false; btn.textContent = "🎨 Xuất video"; return;
  }
  if (!res.ok) {
    msg.textContent = "Lỗi: " + _errDetail(raw, res.status);
    btn.disabled = false; btn.textContent = "🎨 Xuất video"; return;
  }
  msg.textContent = "Đang render — xem tiến độ bên dưới…";
  const j = await visWaitRender(jid, (jj) => {
    if (visJobId !== jid) return;
    const p = document.getElementById("vismsg");
    if (p) p.innerHTML = jobProgressHTML(jj);
  });
  if (visJobId !== jid) return;   // đã rời/mở job khác trong lúc chờ
  if (!j) { msg.textContent = "Render lâu hơn dự kiến — kiểm tra ở danh sách rồi mở lại."; }
  else if (j.stage === "failed") { msg.textContent = "Render lỗi: " + (j.error || ""); }
  else { openVisualEditor(jid); return; }
  btn.disabled = false; btn.textContent = "🎨 Xuất video";
}

loadFonts().then(refresh);  // nạp danh sách font TRƯỚC rồi mới vẽ thẻ job
loadGlossDefault();
(() => {  // đánh dấu "cấu hình có thay đổi chưa lưu" để nhắc khi rời tab Cấu hình
  const cf = document.getElementById("cfgform");
  if (cf) { cf.addEventListener("change", markCfgDirty); cf.addEventListener("input", markCfgDirty); }
})();
_notifBtnLabel();   // #11 nhãn nút thông báo theo quyền hiện tại
refreshSeriesDatalist();   // #7 đổ danh sách series vào ô "Series" của form
syncQueueState();   // trạng thái tạm dừng hàng đợi (đồng bộ tiếp mỗi 10s)
setInterval(refresh, 3000);
setInterval(refreshStats, 10000);
setInterval(syncQueueState, 10000);
setInterval(loadVisualTab, 3000);   // #task "Chỉnh giao diện": tự early-return khi tab không mở
