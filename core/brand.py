"""Brand/xuất bản khi render (S8): nhạc nền (duck theo giọng) + logo watermark +
intro/outro + master LUFS. Asset dùng chung cả kênh: đặt file vào music/ logo/ clips/.

- build_audio(): giọng (voice FX) → trộn nhạc nền đã duck → master → dubbed_render.wav
- append_logo(): chèn logo overlay vào cuối chuỗi -vf (sau khung viền)
- concat_io(): ghép intro + video + outro (chuẩn hoá độ phân giải/fps) sau khi render
"""
from __future__ import annotations

import os
import subprocess

import config
from core import ffmpeg, voice_fx

MUSIC_DIR = config.BASE_DIR / "music"
LOGO_DIR = config.BASE_DIR / "logo"
CLIPS_DIR = config.BASE_DIR / "clips"

_MUSIC_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_CLIP_EXTS = {".mp4", ".mkv", ".mov", ".webm"}
_LOGO_EXTS = {".png"}


def _list(d, exts) -> list[str]:
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.suffix.lower() in exts and p.is_file())


def list_music():
    return _list(MUSIC_DIR, _MUSIC_EXTS)


def list_logo():
    return _list(LOGO_DIR, _LOGO_EXTS)


def list_clips():
    return _list(CLIPS_DIR, _CLIP_EXTS)


def _pick(name, d, exts):
    """Trả path an toàn (basename, đúng đuôi, tồn tại) hoặc None; None nếu 'none'/rỗng."""
    if not name or name == "none":
        return None
    safe = os.path.basename(name)
    if any(ch in safe for ch in "',:;[]\\"):      # ký tự phá filtergraph
        return None
    p = d / safe
    return p if (p.suffix.lower() in exts and p.is_file()) else None


def _rel(path, job_dir) -> str:
    return os.path.relpath(path, job_dir).replace("\\", "/")


# ---------------- AUDIO: voice FX + nhạc nền (duck) + master ----------------
def audio_needed(fx, music, master) -> bool:
    return bool(voice_fx.chain(fx) or _pick(music, MUSIC_DIR, _MUSIC_EXTS) or master)


def build_audio(dubbed, out, fx, music, music_vol, master, job_dir) -> bool:
    """Xử lý audio → out (dubbed_render.wav). Trả True nếu đã tạo out; False nếu không
    có gì để làm (dùng thẳng dubbed)."""
    fxc = voice_fx.chain(fx)
    mpath = _pick(music, MUSIC_DIR, _MUSIC_EXTS)
    if not (fxc or mpath or master):
        return False
    vbranch = fxc or "anull"
    inputs = ["-i", str(dubbed)]
    if mpath:
        try:
            vol = max(0.0, min(1.0, float(music_vol)))
        except (TypeError, ValueError):
            vol = 0.15
        inputs += ["-stream_loop", "-1", "-i", str(mpath)]
        graph = (f"[0:a]{vbranch},asplit=2[v1][v2];"
                 f"[1:a]volume={vol}[m];"
                 f"[m][v2]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[md];"
                 f"[v1][md]amix=inputs=2:duration=first:normalize=0[mix]")
    else:
        graph = f"[0:a]{vbranch}[mix]"
    if master or mpath:   # có nhạc → phải master lại kẻo lệch mức / clip
        graph += ";[mix]loudnorm=I=-14:TP=-1:LRA=11,aresample=48000[out]"
    else:
        graph += ";[mix]aresample=48000[out]"
    ffmpeg.run(*inputs, "-filter_complex", graph, "-map", "[out]", str(out))
    return True


# ---------------- LOGO watermark (chèn vào cuối -vf) ----------------
def append_logo(vf, logo, pos, scale, opacity, w, job_dir) -> str:
    lp = _pick(logo, LOGO_DIR, _LOGO_EXTS)
    if not lp:
        return vf
    rel = _rel(lp, job_dir)
    try:
        lw = max(16, int(float(scale) * w))
    except (TypeError, ValueError):
        lw = max(16, int(0.12 * w))
    try:
        op = max(0.0, min(1.0, float(opacity)))
    except (TypeError, ValueError):
        op = 0.85
    m = max(8, int(0.02 * w))
    xy = {"tl": f"{m}:{m}", "tr": f"W-w-{m}:{m}",
          "bl": f"{m}:H-h-{m}", "br": f"W-w-{m}:H-h-{m}"}.get(pos, f"W-w-{m}:H-h-{m}")
    lg = f"movie=filename='{rel}',scale={lw}:-1,format=rgba,colorchannelmixer=aa={op}[lg]"
    base = vf or "null"
    return f"{base}[lb];{lg};[lb][lg]overlay={xy}"


# ---------------- #18 Nhắc Like/Đăng ký (overlay banner vài giây) ----------------
_SUB_FONTS = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
              r"C:\Windows\Fonts\arial.ttf"]


def make_subscribe_png(text, w, job_dir):
    """Vẽ banner nhắc Like/Đăng ký (PNG trong suốt) bằng PIL → job_dir/subscribe.png.
    Dùng PIL (như thumbnail) để né hoàn toàn chuyện escape drawtext trong filtergraph."""
    text = (text or "").strip()
    if not text:
        return None
    from PIL import Image, ImageDraw, ImageFont
    out = job_dir / "subscribe.png"
    fs = max(20, int(w * 0.042))
    font = None
    for f in _SUB_FONTS:
        try:
            font = ImageFont.truetype(f, fs)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(fs)
    pad = int(fs * 0.7)
    d0 = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    box = d0.textbbox((0, 0), text, font=font, stroke_width=3)
    tw, th = box[2] - box[0], box[3] - box[1]
    W, H = tw + pad * 2, th + pad * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([0, 0, W - 1, H - 1], radius=int(H * 0.28), fill=(200, 30, 30, 210))
    dr.text((pad - box[0], pad - box[1]), text, font=font, fill=(255, 255, 255, 255),
            stroke_width=3, stroke_fill=(0, 0, 0, 255))
    img.save(out, "PNG")
    return out


def append_subscribe(vf, on, text, w, job_dir, duration=0.0, start=3.0, dur=6.0):
    """Chèn banner nhắc Like/Đăng ký hiện từ giây `start` trong `dur` giây (giữa-dưới).
    Video NGẮN (duration < start) → hiện sớm để banner không bao giờ bị lọt ra ngoài."""
    if str(on).strip().lower() != "on":
        return vf
    png = make_subscribe_png(text, w, job_dir)
    if not png:
        return vf
    if duration and duration > 0:
        start = min(start, max(0.0, duration - 2.0))   # kịp hiện trước khi hết video
        end = min(start + dur, duration)
    else:
        end = start + dur
    if end <= start:
        end = start + 1.0
    rel = _rel(png, job_dir)
    sg = f"movie=filename='{rel}',format=rgba[sb]"
    base = vf or "null"
    return (f"{base}[sbb];{sg};[sbb][sb]overlay=(W-w)/2:H*0.80"
            f":enable='between(t,{start:.1f},{end:.1f})'")


# ---------------- INTRO / OUTRO concat (sau khi render final) ----------------
def _has_audio(path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return bool((r.stdout or "").strip())


def _duration(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        return 0.0


def _fps(path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=r_frame_rate", "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True)
    try:
        n, d = (r.stdout or "").strip().split("/")
        return round(float(n) / float(d), 3) if float(d) else 30.0
    except (ValueError, ZeroDivisionError):
        return 30.0


def concat_io(intro, main, outro, out, w, h) -> bool:
    """Ghép [intro] + main + [outro] → out (chuẩn hoá về w×h + fps của main + audio).
    Trả True nếu đã ghép; False nếu không có intro lẫn outro."""
    ip = _pick(intro, CLIPS_DIR, _CLIP_EXTS)
    op = _pick(outro, CLIPS_DIR, _CLIP_EXTS)
    if not ip and not op:
        return False
    clips = [c for c in [ip, main, op] if c]
    fps = _fps(main)
    norm = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p")
    inputs, sil_inputs, filt, labels = [], [], [], ""
    for c in clips:
        inputs += ["-i", str(c)]
    n_ext = len(clips)   # index cho input silence (thêm sau các clip)
    for i, c in enumerate(clips):
        filt.append(f"[{i}:v]{norm}[v{i}]")
        if _has_audio(c):
            filt.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            sil_inputs += ["-f", "lavfi", "-t", f"{_duration(c):.3f}",
                           "-i", "anullsrc=r=48000:cl=stereo"]
            filt.append(f"[{n_ext}:a]aformat=channel_layouts=stereo[a{i}]")
            n_ext += 1
        labels += f"[v{i}][a{i}]"
    filt.append(f"{labels}concat=n={len(clips)}:v=1:a=1[v][a]")
    ffmpeg.run(*inputs, *sil_inputs, "-filter_complex", ";".join(filt),
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
               "-crf", "20", "-c:a", "aac", "-b:a", "192k", str(out))
    return True
