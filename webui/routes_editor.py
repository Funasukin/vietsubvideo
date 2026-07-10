"""Cụm route EDITOR (#16 tách monolith, giai đoạn 2) — tách NGUYÊN VĂN từ
webui/server.py: rerender/preview khung, segments GET/POST, override-impact,
mix-preview, tts-preview + model/helpers chỉ cụm này dùng (_OV_*, _engine_caps,
_mix_detail, _resolve_voice_ref...). Server chỉ còn include_router.
Helper dùng CHUNG với các route khác nằm ở webui/common.py."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config
from core.job import Job
from webui import worker
from webui.common import _JOB_ID_RE, _check_job_id, _job_summary, _unlink_quiet
from webui.envfile import read_env as _read_env
from webui.worker import _enqueue_reserved, _release_job, _reserve_job

router = APIRouter()

class RenderOptions(BaseModel):
    subtitle_mode: str = "soft"   # soft | cover_only | burn | none
    cover: str = "none"           # none | blur | black
    cover_top: float = 0.78       # cạnh TRÊN của băng che (tỉ lệ chiều cao)
    cover_bottom: float = 1.0     # cạnh DƯỚI của băng che (1.0 = dính đáy)
    cover_width: float = 1.0      # độ rộng vùng blur (1.0 = full width, 0.6 = 60% căn giữa)
    style: dict = {}              # font/size/color... — xem DEFAULT_STYLE trong s8_render
    # hậu kỳ giọng khi render: off|canbang|amday|rosang|dienanh|toithieu (core/voice_fx).
    # "" = THEO CẤU HÌNH CHUNG (U8 audit panel: không ghim vào job — trước đây default
    # "off" bị lưu chết vào render.fx làm knob VOICE_FX toàn cục vô hiệu vĩnh viễn)
    fx: str = ""
    frame: str = "none"           # khung viền: none|solid|double|twocolor|corner|png:<file>
    frame_color: str = "#FFD700"  # màu viền procedural
    frame_color2: str = "#FFFFFF" # màu 2 (kiểu "viền 2 màu")
    frame_width: float = 0.02     # độ dày viền = tỉ lệ chiều cao
    frame_pad: bool = False       # True = "khung ngoài": thu video vào trong, khung không che hình
    sub_split: bool = True        # tách phụ đề hiển thị theo nhịp sub gốc (giọng vẫn câu gộp)
    wm_method: str = "none"       # xóa/che watermark kênh gốc: none|delogo|blur|black|logo
    wm_box: list = []             # vùng watermark [x0,y0,x1,y1] chuẩn hóa 0..1
    crop: list = []               # cắt mép [trái,trên,phải,dưới] tỉ lệ 0..0.2 rồi phóng lại


@router.post("/api/jobs/{job_id}/rerender")
def rerender_job(job_id: str, opts: RenderOptions) -> dict:
    _check_job_id(job_id)
    # Bug #12: giữ chỗ TRƯỚC khi sửa state/xoá final — chặn "Chạy tất cả"/resume
    # xếp job chạy giữa lúc đang mutation (trước đây check xong buông lock)
    _reserve_job(job_id)
    try:
        try:
            job = Job.load(job_id)
        except FileNotFoundError:
            raise HTTPException(404, "Không có job này")

        job.render = {"subtitle_mode": opts.subtitle_mode,
                      "cover": opts.cover, "cover_top": opts.cover_top,
                      "cover_bottom": opts.cover_bottom,
                      "cover_width": opts.cover_width,
                      # fx "" = theo cấu hình chung → KHÔNG lưu key (s8 tự fallback config)
                      "style": opts.style, **({"fx": opts.fx} if opts.fx else {}),
                      "frame": opts.frame, "frame_color": opts.frame_color,
                      "frame_color2": opts.frame_color2, "frame_width": opts.frame_width,
                      "frame_pad": opts.frame_pad,
                      "wm_method": opts.wm_method, "wm_box": opts.wm_box,
                      "crop": opts.crop, "sub_split": opts.sub_split}
        job.pause_before_render = False
        # gate như save_segments: final/srt có thể đang bị trình duyệt phát giữ khoá —
        # xoá hụt mà cứ enqueue thì S8 thấy file còn → bỏ qua → "render lại" giả
        locked = [n for n in ("final.mp4", "sub_vi.srt") if not _unlink_quiet(job.dir / n)]
        if locked:
            raise HTTPException(409, "Tệp đang được phát/khoá: " + ", ".join(locked)
                                + ". Dừng phát (hoặc đợi vài giây) rồi thử lại.")
        # job.mode=="visual": không có transcript nên KHÔNG được đụng stage "metadata"
        # (s9_metadata.run đọc transcript_vi.json → crash nếu chạy nhầm cho job visual).
        drop_stages = ("rendering",) if job.mode == "visual" else ("rendering", "metadata")
        if job.mode != "visual":
            _unlink_quiet(job.dir / "metadata.json")
        job.completed_stages = [s for s in job.completed_stages if s not in drop_stages]
        job.error = None
        job.save()
    except BaseException:
        _release_job(job_id)   # mọi đường lỗi phải nhả chỗ, kẻo job kẹt "active" mãi
        raise
    _enqueue_reserved(job_id)
    return _job_summary(job.dir)


@router.post("/api/jobs/{job_id}/preview")
def preview(job_id: str, opts: RenderOptions) -> FileResponse:
    """Áp vùng che + kiểu chữ + phụ đề mẫu lên 1 frame thật — xem trước không cần render."""
    from core import brand, ffmpeg, frames
    from core.stages.s8_render import (auto_cover_chain, build_style,
                                       cover_filter, fontsdir_arg, load_sub_boxes,
                                       style_with_frame_margin)

    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    source = job.find_source()
    if source is None:
        raise HTTPException(404, "Job chưa tải video")

    # chọn 1 thời điểm có thoại + câu phụ đề thật làm mẫu
    t, sample = 30.0, "Phụ đề tiếng Việt xem thử"
    tv = job.dir / "transcript_vi.json"
    if tv.exists():
        segs = json.loads(tv.read_text(encoding="utf-8"))["segments"]
        if segs:
            mid = segs[len(segs) // 2]
            t, sample = mid["start"] + 0.3, mid["text_vi"]
    # video NGẮN hơn mốc mặc định 30s (video visual-mode/Shorts chưa có transcript
    # để chọn mốc thật) → -ss vượt EOF khiến ffmpeg không trích được khung nào.
    dur = brand._duration(source)
    if dur > 0:
        t = max(0.0, min(t, dur - 0.15))

    # chế độ che tự động: nhảy tới giữa lúc một sub gốc đang hiện để thấy hiệu ứng
    cover, auto_box = opts.cover, None
    if cover == "auto":
        boxes = load_sub_boxes(job)
        if boxes:
            hit = (next((b for b in boxes if b["start"] <= t <= b["end"]), None)
                   or min(boxes, key=lambda b: abs((b["start"] + b["end"]) / 2 - t)))
            t = (hit["start"] + hit["end"]) / 2
            auto_box = hit["box"]
        else:
            cover = "blur"  # không có dữ liệu vị trí sub → xem thử dải mờ thủ công

    raw = job.dir / "preview_raw.png"
    ffmpeg.run("-ss", f"{t:.2f}", "-i", str(source), "-frames:v", "1", str(raw))
    (job.dir / "preview.srt").write_text(
        f"1\n00:00:00,000 --> 00:00:10,000\n{sample}\n", encoding="utf-8")

    vw, vh = ffmpeg.probe_dims(source)
    if opts.subtitle_mode == "cover_only":
        sub_filter = "null"   # cover_only không in sub Việt lên hình — xem đúng như final
    else:
        style = style_with_frame_margin(opts.style, opts.frame, opts.frame_width,
                                        vw, vh, job.dir, opts.frame_pad)
        sub_filter = (f"subtitles=preview.srt:fontsdir={fontsdir_arg(job)}"
                      f":force_style='{build_style(style)}'")
    # watermark/crop y hệt S8: chạy đầu chuỗi, quy đổi tọa độ vẽ sau theo crop
    from core import watermark
    wm_r = {"wm_method": opts.wm_method, "wm_box": opts.wm_box,
            "crop": opts.crop, "logo": None}
    wm_pre = watermark.pre_chain(wm_r, vw, vh, job.dir)
    c_top, c_bot = opts.cover_top, opts.cover_bottom
    if watermark.crop_active(opts.crop):
        c_top, c_bot = (watermark.map_y(c_top, opts.crop),
                        watermark.map_y(c_bot, opts.crop))
    if auto_box is not None:
        if watermark.crop_active(opts.crop):
            auto_box = watermark.map_box(auto_box, opts.crop)
        # ảnh PNG tĩnh không có timeline (t=0) → cửa sổ enable phải bao trùm 0
        chain = (auto_cover_chain([{"start": 0.0, "end": 86400.0, "box": auto_box}],
                                  vw, vh) if auto_box else "")
        vf = f"{chain},{sub_filter}" if chain else sub_filter
    else:
        vf = cover_filter(cover, c_top, sub_filter, opts.cover_width, c_bot)
    if wm_pre:
        vf = f"{wm_pre},{vf}"
    vf = frames.append_to_vf(vf, opts.frame, opts.frame_color, opts.frame_color2,
                             opts.frame_width, vw, vh, job.dir, pad=opts.frame_pad)
    ffmpeg.run("-i", "preview_raw.png", "-vf", vf, "-frames:v", "1",
               "preview.png", cwd=job.dir)
    return FileResponse(job.dir / "preview.png", media_type="image/png",
                        headers={"Cache-Control": "no-store"})



@router.get("/api/jobs/{job_id}/segments")
def get_segments(job_id: str) -> dict:
    _check_job_id(job_id)
    tv = config.JOBS_DIR / job_id / "transcript_vi.json"
    if not tv.exists():
        raise HTTPException(404, "Job chưa dịch xong")
    data = json.loads(tv.read_text(encoding="utf-8"))
    segs = [{"id": s["id"], "start": s["start"], "end": s["end"],
             "text": s.get("text", ""), "text_vi": s.get("text_vi", ""),
             "voice": s.get("voice", "nam"), "voice_ref": s.get("voice_ref", ""),
             "character": s.get("character", ""),
             "emotion": s.get("emotion", ""),
             # mốc các dòng sub gốc bị gộp — editor tách phụ đề XEM TRƯỚC đúng nhịp
             # như make_srt (sub_split), khỏi hiện nguyên câu gộp dài
             "pieces": s.get("pieces") or [],
             "mute": bool(s.get("mute", False))}
            for s in data["segments"]]
    # Giọng mặc định nam/nữ theo ĐÚNG engine đang dùng (để editor hiển thị khớp Cấu hình)
    from core import paid_tts
    if config.TTS_ENGINE == "vixtts":
        nam_v = Path(config.VIXTTS_VOICE_NAM).stem or "(mẫu mặc định)"
        nu_v = Path(config.VIXTTS_VOICE_NU).stem or "(mẫu mặc định)"
    elif paid_tts.is_paid(config.TTS_ENGINE):
        nam_v, nu_v = paid_tts.voice_pair(config.TTS_ENGINE)
        nam_v = f"{config.TTS_ENGINE}: {nam_v}"
        nu_v = f"{config.TTS_ENGINE}: {nu_v}"
    else:
        nam_v, nu_v = config.TTS_VOICE, config.TTS_VOICE_NU
    job_dir = config.JOBS_DIR / job_id
    render = {}
    sp = job_dir / "state.json"
    if sp.exists():
        try:
            render = json.loads(sp.read_text(encoding="utf-8")).get("render") or {}
        except (json.JSONDecodeError, OSError):
            render = {}
    from core import frames, series
    job_series = ""
    if sp.exists():
        try:
            job_series = json.loads(sp.read_text(encoding="utf-8")).get("series", "") or ""
        except (json.JSONDecodeError, OSError):
            job_series = ""
    job_state = {}
    if sp.exists():
        try:
            job_state = json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            job_state = {}
    # 1 giọng HIỆU LỰC theo job: ⚙️ override thắng .env (nhãn "không tác dụng" trên
    # dropdown Nam/Nữ phải khớp điều render/nghe thử thật làm — review đối kháng)
    _sv_ov = str((job_state.get("env_overrides") or {}).get("TTS_SINGLE_VOICE", "")).strip()
    single_eff = (_sv_ov.lower() in ("1", "true")) if _sv_ov else config.TTS_SINGLE_VOICE
    return {"segments": segs,
            "engine": config.TTS_ENGINE,
            "voices": {"nam": nam_v, "nu": nu_v},
            # 1 giọng: editor hiện chú thích + nghe thử đọc giọng chính bất kể nhãn
            "single_voice": single_eff,
            "bed_gain_db": job_state.get("bed_gain_db"),
            # ⚙️ Tùy chọn video này: override đang lưu + giá trị cấu hình CHUNG hiện tại
            # (đọc .env trực tiếp — config của server có thể nạp từ lúc khởi động)
            "env_overrides": job_state.get("env_overrides") or {},
            "cfg_defaults": {k: _read_env().get(k, str(getattr(config, k, "")))
                             for k in sorted(_JOB_OVERRIDE_KEYS)},
            "render": render,
            "frames": frames.list_png(),
            "series": job_series,
            "cast_names": series.character_names(job_series),  # gợi ý nhân vật đã cast
            "has_final": (job_dir / "final.mp4").exists(),
            "has_dub": (job_dir / "dubbed_audio.wav").exists(),
            # V13 audit giọng: số đo khớp nhịp per-câu từ lần mix gần nhất → editor
            # tô cảnh báo câu bị nén mạnh / bị cắt / hụt slot. Job chưa mix → {}.
            "mix_detail": _mix_detail(job_dir),
            # U7: engine nào sẵn sàng (thiếu key/model thì disable + lý do)
            "engines": _engine_caps()}


def _mix_detail(job_dir) -> dict:
    """mix_report.json → {id(str): đo đạc per-câu} cho editor (thiếu/hỏng → {})."""
    try:
        rep = json.loads((job_dir / "mix_report.json").read_text(encoding="utf-8"))
        return {str(row["id"]): row for row in rep.get("detail", [])}
    except Exception:
        return {}


class SegmentEdit(BaseModel):
    id: int
    text_vi: str
    voice: str = "nam"   # nam | nu
    voice_ref: str = ""  # casting viXTTS: tên file giọng trong voices/ ("" = theo nam/nu)
    character: str = ""   # tên nhân vật (casting series) — sửa để S5 map đúng giọng
    mute: bool = False    # True = KHÔNG lồng tiếng Việt câu này (giữ nguyên tiếng gốc)


class SegmentEdits(BaseModel):
    edits: list[SegmentEdit]
    render: RenderOptions | None = None   # cài đặt phụ đề/che từ editor (None = giữ nguyên)
    rebuild_only: bool = False            # True = chỉ đọc lại + trộn dub rồi DỪNG trước render
                                          # (để nghe lại trong editor); False = render thẳng final
    # chỉnh âm lượng NỀN GỐC của job (dB, vd -20; kẹp [-40, 0]) — None = giữ nguyên.
    # Đổi giá trị → dựng lại nền (s6) + trộn (s7) + render, KHÔNG phải đọc lại giọng.
    bed_gain_db: float | None = None
    # override cấu hình THEO JOB ("⚙️ Tùy chọn video này"): {ENV_KEY: value}, chỉ nhận
    # khóa trong _JOB_OVERRIDE_KEYS. {} = xóa hết override (về theo cấu hình chung);
    # None = không đụng. Đổi → đọc lại câu bị ảnh hưởng (sig) + dựng nền + trộn + render.
    env_overrides: dict | None = None


# Khóa cấu hình cho phép đè THEO JOB từ editor, chia NHÓM theo độ sâu phải làm lại:
# đổi khóa nhóm nào thì pipeline chạy lại từ stage tương ứng (nhóm sâu nhất thắng).
_OV_TRANSCRIPT = {"TRANSCRIPT_SOURCE", "WHISPER_MODEL", "OCR_FPS", "OCR_CROP_TOP"}
_OV_TRANSLATE = {"TRANSLATE_PROVIDER", "CLAUDE_MODEL", "GEMINI_MODEL",
                 "TRANSLATE_STYLE_EXTRA", "CONTENT_STYLE", "TARGET_LANG"}
_OV_TTS = {"TTS_ENGINE", "TTS_SINGLE_VOICE", "TTS_VOICE", "TTS_VOICE_NU",
           "PROSODY", "EMOTION", "PROSODY_TRANSFER",
           # đợt B audit giọng: ngân sách fit nướng vào giọng đã đọc (sig :f cả edge
           # lẫn viXTTS) — đổi núm phải ĐỌC LẠI, xếp nhóm mix là knob nửa tác dụng
           "MAX_SPEEDUP"}
_OV_MIX = {"KEEP_BGM", "STRETCH_SHORT"}
# U16: DENOISE đụng S2 (audio_16k.wav cho Whisper) — depth RIÊNG sâu hơn transcript
# (Codex: nhét vào nhóm transcript là knob nửa tác dụng vì audio cũ vẫn còn)
_OV_EXTRACT = {"DENOISE"}
_JOB_OVERRIDE_KEYS = _OV_TRANSCRIPT | _OV_TRANSLATE | _OV_TTS | _OV_MIX | _OV_EXTRACT


def _has_emotion_labels(job_dir: Path) -> bool:
    """Transcript có nhãn cảm xúc HỢP LỆ nào không (≠ binhthuong — nhãn chỉ sinh
    lúc dịch với EMOTION bật)."""
    try:
        segs = json.loads((job_dir / "transcript_vi.json").read_text(encoding="utf-8"))["segments"]
        return any((s.get("emotion") or "").strip().lower()
                   in ("gap", "gian", "buon", "thitham") for s in segs)
    except Exception:
        return False


def _ov_depth_for(diff: set, job_dir: Path, new_ov: dict) -> str | None:
    """Nhóm SÂU NHẤT trong các khóa override bị đổi → chạy lại từ stage nào.
    U3 audit panel: BẬT EMOTION khi transcript chưa có nhãn → leo thang lên
    translate (nhãn chỉ sinh lúc dịch — để depth tts thì knob là no-op tuyệt đối).
    Client (edOvDepth) có logic leo thang Y HỆT để confirm khớp server."""
    if not diff:
        return None
    depth = ("extract" if diff & _OV_EXTRACT
             else "transcript" if diff & _OV_TRANSCRIPT
             else "translate" if diff & _OV_TRANSLATE
             else "tts" if diff & _OV_TTS
             else "mix")
    if (depth == "tts" and "EMOTION" in diff
            and str(new_ov.get("EMOTION", "")).strip().lower() not in ("", "0", "false")
            and not _has_emotion_labels(job_dir)):
        depth = "translate"
    return depth


def _engine_caps() -> dict:
    """Trạng thái sẵn sàng từng engine (U7) — KHÔNG lộ secret, chỉ ready+lý do.
    viXTTS kiểm nhẹ (model dir) — is_available() sẽ nạp model lên GPU, quá đắt."""
    from core import paid_tts
    caps = {"edge": {"ready": True, "reason": ""}}
    caps["vixtts"] = ({"ready": True, "reason": ""}
                      if (config.VIXTTS_DIR / "config.json").exists()
                      else {"ready": False, "reason": "Chưa tải model viXTTS"})
    for eng in ("elevenlabs", "vbee", "fpt"):
        ok, why = paid_tts.ready(eng)
        caps[eng] = {"ready": ok, "reason": "" if ok else why}
    return caps




@router.post("/api/jobs/{job_id}/segments")
def save_segments(job_id: str, body: SegmentEdits) -> dict:
    """Lưu sửa lời thoại + giọng; chỉ đọc lại TTS các câu ĐÃ ĐỔI rồi mix+render lại.
    Bug #12: giữ chỗ _active TRƯỚC khi mutation (xoá mp3/transcript/final) — chặn
    'Chạy tất cả'/resume xếp job chạy đúng lúc file đang bị xoá dở."""
    _check_job_id(job_id)
    _reserve_job(job_id)   # 409 nếu đang chạy/chờ; giữ chỗ trong suốt mutation
    try:
        out = _save_segments_inner(job_id, body)
    except BaseException:
        _release_job(job_id)   # mọi đường lỗi (404/409 khoá file/exception) nhả chỗ
        raise
    if out.pop("_enqueue", False):
        _enqueue_reserved(job_id)
    else:
        _release_job(job_id)   # không có gì thay đổi → không chạy lại
    return out


def _save_segments_inner(job_id: str, body: SegmentEdits) -> dict:
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    tv = job.dir / "transcript_vi.json"
    if not tv.exists():
        raise HTTPException(409, "Job chưa dịch xong")

    data = json.loads(tv.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in data["segments"]}
    changed: list[int] = []
    mute_changed = False
    for e in body.edits:
        s = by_id.get(e.id)
        if s is None:
            continue
        voice = "nu" if e.voice == "nu" else "nam"
        character = (e.character or "").strip()
        if (s.get("text_vi", "") != e.text_vi or s.get("voice", "nam") != voice
                or s.get("voice_ref", "") != e.voice_ref
                or s.get("character", "") != character
                or bool(s.get("mute", False)) != e.mute):
            if bool(s.get("mute", False)) != e.mute:
                mute_changed = True   # đổi Mute → vùng hạ nhạc nền đổi → phải dựng lại s6
            s["text_vi"] = e.text_vi
            s["voice"] = voice
            s["voice_ref"] = e.voice_ref
            s["character"] = character   # đổi nhân vật → S5 map lại giọng casting
            changed.append(e.id)
            s["mute"] = e.mute

    has_render = body.render is not None
    # đổi âm nền gốc (dB): kẹp [-40, 0]; chỉ tính là ĐỔI khi khác giá trị đang lưu
    bed_change = (body.bed_gain_db is not None
                  and max(-40.0, min(0.0, float(body.bed_gain_db))) != job.bed_gain_db)
    # override cấu hình theo job: lọc theo whitelist, so với bản đang lưu.
    # Nhóm SÂU NHẤT trong các khóa bị đổi quyết định chạy lại từ stage nào.
    new_ov = None
    if body.env_overrides is not None:
        new_ov = {k: str(v).strip() for k, v in body.env_overrides.items()
                  if k in _JOB_OVERRIDE_KEYS and str(v).strip() and len(str(v)) <= 200}
    old_ov = job.env_overrides or {}
    env_change = new_ov is not None and new_ov != old_ov
    ov_diff = ({k for k in set(old_ov) | set(new_ov or {})
                if old_ov.get(k) != (new_ov or {}).get(k)} if env_change else set())
    # helper chung với /override-impact — gồm cả leo thang EMOTION→translate (U3)
    ov_depth = _ov_depth_for(ov_diff, job.dir, new_ov or {}) if env_change else None
    if not changed and not has_render and not bed_change and not env_change:
        return {"changed": 0, **(_job_summary(job.dir) or {})}

    # XOÁ TRƯỚC các file mà stage sau "có thì bỏ qua" (s7: dubbed_audio.wav; s8: final.mp4,
    # sub_vi.srt) — chúng có thể đang bị TRÌNH DUYỆT phát giữ khoá. Nếu CÒN khoá → 409 NGAY,
    # khi CHƯA ghi gì (transcript/stages) → người dùng dừng phát rồi thử lại, không mất chỉnh
    # sửa và KHÔNG "thành công giả" với dub/final cũ (nếu xoá hụt, s7/s8 sẽ bỏ qua → dữ liệu cũ).
    gating = []
    if changed:
        gating += ["dubbed_audio.wav", "sub_vi.srt", "final.mp4"]
    if bed_change or env_change:
        gating += ["dubbed_audio.wav", "final.mp4"]
    if env_change and ov_depth in ("transcript", "translate"):
        gating += ["sub_vi.srt"]   # phụ đề dựng từ bản dịch → dịch/nhận dạng lại là phải xóa
    if has_render:
        gating += ["sub_vi.srt", "final.mp4"]
    locked = [n for n in dict.fromkeys(gating) if not _unlink_quiet(job.dir / n)]
    if locked:
        raise HTTPException(409, "Tệp đang được phát/khoá: " + ", ".join(locked)
                            + ". Dừng phát (hoặc đợi vài giây) rồi thử lại.")

    if changed:
        tv.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        # xóa TTS câu đã đổi → S5 chỉ đọc lại đúng các câu đó (resume bỏ qua câu còn file)
        tts_dir = job.dir / "tts"
        for sid in changed:
            (tts_dir / f"seg_{sid:04d}.mp3").unlink(missing_ok=True)
        # Tốc độ (atempo) mỗi câu phụ thuộc slot tới câu kế tiếp trong danh sách; sửa
        # 1 câu (nhất là rỗng↔có chữ) đổi slot hàng xóm → xóa HẾT _sped.wav cho S7
        # tính lại (rẻ, chỉ là atempo cục bộ; mp3 TTS của câu không đổi vẫn được giữ).
        for sped in tts_dir.glob("seg_*_sped.wav"):
            sped.unlink(missing_ok=True)
        _unlink_quiet(job.dir / "mix_report.json")   # không phải file gate, best-effort
        job.completed_stages = [s for s in job.completed_stages
                                if s not in ("tts", "mixing", "rendering")]
        if mute_changed:   # vùng hạ nhạc (s6) phụ thuộc câu nào có lồng tiếng → dựng lại nền
            (job.dir / "ducked.wav").unlink(missing_ok=True)
            job.completed_stages = [s for s in job.completed_stages if s != "bgm"]

    if bed_change:
        # âm nền mới → dựng lại nền (s6 tự phát hiện gain đổi qua ducked.mode) + trộn + render
        job.bed_gain_db = max(-40.0, min(0.0, float(body.bed_gain_db)))
        job.completed_stages = [s for s in job.completed_stages
                                if s not in ("bgm", "mixing", "rendering")]

    if env_change:
        job.env_overrides = new_ov
        # Chạy lại từ stage SÂU NHẤT bị ảnh hưởng (xem _OV_* group):
        # - mix: chỉ dựng nền + trộn + render (nhanh, không đọc lại giọng)
        # - tts: đọc lại câu bị ảnh hưởng (.sig tự phát hiện) + trộn + render
        # - translate: DỊCH LẠI toàn bộ (mất chỉnh tay câu) + đọc + trộn + render
        # - transcript: NHẬN DẠNG LẠI từ đầu (mất bản dịch + chỉnh tay) + toàn bộ sau
        drop = {"bgm", "mixing", "rendering"}
        if ov_depth in ("tts", "translate", "transcript", "extract"):
            drop.add("tts")
        if ov_depth in ("translate", "transcript", "extract"):
            drop.add("translating")
            _unlink_quiet(job.dir / "transcript_vi.json")
            _unlink_quiet(job.dir / "metadata.json")   # title/desc theo bản dịch cũ
            _unlink_quiet(job.dir / "mix_report.json")
            shutil.rmtree(job.dir / "tts", ignore_errors=True)  # text đổi → mp3 cũ sai
        if ov_depth in ("transcript", "extract"):
            drop.add("transcribing")
            for name in ("transcript_zh.json", "ocr_raw.json", "sub_boxes.json",
                         "glossary_auto.json", "stage_progress.json"):
                _unlink_quiet(job.dir / name)
        if ov_depth == "extract":
            # U16: DENOISE đổi → audio_16k.wav phải trích lại (S2 skip khi file còn)
            drop.add("extracting")
            _unlink_quiet(job.dir / "audio_16k.wav")
        job.completed_stages = [s for s in job.completed_stages if s not in drop]

    if has_render:
        # áp dụng cài đặt phụ đề/che rồi dựng lại CHỈ khâu render (S8). Giữ nguyên
        # metadata/thumbnail (không phụ thuộc sub/che) để khỏi tốn thêm 1 call Claude.
        r = body.render
        job.render = {"subtitle_mode": r.subtitle_mode, "cover": r.cover,
                      "cover_top": r.cover_top, "cover_bottom": r.cover_bottom,
                      "cover_width": r.cover_width, "style": r.style,
                      **({"fx": r.fx} if r.fx else {}),   # "" = theo cấu hình chung
                      "frame": r.frame, "frame_color": r.frame_color,
                      "frame_color2": r.frame_color2, "frame_width": r.frame_width}
        job.completed_stages = [s for s in job.completed_stages if s != "rendering"]

    # rebuild_only: đọc lại + trộn dub rồi DỪNG trước render (nghe lại trong editor);
    # ngược lại render thẳng ra final.
    job.pause_before_render = bool(body.rebuild_only)
    job.error = None
    job.save()
    # KHÔNG _enqueue ở đây — wrapper save_segments xếp hàng qua _enqueue_reserved
    # (job đã được giữ chỗ từ trước khi mutation)
    return {"changed": len(changed), "_enqueue": True,
            **(_job_summary(job.dir) or {})}


class OverrideImpactBody(BaseModel):
    env_overrides: dict = {}


@router.post("/api/jobs/{job_id}/override-impact")
def override_impact(job_id: str, body: OverrideImpactBody) -> dict:
    """DRY-RUN tác động của ⚙️ override ĐỀ XUẤT (U12 audit panel): chạy lại từ đâu,
    bao nhiêu câu phải đọc lại, gửi bao nhiêu ký tự cho dịch vụ trả phí, mất gì.
    Thuần dữ liệu (core/voicesig — cùng resolver với S5), không đụng config toàn
    cục, không load model — trả lời trong mili-giây."""
    _check_job_id(job_id)
    job_dir = config.JOBS_DIR / job_id
    tv = job_dir / "transcript_vi.json"
    if not tv.exists():
        raise HTTPException(409, "Job chưa dịch xong")
    try:
        state = json.loads((job_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    old_ov = state.get("env_overrides") or {}
    new_ov = {k: str(v).strip() for k, v in (body.env_overrides or {}).items()
              if k in _JOB_OVERRIDE_KEYS and str(v).strip() and len(str(v)) <= 200}
    diff = {k for k in set(old_ov) | set(new_ov) if old_ov.get(k) != new_ov.get(k)}
    base_depth = ("transcript" if diff & _OV_TRANSCRIPT
                  else "translate" if diff & _OV_TRANSLATE
                  else "tts" if diff & _OV_TTS
                  else "mix") if diff else None
    depth = _ov_depth_for(diff, job_dir, new_ov)
    segs = [s for s in json.loads(tv.read_text(encoding="utf-8"))["segments"]
            if s.get("text_vi", "").strip() and not s.get("mute")]
    stages_map = {"mix": ["bgm", "mixing", "rendering"],
                  "tts": ["tts", "bgm", "mixing", "rendering"],
                  "translate": ["translating", "tts", "bgm", "mixing", "rendering"],
                  "transcript": ["transcribing", "translating", "tts", "bgm",
                                 "mixing", "rendering"],
                  "extract": ["extracting", "transcribing", "translating", "tts",
                              "bgm", "mixing", "rendering"]}
    out = {"depth": depth, "stages": stages_map.get(depth or "", []),
           "segments_total": len(segs), "tts_regenerate": 0, "paid_tts_chars": 0,
           "manual_edits_at_risk": 0, "estimated_seconds": [0, 0], "warnings": []}
    if depth is None:
        return out
    if base_depth == "tts" and depth == "translate":
        out["warnings"].append("Bật nhãn cảm xúc khi video CHƯA có nhãn → phải "
                               "dịch lại toàn bộ để tạo nhãn.")

    from core import voicesig
    env_eff = {**_read_env(), **new_ov}
    st = voicesig.TtsSettings.from_env(env_eff)
    caps = _engine_caps()
    if st.engine in caps and not caps[st.engine]["ready"]:
        out["warnings"].append(f"Engine {st.engine}: {caps[st.engine]['reason']}")

    if depth == "mix":
        out["estimated_seconds"] = [5, 30]
        return out
    if depth in ("translate", "transcript", "extract"):
        # chữ ký TƯƠNG LAI phụ thuộc output LLM/ASR — không giả vờ đếm được:
        # toàn bộ output sau stage bị làm lại
        out["tts_regenerate"] = len(segs)
        out["manual_edits_at_risk"] = len(segs)
        if st.engine in voicesig.PAID_ENGINES:
            out["paid_tts_chars"] = sum(len(s.get("text_vi", "")) for s in segs
                                        if not s.get("voice_ref"))
        out["estimated_seconds"] = ([60, 300] if depth == "translate"
                                    else [120, 600] if depth == "transcript"
                                    else [150, 700])
        out["warnings"].append("Các câu đã sửa tay sẽ MẤT (dịch/nhận dạng lại).")
        return out

    # depth == "tts": so chữ ký dự kiến với .sig trên đĩa — đúng cơ chế resume của S5
    prosody_toggled = "PROSODY" in diff
    regen = 0
    paid_chars = 0
    for s in segs:
        sigf = job_dir / "tts" / f"seg_{s['id']:04d}.sig"
        try:
            disk = sigf.read_text(encoding="utf-8")
        except OSError:
            disk = None
        need = disk != voicesig.voice_signature(s, st)
        # bật/tắt Tông giọng: nhãn prosody ĐO LẠI lúc chạy — không đoán trước được
        # → tính mọi câu edge không cast là ảnh hưởng (chặn trên) + cảnh báo
        if prosody_toggled and st.engine == "edge" and not s.get("voice_ref"):
            need = True
        if need:
            regen += 1
            if st.engine in voicesig.PAID_ENGINES and not s.get("voice_ref"):
                paid_chars += len(s.get("text_vi", ""))
    out["tts_regenerate"] = regen
    out["paid_tts_chars"] = paid_chars
    if prosody_toggled:
        out["warnings"].append("Bật/tắt Tông giọng: số câu đọc lại là CHẶN TRÊN "
                               "(nhãn đo lại lúc chạy mới biết chính xác).")
    per = {"edge": (0.8, 2.0), "vixtts": (4.0, 9.0)}.get(st.engine, (1.0, 3.0))
    out["estimated_seconds"] = [int(regen * per[0] + 10), int(regen * per[1] + 30)]
    return out


class MixPreviewBody(BaseModel):
    t: float = 0.0             # mốc bắt đầu cửa sổ (giây, theo video gốc)
    duration_s: float = 10.0   # độ dài cửa sổ (kẹp 3..20)
    bed_gain_db: float | None = None   # thử gain CHƯA lưu; None = theo job/cấu hình
    keep_bgm: str = ""         # "" = theo hiệu lực hiện tại; "0" | "flat" | "1"
    stretch_short: str = ""    # "" = theo hiệu lực; "0" | "1"


@router.post("/api/jobs/{job_id}/mix-preview")
def mix_preview(job_id: str, body: MixPreviewBody):
    """U14: nghe thử ~10s quanh câu đang chọn với chỉnh MIX chưa lưu (âm nền /
    chế độ nền / kéo giãn). Dựng bằng ĐÚNG primitive của render thật
    (s6_bgm.apply_duck + s7_mix.render_voice — Codex: bản 'gần giống' phá lòng
    tin). Giới hạn trung thực: đổi engine/giọng/MAX_SPEEDUP cần đọc lại giọng —
    KHÔNG thuộc preview này; demucs chưa tách sẵn thì nền rơi về audio gốc."""
    _check_job_id(job_id)
    job_dir = config.JOBS_DIR / job_id
    tv = job_dir / "transcript_vi.json"
    if not tv.exists() or not (job_dir / "tts").is_dir():
        raise HTTPException(409, "Job chưa có bản lồng tiếng để nghe thử")
    from core import audio_np, duration
    from core.stages import s6_bgm, s7_mix

    # cấu hình HIỆU LỰC: body (chưa lưu) > env_overrides job > .env/config
    try:
        state = json.loads((job_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    ov = state.get("env_overrides") or {}
    env = _read_env()

    def eff(key: str, default: str) -> str:
        return str(ov.get(key) or env.get(key) or default).strip()

    keep_raw = (body.keep_bgm or eff("KEEP_BGM", "0")).lower()
    duck_all = keep_raw == "flat"
    gain_db = (body.bed_gain_db if body.bed_gain_db is not None
               else state.get("bed_gain_db"))
    if gain_db is None:
        try:
            gain_db = float(eff("DUCK_GAIN_DB", str(config.DUCK_GAIN_DB)))
        except ValueError:
            gain_db = config.DUCK_GAIN_DB
    gain_db = max(-40.0, min(0.0, float(gain_db)))
    stretch = (body.stretch_short if body.stretch_short in ("0", "1")
               else eff("STRETCH_SHORT", "0")) == "1"

    # nền: demucs chỉ dùng khi ĐÃ tách sẵn (tách mới mất nhiều phút — không phải preview)
    src = job_dir / "audio_full.wav"
    warn = ""
    if keep_raw == "1":
        if (job_dir / "no_vocals.wav").exists():
            src = job_dir / "no_vocals.wav"
        else:
            warn = "demucs chưa tách — nền preview dùng audio gốc"
    if not src.exists():
        raise HTTPException(409, "Thiếu audio nền (audio_full.wav)")

    win = max(3.0, min(20.0, float(body.duration_s or 10.0)))
    t0 = max(0.0, float(body.t or 0.0))
    bed, rate = audio_np.read_wav_slice(src, t0, win)
    if not len(bed):
        raise HTTPException(400, "Mốc nghe thử ngoài video")

    data = json.loads(tv.read_text(encoding="utf-8"))
    full = sorted(data["segments"], key=lambda s: s["start"])
    bed = s6_bgm.apply_duck(bed, rate, full, gain_db, duck_all, t0_s=t0)

    # đặt các câu dub giao với cửa sổ — slot y công thức S7 (tới start câu kế)
    fit = duration.load_report(job_dir)
    import numpy as np
    import uuid as _uuid
    total = len(bed)
    tmp_tag = _uuid.uuid4().hex[:8]
    tmps: list[Path] = []
    try:
        for k, seg in enumerate(full):
            if not seg.get("text_vi", "").strip() or seg.get("mute"):
                continue
            nxt = full[k + 1]["start"] if k + 1 < len(full) else None
            slot_s = (nxt - seg["start"]) if nxt is not None else win
            if seg["start"] >= t0 + win or seg["start"] + slot_s <= t0:
                continue
            if not (job_dir / "tts" / f"seg_{seg['id']:04d}.mp3").exists():
                continue
            slot = max(int(0.3 * rate), int(slot_s * rate))
            espeed = float(fit.get(str(seg["id"]), {}).get("engine_speed") or 1.0)
            sped = config.DATA_DIR / f"_mixprev_{tmp_tag}_{seg['id']:04d}.wav"
            tmps.append(sped)
            try:
                voice, _row = s7_mix.render_voice(job_dir, seg, rate, slot, espeed,
                                                  stretch, sped_path=sped)
            except Exception:
                continue   # 1 câu hỏng không được làm chết preview
            rel = int((seg["start"] - t0) * rate)
            v0 = max(0, -rel)          # câu bắt đầu trước cửa sổ → cắt phần đầu
            b0 = max(0, rel)
            n = min(total - b0, len(voice) - v0)
            if n <= 0:
                continue
            mixed = (bed[b0:b0 + n].astype(np.int32)
                     + voice[v0:v0 + n].astype(np.int32))
            bed[b0:b0 + n] = np.clip(mixed, -32768, 32767).astype(np.int16)
    finally:
        for p in tmps:
            p.unlink(missing_ok=True)

    import io
    import wave as _wave
    buf = io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(bed.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.ascontiguousarray(bed, dtype=np.int16).tobytes())
    from fastapi.responses import Response
    return Response(content=buf.getvalue(), media_type="audio/wav",
                    headers={"Cache-Control": "no-store",
                             **({"X-Preview-Note": warn} if warn else {})})


class TtsPreviewBody(BaseModel):
    text: str
    voice: str = "nam"
    voice_ref: str = ""   # tên clip trong voices/ → đọc câu này bằng viXTTS (nhân bản)
    emotion: str = ""     # nhãn cảm xúc của câu → nghe thử ĐÚNG sắc thái sẽ render
    job_id: str = ""      # V11 audit giọng: áp ⚙️ override của job (engine/giọng) —
                          # không có thì nghe thử theo cấu hình CHUNG như cũ


def _resolve_voice_ref(name: str) -> str | None:
    """Đường dẫn clip giọng trong voices/ nếu hợp lệ (chặn ../ và path tuyệt đối).
    Khớp logic _vixtts_ref ở core/stages/s5_tts.py để nghe thử = đúng lúc render."""
    if not name:
        return None
    base = config.VOICES_DIR.resolve()
    p = (config.VOICES_DIR / name).resolve()
    return str(p) if p.is_relative_to(base) and p.is_file() else None


@router.post("/api/tts-preview")
def tts_preview(body: TtsPreviewBody):
    """Đọc thử MỘT câu → mp3, nghe trước khi lưu/render lại.

    voice_ref (giọng nhân bản đã cast) → đọc CHÍNH câu này bằng viXTTS với clip đó,
    đúng giọng sẽ render. Không có voice_ref → nam/nữ đọc nhanh bằng edge-tts."""
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Thiếu text")
    if len(text) > 500:
        raise HTTPException(400, "Câu quá dài để nghe thử")

    from fastapi.responses import Response

    # Giọng nhân bản: tổng hợp câu bằng viXTTS với clip mẫu (KHÔNG phát clip mẫu thô)
    if body.voice_ref:
        ref = _resolve_voice_ref(body.voice_ref)
        if not ref:
            raise HTTPException(404, "Không tìm thấy clip giọng trong voices/")
        from core import vixtts
        if not vixtts.is_available():
            raise HTTPException(503, "viXTTS chưa sẵn sàng (cần GPU + cài đặt viXTTS)")
        import uuid as _uuid
        out = config.DATA_DIR / f"_tts_preview_{_uuid.uuid4().hex}.mp3"
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            vixtts.synth(text, ref, str(out))
            if not out.exists() or out.stat().st_size == 0:
                raise HTTPException(502, "viXTTS trả file rỗng")
            data = out.read_bytes()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, f"viXTTS lỗi: {e}")
        finally:
            out.unlink(missing_ok=True)
        return Response(content=data, media_type="audio/mpeg",
                        headers={"Cache-Control": "no-store"})

    # V11 audit giọng: nghe thử phải TRUNG THỰC với render — áp ⚙️ override của job
    # (engine/giọng/1-giọng) nếu editor gửi job_id; trước đây luôn dùng cấu hình chung
    # nên đổi engine per-job xong bấm 🔊 vẫn nghe engine cũ.
    ov: dict = {}
    if body.job_id and _JOB_ID_RE.match(body.job_id):
        sp = config.JOBS_DIR / body.job_id / "state.json"
        try:
            ov = json.loads(sp.read_text(encoding="utf-8")).get("env_overrides") or {}
        except (OSError, json.JSONDecodeError):
            ov = {}

    def _ov(key: str, cur):
        v = str(ov.get(key, "")).strip()
        return v if v else cur

    # engine trả phí (PLAN 11 C/D): nghe thử bằng CHÍNH dịch vụ đó (tốn phí ~1 câu)
    from core import langs, paid_tts
    eng = _ov("TTS_ENGINE", config.TTS_ENGINE)
    single = str(_ov("TTS_SINGLE_VOICE", "1" if config.TTS_SINGLE_VOICE else "0")
                 ).lower() in ("1", "true")
    # ngôn ngữ đích HIỆU LỰC theo job (⚙️ TARGET_LANG) — job đổi ngôn ngữ mà nghe
    # thử theo ngôn ngữ toàn cục là sai engine lẫn giọng (review đối kháng)
    lang = str(_ov("TARGET_LANG", langs.code())).strip().lower()
    lang = lang if lang in langs.LANGS else "vi"
    is_vi = lang == "vi"
    # nghe thử phải khớp giọng SẼ render: chế độ 1 giọng đọc mọi câu bằng giọng chính
    # (cùng logic s5_tts._seg_nu) — kẻo nhãn "nữ" nghe thử ra HoaiMy mà render NamMinh
    nu = body.voice == "nu" and not single

    # V11: engine viXTTS + câu KHÔNG cast → render sẽ đọc viXTTS giọng mặc định,
    # nghe thử cũng phải vậy (trước đây rơi xuống edge — nghe một đằng render một nẻo)
    if eng == "vixtts" and is_vi:
        from core import emotion as _emo, vixtts
        name = _ov("VIXTTS_VOICE_NU" if nu else "VIXTTS_VOICE_NAM",
                   config.VIXTTS_VOICE_NU if nu else config.VIXTTS_VOICE_NAM)
        # khớp thứ tự _vixtts_ref của render: clip mẫu theo CẢM XÚC (khi EMOTION bật
        # toàn cục) thắng giọng mặc định; câu không nhãn → vixtts_sample trả None
        es = _emo.vixtts_sample({"voice": body.voice, "emotion": body.emotion})
        if es:
            name = es
        ref = _resolve_voice_ref(name) or (
            str(config.VIXTTS_DIR / "vi_sample.wav")
            if (config.VIXTTS_DIR / "vi_sample.wav").is_file() else None)
        if ref and vixtts.is_available():
            import uuid as _uu
            vout = config.DATA_DIR / f"_tts_preview_{_uu.uuid4().hex}.mp3"
            try:
                vixtts.synth(text, ref, str(vout))
                data = vout.read_bytes()
                return Response(content=data, media_type="audio/mpeg",
                                headers={"Cache-Control": "no-store"})
            except Exception as e:
                print(f"  nghe thử viXTTS mặc định lỗi ({e}) → edge")
            finally:
                vout.unlink(missing_ok=True)
    if paid_tts.is_paid(eng) and not (eng in paid_tts.VI_ONLY and not is_vi):
        ok, why = paid_tts.ready(eng)
        if not ok:
            raise HTTPException(400, why)
        nam_v, nu_v = paid_tts.voice_pair(eng)
        import uuid as _u   # hàm này có "import uuid" cục bộ bên dưới → tránh UnboundLocalError
        pout = config.DATA_DIR / f"_tts_preview_{_u.uuid4().hex}.mp3"
        pout.parent.mkdir(parents=True, exist_ok=True)
        try:
            paid_tts.synth(eng, text, nu_v if nu else nam_v, pout)
            data = pout.read_bytes()
        except RuntimeError as e:
            raise HTTPException(502, f"{eng} lỗi: {e}")
        finally:
            pout.unlink(missing_ok=True)
        return Response(content=data, media_type="audio/mpeg",
                        headers={"Cache-Control": "no-store"})

    # giọng theo NGÔN NGỮ ĐÍCH hiệu lực (#16) — nghe thử đúng giọng sẽ render
    from core import emotion as emo
    _nam, _nu = langs.edge_voices(lang)
    if is_vi:   # V11: tôn trọng ⚙️ giọng edge override theo job
        _nam = _ov("TTS_VOICE", _nam)
        _nu = _ov("TTS_VOICE_NU", _nu)
    voice = _nu if nu else _nam
    # nhãn cảm xúc như lúc render (prosody đo audio thì bỏ — nghe thử lẻ không có audio)
    emo_kw = emo.edge_kwargs({"voice": body.voice, "emotion": body.emotion})

    import asyncio
    import uuid

    import edge_tts
    from fastapi.responses import Response

    # file tạm riêng mỗi request → không bị request khác ghi đè khi trả về
    out = config.DATA_DIR / f"_tts_preview_{uuid.uuid4().hex}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)

    # edge-tts hay lỗi "NoAudioReceived" TẠM THỜI (Microsoft chặn/nghẽn) → thử lại vài
    # lần như S5, nếu không nghe thử lẻ sẽ thỉnh thoảng lỗi dù pipeline batch vẫn chạy.
    async def _gen() -> bool:
        last = None
        for attempt in range(1, 4):
            out.unlink(missing_ok=True)
            try:
                await asyncio.wait_for(
                    edge_tts.Communicate(text, voice, **emo_kw).save(str(out)),
                    timeout=config.TTS_TIMEOUT_S)
            except Exception as e:  # noqa: BLE001 — gồm cả NoAudioReceived
                last = e
            if out.exists() and out.stat().st_size > 0:
                return True
            if attempt < 3:
                await asyncio.sleep(attempt)   # 1s, 2s
        if last:
            raise last
        return False

    try:
        if not asyncio.run(_gen()):
            raise HTTPException(502, "edge-tts không trả audio sau nhiều lần thử "
                                     "(mạng/Microsoft chặn?) — thử lại hoặc dùng giọng viXTTS")
        data = out.read_bytes()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"edge-tts lỗi: {e}")
    finally:
        out.unlink(missing_ok=True)
    return Response(content=data, media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store"})


