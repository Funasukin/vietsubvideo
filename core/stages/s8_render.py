"""S8: sinh phụ đề sub_vi.srt + ghép audio lồng tiếng (và phụ đề) → final.mp4.

SUBTITLE_MODE quyết định cách lồng phụ đề (xem config.py). sub_vi.srt luôn
được tạo để Phase 3 upload làm caption YouTube/Facebook.
"""
from __future__ import annotations

import json
import re
import textwrap

import config
from core import ffmpeg
from core.job import Job


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


def make_srt(job: Job) -> None:
    srt_path = job.dir / "sub_vi.srt"
    if srt_path.exists():
        return
    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    segs = [s for s in data["segments"] if s["text_vi"].strip()]

    blocks = []
    for n, seg in enumerate(segs):
        start = seg["start"]
        end = max(seg["end"], start + 1.0)  # hiển thị tối thiểu 1s
        if n + 1 < len(segs):
            end = min(end, segs[n + 1]["start"] - 0.05)
        if end <= start:
            end = start + 0.5
        blocks.append(
            f"{n + 1}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{_wrap(seg['text_vi'])}\n"
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
    font = "".join(c for c in str(s["font"]) if c.isalnum() or c in " -")[:40] or "Arial"
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


def cover_filter(cover: str, top: float, sub_filter: str) -> str:
    """Chuỗi -vf: che vùng sub gốc (blur/black) rồi vẽ phụ đề lên trên."""
    if cover == "blur":
        return (f"split[a][b];"
                f"[b]crop=iw:ih*{1 - top:.3f}:0:ih*{top:.3f},boxblur=14:2[blur];"
                f"[a][blur]overlay=0:H*{top:.3f},{sub_filter}")
    if cover == "black":
        return (f"drawbox=x=0:y=ih*{top:.3f}:w=iw:h=ih*{1 - top:.3f}"
                f":color=black:t=fill,{sub_filter}")
    return sub_filter


def run(job: Job) -> None:
    out_path = job.dir / "final.mp4"
    if out_path.exists():
        return

    make_srt(job)
    source = job.find_source()
    dubbed = job.dir / "dubbed_audio.wav"

    r = job.render or {}
    mode = r.get("subtitle_mode", config.SUBTITLE_MODE)
    cover = r.get("cover", config.COVER_SOURCE_SUBS)
    top = float(r.get("cover_top", config.COVER_TOP))
    if cover != "none":
        mode = "burn"  # che sub gốc = sửa pixel = bắt buộc re-encode

    if mode == "soft":
        ffmpeg.run(
            "-i", str(source), "-i", str(dubbed), "-i", str(job.dir / "sub_vi.srt"),
            "-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-c:s", "mov_text", "-metadata:s:s:0", "language=vie",
            "-shortest",
            str(out_path),
        )
    elif mode == "burn":
        sub_filter = f"subtitles=sub_vi.srt:force_style='{build_style(r.get('style'))}'"
        vf = cover_filter(cover, top, sub_filter)
        # chạy với cwd=job.dir để né escape đường dẫn Windows trong filter
        def encode(*codec_args: str) -> None:
            ffmpeg.run("-i", str(source), "-i", str(dubbed),
                       "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
                       *codec_args, "-c:a", "aac", "-b:a", "192k",
                       "-shortest", "final.mp4", cwd=job.dir)

        try:
            # Intel QuickSync: nhanh gấp nhiều lần x264 trên CPU
            encode("-c:v", "h264_qsv", "-global_quality", "23")
        except RuntimeError:
            encode("-c:v", "libx264", "-preset", "fast", "-crf", "20")
    else:  # none
        ffmpeg.run(
            "-i", str(source), "-i", str(dubbed),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        )

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError("final.mp4 không được tạo hoặc quá nhỏ")
