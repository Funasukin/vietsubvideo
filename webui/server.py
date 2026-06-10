"""Dashboard web local cho FlowApp.

Chạy:  .venv\\Scripts\\python -m uvicorn webui.server:app --port 8765

Hàng đợi job chạy tuần tự trong 1 worker thread (mỗi job là 1 subprocess
cli.py --resume nên server restart không làm hỏng job — checkpoint lo phần đó).
Phase 2: bot Telegram sẽ dùng chung cơ chế hàng đợi này.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
from core.job import Job

app = FastAPI(title="FlowApp")

_pending: "queue.Queue[str]" = queue.Queue()
_running_id: str | None = None


def _worker() -> None:
    global _running_id
    while True:
        job_id = _pending.get()
        _running_id = job_id
        try:
            subprocess.run(
                [sys.executable, str(config.BASE_DIR / "cli.py"), "--resume", job_id],
                cwd=config.BASE_DIR,
            )
        finally:
            _running_id = None


threading.Thread(target=_worker, daemon=True, name="flowapp-worker").start()


class NewJob(BaseModel):
    url: str


class RenderOptions(BaseModel):
    subtitle_mode: str = "soft"   # soft | burn | none
    cover: str = "none"           # none | blur | black
    cover_top: float = 0.78       # che từ tỉ lệ chiều cao này xuống đáy
    style: dict = {}              # font/size/color... — xem DEFAULT_STYLE trong s8_render


def _job_summary(job_dir: Path) -> dict | None:
    state_path = job_dir / "state.json"
    if not state_path.exists():
        return None
    state = json.loads(state_path.read_text(encoding="utf-8"))

    seg_total = tts_done = 0
    tv = job_dir / "transcript_vi.json"
    if tv.exists():
        seg_total = len(json.loads(tv.read_text(encoding="utf-8"))["segments"])
    if (job_dir / "tts").exists():
        tts_done = len(list((job_dir / "tts").glob("seg_????.mp3")))

    state["seg_total"] = seg_total
    state["tts_done"] = tts_done
    state["has_final"] = (job_dir / "final.mp4").exists()
    state["has_srt"] = (job_dir / "sub_vi.srt").exists()
    state["queued"] = state["id"] in list(_pending.queue)
    state["running"] = state["id"] == _running_id

    mr = job_dir / "mix_report.json"
    if mr.exists():
        report = json.loads(mr.read_text(encoding="utf-8"))
        state["overflow"] = len(report.get("overflow_warnings", []))
    return state


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    jobs = []
    if config.JOBS_DIR.exists():
        for d in sorted(config.JOBS_DIR.iterdir(), reverse=True):
            if d.is_dir():
                s = _job_summary(d)
                if s:
                    jobs.append(s)
    return jobs


@app.post("/api/jobs")
def create_job(body: NewJob) -> dict:
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "Thiếu URL")
    job = Job.create(url=url)
    _pending.put(job.id)
    return _job_summary(job.dir)


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict:
    job_dir = config.JOBS_DIR / job_id
    if not (job_dir / "state.json").exists():
        raise HTTPException(404, "Không có job này")
    if job_id == _running_id or job_id in list(_pending.queue):
        raise HTTPException(409, "Job đang chạy hoặc đã trong hàng đợi")
    _pending.put(job_id)
    return _job_summary(job_dir)


@app.post("/api/jobs/{job_id}/rerender")
def rerender_job(job_id: str, opts: RenderOptions) -> dict:
    if job_id == _running_id or job_id in list(_pending.queue):
        raise HTTPException(409, "Job đang chạy hoặc đã trong hàng đợi")
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")

    job.render = {"subtitle_mode": opts.subtitle_mode,
                  "cover": opts.cover, "cover_top": opts.cover_top,
                  "style": opts.style}
    for name in ["final.mp4", "sub_vi.srt", "metadata.json"]:
        (job.dir / name).unlink(missing_ok=True)
    job.completed_stages = [s for s in job.completed_stages
                            if s not in ("rendering", "metadata")]
    job.error = None
    job.save()
    _pending.put(job_id)
    return _job_summary(job.dir)


@app.post("/api/jobs/{job_id}/preview")
def preview(job_id: str, opts: RenderOptions) -> FileResponse:
    """Áp vùng che + kiểu chữ + phụ đề mẫu lên 1 frame thật — xem trước không cần render."""
    from core import ffmpeg
    from core.stages.s8_render import build_style, cover_filter

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

    raw = job.dir / "preview_raw.png"
    ffmpeg.run("-ss", f"{t:.2f}", "-i", str(source), "-frames:v", "1", str(raw))
    (job.dir / "preview.srt").write_text(
        f"1\n00:00:00,000 --> 00:00:10,000\n{sample}\n", encoding="utf-8")

    sub_filter = f"subtitles=preview.srt:force_style='{build_style(opts.style)}'"
    vf = cover_filter(opts.cover, opts.cover_top, sub_filter)
    ffmpeg.run("-i", "preview_raw.png", "-vf", vf, "-frames:v", "1",
               "preview.png", cwd=job.dir)
    return FileResponse(job.dir / "preview.png", media_type="image/png",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str) -> FileResponse:
    path = config.JOBS_DIR / job_id / "final.mp4"
    if not path.exists():
        raise HTTPException(404, "Chưa có final.mp4")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/srt")
def job_srt(job_id: str) -> FileResponse:
    path = config.JOBS_DIR / job_id / "sub_vi.srt"
    if not path.exists():
        raise HTTPException(404, "Chưa có sub_vi.srt")
    return FileResponse(path, media_type="text/plain", filename=f"{job_id}_vi.srt")


@app.get("/")
def index() -> HTMLResponse:
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)
