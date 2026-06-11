"""Dashboard web local cho FlowApp.

Chạy:  .venv\\Scripts\\python -m uvicorn webui.server:app --port 8765

Hàng đợi job chạy tuần tự trong 1 worker thread (mỗi job là 1 subprocess
cli.py --resume nên server restart không làm hỏng job — checkpoint lo phần đó).
Phase 2: bot Telegram sẽ dùng chung cơ chế hàng đợi này.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
from core.job import Job

# Các khóa .env được phép sửa từ giao diện (không bao giờ gồm API key)
SAFE_ENV_KEYS = ["CLAUDE_MODEL", "TTS_VOICE", "TTS_VOICE_NU", "WHISPER_MODEL",
                 "TRANSCRIPT_SOURCE", "SUBTITLE_MODE", "OCR_WORKERS"]
ENV_PATH = config.BASE_DIR / ".env"

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


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


@app.get("/api/stats")
def stats() -> dict:
    jobs = list_jobs()
    total_seconds = total_segments = 0
    for j in jobs:
        tv = config.JOBS_DIR / j["id"] / "transcript_vi.json"
        if tv.exists():
            segs = json.loads(tv.read_text(encoding="utf-8"))["segments"]
            total_segments += len(segs)
            if segs:
                total_seconds += segs[-1]["end"]
    disk = shutil.disk_usage(config.BASE_DIR)
    return {
        "jobs_total": len(jobs),
        "jobs_done": sum(1 for j in jobs if j["stage"] == "done"),
        "jobs_failed": sum(1 for j in jobs if j["stage"] == "failed"),
        "jobs_active": sum(1 for j in jobs if j["running"] or j["queued"]),
        "video_minutes": round(total_seconds / 60),
        "segments_translated": total_segments,
        "est_cost_usd": round(total_segments * 0.001, 2),  # ~đo thực tế Haiku
        "jobs_size_gb": round(_dir_size(config.JOBS_DIR) / 1e9, 2)
                        if config.JOBS_DIR.exists() else 0,
        "disk_free_gb": round(disk.free / 1e9, 1),
    }


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    if job_id == _running_id or job_id in list(_pending.queue):
        raise HTTPException(409, "Job đang chạy hoặc trong hàng đợi — không xóa được")
    job_dir = config.JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Không có job này")
    try:
        shutil.rmtree(job_dir)
    except OSError as e:
        raise HTTPException(500, f"Không xóa được (file đang mở?): {e}")
    return {"deleted": job_id}


@app.post("/api/jobs/{job_id}/open")
def open_job_folder(job_id: str) -> dict:
    job_dir = config.JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Không có job này")
    os.startfile(job_dir)  # server chạy local nên mở Explorer ngay trên máy
    return {"opened": job_id}


def _read_env() -> dict[str, str]:
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2)
    return values


@app.get("/api/config")
def get_config() -> dict:
    env = _read_env()
    defaults = {k: str(getattr(config, k, "")) for k in SAFE_ENV_KEYS}
    return {
        "values": {k: env.get(k, defaults[k]) for k in SAFE_ENV_KEYS},
        "api_key_set": bool(env.get("ANTHROPIC_API_KEY")),
    }


@app.post("/api/config")
def set_config(body: dict) -> dict:
    updates = {}
    for k, v in body.items():
        if k not in SAFE_ENV_KEYS:
            continue
        v = str(v).strip()
        if not v or "\n" in v or len(v) > 100:
            raise HTTPException(400, f"Giá trị không hợp lệ cho {k}")
        updates[k] = v
    if not updates:
        raise HTTPException(400, "Không có khóa hợp lệ nào để lưu")

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Z_]+)=", line.strip())
        if m and m.group(1) in updates:
            lines[i] = f"{m.group(1)}={updates[m.group(1)]}"
            seen.add(m.group(1))
    for k in updates:
        if k not in seen:
            lines.append(f"{k}={updates[k]}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"saved": sorted(updates), "note": "Áp dụng cho job chạy mới"}


@app.get("/")
def index() -> HTMLResponse:
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)
