"""#17 Cắt video dài thành nhiều phần → mỗi phần 1 job độc lập.

Cắt tại VỊ TRÍ người dùng chọn (danh sách mốc thời gian) HOẶC chia N phần đều.
Nguồn: file đã có sẵn (upload) hoặc URL (tự tải bằng yt-dlp). Cắt bằng ffmpeg -c copy
(nhanh, không re-encode; mốc bám keyframe gần nhất — đủ tốt để chia phần). Mỗi phần
tạo 1 job với source.mp4 sẵn → S1 bỏ qua tải, job vào 'Chờ chạy'.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import config
from core import ffmpeg, sources
from core.job import Job

MAX_PARTS = 50


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def parse_cuts(text: str, duration: float) -> list[float]:
    """'m:ss, h:mm:ss, 90' → danh sách GIÂY (0<t<duration), sắp xếp, bỏ trùng/ngoài."""
    cuts = []
    for tok in (text or "").replace(";", ",").replace("\n", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            sec = 0.0
            for p in tok.split(":"):
                sec = sec * 60 + float(p)
        except ValueError:
            continue
        if 0 < sec < duration:
            cuts.append(round(sec, 2))
    return sorted(set(cuts))


def _boundaries(duration: float, parts: int, cuts: list[float]) -> list[tuple[float, float]]:
    if cuts:
        pts = [0.0] + cuts + [duration]
    else:
        n = max(2, min(MAX_PARTS, parts))
        pts = [duration * i / n for i in range(n + 1)]
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)
            if pts[i + 1] - pts[i] >= 1.0]


def _cut(src: Path, start: float, dur: float, out: Path) -> None:
    """Cắt CHÍNH XÁC 1 đoạn [start, start+dur) → out. RE-ENCODE (không dùng -c copy) để
    mốc cắt đúng vị trí + timestamp reset về 0 (copy chỉ cắt được ở keyframe → lệch/sai
    độ dài). QSV cho nhanh trên Intel, fallback libx264. -ss trước -i = seek nhanh."""
    base = ["-ss", f"{start:.2f}", "-i", str(src), "-t", f"{dur:.2f}"]
    tail = ["-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero", str(out)]
    try:
        ffmpeg.run(*base, "-c:v", "h264_qsv", "-global_quality", "23", *tail)
    except RuntimeError:
        ffmpeg.run(*base, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", *tail)


def _fetch_source(url: str, tmp_dir: Path) -> Path:
    import yt_dlp
    opts = {
        "outtmpl": str(tmp_dir / "full.%(ext)s"),
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4", "noplaylist": True,
        "quiet": True, "no_warnings": True, **sources.cookie_opts(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    for p in sorted(tmp_dir.glob("full.*")):
        if p.suffix.lower() in (".mp4", ".mkv", ".webm"):
            return p
    raise RuntimeError("Tải nguồn để cắt không thành công")


def run(source_path: str | Path | None = None, url: str | None = None,
        base_name: str = "Video", parts: int = 0, cuts_text: str = "",
        pause_before_render: bool = False, glossary: str = "",
        series: str = "") -> list[str]:
    """Cắt + tạo job cho từng phần. Trả list job id. Chạy trong thread nền."""
    tmp = Path(tempfile.mkdtemp(prefix="split_", dir=config.DATA_DIR))
    created: list[str] = []
    try:
        src = Path(source_path) if source_path else _fetch_source(url, tmp)
        dur = _duration(src)
        segs = _boundaries(dur, parts, parse_cuts(cuts_text, dur))
        n = len(segs)
        for i, (a, b) in enumerate(segs, 1):
            title = f"{base_name} — Phần {i}/{n}"
            job = Job.create(url=f"[Cắt] {title}",
                             pause_before_render=pause_before_render,
                             glossary=glossary, series=series)
            out = job.dir / "source.mp4"
            _cut(src, a, b - a, out)
            if not out.exists() or out.stat().st_size == 0:
                shutil.rmtree(job.dir, ignore_errors=True)   # cắt hụt → bỏ job rỗng
                continue
            created.append(job.id)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return created
