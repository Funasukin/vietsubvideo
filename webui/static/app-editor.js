// #17 tách monolith — NỘI DUNG: editor lồng tiếng (điều khiển video, panel ⚙️ override + impact + reset, panel 🎨, lưu/áp dụng, nghe thử câu + mix 10s) + nút dọn ổ đĩa.
// đúng thứ tự cũ (classic script — cùng global scope, hành vi không đổi).
// ----- Bộ điều khiển video gọn (thay thanh điều khiển mặc định để âm lượng = 1 nút) -----
function edTogglePlay() {
  const v = document.getElementById("edvideo");
  if (!v) return;
  if (v.paused) { const p = v.play(); if (p) p.catch(() => {}); } else v.pause();
}
function edSeekBar(val) {
  const v = document.getElementById("edvideo");
  if (v && v.duration) { v.currentTime = (val / 1000) * v.duration; edHighlight(); }
}
function edUpdatePlayer() {
  const v = document.getElementById("edvideo");
  if (!v) return;
  const pb = document.getElementById("edplay"); if (pb) pb.textContent = v.paused ? "▶" : "⏸";
  const sk = document.getElementById("edseek");
  if (sk && v.duration && document.activeElement !== sk)
    sk.value = Math.round((v.currentTime / v.duration) * 1000);
  const tt = document.getElementById("edtime");
  if (tt) tt.textContent = fmtT(v.currentTime) + " / " + fmtT(v.duration || 0);
}
function edFullscreen() {
  // toàn màn hình CẢ video + thanh điều khiển (ed-stage) để không mất nút khi fullscreen
  const w = document.getElementById("ed-stage");
  if (!document.fullscreenElement) { if (w && w.requestFullscreen) w.requestFullscreen().catch(() => {}); }
  else document.exitFullscreen().catch(() => {});
}

// #2 + #3: bảng cài đặt phụ đề/che NGAY trong editor (id hậu tố "-ed", tái dùng helper),
// xem trước trực tiếp bằng lớp phủ trên video.
function edSettingsPanel(data) {
  const r = data.render || {}, s = r.style || {};
  const sm = r.subtitle_mode || "soft", cv = r.cover || "none";
  const ct = Math.round((r.cover_top ?? 0.78) * 100), cb = Math.round((r.cover_bottom ?? 1.0) * 100), cw = Math.round((r.cover_width ?? 1.0) * 100);
  const font = s.font || "Arial", size = s.size || 18, color = s.color || "#FFFFFF", oColor = s.outline_color || "#000000";
  const outline = s.outline ?? 2, marginV = s.margin_v ?? 16;
  const back = s.back ? "checked" : "", backColor = s.back_color || "#000000", backOp = Math.round((s.back_opacity ?? 0.6) * 100);
  const frame = r.frame || "none";
  const frameColor = r.frame_color || "#FFD700";
  const frameColor2 = r.frame_color2 || "#FFFFFF";
  const frameW = Math.round((r.frame_width ?? 0.02) * 1000) / 10;   // % chiều cao
  const framePad = r.frame_pad ? "checked" : "";
  const wmM = r.wm_method || "none";
  const wb = (r.wm_box && r.wm_box.length === 4) ? r.wm_box : [0.80, 0.03, 0.97, 0.12];
  const wmX = Math.round(wb[0] * 100), wmY = Math.round(wb[1] * 100);
  const wmW = Math.max(1, Math.round((wb[2] - wb[0]) * 100));
  const wmH = Math.max(1, Math.round((wb[3] - wb[1]) * 100));
  const cr = (r.crop && r.crop.length === 4) ? r.crop : [0, 0, 0, 0];
  const crL = Math.round(cr[0] * 100), crT = Math.round(cr[1] * 100);
  const crR = Math.round(cr[2] * 100), crB = Math.round(cr[3] * 100);
  const FRAME_PRESETS = [["none","Không khung"],["solid","Viền đơn"],["double","Viền đôi"],
    ["twocolor","Viền 2 màu"],["corner","Bo góc / 4 góc"]];
  const pngFrames = data.frames || [];
  const frameOptsHtml = FRAME_PRESETS.map(([v,l]) => `<option value="${v}" ${frame===v?"selected":""}>${l}</option>`).join("")
    + pngFrames.map(n => `<option value="png:${esc(n)}" ${frame==="png:"+n?"selected":""}>🖼 ${esc(n)}</option>`).join("");
  return `<details class="ed-settings"><summary>🎨 Phụ đề / che sub gốc / khung viền — xem trước trực tiếp</summary>
    <div oninput="updateEdOverlay()" onchange="updateEdOverlay()">
    <div class="opts">🎛 Xử lý giọng (áp lúc RENDER):
      <select id="fx-ed">
        <option value="" ${!r.fx ? "selected" : ""}>— theo cấu hình chung —</option>
        ${fxOptionsHtml(r.fx || "none-selected")}
      </select>
      <span class="meta">EQ + nén + chuẩn độ to trên audio ĐÃ TRỘN — không đọc lại giọng, chỉ render lại. Chọn "theo cấu hình chung" để núm VOICE_FX ở tab Cấu hình có tác dụng với video này.</span></div>
    <div class="opts">🖼 Khung viền: <select id="frm-ed" onchange="toggleFrameCtl()">${frameOptsHtml}</select>
      Màu: <input type="color" id="frmc-ed" value="${esc(frameColor)}">
      <span id="frmc2-wrap">Màu 2: <input type="color" id="frmc2-ed" value="${esc(frameColor2)}"></span>
      Độ dày: <input type="range" id="frmw-ed" min="0.5" max="6" step="0.1" value="${frameW}"
             oninput="document.getElementById('frmwp-ed').textContent=this.value+'%'">
      <span class="pct" id="frmwp-ed">${frameW}%</span>
      <label><input type="checkbox" id="frmp-ed" ${framePad}> Khung ngoài (thu hình vào trong — khung không che mép video)</label>
      <span class="meta">Khung vẽ cứng vào video (phụ đề cũng thành vẽ cứng); phụ đề tự né khung. Khung PNG: thả file .png (nền giữa trong suốt) vào thư mục frames/ — tự co giãn 9-slice, không méo hoa văn. Bấm "Xem thử" để thấy chính xác khung + phụ đề.</span></div>
    <div class="opts">🚿 Watermark kênh gốc:
      <select id="wmm-ed" onchange="updateEdOverlay()">
        <option value="none" ${wmM === "none" ? "selected" : ""}>Không xử lý</option>
        <option value="delogo" ${wmM === "delogo" ? "selected" : ""}>Xóa (delogo — vệt mờ nhẹ)</option>
        <option value="blur" ${wmM === "blur" ? "selected" : ""}>Làm mờ vùng</option>
        <option value="black" ${wmM === "black" ? "selected" : ""}>Dải đen</option>
        <option value="logo" ${wmM === "logo" ? "selected" : ""}>Đè logo kênh mình</option>
      </select>
      Vùng: X <input type="number" id="wmx-ed" min="0" max="99" value="${wmX}" style="width:52px">%
      Y <input type="number" id="wmy-ed" min="0" max="99" value="${wmY}" style="width:52px">%
      Rộng <input type="number" id="wmw-ed" min="1" max="100" value="${wmW}" style="width:52px">%
      Cao <input type="number" id="wmh-ed" min="1" max="100" value="${wmH}" style="width:52px">%
      <span class="meta">Khung đỏ trên video = vùng sẽ xử lý (suốt thời lượng). "Xóa" hợp watermark TĨNH ở góc; "Đè logo" dùng logo trong thư mục logo/ (tab Cấu hình).</span></div>
    <div class="opts">✂ Cắt mép:
      Trên <input type="number" id="crt-ed" min="0" max="20" value="${crT}" style="width:52px">%
      Dưới <input type="number" id="crb-ed" min="0" max="20" value="${crB}" style="width:52px">%
      Trái <input type="number" id="crl-ed" min="0" max="20" value="${crL}" style="width:52px">%
      Phải <input type="number" id="crr-ed" min="0" max="20" value="${crR}" style="width:52px">%
      <span class="meta">Cắt dải watermark sát rìa rồi phóng lại đúng cỡ — sạch tuyệt đối, mất một dải hình (khung xanh = phần GIỮ LẠI). Mọi cách xử lý watermark đều ép render "vẽ cứng".</span></div>
    <div class="opts">
      Phụ đề: <select id="sm-ed">
        <option value="soft" ${sm === "soft" ? "selected" : ""}>Track bật/tắt</option>
        <option value="cover_only" ${sm === "cover_only" ? "selected" : ""}>Chỉ che sub gốc (upload .srt riêng lên YouTube)</option>
        <option value="burn" ${sm === "burn" ? "selected" : ""}>Vẽ cứng</option>
        <option value="none" ${sm === "none" ? "selected" : ""}>Không</option></select>
      Nhịp: <select id="sspl-ed" title="Câu gộp cho giọng đọc có tách lại khi HIỂN THỊ phụ đề không">
        <option value="1" ${(r.sub_split ?? true) ? "selected" : ""}>Tách theo nhịp sub gốc</option>
        <option value="0" ${(r.sub_split ?? true) ? "" : "selected"}>Hiện cả câu (gộp)</option></select>
      Che sub gốc: <select id="cv-ed" onchange="toggleCoverSliders('ed')">
        <option value="none" ${cv === "none" ? "selected" : ""}>Không che</option>
        <option value="auto" ${cv === "auto" ? "selected" : ""}>Mờ tự động theo sub</option>
        <option value="blur" ${cv === "blur" ? "selected" : ""}>Làm mờ</option>
        <option value="black" ${cv === "black" ? "selected" : ""}>Dải đen</option></select>
    </div>
    <div class="opts">
      Vùng che từ: <input type="range" id="ct-ed" min="0" max="97" value="${ct}" ${cv === "auto" ? "disabled" : ""} oninput="syncBand('ed','ct')">
      <span class="pct" id="pct-ed">${ct}%</span>
      đến: <input type="range" id="cb-ed" min="3" max="100" value="${cb}" ${cv === "auto" ? "disabled" : ""} oninput="syncBand('ed','cb')">
      <span class="pct" id="cbp-ed">${cb}%</span>
      Rộng: <input type="range" id="cw-ed" min="20" max="100" value="${cw}" ${cv === "auto" ? "disabled" : ""} oninput="document.getElementById('cwp-ed').textContent=this.value+'%'">
      <span class="pct" id="cwp-ed">${cw}%</span>
    </div>
    <div class="opts">
      Font: <select id="ft-ed" onchange="updateFontPreview('ed')">${fontOptions(font)}</select>
      Cỡ: <input type="number" id="fs-ed" min="10" max="40" value="${size}" style="width:56px">
      Màu chữ: <input type="color" id="fc-ed" value="${color}" oninput="updateFontPreview('ed')">
      Màu viền: <input type="color" id="oc-ed" value="${oColor}">
      Viền: <input type="number" id="ow-ed" min="0" max="4" value="${outline}" style="width:48px">
    </div>
    <div class="font-prev" id="fp-ed" style="font-family:'${esc(font)}';color:${esc(color)}">Xem trước · Cốt truyện Ầ Ằ Ẻ Đ Ợ Ư</div>
    <div class="opts">
      <label><input type="checkbox" id="bk-ed" ${back}> Hộp nền</label>
      Màu nền: <input type="color" id="bc-ed" value="${backColor}">
      Đậm: <input type="range" id="bo-ed" min="0" max="100" value="${backOp}" oninput="document.getElementById('bop-ed').textContent=this.value+'%'">
      <span class="pct" id="bop-ed">${backOp}%</span>
      Dời sub lên: <input type="range" id="mv-ed" min="0" max="320" step="4" value="${marginV}" oninput="document.getElementById('mvp-ed').textContent=this.value">
      <span class="pct" id="mvp-ed">${marginV}</span>
    </div>
    <div class="meta">Bấm 💾 Lưu &amp; render lại để áp dụng. Làm mờ ở đây là xem trước gần đúng (bản render dùng FFmpeg chính xác hơn). Kiểu chữ chỉ áp dụng khi phụ đề "Vẽ cứng".</div>
    <div class="row">
      <button class="ghost" id="edpvbtn" onclick="edPreviewFrame()" title="Dựng thử 1 khung bằng FFmpeg — chính xác hơn xem trước trực tiếp">👁 Xem trước 1 khung (chính xác)</button>
    </div>
    <img class="preview" id="ed-preview-frame" style="display:none">
    </div>
  </details>` + edOverridePanel(data);
}

// ⚙️ Tùy chọn cấu hình THEO VIDEO NÀY (đè cấu hình chung): output không vừa ý thì
// chỉnh tại đây rồi 💾 Lưu & render lại — không đụng cấu hình chung, không ảnh
// hưởng video khác. Server whitelist khóa + tự chạy lại từ stage SÂU NHẤT bị đổi
// (nhóm "group" phải khớp _OV_* trong server.py). opts=null → ô nhập chữ tự do.
const ED_OV_FIELDS = [
  // [key, nhãn, options|null(ô chữ), nhóm, helptext ⓘ]
  // nhóm TRỘN — đổi xong chỉ dựng nền + trộn + render (NHANH, không đọc lại giọng)
  ["MAX_SPEEDUP", "⏩ Đồng bộ khớp thoại", [["1.0", "1.0× — không tăng tốc"], ["1.2", "1.2×"], ["1.4", "1.4× — cân bằng"], ["1.6", "1.6×"], ["1.8", "1.8×"], ["2.0", "2.0× — khớp gắt"]], "tts",
    "Trần NHÂN tổng của mọi lớp tăng tốc vì khớp thoại (engine × atempo ≤ mức này); hết ngân sách thì fade + cắt ở biên, KHÔNG đè câu kế. <b>1.0× = KHÔNG ép nhanh</b> — tự nhiên nhất, câu dài bị cắt sớm; <b>2.0×</b> = bám hình gắt nhưng đọc dồn rõ. Đổi núm sẽ ĐỌC LẠI các câu bị ảnh hưởng (ngân sách nằm trong giọng đã đọc)."],
  // (đợt T: STRETCH_SHORT đã gỡ — kéo giãn câu ngắn trái triết lý nhịp đồng đều)
  ["TTS_BASE_SPEED", "🚀 Nhịp đọc nền", [["1.0", "Mặc định (chậm rãi)"], ["1.1", "+10%"], ["1.2", "+20%"], ["1.3", "+30% — nhanh tự nhiên"], ["1.4", "+40%"], ["1.5", "+50% — dồn dập"]], "tts",
    "Nền tốc độ đọc cho MỌI câu của video này (gu đọc kênh) — câu ngắn hết rề rà, nhịp đều giữa các câu. KHÔNG tính vào ngân sách khớp thoại: câu vượt khung vẫn được nén thêm trong trần ⏩ rồi mới cắt. Hiện áp engine edge; viXTTS/trả phí sẽ theo sau. Đổi núm sẽ ĐỌC LẠI các câu edge."],
  ["KEEP_BGM", "🎵 Nhạc/SFX gốc", [["0", "Hạ KHI CÓ thoại"], ["flat", "Hạ ĐỀU suốt video"], ["1", "Tách giọng demucs (GPU)"]], "mix",
    "Xử lý audio gốc dưới giọng đọc. <b>Khi có thoại</b>: nền to–nhỏ theo thoại (có người thấy 'bơm' khó chịu). <b>Đều suốt video</b>: âm gốc nhỏ ổn định, dễ nghe. <b>demucs</b>: tách hẳn giọng nói gốc (GPU, chậm) — nền giữ trọn vẹn nhất."],
  // nhóm GIỌNG — đọc lại các câu bị ảnh hưởng (vài phút với edge)
  ["TTS_ENGINE", "🗣 Engine giọng", [["edge", "edge — miễn phí"], ["vixtts", "viXTTS — nhân bản (GPU)"], ["elevenlabs", "ElevenLabs (trả phí)"], ["vbee", "VBee (trả phí)"], ["fpt", "FPT.AI (trả phí)"]], "tts",
    "Bộ máy đọc giọng. <b>edge/viXTTS miễn phí nhưng license KHÔNG cho dùng video bật kiếm tiền</b>; 3 engine trả phí cần API key (nhập ở Cấu hình → 🔑). Câu đã cast giọng nhân vật vẫn đọc viXTTS clone bất kể engine."],
  ["TTS_SINGLE_VOICE", "🔊 Chế độ giọng", [["1", "1 giọng — cả video một giọng"], ["0", "2 giọng — nam & nữ tự gán"]], "tts",
    "<b>1 giọng</b>: mọi câu đọc cùng một giọng, bỏ phân biệt nam/nữ. <b>2 giọng</b>: câu nhân vật nam đọc giọng nam, nữ giọng nữ (AI tự gán nhãn). Nhân vật đã cast trong Series vẫn giữ giọng riêng. DANH TÍNH giọng do engine quyết: edge chỉnh 2 ô trong Nâng cao; viXTTS/trả phí theo cặp giọng ở tab Cấu hình."],
  ["TTS_VOICE", "👨 Giọng chính (edge)", [["vi-VN-NamMinhNeural", "NamMinh (nam)"], ["vi-VN-HoaiMyNeural", "HoaiMy (nữ)"]], "tts",
    "Giọng đọc chính: mọi câu khi chọn 1 giọng; các câu nhãn NAM khi chọn 2 giọng. Chỉ áp engine edge."],
  ["TTS_VOICE_NU", "👩 Giọng phụ (edge)", [["vi-VN-HoaiMyNeural", "HoaiMy (nữ)"], ["vi-VN-NamMinhNeural", "NamMinh (nam)"]], "tts",
    "Giọng đọc các câu gắn nhãn NỮ (chỉ áp khi chọn 2 giọng, engine edge)."],
  ["PROSODY", "🎼 Tông giọng theo audio gốc", [["1", "Bật"], ["0", "Tắt"]], "tts",
    "Đo tốc độ/độ to từng câu GỐC so với nền người nói → chỉnh giọng đọc theo (câu quát → đọc dồn, câu trầm → chậm lại). Nguồn đo: ƯU TIÊN giọng đã tách demucs (vocals — có khi Nhạc/SFX gốc = demucs đã chạy); chưa tách thì đo trên audio gốc, cảnh nhạc to có thể nhiễu. Chỉ áp engine edge."],
  ["EMOTION", "🎭 Nhãn cảm xúc", [["1", "Bật"], ["0", "Tắt"]], "tts",
    "AI gắn nhãn cảm xúc từng câu khi dịch (gấp/giận/buồn/thì thầm) → giọng đọc chỉnh nhịp/âm lượng theo — bắt được sắc thái audio không lộ (mỉa mai, đe dọa nói nhỏ...)."],
  // (U-3: PROSODY_TRANSFER + 2 danh sách model đã RÚT khỏi per-job — chính sách
  //  toàn cục, chỉnh ở tab Cấu hình; per-job thay bằng ⭐ Chất lượng dịch.
  //  Override cũ của khóa rút tự rơi ở lần Lưu kế — cơ chế field-ẩn sẵn có.)
  // nhóm DỊCH — DỊCH LẠI toàn bộ (tốn phí API, MẤT chỉnh tay câu)
  ["TRANSLATE_PROVIDER", "🌐 Nhà cung cấp dịch", [["claude", "Claude"], ["gemini", "Gemini"]], "translate",
    "LLM dịch/soát. <b>Claude</b> ổn định; <b>Gemini</b> free tier gần như $0 nhưng giới hạn request — lỗi/hết quota giữa chừng TỰ chuyển về Claude (model Claude khi đó theo Chất lượng dịch/cấu hình chung), job không chết."],
  ["CONTENT_STYLE", "Kiểu nội dung", [["donghua", "Donghua/cổ trang — Hán-Việt"], ["general", "Chung — dịch tự nhiên"]], "translate",
    "Văn phong bản dịch. <b>Donghua</b>: tên riêng ép Hán-Việt (叶凡→Diệp Phàm), xưng hô cổ trang (ngươi/ta). <b>Chung</b>: xưng hô hiện đại, giữ tên gốc — hợp vlog/tài liệu/phim hiện đại."],
  ["TARGET_LANG", "Ngôn ngữ lồng tiếng", [["vi", "Tiếng Việt"], ["en", "English"], ["zh", "中文"], ["ja", "日本語"], ["ko", "한국어"], ["es", "Español"], ["fr", "Français"], ["id", "Indonesia"], ["th", "ไทย"], ["pt", "Português"]], "translate",
    "Ngôn ngữ ĐÍCH của bản dịch + giọng đọc + phụ đề. Khác Tiếng Việt: đọc bằng cặp giọng edge của ngôn ngữ đó; viXTTS/casting clone không áp dụng."],
  ["TRANSLATE_STYLE_EXTRA", "Phong cách dịch riêng", null, "translate",
    "Mô tả tự do chèn thêm vào prompt dịch + soát (vd: <b>giọng hài hước, dùng teencode</b>) — cộng thêm lên trên Kiểu nội dung."],
  // nhóm NHẬN DẠNG — làm lại từ transcript (LÂU NHẤT, mất bản dịch + chỉnh tay)
  ["TRANSCRIPT_SOURCE", "📝 Nguồn transcript", [["auto", "auto — tự chọn"], ["ocr", "ocr — đọc hardsub"], ["whisper", "whisper — nghe tiếng"]], "transcript",
    "Cách lấy lời thoại gốc. <b>auto</b>: thử OCR đọc sub cứng trước, không có → Whisper nghe tiếng. Ép <b>ocr</b> khi chắc chắn video có hardsub (chính xác nhất); <b>whisper</b> khi video không sub."],
  ["WHISPER_MODEL", "Nghe tiếng (whisper)", [["tiny", "Nhanh nhất (tiny)"], ["base", "Nhanh (base)"], ["small", "Cân bằng (small)"], ["medium", "Chính xác (medium)"], ["large-v3", "Chính xác nhất (large-v3, GPU)"]], "transcript",
    "Chất lượng nghe tiếng — chính xác hơn = chậm hơn. Máy CPU: <b>Cân bằng</b>; máy GPU: <b>Chính xác nhất</b>. Dùng khi audio khó nghe/nhiều tạp âm."],
  ["OCR_FPS", "Quét chữ (OCR)", [["1.0", "Nhanh (1 fps)"], ["1.5", "Cân bằng (1.5 fps)"], ["2.0", "Kỹ (2 fps)"]], "transcript",
    "Số khung hình quét chữ mỗi giây. <b>Kỹ</b> bắt được cả sub hiện cực ngắn (sub nháy nhanh); <b>Nhanh</b> nhanh gấp đôi, đủ cho sub ≥2 giây."],
  ["OCR_CROP_TOP", "Vùng quét phụ đề", [["auto", "auto — tự đo"], ["0.50", "Từ 50%"], ["0.60", "Từ 60%"], ["0.70", "Từ 70%"], ["0.80", "Từ 80%"]], "transcript",
    "OCR chỉ quét dải này (theo chiều cao) tìm phụ đề. <b>auto</b> tự đo vị trí sub từng video — quan trọng với video DỌC (sub ~65%, không sát đáy); số lớn = chỉ quét đáy, hợp phim ngang 16:9."],
  // nhóm TRÍCH AUDIO (U16) — sâu nhất: trích lại audio rồi làm lại toàn bộ
  ["DENOISE", "🎧 Khử ồn trước khi nghe", [["0", "Tắt"], ["1", "Bật — lọc ù/ồn cho Whisper"]], "extract",
    "Video nguồn nhiều tạp âm/ù → bật để Whisper nghe rõ hơn (chỉ áp cho bản audio NHẬN DẠNG, không đụng nền mix). Audio sạch sẵn thì đừng bật kẻo méo. Đổi là trích lại audio + nhận dạng + dịch lại TỪ ĐẦU."],
];
const ED_OV_GROUPS = [
  ["mix", "🎛 Trộn âm", "đổi xong: chỉ trộn + render lại (NHANH, giọng giữ nguyên)"],
  ["tts", "🔊 Giọng đọc", "đổi xong: đọc lại các câu bị ảnh hưởng rồi trộn + render (vài phút)"],
  ["translate", "🌐 Dịch", "⚠️ đổi xong: DỊCH LẠI TOÀN BỘ — tốn phí API, MẤT các câu đã sửa tay"],
  ["transcript", "📝 Nhận dạng thoại", "⚠️ đổi xong: làm lại TỪ TRANSCRIPT — lâu nhất, mất bản dịch + mọi chỉnh tay"],
  ["extract", "🎧 Trích audio", "⚠️ đổi xong: trích lại audio + làm lại TOÀN BỘ nhận dạng/dịch — sâu nhất"],
];
function edOvNorm(k, v) {   // bool từ config có thể là "True"/"False" → chuẩn về mã option
  v = String(v ?? "").trim();
  if (/^true$/i.test(v)) return "1";
  if (/^false$/i.test(v)) return "0";
  if (k === "MAX_SPEEDUP" && v && !v.includes(".")) return v + ".0";
  return v;
}
// tooltip ⓘ cạnh nhãn — cùng kiểu .finfo/.ftip với trang Cấu hình (CSS toàn cục)
function ovHint(h) {
  return h ? ` <span class="finfo" tabindex="0">i<span class="ftip">${h}</span></span>` : "";
}
function edOverridePanel(data) {
  const ov = data.env_overrides || {};
  const cfg = data.cfg_defaults || {};
  const field = ([key, label, opts, , help]) => {
    const cur = ov[key] ?? "";
    const inner = !opts   // ô chữ tự do (vd phong cách dịch); trống = theo cấu hình chung
      ? `<input type="text" id="ov-${key}" value="${esc(cur)}"
           placeholder="— theo cấu hình chung (${esc(cfg[key] || "trống")}) —">`
      : `<select id="ov-${key}">
           <option value="">— theo cấu hình chung (${esc((opts.find(([v]) => v === edOvNorm(key, cfg[key])) || [])[1] || edOvNorm(key, cfg[key]) || "?")}) —</option>
           ${opts.map(([v, l]) => `<option value="${v}" ${cur === v ? "selected" : ""}>${l}</option>`).join("")}
         </select>`;
    return `<div class="ov-field" id="ovf-${key}">
      <span class="ov-label" id="ovl-${key}">${label}${ovHint(help)}</span>${inner}</div>`;
  };
  // control KHÔNG phải env-override nhưng cùng ngữ cảnh — nhét vào đúng nhóm:
  // 🎚 Âm nền gốc (bed_gain_db, nhóm Trộn — hiện Ở MỌI mode từ U13),
  // 🎙 giọng tất cả câu (nhóm Giọng đọc). Xử lý giọng đã dời sang panel 🎨 (U8).
  const extras = {
    mix: `<div class="ov-field" id="ovf-BEDVOL">
      <span class="ov-label">🎚 Âm nền gốc${ovHint("Mức hạ audio GỐC dưới giọng đọc — nền to/nhỏ quá thì chỉnh rồi 💾 Lưu &amp; render lại (chỉ trộn lại, KHÔNG đọc lại giọng). Áp ở MỌI chế độ Nhạc/SFX: hạ đều = mức toàn video; hạ khi có thoại = mức trong vùng thoại; demucs = mức nền nhạc đã tách.")}</span>
      <select id="ed-bedvol">
        ${[["", "— giữ nguyên —"], ["-8", "To hơn (-8dB)"], ["-14", "Vừa (-14dB, mặc định)"],
           ["-20", "Nhỏ (-20dB)"], ["-26", "Rất nhỏ (-26dB)"], ["-34", "Gần tắt (-34dB)"]]
          .map(([v, l]) => `<option value="${v}" ${String(data.bed_gain_db ?? "") === v ? "selected" : ""}>${l}</option>`).join("")}
      </select></div>`,
    tts: `<div class="ov-field">
      <span class="ov-label">🎙 Giọng tất cả câu${ovHint("Đặt giọng đã chọn cho TẤT CẢ câu (đè lựa chọn riêng từng câu trong danh sách), rồi bấm 🔁 Áp dụng hoặc 💾 Lưu &amp; render để đọc lại.")}</span>
      <span style="display:flex;gap:6px;min-width:0">
        <select id="edbulkvoice" style="flex:1;min-width:0">
          <option value="nam">Nam — mặc định (${esc(data.voices.nam)})</option>
          <option value="nu">Nữ — mặc định (${esc(data.voices.nu)})</option>
          ${edVoices.map(v => `<option value="ref:${esc(v.file)}">🎙 ${esc(v.name)}</option>`).join("")}
        </select>
        <button class="ghost" type="button" onclick="edApplyAllVoice()">↪ Đổi toàn bộ</button>
      </span></div>`,
  };
  const hint = data.single_voice
    ? ' <span class="meta" style="margin:0">· 🔊 1 giọng: mọi câu đọc giọng chính — nhãn nam/nữ chỉ để casting</span>' : "";
  // U15: THƯỜNG DÙNG (6 control chỉnh nhanh theo video) + NÂNG CAO gập lại (nhớ
  // trạng thái qua localStorage) — panel cũ 20+ knob phẳng là quá tải.
  const COMMON = new Set(["KEEP_BGM", "TTS_ENGINE", "TTS_SINGLE_VOICE"]);
  const fmap = Object.fromEntries(ED_OV_FIELDS.map(f => [f[0], f]));
  const presetRow = `<div class="ov-field">
      <span class="ov-label">🎯 Preset khớp thoại${ovHint("Đặt nhanh núm Đồng bộ khớp thoại (chi tiết trong Nâng cao — cùng bộ preset với tab Cấu hình). <b>Chặt</b>: nén tối đa 2.0×, bám khẩu hình sát nhất. <b>Tự nhiên</b>: nén tối đa 1.2×, ưu tiên nghe êm. Vẫn phải bấm Áp dụng/Lưu.")}</span>
      <span style="display:flex;gap:6px;min-width:0">
        <button class="ghost" type="button" onclick="edOvPreset('tight')">🎯 Chặt</button>
        <button class="ghost" type="button" onclick="edOvPreset('natural')">🌿 Tự nhiên</button>
      </span></div>`;
  const mixPrevRow = `<div class="ov-field">
      <span class="ov-label">👂 Nghe thử 10s${ovHint("Trộn nhanh ~10 giây quanh câu đang chọn với Âm nền / Nhạc SFX ĐANG chỉnh (chưa cần Lưu) — dựng bằng đúng bộ trộn của render thật. Đổi engine/giọng/nhịp đọc cần ĐỌC LẠI giọng nên không nằm trong nghe thử này; demucs chưa tách sẵn thì nền tạm dùng audio gốc.")}</span>
      <button class="ghost" type="button" id="edmixprevbtn" onclick="edMixPreview()">▶ Nghe quanh câu đang chọn</button></div>`;
  const qOv = qualityFromOv(ov);
  const qualityRow = `<div class="ov-field" id="ovf-QUALITY">
      <span class="ov-label">⭐ Chất lượng dịch${ovHint("Một núm thay cho chọn model từng nhà cung cấp: <b>Tiết kiệm</b> (Haiku / Flash-Lite), <b>Cân bằng</b> (Haiku / Flash), <b>Tốt nhất</b> (Sonnet / Pro — phí ~10×). Áp cho provider đang hiệu lực, kể cả khi Gemini fallback về Claude.")}</span>
      <select id="ov-QUALITY">
        <option value="">— theo cấu hình chung —</option>
        <option value="eco" ${qOv === "eco" ? "selected" : ""}>Tiết kiệm</option>
        <option value="balanced" ${qOv === "balanced" ? "selected" : ""}>Cân bằng</option>
        <option value="best" ${qOv === "best" ? "selected" : ""}>Tốt nhất</option>
      </select></div>`;
  const commonGrid = extras.mix + field(fmap.KEEP_BGM) + presetRow
    + field(fmap.TTS_ENGINE) + field(fmap.TTS_SINGLE_VOICE) + extras.tts + mixPrevRow;
  const advGroups = ED_OV_GROUPS.map(([g, title, cost]) => {
    const fields = ED_OV_FIELDS.filter(f => f[3] === g && !COMMON.has(f[0]));
    const extra = g === "translate" ? qualityRow : "";
    if (!fields.length && !extra) return "";
    return `
    <div class="ov-group"><b style="color:var(--accent)">${title}</b>
      <span class="meta" style="margin:0"> — ${cost}</span>${g === "tts" ? hint : ""}</div>
    <div class="ov-grid">${extra + fields.map(field).join("")}</div>`;
  }).join("");
  const panelOpen = localStorage.getItem("ovPanelOpen") !== "0" ? " open" : "";
  const advOpen = localStorage.getItem("ovAdvOpen") === "1" ? " open" : "";
  // onchange nổi bọt từ mọi select bên trong → cập nhật ẩn/hiện field phụ thuộc.
  // toggle KHÔNG nổi bọt nên 2 details nhớ trạng thái độc lập.
  return `<details class="ed-settings"${panelOpen} onchange="applyOvDeps()"
      ontoggle="localStorage.setItem('ovPanelOpen', this.open ? '1' : '0')">
    <summary>⚙️ Tùy chọn video này (đè cấu hình chung)
      <button class="ghost" type="button" style="float:right;font-size:12px"
        onclick="event.preventDefault();edOvReset()"
        title="Xoá mọi tùy chọn riêng của video này — quay về theo cấu hình chung (không đụng 🎚 âm nền và panel 🎨)">↺ Về cấu hình chung</button></summary>
    <div class="ov-group"><b style="color:var(--accent)">🧰 Thường dùng</b>
      <span class="meta" style="margin:0"> — chỉnh nhanh theo video; chi phí hiện khi bấm Áp dụng/Lưu</span></div>
    <div class="ov-grid">${commonGrid}</div>
    <details class="ov-adv"${advOpen}
      ontoggle="localStorage.setItem('ovAdvOpen', this.open ? '1' : '0')">
      <summary>🛠 Nâng cao — tinh chỉnh giọng / dịch / nhận dạng</summary>
      ${advGroups}
    </details>
    <div class="meta">Chỉ áp cho VIDEO NÀY — cấu hình chung và video khác giữ nguyên. Bấm
    🔁 Áp dụng để NGHE THỬ (không render) hoặc 💾 Lưu &amp; render lại để xuất video;
    hệ thống tự chạy lại từ đúng khâu bị ảnh hưởng (nhóm sâu nhất thắng).
    Chọn "— theo cấu hình chung —" / xoá trống ô chữ để bỏ đè.</div>
  </details>`;
}
// U14: nghe thử ~10s quanh câu đang chọn với chỉnh MIX chưa lưu (đúng bộ trộn thật)
let edMixPrevAudio = null;
async function edMixPreview() {
  if (!edJobId || !edSegs.length) return;
  const seg = edSegs[Math.max(0, edCurIdx)] || edSegs[0];
  document.getElementById("edvideo")?.pause();
  if (edMixPrevAudio) {
    edMixPrevAudio.pause();
    if (edMixPrevAudio.src.startsWith("blob:")) URL.revokeObjectURL(edMixPrevAudio.src);
    edMixPrevAudio = null;
  }
  const bedSel = document.getElementById("ed-bedvol");
  const body = {
    t: Math.max(0, (seg.start || 0) - 2), duration_s: 10,
    keep_bgm: edOvEff("KEEP_BGM") || "",
    // STRETCH_SHORT đã gỡ (đợt T) — server bỏ qua field này, gửi "0" cho tương thích
    stretch_short: "0",
    ...(bedSel && bedSel.value !== "" ? { bed_gain_db: parseFloat(bedSel.value) } : {}),
  };
  const btn = document.getElementById("edmixprevbtn");
  if (btn) btn.textContent = "⏳ Đang trộn 10s...";
  try {
    const res = await fetch(`/api/jobs/${edJobId}/mix-preview`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) { toast("Nghe thử lỗi: " + _errDetail(await res.text(), res.status)); return; }
    const url = URL.createObjectURL(await res.blob());
    edMixPrevAudio = new Audio(url);
    edMixPrevAudio.addEventListener("ended", () => URL.revokeObjectURL(url));
    edMixPrevAudio.play().catch(() => {});
  } catch (e) { toast("Lỗi nghe thử: " + e); }
  finally { if (btn) btn.textContent = "▶ Nghe quanh câu đang chọn"; }
}
// Giá trị HIỆU LỰC của 1 khóa: override đang chọn, không thì giá trị cấu hình chung
function edOvEff(key) {
  const el = document.getElementById("ov-" + key);
  return el && el.value !== "" ? el.value : edOvNorm(key, (edOvCfg || {})[key]);
}
// Ẩn/hiện field PHỤ THUỘC nhau trong panel ⚙️ (và đổi nhãn cho khớp ngữ cảnh):
// - 1 giọng → ẩn "Giọng nữ", nhãn giọng chính bỏ chữ "nam"
// - engine ≠ edge / ngôn ngữ ≠ vi → ẩn cặp giọng edge (giọng do engine/ngôn ngữ quyết)
// - Nhà cung cấp dịch: claude ẩn Model Gemini, gemini ẩn Model Claude
// - Nguồn transcript: ocr ẩn Model whisper; whisper ẩn 2 option OCR
function applyOvDeps() {
  const show = (key, on) => {
    const w = document.getElementById("ovf-" + key);
    if (w) w.style.display = on ? "" : "none";
  };
  if (!document.getElementById("ovf-TTS_VOICE")) return;
  const edgeVi = edOvEff("TTS_ENGINE") === "edge" && edOvEff("TARGET_LANG") === "vi";
  const single = edOvEff("TTS_SINGLE_VOICE") === "1";
  show("TTS_VOICE", edgeVi);
  show("TTS_VOICE_NU", edgeVi && !single);
  const lb = document.getElementById("ovl-TTS_VOICE");
  if (lb) {   // chỉ sửa TEXT NODE đầu — textContent sẽ xoá mất icon ⓘ tooltip bên trong
    const txt = single ? "👤 Giọng đọc (edge)" : "👨 Giọng chính (edge)";
    if (lb.firstChild && lb.firstChild.nodeType === 3) lb.firstChild.nodeValue = txt;
    else lb.insertBefore(document.createTextNode(txt), lb.firstChild);
  }
  const ts = edOvEff("TRANSCRIPT_SOURCE");
  show("WHISPER_MODEL", ts !== "ocr");
  show("OCR_FPS", ts !== "whisper");
  show("OCR_CROP_TOP", ts !== "whisper");
  // U13: Âm nền gốc hiện Ở MỌI mode — S6 áp gain cả khi duck theo thoại lẫn nền
  // demucs, không riêng "hạ đều" (review Codex bắt: ẩn là mất control hợp lệ)
  show("BEDVOL", true);
  // U4: Tông giọng chỉ áp engine edge (viXTTS bắt chước clip mẫu, paid nhịp riêng)
  show("PROSODY", edOvEff("TTS_ENGINE") === "edge");
  // U3: EMOTION — nhãn chỉ sinh LÚC DỊCH; video chưa có nhãn mà chọn Bật thì server
  // leo thang chạy lại từ DỊCH (edOvDepth cùng logic) → cảnh báo ngay tại chỗ
  const emoSel = document.getElementById("ov-EMOTION");
  if (emoSel) {
    const hasEmo = (edSegs || []).some(s => (s.emotion || "").trim());
    let warn = document.getElementById("ov-emotion-warn");
    if (!hasEmo) {
      if (!warn) {
        warn = document.createElement("div");
        warn.id = "ov-emotion-warn";
        warn.className = "meta";
        warn.style.gridColumn = "1 / -1";
        emoSel.parentElement.appendChild(warn);
      }
      warn.textContent = edOvEff("EMOTION") === "1"
        ? "⚠️ Video chưa có nhãn cảm xúc → Bật sẽ DỊCH LẠI TOÀN BỘ để tạo nhãn (mất câu sửa tay, tốn phí API)."
        : "Video này dịch khi chưa bật nhãn cảm xúc — chọn Bật đồng nghĩa dịch lại toàn bộ để tạo nhãn.";
    } else if (warn) warn.remove();
  }
  // U7: engine thiếu key/model → disable option kèm lý do (giá trị ĐANG chọn thì
  // giữ chọn được + cảnh báo, kẻo job cũ override engine mất key bị kẹt không sửa được)
  const engSel = document.getElementById("ov-TTS_ENGINE");
  if (engSel && typeof edEngineCaps === "object") {
    for (const opt of engSel.options) {
      const cap = edEngineCaps[opt.value];
      if (!opt.value || !cap) continue;
      if (!cap.ready && !opt.dataset.capmark) {
        opt.dataset.capmark = "1";
        opt.text += " — " + cap.reason;
      }
      opt.disabled = !cap.ready && engSel.value !== opt.value;
    }
  }
}
function edCollectOverrides() {
  const out = {};
  for (const [key] of ED_OV_FIELDS) {
    const el = document.getElementById("ov-" + key);
    const wrap = document.getElementById("ovf-" + key);
    // field đang ẨN (không áp trong ngữ cảnh hiện tại) → không gửi, override cũ tự rơi
    if (!el || (wrap && wrap.style.display === "none")) continue;
    if (el.value.trim() !== "") out[key] = el.value.trim();
  }
  // ⭐ Chất lượng dịch (U10): 1 núm → 2 khóa model (server whitelist sẵn có)
  const q = document.getElementById("ov-QUALITY");
  if (q && q.value && QUALITY_MODELS[q.value]) Object.assign(out, QUALITY_MODELS[q.value]);
  return out;
}
// nhóm sâu nhất bị ĐỔI so với override đang lưu — để cảnh báo trước khi Lưu
function edOvDepth(newOv) {
  const old = edOvOrig || {};
  const diff = new Set();
  for (const k of new Set([...Object.keys(old), ...Object.keys(newOv)]))
    if ((old[k] ?? "") !== (newOv[k] ?? "")) diff.add(k);
  // model dịch không còn field riêng (đi qua ⭐ Chất lượng dịch) nhưng vẫn là khóa
  // override nhóm dịch — thiếu map là depth rơi nhầm về "mix"
  const EXTRA_G = { CLAUDE_MODEL: "translate", GEMINI_MODEL: "translate" };
  const g = k => (ED_OV_FIELDS.find(f => f[0] === k) || [])[3] || EXTRA_G[k];
  if ([...diff].some(k => g(k) === "extract")) return "extract";
  if ([...diff].some(k => g(k) === "transcript")) return "transcript";
  if ([...diff].some(k => g(k) === "translate")) return "translate";
  if ([...diff].some(k => g(k) === "tts")) {
    // U3: bật EMOTION khi video chưa có nhãn → server leo thang chạy lại từ DỊCH
    // (nhãn chỉ sinh lúc dịch) — client phải cảnh báo Y HỆT kẻo confirm nói dối
    if (diff.has("EMOTION") && (newOv.EMOTION === "1")
        && !(edSegs || []).some(s => (s.emotion || "").trim())) return "translate";
    return "tts";
  }
  return diff.size ? "mix" : null;
}
// U6: xoá mọi ⚙️ override một phát — về theo cấu hình chung (KHÔNG đụng 🎚 âm nền
// và panel 🎨; vẫn phải bấm Áp dụng/Lưu, hệ thống chạy lại từ nhóm sâu nhất bị đổi)
function edOvReset() {
  let n = 0;
  for (const [key] of ED_OV_FIELDS) {
    const el = document.getElementById("ov-" + key);
    if (el && el.value !== "") { el.value = ""; n++; }
  }
  const q = document.getElementById("ov-QUALITY");   // ⭐ Chất lượng dịch cũng về chung
  if (q && q.value !== "") { q.value = ""; n++; }
  applyOvDeps();
  toast(n ? `Đã bỏ ${n} tùy chọn riêng — bấm 🔁 Áp dụng hoặc 💾 Lưu để chạy lại theo cấu hình chung`
          : "Không có tùy chọn riêng nào đang đặt");
}
// U12: hỏi server tác động THẬT của ⚙️ đề xuất (đọc lại bao nhiêu câu, phí gì) →
// chuỗi confirm có số liệu. Lỗi mạng/endpoint → trả null, caller dùng confirm cũ.
async function edOvImpactMsg(env_overrides) {
  try {
    const r = await fetch(`/api/jobs/${edJobId}/override-impact`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ env_overrides: env_overrides || {} }) });
    if (!r.ok) return null;
    const d = await r.json();
    if (!d.depth) return "";   // không đổi gì sâu — khỏi hỏi
    const names = { mix: "🎛 Trộn âm (nhanh, giọng giữ nguyên)", tts: "🔊 Đọc lại giọng",
                    translate: "🌐 DỊCH LẠI TOÀN BỘ", transcript: "📝 NHẬN DẠNG LẠI TỪ ĐẦU" };
    let m = `Tùy chọn ⚙️ thay đổi → chạy lại từ: ${names[d.depth] || d.depth}\n`;
    if (d.tts_regenerate) m += `• Đọc lại ${d.tts_regenerate}/${d.segments_total} câu\n`;
    if (d.paid_tts_chars) m += `• Gửi dịch vụ TRẢ PHÍ ~${d.paid_tts_chars} ký tự\n`;
    if (d.manual_edits_at_risk) m += `• MẤT các câu đã sửa tay\n`;
    if (d.estimated_seconds && d.estimated_seconds[1])
      m += `• Ước tính ${d.estimated_seconds[0]}–${d.estimated_seconds[1]} giây\n`;
    for (const w of (d.warnings || [])) m += `• ⚠️ ${w}\n`;
    return m + "Tiếp tục?";
  } catch { return null; }
}

// #5: xem trước CHÍNH XÁC 1 khung bằng FFmpeg (che + kiểu chữ + phụ đề thật) — tái dùng
// endpoint /preview. Khác với lớp phủ CSS trực tiếp ở trên (chỉ gần đúng).
async function edPreviewFrame() {
  if (!edJobId) return;
  const img = document.getElementById("ed-preview-frame");
  const btn = document.getElementById("edpvbtn");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Đang dựng khung..."; }
  if (img) { img.style.display = "block"; img.style.opacity = 0.4; }
  try {
    const res = await fetch(`/api/jobs/${edJobId}/preview`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(readOpts("ed")) });
    if (res.ok) {
      if (img && img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
      if (img) img.src = URL.createObjectURL(await res.blob());
    } else {
      const m = document.getElementById("edmsg");
      if (m) m.textContent = "Xem trước lỗi: " + _errDetail(await res.text(), res.status);
    }
  } catch (e) {
    const m = document.getElementById("edmsg"); if (m) m.textContent = "Xem trước lỗi: " + e;
  } finally {
    if (img) img.style.opacity = 1;
    if (btn) { btn.disabled = false; btn.textContent = "👁 Xem trước 1 khung (chính xác)"; }
  }
}

function updateEdOverlay() {
  if (!document.getElementById("cv-ed")) return;
  const o = readOpts("ed");
  const cov = document.getElementById("ed-cover-ov");
  if (cov) {
    if (o.cover === "none") { cov.style.display = "none"; }
    else {
      const auto = o.cover === "auto";
      const top = auto ? 78 : o.cover_top * 100, bot = auto ? 100 : o.cover_bottom * 100, w = auto ? 100 : o.cover_width * 100;
      cov.style.display = "block";
      cov.style.top = top + "%"; cov.style.height = Math.max(0, bot - top) + "%";
      cov.style.left = ((100 - w) / 2) + "%"; cov.style.width = w + "%";
      if (o.cover === "black") { cov.style.background = "#000"; cov.style.backdropFilter = cov.style.webkitBackdropFilter = "none"; }
      else { cov.style.background = "rgba(0,0,0,.04)"; cov.style.backdropFilter = cov.style.webkitBackdropFilter = "blur(7px)"; }
    }
  }
  // xem trước khung viền (gần đúng): procedural = CSS border; png = ảnh phủ
  const fov = document.getElementById("ed-frame-ov");
  if (fov) {
    const v = document.getElementById("edvideo");
    if (!o.frame || o.frame === "none") {
      fov.style.display = "none";
    } else if (o.frame.startsWith("png:")) {
      fov.style.display = "block"; fov.style.border = "none"; fov.style.boxShadow = "none";
      fov.style.backgroundImage = `url(/api/frames/${encodeURIComponent(o.frame.slice(4))})`;
    } else {
      fov.style.display = "block"; fov.style.backgroundImage = "none";
      const px = Math.max(1, Math.round(o.frame_width * (v && v.clientHeight ? v.clientHeight : 360)));
      fov.style.border = `${px}px ${o.frame === "double" ? "double" : "solid"} ${o.frame_color}`;
      // viền 2 màu: thêm vòng trong màu 2; bo góc: gạch đứt gợi ý (render mới chính xác 4 góc)
      fov.style.boxShadow = (o.frame === "twocolor") ? `inset 0 0 0 ${2 * px}px ${o.frame_color2}` : "none";
      if (o.frame === "corner") fov.style.borderStyle = "dashed";
    }
  }
  // vùng watermark (khung đỏ) + phần giữ lại sau cắt mép (khung xanh)
  const wmo = document.getElementById("ed-wm-ov");
  if (wmo) {
    const on = o.wm_method && o.wm_method !== "none" && o.wm_box.length === 4;
    wmo.style.display = on ? "block" : "none";
    if (on) {
      wmo.style.left = (o.wm_box[0] * 100) + "%";
      wmo.style.top = (o.wm_box[1] * 100) + "%";
      wmo.style.width = ((o.wm_box[2] - o.wm_box[0]) * 100) + "%";
      wmo.style.height = ((o.wm_box[3] - o.wm_box[1]) * 100) + "%";
    }
  }
  const cro = document.getElementById("ed-crop-ov");
  if (cro) {
    const c = o.crop || [];
    const on = c.some(v => v > 0.001);
    cro.style.display = on ? "block" : "none";
    // crop lưu [trái,trên,phải,dưới]; CSS inset theo thứ tự trên/phải/dưới/trái
    if (on) cro.style.inset = `${c[1] * 100}% ${c[2] * 100}% ${c[3] * 100}% ${c[0] * 100}%`;
  }
  edStyleSub();
}
function toggleFrameCtl() {
  const sel = document.getElementById("frm-ed"); if (!sel) return;
  const f = sel.value;
  const proc = (f === "solid" || f === "double" || f === "twocolor" || f === "corner");
  const c = document.getElementById("frmc-ed"), w = document.getElementById("frmw-ed");
  if (c) c.disabled = !proc;
  if (w) w.disabled = !proc;
  const c2w = document.getElementById("frmc2-wrap");
  if (c2w) c2w.style.display = (f === "twocolor") ? "" : "none";   // màu 2 chỉ cho viền 2 màu
  updateEdOverlay();
}
function edStyleSub() {
  const sub = document.getElementById("ed-sub-ov"), span = sub && sub.firstElementChild;
  if (!sub || !span || !document.getElementById("fc-ed")) return;
  const v = document.getElementById("edvideo");
  if (!v || !v.clientHeight) return;   // chưa có kích thước → loadedmetadata/edHighlight sẽ tô lại
  const st = readOpts("ed").style, sm = document.getElementById("sm-ed").value;
  const scale = v.videoHeight ? v.clientHeight / v.videoHeight : v.clientHeight / 720;
  sub.style.display = (sm === "none" || !span.textContent) ? "none" : "block";
  sub.style.bottom = Math.round(st.margin_v * scale) + "px";
  span.style.fontFamily = '"' + st.font + '"';
  span.style.fontSize = Math.max(9, Math.round(st.size * scale)) + "px";
  span.style.color = st.color;
  const ow = Math.max(0, st.outline * scale);
  span.style.textShadow = ow ? [[ow, 0], [-ow, 0], [0, ow], [0, -ow]].map(p => `${p[0]}px ${p[1]}px 0 ${st.outline_color}`).join(",") : "none";
  span.style.background = st.back ? hexA(st.back_color, st.back_opacity) : "transparent";
}
function hexA(hex, a) {
  const n = parseInt(String(hex).replace("#", ""), 16) || 0;
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function _revokeEdPreview() {   // nhả blob URL của ảnh "Xem trước 1 khung" trước khi huỷ DOM editor
  const img = document.getElementById("ed-preview-frame");
  if (img && img.src && img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
}
function _teardownEditorMedia() {   // dừng video + audio lồng tiếng dù rời editor kiểu nào
  const v = document.getElementById("edvideo"); if (v) v.pause();
  if (edDub) { edDub.pause(); edDub = null; }
  edDubOn = false;
  _revokeEdPreview();   // closeEditor + _doShowTab gọi hàm này → khỏi rò blob khi đóng/đổi tab
}

function closeEditor() {
  _teardownEditorMedia();
  const pe = document.getElementById("pane-edit");
  pe.style.display = "none"; pe.innerHTML = "";
  edJobId = null; edSegs = []; edDirty = new Set(); edRenderWatch = null;
  showTab("jobs"); refresh();
}

function edSeek(i) {
  // Nhấp 1 LẦN: chỉ tua tới vị trí câu (giữ nguyên đang phát/tạm dừng), không tự phát.
  const v = document.getElementById("edvideo");
  v.currentTime = edSegs[i].start;
  edHighlight(); edUpdatePlayer();
}

// Nhấp 1 lần vào dòng → tua tới câu. Trừ khi bấm ô sửa chữ / chọn giọng / nút nghe.
function edRowClick(e, i) {
  if (e.target.closest("textarea, select, button")) return;
  edSeek(i);
}
// Nhấp ĐÚP vào dòng → tua tới câu RỒI PHÁT từ đó (kèm lồng tiếng đang áp dụng).
function edRowPlay(e, i) {
  if (e.target.closest("textarea, select, button")) return;
  const v = document.getElementById("edvideo");
  v.currentTime = edSegs[i].start;
  const p = v.play(); if (p) p.catch(() => {});
  edHighlight();
}

// Port của s8_render._split_text: chia text thành weights.length phần theo tỉ trọng,
// cắt tại dấu câu khi đủ vế (không đủ thì cắt theo từ). null nếu quá ít từ để chia.
const _CLAUSE_SPLIT_RE = /(?<=[,;:.!?…—])\s+|(?<=[。？！、；：])\s*/;
function edSplitText(text, weights) {
  const n = weights.length;
  let parts = text.split(_CLAUSE_SPLIT_RE).filter(p => p && p.trim());
  if (parts.length < n) {
    parts = text.split(/\s+/).filter(Boolean);
    if (parts.length < n) return null;
  }
  const totW = weights.reduce((a, b) => a + b, 0) || 1.0;
  const totLen = parts.reduce((a, p) => a + p.length + 1, 0);
  const out = []; let ci = 0;
  for (let i = 0; i < n; i++) {
    const leftParts = parts.length - ci;
    let take;
    if (i === n - 1) take = leftParts;
    else {
      const target = totLen * weights[i] / totW;
      take = 0; let ln = 0;
      while (take < leftParts - (n - 1 - i)) {         // chừa đủ mỗi phần sau ≥1 vế
        const nxt = parts[ci + take].length + 1;
        if (take > 0 && ln + nxt / 2 > target) break;  // vượt quá nửa vế kế thì dừng
        ln += nxt; take += 1;
      }
      take = Math.max(1, take);
    }
    out.push(parts.slice(ci, ci + take).join(" "));
    ci += take;
  }
  return out;
}

// Phụ đề XEM TRƯỚC tại thời điểm t của câu idx — cùng logic tách nhịp với make_srt
// (sub_split): câu gộp từ nhiều dòng sub gốc → chỉ hiện ĐÚNG mảnh đang tới nhịp,
// khỏi lòi nguyên câu dài che màn hình (điều kiện, tỉ trọng y hệt bản render).
function edSubAt(idx, t) {
  const seg = edSegs[idx];
  const txt = document.getElementById("edvi-" + idx).value;
  const sspl = document.getElementById("sspl-ed");   // select "Nhịp" trong panel 🎨 của editor
  const splitOn = sspl ? sspl.value === "1" : true;
  const pieces = seg.pieces || [];
  if (!splitOn || pieces.length < 2 || txt.split(/\s+/).filter(Boolean).length < 2 * pieces.length)
    return txt;
  const texts = edSplitText(txt, pieces.map(p => Math.max(1.0, p.len || 1)));
  if (!texts) return txt;
  for (let k = 0; k < pieces.length; k++) {
    const end = (k + 1 < pieces.length) ? pieces[k + 1].start : pieces[k].end;
    if (t < end) return texts[k];
  }
  return texts[texts.length - 1];
}

function edHighlight() {
  const t = document.getElementById("edvideo").currentTime;
  let idx = -1;
  for (let i = 0; i < edSegs.length; i++)
    if (t >= edSegs[i].start && t < edSegs[i].end) { idx = i; break; }
  const subSpan = document.querySelector("#ed-sub-ov span");
  // phụ đề xem trước cập nhật theo TỪNG mảnh (không chỉ khi đổi câu) — nhịp sub gốc
  if (subSpan && idx >= 0) { subSpan.textContent = edSubAt(idx, t); edStyleSub(); }
  if (idx === edCurIdx) return;
  if (edCurIdx >= 0) document.getElementById("edrow-" + edCurIdx)?.classList.remove("cur");
  edCurIdx = idx;
  if (idx >= 0) {
    const row = document.getElementById("edrow-" + idx);
    row.classList.add("cur");
    // đừng giật danh sách về câu đang phát nếu người dùng đang sửa/cuộn chỗ khác
    const ae = document.activeElement;
    if (!(ae && document.getElementById("edlist").contains(ae)))
      row.scrollIntoView({ block: "center", behavior: "smooth" });
    document.getElementById("ednow").textContent = document.getElementById("edvi-" + idx).value;
  } else if (subSpan) {
    subSpan.textContent = ""; edStyleSub();   // ngoài câu → ẩn phụ đề xem trước
  }
}

let edAudio = null;
let edPreviewSeq = 0;
async function edPreview(i) {
  const text = document.getElementById("edvi-" + i).value.trim();
  const voice = document.getElementById("edvoice-" + i).value;
  if (!text) return;
  document.getElementById("edvideo")?.pause();   // dừng video/dub để nghe rõ câu này
  const seq = ++edPreviewSeq;   // chỉ lần nghe MỚI NHẤT được phát (synth viXTTS chậm)
  if (edAudio) {  // dừng + thu hồi blob cũ kẻo rò bộ nhớ qua nhiều lần nghe thử
    edAudio.pause();
    if (edAudio.src.startsWith("blob:")) URL.revokeObjectURL(edAudio.src);
    edAudio = null;
  }
  // Đọc CHÍNH nội dung dòng này bằng giọng đang chọn:
  //  - ref: (giọng nhân bản đã cast) → viXTTS tổng hợp câu với clip đó (đúng giọng render)
  //  - nam/nữ → edge-tts đọc nhanh để soát chữ
  // job_id (V11): server áp ⚙️ override của job (engine/giọng) → nghe thử ĐÚNG engine render
  const body = voice.startsWith("ref:")
    ? { text, voice_ref: voice.slice(4), job_id: edJobId || "" }
    : { text, voice, emotion: edSegs[i].emotion || "", job_id: edJobId || "" };
  const btn = document.querySelector(`#edrow-${i} .ed-ctl .ed-preview`);   // ĐÚNG nút loa (không phải nút Mute)
  // KHÔNG disable nút: đổi giọng rồi bấm lại sẽ tạo lần nghe mới (seq) đè lần cũ,
  // nên luôn nghe đúng giọng vừa chọn (trước đây nút bị khoá → bỏ qua lần bấm thứ 2).
  if (btn) btn.textContent = "⏳";
  try {
    const res = await fetch("/api/tts-preview", { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (seq !== edPreviewSeq) return;   // đã có lần nghe khác đè lên → bỏ kết quả này
    if (!res.ok) { toast("Nghe thử lỗi: " + ((await res.json()).detail || res.status)); return; }
    const blob = await res.blob();
    if (seq !== edPreviewSeq) return;
    const url = URL.createObjectURL(blob);
    edAudio = new Audio(url);
    edAudio.addEventListener("ended", () => URL.revokeObjectURL(url));
    edAudio.play().catch(() => {});
  } catch (e) { toast("Lỗi nghe thử: " + e); }
  finally { if (btn && btn.isConnected && seq === edPreviewSeq) btn.textContent = "🔊"; }
}

function edCollectEdits() {
  return [...edDirty].map(i => {
    const vsel = document.getElementById("edvoice-" + i).value;
    let voice = "nam", voice_ref = "";
    if (vsel === "nu") voice = "nu";
    else if (vsel.startsWith("ref:")) voice_ref = vsel.slice(4);
    // ô nhân vật (nếu series có casting) → cho sửa; không có ô thì giữ nguyên character cũ
    const ci = document.getElementById("edchar-" + i);
    const character = ci ? ci.value.trim() : (edSegs[i].character || "");
    return { id: edSegs[i].id, text_vi: document.getElementById("edvi-" + i).value,
             voice, voice_ref, character, mute: edMuteState.has(i) };
  });
}

async function edSave() {
  const edits = edCollectEdits();
  const msg = document.getElementById("edmsg");
  // chặn khi đang đọc lại (Áp dụng) hoặc đang render dở: hai luồng cùng ghi đè dubbed_audio.wav
  // → tránh va khoá file (Windows) làm hỏng/đứng dub của worker đang chạy.
  if (edRenderWatch || document.getElementById("edapplybtn")?.disabled) {
    msg.textContent = "Đang đọc lại / đang render — chờ xong rồi Lưu.";
    return;
  }
  // gửi kèm cài đặt phụ đề/che của editor → render lại áp dụng luôn (kể cả khi chỉ đổi
  // cài đặt, không sửa câu nào)
  const render = document.getElementById("cv-ed") ? readOpts("ed") : null;
  const btn = document.getElementById("edsavebtn");
  btn.disabled = true; btn.textContent = "⏳ Đang lưu...";
  // nhả dub + video để server xoá/ghi đè dubbed_audio.wav / final.mp4 (Windows khoá file
  // đang phát). Ở LẠI editor để xem tiến độ → video tạm trống trong lúc render là bình thường.
  edReleaseDub();
  const sv = document.getElementById("edvideo");
  if (sv) { sv.pause(); sv.removeAttribute("src"); try { sv.load(); } catch (e) {} }
  const reset = () => { btn.disabled = false; btn.textContent = "💾 Lưu & render lại"; };
  try {
    const bedSel = document.getElementById("ed-bedvol"), bedWrap = document.getElementById("ovf-BEDVOL");
    const bedHidden = bedWrap && bedWrap.style.display === "none";   // chỉ áp khi chế độ hạ đều
    const bed_gain_db = bedSel && bedSel.value !== "" && !bedHidden ? parseFloat(bedSel.value) : null;
    // ⚙️ override theo job: gửi cả {} (= xóa hết đè, về theo cấu hình chung)
    const env_overrides = document.getElementById("ov-TTS_SINGLE_VOICE") ? edCollectOverrides() : null;
    // đổi nhóm SÂU (dịch lại / nhận dạng lại) phá nhiều thứ → xác nhận trước
    const depth = env_overrides !== null ? edOvDepth(env_overrides) : null;
    if (depth) {   // U12: confirm CÓ SỐ từ /override-impact; endpoint lỗi → confirm tĩnh cũ
      const m = await edOvImpactMsg(env_overrides);
      if (m === null) {
        if (depth === "translate" && !confirm("Tùy chọn nhóm 🌐 Dịch bị đổi → video sẽ DỊCH LẠI TOÀN BỘ:\n- Tốn phí API dịch\n- MẤT các câu bạn đã sửa tay\nTiếp tục?")) { reset(); edRestoreEditorMedia(); return; }
        if (depth === "transcript" && !confirm("Tùy chọn nhóm 📝 Nhận dạng thoại bị đổi → làm lại TỪ TRANSCRIPT:\n- Lâu nhất (OCR/Whisper lại từ đầu)\n- MẤT bản dịch + mọi câu đã sửa tay\nTiếp tục?")) { reset(); edRestoreEditorMedia(); return; }
      } else if (m && !confirm(m)) { reset(); edRestoreEditorMedia(); return; }
    }
    const res = await fetch(`/api/jobs/${edJobId}/segments`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ edits, render, bed_gain_db, env_overrides }) });
    const raw = await res.text();
    if (!res.ok) {
      msg.textContent = "Lỗi: " + _errDetail(raw, res.status);
      // 409 = job khác đang chạy & giữ dubbed_audio.wav → KHÔNG mở lại dub kẻo khoá file worker đang ghi
      if (res.status !== 409) edRestoreEditorMedia();
      refresh(); reset(); return;
    }
    const r = raw ? JSON.parse(raw) : {};
    // KHÔNG đóng editor: ở lại theo dõi thanh tiến độ ngay trong màn hình này. Khi render
    // xong, refresh() phát hiện job rời trạng thái chạy → tự mở lại editor với bản mới.
    edDirty = new Set();
    document.querySelectorAll("#edlist .ed-row.dirty").forEach(el => el.classList.remove("dirty"));
    // base = số câu còn mp3 NGAY SAU khi server xoá câu đã đổi (server trả tts_done trong r) →
    // thanh TTS đo theo số câu phải đọc lại, không nhảy lên ~95% vì câu cũ còn mp3.
    // armGen = gen hiện tại: mọi refresh đang dở (myGen<=armGen, snapshot tiền-enqueue) sẽ bị
    // bỏ qua; refresh() gọi ngay dưới (++gen) và các tick sau mới được xét hoàn tất.
    edRenderWatch = { id: edJobId, ttsBase: (r.tts_done || 0), armGen: refreshGen };
    btn.textContent = "⏳ Đang render...";   // giữ disabled tới khi render xong (chống bấm lại)
    msg.textContent = "Đã lưu — đang render"
      + (r.changed ? ` (đọc lại ${r.changed} câu)` : "") + " · xem tiến độ bên dưới (đổi tab nếu muốn thoát)…";
    refresh();   // hiện thanh tiến độ ngay
  } catch (e) {
    msg.textContent = "Lỗi: " + e;
    edRestoreEditorMedia();   // lưu lỗi → editor còn mở, khôi phục video + tiếng
    reset();
  }
}

// #3: Áp dụng thay đổi (câu sửa + ⚙️ config + 🎚 âm nền) vào lồng tiếng — DỪNG trước
// render để nghe thử ngay trong editor (không xuất final). Panel 🎨 (phụ đề/che/khung)
// KHÔNG áp ở đây vì chỉ có nghĩa khi render.
async function edApplyVoices() {
  const edits = edCollectEdits();
  const msg = document.getElementById("edmsg");
  // thay đổi config ⚙️ / âm nền cũng áp được qua nút này (không cần sửa câu)
  const bedSel = document.getElementById("ed-bedvol"), bedWrap = document.getElementById("ovf-BEDVOL");
  const bedHidden = bedWrap && bedWrap.style.display === "none";
  const bed_gain_db = bedSel && bedSel.value !== "" && !bedHidden ? parseFloat(bedSel.value) : null;
  const env_overrides = document.getElementById("ov-TTS_SINGLE_VOICE") ? edCollectOverrides() : null;
  const depth = env_overrides !== null ? edOvDepth(env_overrides) : null;
  const bedChanged = bed_gain_db !== null && String(bed_gain_db) !== String(edBedOrig ?? "");
  if (!edits.length && !depth && !bedChanged) {
    msg.textContent = "Chưa có thay đổi nào (câu / ⚙️ tùy chọn / 🎚 âm nền) để áp dụng."; return;
  }
  // đổi nhóm SÂU phá nhiều thứ → xác nhận như nút 💾 (áp dụng cũng dịch/nhận dạng lại thật)
  if (depth) {   // U12: confirm CÓ SỐ từ /override-impact; endpoint lỗi → confirm tĩnh cũ
    const m = await edOvImpactMsg(env_overrides);
    if (m === null) {
      if (depth === "translate" && !confirm("Tùy chọn nhóm 🌐 Dịch bị đổi → video sẽ DỊCH LẠI TOÀN BỘ:\n- Tốn phí API dịch\n- MẤT các câu bạn đã sửa tay\nTiếp tục?")) return;
      if (depth === "transcript" && !confirm("Tùy chọn nhóm 📝 Nhận dạng thoại bị đổi → làm lại TỪ TRANSCRIPT:\n- Lâu nhất (OCR/Whisper lại từ đầu)\n- MẤT bản dịch + mọi câu đã sửa tay\nTiếp tục?")) return;
    } else if (m && !confirm(m)) return;
  }
  // job đã render xong: đọc lại sẽ xoá bản final hiện tại (phải render lại sau) → hỏi trước
  if (edHadFinal && !confirm("Áp dụng sẽ xoá bản video đã render (final) và cần render lại sau khi ưng. Tiếp tục?")) return;
  const btn = document.getElementById("edapplybtn");
  btn.disabled = true; btn.textContent = "⏳ Đang áp dụng...";
  const v = document.getElementById("edvideo");
  const resumeAt = v ? v.currentTime : 0;
  // PHẢI nhả dub trước khi server xoá/trộn lại (Windows khoá dubbed_audio.wav đang phát →
  // lần áp dụng thứ 2 sẽ 500 nếu không nhả). Job đã render thì cũng nhả final.mp4 (đang
  // bị video giữ) bằng cách chuyển khung hình sang video gốc trước.
  edReleaseDub();
  if (edHadFinal && v) { v.src = `/api/jobs/${edJobId}/source`; edHadFinal = false; }
  try {
    const res = await fetch(`/api/jobs/${edJobId}/segments`, { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ edits, render: null, rebuild_only: true, bed_gain_db, env_overrides }) });
    const raw = await res.text();
    if (!res.ok) { msg.textContent = "Lỗi: " + _errDetail(raw, res.status); edReloadDub(); refresh(); return; }
    const r = raw ? JSON.parse(raw) : {};
    if (!r.changed && !depth && !bedChanged) { msg.textContent = "Không có thay đổi để áp dụng (trùng bản đã lưu)."; edReloadDub(); return; }
    if (env_overrides !== null) edOvOrig = env_overrides;   // chốt bản mới làm mốc so sánh
    if (bedChanged) edBedOrig = bed_gain_db;
    msg.textContent = "Đang áp dụng + trộn lồng tiếng — xem tiến độ ngay bên dưới…";
    const j = await edWaitRebuild(edJobId);
    if (!j) { msg.textContent = "Đọc lại lâu hơn dự kiến — kiểm tra tab Jobs rồi mở lại."; return; }
    if (j.stage === "failed") { msg.textContent = "Đọc lại lỗi: " + (j.error || "(xem tab Jobs)"); edReloadDub(); return; }
    if (depth === "translate" || depth === "transcript") {
      // bản dịch/transcript đã THAY HOÀN TOÀN → nạp lại editor với dữ liệu mới
      await openEditor(edJobId);
      return;
    }
    // áp dụng xong: cập nhật edSegs theo nội dung đã lưu, bỏ đánh dấu sửa
    for (const e of edits) {
      const seg = edSegs.find(s => s.id === e.id);
      if (seg) { seg.text_vi = e.text_vi; seg.voice = e.voice; seg.voice_ref = e.voice_ref; seg.character = e.character; seg.mute = e.mute; }
    }
    edDirty = new Set();
    document.querySelectorAll("#edlist .ed-row.dirty").forEach(el => el.classList.remove("dirty"));
    edReloadDub();
    if (v && resumeAt) v.currentTime = resumeAt;   // giữ lại vị trí đang xem
    msg.textContent = "✓ Đã áp dụng vào lồng tiếng — nhấp ĐÚP vào dòng để nghe.";
    setTimeout(() => { if (msg.textContent.startsWith("✓")) msg.textContent = ""; }, 7000);
  } catch (e) {
    msg.textContent = "Lỗi: " + e;
  } finally {
    btn.disabled = false; btn.textContent = "🔁 Áp dụng & nghe thử (không render)";
  }
}
// Chờ worker đọc lại + trộn xong (job rời khỏi trạng thái chạy/hàng đợi). Trả job hoặc null.
async function edWaitRebuild(id) {
  for (let i = 0; i < 180; i++) {   // tối đa ~6 phút
    await new Promise(r => setTimeout(r, 2000));
    let jobs;
    try { jobs = await (await fetch("/api/jobs")).json(); } catch (e) { continue; }
    const j = jobs.find(x => x.id === id);
    if (j && !j.running && !j.queued) return j;
  }
  return null;
}

async function openJob(id) {
  await fetch(`/api/jobs/${id}/open`, { method: "POST" });
}

async function regenThumb(id) {
  const btn = document.getElementById("thumb-" + id);
  btn.disabled = true;
  btn.textContent = "⏳ Đang tạo (~30s)...";
  try { await fetch(`/api/jobs/${id}/thumbnail`, { method: "POST" }); }
  finally { delete lastJson[id]; refresh(); }
}

async function deleteJob(id) {
  if (!confirm(`Xóa job ${id}?\nToàn bộ video/audio/transcript của job này sẽ bị xóa khỏi ổ đĩa.`)) return;
  const res = await fetch(`/api/jobs/${id}`, { method: "DELETE" });
  if (!res.ok) toast((await res.json()).detail || "Không xóa được");
  delete lastJson[id];
  refresh();
}

// 🧹 Dọn dẹp toàn cục (audit #2): dry-run đếm trước → confirm với con số thật → dọn
async function runCleanup() {
  const btn = document.getElementById("cleanupbtn");
  const msg = document.getElementById("cleanupmsg");
  btn.disabled = true; msg.textContent = "Đang đo…";
  try {
    const d = await (await fetch("/api/cleanup?dry=true", { method: "POST" })).json();
    if (d.total_freed_mb < 1) {
      msg.textContent = "Không có gì đáng dọn (" + d.total_freed_mb + " MB).";
      return;
    }
    const ask = `Sẽ lấy lại ~${Math.round(d.total_freed_mb)} MB:\n` +
      `- ${d.jobs_cleaned} job xong: xóa WAV trung gian (~${Math.round(d.jobs_freed_mb)} MB)\n` +
      `- output/: xóa ${d.output_dupes_removed} bản final trùng nguyên vẹn (~${Math.round(d.output_freed_mb)} MB, giữ bản mới nhất)\n` +
      (d.skipped_running ? `- bỏ qua ${d.skipped_running} job đang chạy\n` : "") +
      `\nGiữ nguyên: final, phụ đề, bản dịch, giọng đã đọc, video nguồn. Tiếp tục?`;
    if (!confirm(ask)) { msg.textContent = ""; return; }
    msg.textContent = "Đang dọn…";
    const r = await (await fetch("/api/cleanup", { method: "POST" })).json();
    msg.textContent = `✓ Đã lấy lại ${Math.round(r.total_freed_mb)} MB `
      + `(${r.jobs_cleaned} job + ${r.output_dupes_removed} bản output trùng).`;
    refreshStats();
  } catch (e) {
    msg.textContent = "Lỗi: " + e;
  } finally { btn.disabled = false; }
}

