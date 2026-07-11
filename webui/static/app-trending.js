// #17 tách monolith — NỘI DUNG: bảng Phim hot (trending) + PHẦN ĐẦU editor lồng tiếng (fmtT, edVoiceSel, edFitChip, openEditor — phần sau ở app-editor.js).
// đúng thứ tự cũ (classic script — cùng global scope, hành vi không đổi).
// ---------- Bảng phim AI hot (Bilibili + check YouTube) ----------
function _fmtCount(n) { n = +n || 0; return n >= 10000 ? (n / 10000).toFixed(1) + "万" : String(n); }
async function renderTrending() {
  const box = document.getElementById("trendtable");
  const meta = document.getElementById("trendmeta");
  let d;
  try { d = await (await fetch("/api/trending")).json(); }
  catch (e) { box.innerHTML = `<div class="err">Không tải được bảng: ${esc(String(e))}</div>`; return; }
  const rows = d.rows || [];
  const when = d.scanned_at ? new Date(d.scanned_at * 1000).toLocaleString() : "chưa quét";
  meta.textContent = `${rows.length} phim · quét lúc ${when}`
    + (d.yt_enabled ? ` · YouTube: bật (đã check ${d.yt_checked || 0})` : " · YouTube: chưa có key");
  if (!rows.length) {
    box.innerHTML = `<div class="note">Chưa có dữ liệu — bấm "🔄 Quét ngay" (lần đầu ~15–30 giây).</div>`;
    return;
  }
  const ytCell = (r) => {
    if (!d.yt_enabled) return '<span class="meta">—</span>';
    const y = r.youtube;
    if (!y) return '<span class="meta">(chưa check)</span>';
    if (y.error) return `<span class="meta">lỗi: ${esc(y.error)}</span>`;
    if (!y.found) return '<span style="color:var(--ok)">✓ Chưa có ai làm</span>';
    return `<a href="${esc(y.url)}" target="_blank" rel="noopener">⚠ Đã có — ${esc(y.channel || "xem")}</a>`;
  };
  let h = `<table class="trend"><thead><tr><th>#</th><th>Tựa (Bilibili)</th><th>View</th><th>Like</th><th>YouTube đã có?</th><th>Từ khoá</th></tr></thead><tbody>`;
  rows.forEach((r, i) => {
    h += `<tr><td>${i + 1}</td>`
      + `<td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`
      + `<div class="meta">${esc(r.author)}${r.duration ? " · " + esc(r.duration) : ""}</div></td>`
      + `<td>${_fmtCount(r.play)}</td><td>${_fmtCount(r.like)}</td>`
      + `<td>${ytCell(r)}</td><td class="meta">${esc(r.keyword)}</td></tr>`;
  });
  box.innerHTML = h + `</tbody></table>`;
}
async function scanTrending() {
  const btn = document.getElementById("trendscanbtn");
  const meta = document.getElementById("trendmeta");
  btn.disabled = true; btn.textContent = "⏳ Đang quét...";
  meta.textContent = "Đang quét Bilibili… (~15–30 giây)";
  try {
    const res = await fetch("/api/trending/scan", { method: "POST" });
    if (!res.ok) { meta.textContent = "Lỗi: " + _errDetail(await res.text(), res.status); return; }
    await renderTrending();
  } catch (e) { meta.textContent = "Lỗi: " + e; }
  finally { btn.disabled = false; btn.textContent = "🔄 Quét ngay"; }
}

/* ---------- Editor lời thoại ---------- */
let edJobId = null, edSegs = [], edCurIdx = -1, edDirty = new Set(), edVoices = [], edHadFinal = false;
let edOvOrig = {};   // ⚙️ override theo job lúc MỞ editor — so sánh để biết nhóm nào bị đổi
let edEngineCaps = {};   // U7: {engine: {ready, reason}} — disable engine thiếu key/model
let edOvCfg = {};    // giá trị cấu hình CHUNG hiện tại — nền cho ẩn/hiện field phụ thuộc
let edBedOrig = null; // 🎚 âm nền đang lưu của job — biết user có đổi hay không
let edCastNames = [];   // nhân vật đã cast của series (nếu có) → gợi ý gán câu trong editor
let edMuteState = new Set();   // chỉ số dòng đang Mute (không lồng tiếng Việt)
let edRenderWatch = null;      // {id, ttsBase, armGen}: edSave đang render → theo dõi để mở lại editor khi xong

function fmtT(s) {
  s = Math.max(0, Math.floor(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function autoGrow(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }
// giá trị dropdown giọng của 1 segment: "ref:<file>" (casting) | "nu" | "nam"
function edVoiceSel(s) {
  return s.voice_ref ? ("ref:" + s.voice_ref) : (s.voice === "nu" ? "nu" : "nam");
}
// V13 audit giọng: chip cảnh báo khớp nhịp cho 1 câu từ mix_detail (lần mix gần nhất).
// Đỏ = bị cắt tại biên slot hoặc nén tổng ≥1.3× (sửa lời cho NGẮN đi là hết);
// vàng = đọc xong sớm, hụt >30% slot (thường là khoảng lặng tự nhiên — chỉ để ý).
function edFitChip(m) {
  if (!m) return "";
  const tot = m.total_speed || m.post_atempo || 1;
  if (m.clipped_ms > 0)
    return `<br><span class="ed-fit bad" title="Hết ngân sách tăng tốc mà vẫn dài hơn slot ${(m.clipped_ms / 1000).toFixed(1)}s — đã fade + cắt ở biên. Rút gọn lời dịch câu này.">✂ cắt ${(m.clipped_ms / 1000).toFixed(1)}s</span>`;
  if (tot >= 1.3)
    return `<br><span class="ed-fit bad" title="Câu bị nén ${tot.toFixed(2)}× cho vừa slot — nghe dồn. Rút gọn lời dịch để đọc chậm lại.">⏩ ${tot.toFixed(2)}×</span>`;
  if (m.gap_ms > 700 && m.slot_ms > 0 && m.final_ms < 0.7 * m.slot_ms)
    return `<br><span class="ed-fit warn" title="Đọc xong sớm ${(m.gap_ms / 1000).toFixed(1)}s trước câu kế (phần lớn thường là khoảng lặng tự nhiên của video gốc).">⏳ ${(m.gap_ms / 1000).toFixed(1)}s</span>`;
  return "";
}
function edMark(i) {
  const ta = document.getElementById("edvi-" + i);
  const vc = document.getElementById("edvoice-" + i).value;
  const orig = edSegs[i];
  const ov = edVoiceSel(orig);
  const row = document.getElementById("edrow-" + i);
  const muteSame = edMuteState.has(i) === !!orig.mute;
  const ci = document.getElementById("edchar-" + i);
  const charSame = !ci || ci.value.trim() === (orig.character || "").trim();
  if (ta.value === orig.text_vi && vc === ov && muteSame && charSame) {  // sửa rồi trả về như cũ
    edDirty.delete(i); row.classList.remove("dirty");
  } else {
    edDirty.add(i); row.classList.add("dirty");
  }
  autoGrow(ta);  // dự phòng cho trình duyệt chưa hỗ trợ field-sizing
}
// Tắt/bật lồng tiếng cho 1 dòng: Mute → dòng xám, không đọc tiếng Việt (giữ tiếng gốc);
// bấm "Áp dụng câu đã sửa" mới có hiệu lực vào video.
function edLineMute(i) {
  if (edMuteState.has(i)) edMuteState.delete(i); else edMuteState.add(i);
  const muted = edMuteState.has(i);
  document.getElementById("edrow-" + i).classList.toggle("muted", muted);
  const b = document.getElementById("edmute-" + i);
  if (b) {
    b.textContent = muted ? "🔊" : "🔇";
    b.title = muted ? "Bật lại lồng tiếng câu này" : "Tắt lồng tiếng câu này (giữ tiếng gốc)";
  }
  edMark(i);
}
// "Đổi toàn bộ": đặt giọng đã chọn cho TẤT CẢ câu (đánh dấu sửa); bấm Áp dụng/Lưu để đọc lại.
function edApplyAllVoice() {
  const val = document.getElementById("edbulkvoice").value;
  let n = 0;
  for (let i = 0; i < edSegs.length; i++) {
    const sel = document.getElementById("edvoice-" + i);
    if (sel && sel.value !== val) { sel.value = val; edMark(i); n++; }
  }
  const msg = document.getElementById("edmsg");
  msg.textContent = n
    ? `Đã đổi giọng ${n} câu — bấm "🔁 Áp dụng câu đã sửa" hoặc "💾 Lưu & render lại" để đọc lại.`
    : "Tất cả câu đã dùng giọng này rồi.";
}

async function openEditor(id) {
  let data;
  try {
    const res = await fetch(`/api/jobs/${id}/segments`);
    if (!res.ok) { toast("Không tải được lời thoại: " + (await res.json()).detail); return; }
    data = await res.json();
  } catch (e) { toast("Lỗi tải lời thoại: " + e); return; }

  try { edVoices = (await (await fetch("/api/voices")).json()).voices || []; }
  catch (e) { edVoices = []; }

  // Tự mở lại sau render (cùng job đang mở) NHƯNG người dùng vừa gõ thêm trong lúc fetch →
  // đừng ghi đè bản đang sửa. (Mở mới từ thẻ Jobs thì edJobId đã null → bỏ qua nhánh này.)
  if (edJobId === id && edDirty.size) {
    const m = document.getElementById("edmsg");
    if (m) m.textContent = "✓ Render xong. Có câu sửa mới chưa lưu — bấm 💾 để render lại.";
    return;
  }

  edJobId = id; edSegs = data.segments; edCurIdx = -1; edDirty = new Set();
  edOvOrig = data.env_overrides || {};
  edOvCfg = data.cfg_defaults || {};
  edEngineCaps = data.engines || {};   // U7: engine nào thiếu key/model → disable + lý do
  edBedOrig = data.bed_gain_db ?? null;
  edCastNames = data.cast_names || [];   // series có casting → hiện ô gán nhân vật
  edMuteState = new Set();
  edSegs.forEach((s, i) => { if (s.mute) edMuteState.add(i); });
  edHadFinal = data.has_final;   // job đã render → "Áp dụng giọng" sẽ xoá final, cần cảnh báo
  const vsrc = data.has_final ? `/api/jobs/${id}/video` : `/api/jobs/${id}/source`;
  const edMix = data.mix_detail || {};   // V13: số đo khớp nhịp per-câu từ lần mix gần nhất
  const rows = edSegs.map((s, i) => {
    const vsel = edVoiceSel(s);
    return `
    <div class="ed-row${s.mute ? " muted" : ""}" id="edrow-${i}" onclick="edRowClick(event, ${i})" ondblclick="edRowPlay(event, ${i})">
      <div class="ed-t" title="Nhảy video tới câu này">${fmtT(s.start)}${s.speaker ? `<br><span class="ed-spk" title="Cụm người nói (nhận từ giọng trong audio gốc)">${esc(s.speaker)}</span>` : ""}${edFitChip(edMix[s.id])}</div>
      <div class="ed-mid">
        ${s.text ? `<div class="ed-zh">${esc(s.text)}</div>` : ""}
        <textarea class="ed-vi" id="edvi-${i}" rows="1" oninput="edMark(${i})">${esc(s.text_vi)}</textarea>
        ${edCastNames.length ? `<input class="ed-char" id="edchar-${i}" list="ed-castnames" value="${esc(s.character || "")}" oninput="edMark(${i})" placeholder="👤 nhân vật (casting)" title="Nhân vật nói câu này — quyết định giọng theo bảng casting series" style="margin-top:4px;width:100%;box-sizing:border-box;background:var(--card);color:var(--dim);border:1px solid var(--border);border-radius:6px;padding:3px 8px;font:inherit;font-size:12px">` : ""}
      </div>
      <div class="ed-ctl">
        <select id="edvoice-${i}" class="ed-voice" onchange="edMark(${i})">
          <option value="nam" ${vsel === "nam" ? "selected" : ""}>Nam — mặc định (${esc(data.voices.nam)})</option>
          <option value="nu" ${vsel === "nu" ? "selected" : ""}>Nữ ${data.single_voice ? "(1 giọng — không tác dụng)" : "— mặc định (" + esc(data.voices.nu) + ")"}</option>
          ${edVoices.map(v => `<option value="ref:${esc(v.file)}" ${vsel === "ref:" + v.file ? "selected" : ""}>🎙 ${esc(v.name)}</option>`).join("")}
        </select>
        <div class="ed-btns">
          <button class="ghost ed-mute" id="edmute-${i}" onclick="edLineMute(${i})" title="${s.mute ? "Bật lại lồng tiếng câu này" : "Tắt lồng tiếng câu này (giữ tiếng gốc)"}">${s.mute ? "🔊" : "🔇"}</button>
          <button class="ghost ed-preview" onclick="edPreview(${i})" title="Nghe thử">🔊</button>
        </div>
      </div>
    </div>`;
  }).join("");
  _revokeEdPreview();   // mở lại (auto-reopen) thay innerHTML → nhả blob ảnh xem trước cũ trước
  document.getElementById("pane-edit").innerHTML = `
    <div class="ed-top">
      <button class="ghost" onclick="closeEditor()">← Quay lại</button>
      <b>Chỉnh sửa</b>
      <span class="meta">${edSegs.length} câu · chỉ câu sửa mới được đọc lại · nút Lưu/Áp dụng ở thanh DƯỚI cùng</span>
    </div>
    <div class="ed-prog" id="edprogress"></div>
    <div class="ed-split">
      <div class="ed-left">
        <div id="ed-stage">
          <div class="ed-vwrap" id="ed-vwrap">
            <video id="edvideo" preload="metadata" src="${vsrc}" onclick="if(event.detail<2)edTogglePlay()"></video>
            <div class="ed-cover-ov" id="ed-cover-ov"></div>
            <div class="ed-sub-ov" id="ed-sub-ov"><span></span></div>
            <div class="ed-frame-ov" id="ed-frame-ov"></div>
            <div id="ed-wm-ov"></div>
            <div id="ed-crop-ov"></div>
          </div>
          <div class="ed-player">
            <button class="ghost" id="edplay" onclick="edTogglePlay()" title="Phát / Dừng">▶</button>
            <input type="range" id="edseek" min="0" max="1000" value="0" step="1" oninput="edSeekBar(this.value)" title="Tua">
            <span class="meta" id="edtime">0:00 / 0:00</span>
            <button class="ghost" id="edmutebtn" onclick="edToggleMute()" title="Tắt / bật tiếng">🔊</button>
            <input type="range" id="edvol" min="0" max="100" value="100" oninput="edSetVol(this.value)" title="Âm lượng">
            <button class="ghost" onclick="edFullscreen()" title="Toàn màn hình">⛶</button>
          </div>
        </div>
        ${!data.has_final ? `<div class="meta" style="margin:6px 0 0">Khung hình là video GỐC; ${data.has_dub ? "đang phát LỒNG TIẾNG VIỆT; " : ""}phụ đề + làm mờ bên dưới là xem trước gần đúng (bản chính xác sau khi render). Nhấp 1 lần vào dòng để tua tới, nhấp ĐÚP để phát từ đó, 🔊 để nghe riêng câu.</div>` : ""}
        <div class="ed-now" id="ednow">▶ Phát video — câu đang chiếu sẽ tự sáng & cuộn tới.</div>
      </div>
      <div class="ed-list" id="edlist">${rows}</div>
      <datalist id="ed-castnames">${edCastNames.map(n => `<option value="${esc(n)}">`).join("")}</datalist>
    </div>
    ${edSettingsPanel(data)}
    <div class="ed-actionbar">
      <button class="ghost" onclick="edApplyVoices()" id="edapplybtn" title="Áp câu đã sửa + ⚙️ tùy chọn + 🎚 âm nền vào lồng tiếng rồi DỪNG trước render — nghe thử ngay trong editor. Panel 🎨 phụ đề/che/khung chỉ áp khi render.">🔁 Áp dụng & nghe thử (không render)</button>
      <button onclick="edSave()" id="edsavebtn" title="Chốt TẤT CẢ thay đổi (câu + ⚙️ + 🎨 + 🎚) và render ra video final hoàn chỉnh">💾 Lưu & render lại</button>
      <span class="meta" id="edmsg" style="margin:0"></span>
    </div>`;
  for (const t of ["over", "jobs", "cfg"]) document.getElementById("pane-" + t).style.display = "none";
  document.getElementById("pane-edit").style.display = "";
  const ev = document.getElementById("edvideo");
  // #UX: danh sách câu cao BẰNG video bên cạnh (video dọc rất cao mà list bị kẹp 78vh
  // thì thừa khoảng trống). Đo lại khi có metadata / đổi cỡ cửa sổ.
  const fitList = () => {
    const l = document.getElementById("edlist"), st = document.getElementById("ed-stage");
    if (l && st && st.offsetHeight > 250) l.style.maxHeight = st.offsetHeight + "px";
  };
  ev.addEventListener("loadedmetadata", fitList);
  window.addEventListener("resize", fitList);
  setTimeout(fitList, 50);
  applyOvDeps();   // ẩn/hiện field ⚙️ phụ thuộc theo giá trị hiệu lực ban đầu
  ev.addEventListener("timeupdate", edHighlight);
  ev.addEventListener("timeupdate", edUpdatePlayer);
  ev.addEventListener("loadedmetadata", () => { edStyleSub(); edUpdatePlayer(); });
  ev.addEventListener("play", edUpdatePlayer);
  ev.addEventListener("pause", edUpdatePlayer);
  edSetupDub(id, data.has_dub);
  updateEdOverlay();
  toggleFrameCtl();   // bật/tắt ô màu+độ dày theo loại khung đang chọn
  edUpdatePlayer();
  refresh();   // hiện ngay thanh tiến độ nếu job đang chạy lúc mở editor
}

// Phát bản LỒNG TIẾNG VIỆT (dubbed_audio.wav) đè lên video gốc (video tắt tiếng), đồng
// bộ qua sự kiện của video. edDubJob giữ jobId để NẠP LẠI dub sau khi "Áp dụng giọng".
let edDub = null, edDubOn = false, edVol = 1, edMuted = false, edDubJob = null;
function edSetupDub(id, hasDub) {
  edDubJob = id;
  if (edDub) { edDub.pause(); }
  edDub = null; edDubOn = false; edVol = 1; edMuted = false;
  const v = document.getElementById("edvideo");
  // Gắn listener đồng bộ MỘT LẦN, KHÔNG phụ thuộc hasDub (mỗi listener tự null-check
  // nên là no-op khi chưa có dub). Nhờ vậy sau "Áp dụng giọng" tạo dub mới, listener
  // vẫn lái edDub mới mà không cần gắn lại — kể cả khi mở editor lúc chưa có dub.
  v.addEventListener("play", () => { if (edDubOn && edDub) { edDub.currentTime = v.currentTime; edDub.play().catch(() => {}); } });
  v.addEventListener("pause", () => { if (edDub) edDub.pause(); });
  v.addEventListener("seeking", () => { if (edDub) edDub.currentTime = v.currentTime; });
  v.addEventListener("ratechange", () => { if (edDub) edDub.playbackRate = v.playbackRate; });
  v.addEventListener("timeupdate", () => {   // chống lệch dần trên video dài
    if (edDubOn && edDub && !v.paused && Math.abs(edDub.currentTime - v.currentTime) > 0.3)
      edDub.currentTime = v.currentTime;
  });
  if (hasDub) { edDub = new Audio(`/api/jobs/${id}/dub`); edDubOn = true; }
  edApplyAudio();
}
// Nạp lại bản dub sau khi "Áp dụng giọng" (đọc lại) — tái dùng listener đã gắn ở trên.
function edReloadDub() {
  const v = document.getElementById("edvideo");
  const wasPlaying = v && !v.paused;
  if (edDub) edDub.pause();
  edDub = new Audio(`/api/jobs/${edDubJob}/dub?v=${Date.now()}`);  // cache-bust
  edDubOn = true;
  edDub.addEventListener("error", () => {   // dub thiếu/404 → bỏ dub, trả tiếng cho video (khỏi câm)
    if (edDubOn) { edDubOn = false; edApplyAudio(); }
  });
  edApplyAudio();
  if (wasPlaying && v) { edDub.currentTime = v.currentTime; edDub.play().catch(() => {}); }
}
// Khôi phục video + dub sau khi LƯU LỖI (editor còn mở) — tránh để khung hình đen + mất tiếng.
function edRestoreEditorMedia() {
  const v = document.getElementById("edvideo");
  if (v && !v.getAttribute("src"))
    v.src = edHadFinal ? `/api/jobs/${edJobId}/video` : `/api/jobs/${edJobId}/source`;
  edReloadDub();
}
// Nhả file dub: dừng + bỏ src + load() để trình duyệt ĐÓNG kết nối → server hết khoá
// dubbed_audio.wav. Bắt buộc gọi TRƯỚC khi đọc lại, vì Windows khoá file đang phát nên
// server không xoá/ghi đè được (gây 500 ở lần áp dụng thứ 2 trở đi).
function edReleaseDub() {
  if (edDub) { edDub.pause(); edDub.removeAttribute("src"); try { edDub.load(); } catch (e) {} edDub = null; }
  edDubOn = false;
}
// Lấy chi tiết lỗi an toàn kể cả khi server trả TEXT (vd "Internal Server Error", không phải JSON).
function _errDetail(raw, status) {
  try { return JSON.parse(raw).detail || raw || status; } catch (e) { return raw || status; }
}
// MỘT thanh âm lượng + nút tắt tiếng duy nhất, điều khiển nguồn đang nghe (dub nếu có).
function edApplyAudio() {
  const v = document.getElementById("edvideo");
  if (edDubOn && edDub) { if (v) v.muted = true; edDub.volume = edVol; edDub.muted = edMuted; }
  else if (v) { v.muted = edMuted; v.volume = edVol; }
  const mb = document.getElementById("edmutebtn"); if (mb) mb.textContent = edMuted ? "🔇" : "🔊";
  const vs = document.getElementById("edvol"); if (vs) vs.value = Math.round(edVol * 100);
}
function edSetVol(pct) { edVol = Math.max(0, Math.min(1, pct / 100)); if (edVol > 0) edMuted = false; edApplyAudio(); }
function edToggleMute() { edMuted = !edMuted; edApplyAudio(); }

