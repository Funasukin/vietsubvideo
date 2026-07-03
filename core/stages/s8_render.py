"""S8: sinh phụ đề sub_vi.srt + ghép audio lồng tiếng (và phụ đề) → final.mp4.

SUBTITLE_MODE quyết định cách lồng phụ đề (xem config.py). sub_vi.srt luôn
được tạo để Phase 3 upload làm caption YouTube/Facebook.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import textwrap
from datetime import datetime

import config
from core import brand, ffmpeg, frames, watermark
from core.job import Job


def fontsdir_arg(job: Job) -> str:
    """Đường dẫn (tương đối từ cwd=job.dir) tới fonts/ của dự án — libass nạp font
    tùy biến người dùng thả vào, KHÔNG cần cài vào Windows. Tương đối nên né
    được rắc rối escape đường dẫn Windows (dấu ':' ổ đĩa) trong filtergraph."""
    config.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    return os.path.relpath(config.FONTS_DIR, job.dir).replace("\\", "/")


def _fmt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _wrap(text: str) -> str:
    lines = textwrap.wrap(text, width=42)
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return "\n".join(lines)


# tách câu Việt tại dấu câu (ưu tiên) để chia theo nhịp sub gốc
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:.!?…—])\s+")


def _split_text(text: str, weights: list[float]) -> list[str] | None:
    """Chia text thành len(weights) phần theo tỉ trọng, cắt tại dấu câu khi đủ vế
    (không đủ thì cắt theo từ). None nếu quá ít từ để chia."""
    n = len(weights)
    parts = [p for p in _CLAUSE_SPLIT.split(text) if p.strip()]
    if len(parts) < n:
        parts = text.split()
        if len(parts) < n:
            return None
    tot_w = sum(weights) or 1.0
    tot_len = sum(len(p) + 1 for p in parts)
    out, ci = [], 0
    for i in range(n):
        left_parts = len(parts) - ci
        if i == n - 1:
            take = left_parts
        else:
            target = tot_len * weights[i] / tot_w
            take, ln = 0, 0.0
            # luôn chừa đủ mỗi phần sau ≥1 vế; vượt quá nửa vế kế thì dừng
            while take < left_parts - (n - 1 - i):
                nxt = len(parts[ci + take]) + 1
                if take > 0 and ln + nxt / 2 > target:
                    break
                ln += nxt
                take += 1
            take = max(1, take)
        out.append(" ".join(parts[ci:ci + take]))
        ci += take
    return out


def make_srt(job: Job, split: bool = False) -> None:
    """split=True: câu nào từng bị GỘP từ nhiều dòng sub gốc thì tách chữ Việt ra
    hiển thị theo đúng mốc thời gian từng dòng (nhịp như bản gốc). Giọng đọc không
    đổi — vẫn dùng câu gộp. Job cũ không có dữ liệu pieces → tự về hiện cả câu."""
    srt_path = job.dir / "sub_vi.srt"
    if srt_path.exists():
        return
    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    # bỏ câu rỗng và câu bị "Mute" → câu Mute để hoàn toàn nguyên gốc (không phụ đề Việt)
    segs = [s for s in data["segments"] if s["text_vi"].strip() and not s.get("mute")]

    entries: list[tuple[float, float, str]] = []
    for seg in segs:
        pieces = seg.get("pieces") or []
        if split and len(pieces) > 1:
            texts = _split_text(seg["text_vi"],
                                [max(1.0, float(p.get("len", 1))) for p in pieces])
            if texts:
                entries += [(p["start"], p["end"], t)
                            for p, t in zip(pieces, texts) if t.strip()]
                continue
        entries.append((seg["start"], seg["end"], seg["text_vi"]))

    blocks = []
    for n, (start, end, text) in enumerate(entries):
        end = max(end, start + 1.0)  # hiển thị tối thiểu 1s
        if n + 1 < len(entries):
            end = min(end, entries[n + 1][0] - 0.05)
        if end <= start:
            end = start + 0.5
        blocks.append(
            f"{n + 1}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{_wrap(text)}\n"
        )
    srt_path.write_text("\n".join(blocks), encoding="utf-8")


# Kiểu chữ mặc định cho phụ đề vẽ cứng — override theo job qua job.render["style"]
DEFAULT_STYLE = {
    "font": "Arial",
    "size": 18,
    "color": "#FFFFFF",          # màu chữ
    "outline_color": "#000000",  # màu viền
    "outline": 2,                # độ dày viền (0 = không viền)
    "back": False,               # hộp nền sau chữ
    "back_color": "#000000",
    "back_opacity": 0.6,         # 0..1
    "margin_v": 16,              # cách đáy (theo thang PlayResY=384 của libass)
}

_HEX = re.compile(r"^#?([0-9A-Fa-f]{6})$")


def _ass_color(hex_color: str, opacity: float = 1.0) -> str:
    """#RRGGBB → &HAABBGGRR (ASS: alpha 00 = đặc, FF = trong suốt)."""
    m = _HEX.match(str(hex_color))
    rgb = m.group(1) if m else "FFFFFF"
    r, g, b = rgb[0:2], rgb[2:4], rgb[4:6]
    alpha = max(0, min(255, round((1 - float(opacity)) * 255)))
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def build_style(style: dict | None) -> str:
    s = {**DEFAULT_STYLE, **(style or {})}
    # Chỉ bỏ ký tự phá cú pháp filtergraph/force_style: ',' (ngăn cách entry),
    # "'" (kết thúc chuỗi force_style='...'), '=' , '\' và ký tự điều khiển.
    # GIỮ '.', '+', '(' ... để FontName khớp đúng tên họ font libass cần — nếu
    # lọc quá tay thì libass không tìm ra font và âm thầm về font mặc định.
    raw = str(s["font"])
    font = "".join(c for c in raw if c not in ",'=\\" and ord(c) >= 32)[:100] or "Arial"
    if font != raw:
        print(f"  ! Tên font '{raw}' bị lọc thành '{font}' — nếu sai, libass sẽ "
              f"dùng font mặc định.")
    parts = [
        f"FontName={font}",
        f"FontSize={int(s['size'])}",
        f"PrimaryColour={_ass_color(s['color'])}",
        f"OutlineColour={_ass_color(s['outline_color'], 0.7)}",
        f"Outline={int(s['outline'])}",
        f"MarginV={int(s['margin_v'])}",
    ]
    if s["back"]:
        # BorderStyle=4 (libass): hộp nền màu BackColour, vẫn giữ viền chữ
        parts += ["BorderStyle=4",
                  f"BackColour={_ass_color(s['back_color'], float(s['back_opacity']))}"]
    return ",".join(parts)


# Nới vùng che quanh box chữ OCR (tỉ lệ khung hình) — giữ nhỏ để ô mờ ÔM SÁT chữ,
# chỉ chừa đủ phủ viền/đổ bóng glyph (delogo nội suy từ pixel quanh box).
AUTO_PAD_X = 0.006
AUTO_PAD_Y = 0.010


def load_sub_boxes(job: Job) -> list[dict]:
    """sub_boxes.json do OCR ghi: [{start, end, box: [x0,y0,x1,y1] 0..1}]."""
    p = job.dir / "sub_boxes.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def auto_cover_chain(boxes: list[dict], w: int, h: int) -> str:
    """Chuỗi delogo che đúng vùng chữ sub gốc, đúng khoảng thời gian nó hiện.

    delogo nội suy từ pixel xung quanh nên trông như vết mờ — vùng nhỏ hơn
    nhiều so với dải blur cố định, và biến mất khi không có sub.
    """
    filters = []
    for b in boxes:
        x0 = max(2, int((b["box"][0] - AUTO_PAD_X) * w))
        y0 = max(2, int((b["box"][1] - AUTO_PAD_Y) * h))
        x1 = min(w - 2, int((b["box"][2] + AUTO_PAD_X) * w))
        y1 = min(h - 2, int((b["box"][3] + AUTO_PAD_Y) * h))
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        filters.append(f"delogo=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0}"
                       f":enable='between(t,{b['start']:.3f},{b['end']:.3f})'")
    return ",".join(filters)


def cover_filter(cover: str, top: float, sub_filter: str, width: float = 1.0,
                 bottom: float = 1.0) -> str:
    """Chuỗi -vf: che vùng sub gốc (blur/black) rồi vẽ phụ đề lên trên.

    Băng che nằm dọc từ `top` đến `bottom` (tỉ lệ chiều cao 0..1), rộng `width`
    căn giữa. bottom=1.0 = dính đáy (mặc định cũ); hạ bottom + top để dời băng
    lên giữa khung khi sub gốc không nằm sát đáy.
    """
    top = max(0.0, min(0.97, top))
    bottom = max(top + 0.03, min(1.0, bottom))
    band_h = bottom - top
    if cover == "blur":
        w = max(0.1, min(1.0, width))
        # gblur thay boxblur: bán kính boxblur lớn vượt plane chroma khi băng
        # mỏng/đặt giữa khung → lỗi -22; gblur theo sigma an toàn ở mọi kích thước
        return (f"split[a][b];"
                f"[b]crop=iw*{w:.3f}:ih*{band_h:.3f}:iw*(1-{w:.3f})/2:ih*{top:.3f},gblur=sigma=14[blur];"
                f"[a][blur]overlay=(W-w)/2:H*{top:.3f},{sub_filter}")
    if cover == "black":
        return (f"drawbox=x=0:y=ih*{top:.3f}:w=iw:h=ih*{band_h:.3f}"
                f":color=black:t=fill,{sub_filter}")
    return sub_filter


def style_with_frame_margin(style: dict | None, frame: str, frame_width: float,
                            vw: int, vh: int, job_dir, pad: bool) -> dict:
    """Tự đẩy phụ đề lên khỏi khung viền: cộng margin_v (thang PlayResY=384 của
    libass) thêm bề dày khung ở mép dưới — chữ không bao giờ bị khung đè.
    pad=True ("khung ngoài"): video đã co vào trong khung → khỏi đẩy."""
    s = dict(style or {})
    if frame and frame != "none" and not pad:
        ins = frames.bottom_inset_px(frame, frame_width, vw, vh, job_dir)
        if ins:
            base = int(s.get("margin_v", DEFAULT_STYLE["margin_v"]))
            s["margin_v"] = base + math.ceil(ins * 384 / vh) + 2
    return s


def run(job: Job) -> None:
    out_path = job.dir / "final.mp4"
    if out_path.exists():
        return

    r = job.render or {}
    # nhịp phụ đề: 1 = tách theo nhịp sub gốc (mặc định) | 0 = hiện cả câu gộp
    sub_split = str(r.get("sub_split", config.SUB_SPLIT)).strip().lower() in ("1", "true")
    make_srt(job, split=sub_split)
    source = job.find_source()
    dubbed = job.dir / "dubbed_audio.wav"
    mode = r.get("subtitle_mode", config.SUBTITLE_MODE)
    cover = r.get("cover", config.COVER_SOURCE_SUBS)
    top = float(r.get("cover_top", config.COVER_TOP))
    cw = float(r.get("cover_width", 1.0))
    cb = float(r.get("cover_bottom", 1.0))
    frame = r.get("frame", config.FRAME)
    frame_color = r.get("frame_color", config.FRAME_COLOR)
    frame_color2 = r.get("frame_color2", config.FRAME_COLOR2)
    frame_width = float(r.get("frame_width", config.FRAME_WIDTH))
    frame_pad = str(r.get("frame_pad", config.FRAME_PAD)).strip().lower() in ("1", "true")
    # brand/xuất bản (asset dùng chung, cấu hình toàn cục — xem core/brand.py)
    music = r.get("music", config.MUSIC)
    music_vol = r.get("music_vol", config.MUSIC_VOL)
    logo = r.get("logo", config.LOGO)
    logo_pos = r.get("logo_pos", config.LOGO_POS)
    logo_scale = r.get("logo_scale", config.LOGO_SCALE)
    logo_opacity = r.get("logo_opacity", config.LOGO_OPACITY)
    intro = r.get("intro", config.INTRO)
    outro = r.get("outro", config.OUTRO)
    master = str(r.get("master", config.MASTER)).strip().lower() in ("1", "true")
    subscribe = str(r.get("subscribe", config.SUBSCRIBE)).strip().lower()
    # cover_only: che sub gốc/khung/logo như burn nhưng KHÔNG in sub Việt lên hình
    # (upload sub_vi.srt riêng lên YouTube Studio → viewer bật/tắt, không chồng sub)
    draw_subs = mode != "cover_only"
    if (mode == "cover_only" or cover != "none" or frame != "none"
            or logo not in ("", "none") or subscribe == "on"
            or watermark.active(r)):
        mode = "burn"  # che sub/khung/logo/nhắc sub/xóa watermark = sửa pixel = re-encode

    # Audio: voice FX + nhạc nền (duck theo giọng) + master → dubbed_render.wav.
    # Nếu không có gì để làm (fx off, không nhạc, không master) → dùng thẳng dubbed_audio.wav.
    audio = dubbed
    render_wav = job.dir / "dubbed_render.wav"
    if brand.build_audio(dubbed, render_wav, r.get("fx", config.VOICE_FX),
                         music, music_vol, master, job.dir):
        audio = render_wav

    if mode == "soft":
        ffmpeg.run(
            "-i", str(source), "-i", str(audio), "-i", str(job.dir / "sub_vi.srt"),
            "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-c:s", "mov_text", "-metadata:s:s:0", "language=vie",
            "-shortest",
            str(out_path),
        )
    elif mode == "burn":
        vw, vh = ffmpeg.probe_dims(source)
        if draw_subs:
            style = style_with_frame_margin(r.get("style"), frame, frame_width,
                                            vw, vh, job.dir, frame_pad)
            sub_filter = (f"subtitles=sub_vi.srt:fontsdir={fontsdir_arg(job)}"
                          f":force_style='{build_style(style)}'")
        else:
            sub_filter = "null"   # filter passthrough — giữ nguyên cấu trúc chuỗi -vf
        # Xóa/che watermark kênh gốc + crop mép: chạy ĐẦU chuỗi -vf. Crop làm dịch
        # tọa độ mọi thứ vẽ sau → quy đổi băng che + box sub tự động qua map_y/map_box.
        wm_pre = watermark.pre_chain(r, vw, vh, job.dir)
        crop_r = r.get("crop") or []
        if watermark.crop_active(crop_r):
            top, cb = watermark.map_y(top, crop_r), watermark.map_y(cb, crop_r)
        chain = ""
        if cover == "auto":
            boxes = load_sub_boxes(job)
            if watermark.crop_active(crop_r):
                boxes = [dict(b, box=m) for b in boxes
                         if (m := watermark.map_box(b["box"], crop_r))]
            if boxes:
                chain = auto_cover_chain(boxes, vw, vh)
        if chain:
            base = f"{chain},{sub_filter}"
        else:
            # auto nhưng không có dữ liệu vị trí sub (transcript whisper /
            # job cũ chưa có sub_boxes.json) → về dải mờ thủ công
            eff = "blur" if cover == "auto" else cover
            base = cover_filter(eff, top, sub_filter, cw, cb)
        if wm_pre:
            base = f"{wm_pre},{base}"
        # chèn khung viền + logo watermark vào cuối chuỗi (sau cover/sub)
        vf_full = frames.append_to_vf(base, frame, frame_color, frame_color2,
                                      frame_width, vw, vh, job.dir, pad=frame_pad)
        vf_full = brand.append_logo(vf_full, logo, logo_pos, logo_scale, logo_opacity, vw, job.dir)
        sub_dur = brand._duration(source) if subscribe == "on" else 0.0
        vf_full = brand.append_subscribe(vf_full, subscribe,   # #18 nhắc Like/Đăng ký
                                         r.get("subscribe_text", config.SUBSCRIBE_TEXT),
                                         vw, job.dir, sub_dur)
        if chain or len(vf_full) > 1000:
            # chuỗi dài (hàng trăm delogo) → ghi ra file, né giới hạn độ dài command line
            (job.dir / "vf_auto.txt").write_text(vf_full, encoding="utf-8")
            vf_args = ("-filter_script:v", "vf_auto.txt")
        else:
            vf_args = ("-vf", vf_full)

        # chạy với cwd=job.dir để né escape đường dẫn Windows trong filter
        def encode(*codec_args: str) -> None:
            ffmpeg.run("-i", str(source), "-i", str(audio),
                       "-map", "0:v:0", "-map", "1:a:0", *vf_args,
                       *codec_args, "-c:a", "aac", "-b:a", "192k",
                       "-shortest", "final.mp4", cwd=job.dir)

        try:
            # Intel QuickSync: nhanh gấp nhiều lần x264 trên CPU
            encode("-c:v", "h264_qsv", "-global_quality", "23")
        except RuntimeError:
            encode("-c:v", "libx264", "-preset", "fast", "-crf", "20")
    else:  # none
        ffmpeg.run(
            "-i", str(source), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        )

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("final.mp4 không được tạo hoặc quá nhỏ")

    # Ghép intro/outro (nếu có) → thay final.mp4 (chuẩn hoá về kích thước/fps của final)
    if intro not in ("", "none") or outro not in ("", "none"):
        cw2, ch2 = ffmpeg.probe_dims(out_path)
        io_tmp = job.dir / "final_io.mp4"
        if brand.concat_io(intro, out_path, outro, io_tmp, cw2, ch2):
            os.replace(io_tmp, out_path)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(out_path, config.OUTPUT_DIR / f"final-{ts}.mp4")
