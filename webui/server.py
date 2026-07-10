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
import atexit
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

# Console Windows mặc định cp1258 — print tiếng Việt trong request handler (vd cảnh
# báo thiếu logo của core/watermark) sẽ UnicodeEncodeError → 500. Ép UTF-8 như cli.py.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
from core.job import Job, Stage

# Các khóa .env được phép sửa từ giao diện (không bao giờ gồm API key)
SAFE_ENV_KEYS = ["CLAUDE_MODEL", "TRANSLATE_PROVIDER", "GEMINI_MODEL",
                 "GEMINI_MIN_INTERVAL", "TRANSLATE_STYLE_EXTRA",
                 "CONTENT_STYLE", "TARGET_LANG", "MAX_SPEEDUP", "STRETCH_SHORT",
                 "TTS_ENGINE", "TTS_SINGLE_VOICE", "TTS_VOICE", "TTS_VOICE_NU",
                 "VIXTTS_VOICE_NAM", "VIXTTS_VOICE_NU", "KEEP_BGM", "DUCK_GAIN_DB",
                 "VOICE_FX", "EMOTION", "PROSODY_TRANSFER",
                 "ELEVENLABS_VOICE_NAM", "ELEVENLABS_VOICE_NU", "ELEVENLABS_MODEL",
                 "VBEE_APP_ID", "VBEE_VOICE_NAM", "VBEE_VOICE_NU",
                 "FPT_VOICE_NAM", "FPT_VOICE_NU", "PROSODY",
                 "WHISPER_MODEL", "TRANSCRIPT_SOURCE", "SUBTITLE_MODE", "SUB_SPLIT",
                 "OCR_WORKERS", "OCR_FPS", "OCR_CROP_TOP",
                 "AUTO_RETRY", "DIARIZE", "DIARIZE_MAX_SPK",
                 "MUSIC", "MUSIC_VOL", "LOGO", "LOGO_POS", "LOGO_SCALE", "LOGO_OPACITY",
                 "INTRO", "OUTRO", "MASTER",
                 "SHORTS_COUNT", "SHORTS_LEN", "SHORTS_STYLE",
                 "DENOISE", "SUBSCRIBE", "SUBSCRIBE_TEXT",
                 "TELEGRAM_CHAT_ID", "YOUTUBE_CLIENT_SECRETS", "YOUTUBE_PRIVACY"]
# Khóa bí mật: cho GHI qua UI nhưng KHÔNG bao giờ trả giá trị về (chỉ báo đã-đặt-hay-chưa),
# giống ANTHROPIC_API_KEY. Bot token điều khiển bot của người dùng → coi như credential.
# HF_TOKEN là token tài khoản HuggingFace (diarization #8) → cũng là credential.
SECRET_ENV_KEYS = {"ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "HF_TOKEN", "GEMINI_API_KEY",
                   "ELEVENLABS_API_KEY", "VBEE_TOKEN", "FPT_TTS_API_KEY"}
ENV_PATH = config.BASE_DIR / ".env"

app = FastAPI(title="FlowApp")

# #16 tách monolith (giai đoạn 1): toàn bộ hàng đợi + vòng đời tiến trình job
# nằm ở webui/worker.py (worker thread tự khởi động khi import). Object dùng chung
# (_pending/_lock/_active/_cancel/_retries + các hàm) import trực tiếp; biến VÔ
# HƯỚNG bị gán lại bên worker (_running_id/_current_proc/_queue_paused) PHẢI
# đọc/ghi qua `worker.` — import from sẽ dính bản cũ.
from webui import worker
from webui.envfile import read_env as _read_env
from webui.worker import (_active, _cancel, _drain_remove, _enqueue,
                          _enqueue_reserved, _kill_proc_tree, _lock, _pending,
                          _release_job, _reserve_job, _retries)

# #16 giai đoạn 2: helper chung + cụm route editor tách ra module riêng
from webui.common import _check_job_id, _job_summary, _unlink_quiet
from webui.routes_editor import router as _editor_router
app.include_router(_editor_router)



def _trending_safe_scan() -> None:
    from core import trending
    try:
        trending.run_scan()
    except Exception as e:
        print(f"[trending] quét lỗi: {e}")


def _start_trending_scheduler() -> None:
    """Quét bảng phim AI hot 1 lần/ngày; quét ngay (nền) nếu chưa có cache lần đầu."""
    from core import trending
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        sched = BackgroundScheduler(daemon=True)
        sched.add_job(_trending_safe_scan, CronTrigger(hour=config.TRENDING_HOUR),
                      id="trending_daily", replace_existing=True, misfire_grace_time=3600)
        sched.start()
    except Exception as e:
        print(f"[trending] scheduler không khởi động được: {e}")
    if not trending.CACHE.exists():
        threading.Thread(target=_trending_safe_scan, daemon=True,
                         name="trending-initial").start()


_start_trending_scheduler()


# Job thêm mới KHÔNG tự chạy nữa — luôn chờ người dùng bấm ▶ Chạy (hoặc Chạy tất
# cả). Vì vậy KHÔNG tự xếp lại hàng đợi khi server khởi động lại: job 'pending' vẫn
# lưu trên đĩa và hiện trong danh sách ở trạng thái "Chờ chạy", chỉ là không tự chạy.


class NewJob(BaseModel):
    url: str
    pause_before_render: bool = False
    glossary: str = ""
    series: str = ""   # tên series (nhiều tập cùng phim) → dùng chung glossary + casting
    mode: str = "dub"  # "dub" (mặc định, dịch+lồng tiếng đầy đủ) | "visual" (#task "Chỉnh giao diện")




def _check_glossary(text: str) -> None:
    """Chặn glossary khổng lồ (paste nhầm) → tránh phình prompt / vỡ context dịch."""
    if len(text or "") > 20000:
        raise HTTPException(400, "Bảng tên riêng quá dài (tối đa 20000 ký tự)")


@app.get("/api/jobs")
def list_jobs(mode: str = "dub") -> list[dict]:
    """mode='dub' (mặc định — job cũ không có key 'mode' cũng tính là dub, giữ hành vi
    cũ nguyên vẹn) | 'visual' (#task 'Chỉnh giao diện') | 'all' = không lọc."""
    jobs = []
    if config.JOBS_DIR.exists():
        for d in sorted(config.JOBS_DIR.iterdir(), reverse=True):
            if d.is_dir():
                s = _job_summary(d)
                if s and (mode == "all" or s.get("mode", "dub") == mode):
                    jobs.append(s)
    return jobs


@app.post("/api/jobs")
def create_job(body: NewJob) -> dict:
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "Thiếu URL")
    if body.mode == "visual":
        # #task "Chỉnh giao diện": không glossary/series (không dịch) — tự chạy luôn
        # (chỉ tải video, nhanh) rồi dừng trước render để mở thẳng vào editor chỉnh.
        job = Job.create(url=url, pause_before_render=True, mode="visual")
        _enqueue(job.id)
    else:
        _check_glossary(body.glossary)
        job = Job.create(url=url, pause_before_render=body.pause_before_render,
                         glossary=body.glossary, series=body.series.strip())
        # KHÔNG _pending.put ở đây: job tạo xong ở trạng thái "Chờ chạy", chờ ▶ Chạy.
    return _job_summary(job.dir)


# Đuôi video nhận upload — khớp _VIDEO_EXTS mà Job.find_source() chấp nhận
_UPLOAD_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".flv"}


@app.post("/api/jobs/upload")
def upload_job(file: UploadFile = File(...),
               pause_before_render: bool = Form(False),
               glossary: str = Form(""),
               series: str = Form(""),
               mode: str = Form("dub")) -> dict:
    """Tạo job từ video UPLOAD ở máy: lưu thẳng thành source.<ext> trong thư mục job.
    Không đặt completed_stages — S1 (download) tự bỏ qua khi đã có source nên job
    vẫn là 'Chờ chạy' bình thường (hiện nút ▶ Chạy, tính vào 'Chạy tất cả').
    mode='visual' (#task 'Chỉnh giao diện'): không glossary/series, tự chạy luôn."""
    name = Path(file.filename or "video").name
    ext = Path(name).suffix.lower()
    if ext not in _UPLOAD_EXTS:
        raise HTTPException(400, "Định dạng không hỗ trợ: " + (ext or "(không rõ)")
                            + ". Chấp nhận: " + ", ".join(sorted(_UPLOAD_EXTS)))
    visual = mode == "visual"
    if not visual:
        _check_glossary(glossary)
    job = Job.create(url=f"[Upload] {name}",
                     pause_before_render=(True if visual else pause_before_render),
                     glossary=("" if visual else glossary),
                     series=("" if visual else series.strip()),
                     mode=("visual" if visual else "dub"))
    dest = job.dir / f"source{ext}"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)  # stream 1MB/lần
    except Exception as e:
        shutil.rmtree(job.dir, ignore_errors=True)
        raise HTTPException(500, f"Lưu file lỗi: {e}")
    finally:
        file.file.close()
    try:
        size = dest.stat().st_size   # .stat() có thể lỗi nếu AV/Windows khoá-xoá file ngay sau khi ghi
    except OSError:
        size = 0
    if size == 0:
        shutil.rmtree(job.dir, ignore_errors=True)
        raise HTTPException(400, "File rỗng hoặc upload hỏng (thử lại)")
    if visual:
        _enqueue(job.id)   # tự chạy luôn (chỉ copy file, S1 thấy source đã có → xong ngay)
    return _job_summary(job.dir)


@app.post("/api/jobs/split")
def split_video(file: UploadFile = File(None), url: str = Form(""),
                mode: str = Form("parts"), parts: int = Form(2), cuts: str = Form(""),
                pause_before_render: bool = Form(False), glossary: str = Form(""),
                series: str = Form("")) -> dict:
    """#17 Cắt video dài (upload hoặc URL) thành nhiều phần → mỗi phần 1 job.
    mode='parts' chia đều `parts` phần; mode='cuts' cắt tại các mốc `cuts` (mm:ss,...)."""
    _check_glossary(glossary)
    url = url.strip()
    src_tmp = None
    base_name = "Video"
    if file is not None and getattr(file, "filename", ""):
        ext = Path(file.filename).suffix.lower()
        if ext not in _UPLOAD_EXTS:
            raise HTTPException(400, "Định dạng không hỗ trợ để cắt")
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        src_tmp = config.DATA_DIR / f"_split_src_{uuid.uuid4().hex}{ext}"
        try:
            with src_tmp.open("wb") as out:
                shutil.copyfileobj(file.file, out, length=1024 * 1024)
        finally:
            file.file.close()
        base_name = Path(file.filename).stem[:60]
    elif not url:
        raise HTTPException(400, "Cần URL hoặc file để cắt")

    n_parts = max(2, min(50, int(parts))) if mode == "parts" else 0
    cuts_text = cuts if mode == "cuts" else ""
    if mode == "cuts" and not cuts_text.strip():
        if src_tmp:
            src_tmp.unlink(missing_ok=True)
        raise HTTPException(400, "Chọn chế độ 'mốc thời gian' thì phải nhập ít nhất 1 mốc")

    def _work() -> None:
        try:
            from core import splitter
            ids = splitter.run(source_path=src_tmp, url=(url or None), base_name=base_name,
                               parts=n_parts, cuts_text=cuts_text,
                               pause_before_render=pause_before_render,
                               glossary=glossary, series=series)
            print(f"[split] đã tạo {len(ids)} job phần")
        except Exception as e:
            print(f"[split] lỗi: {e}")
        finally:
            if src_tmp is not None:
                try:
                    src_tmp.unlink(missing_ok=True)
                except OSError:
                    pass

    threading.Thread(target=_work, daemon=True, name="flowapp-split").start()
    return {"started": True,
            "note": "Đang cắt & tạo job — các phần sẽ hiện dần trong danh sách Jobs."}


@app.get("/api/trending")
def get_trending() -> dict:
    """Trả bảng phim AI hot đã cache (đọc data/trending.json)."""
    from core import trending
    return trending.load_cache()


@app.post("/api/trending/scan")
def scan_trending() -> dict:
    """Quét NGAY (đồng bộ, chạy ở threadpool nên asyncio.run trong trending hợp lệ)."""
    from core import trending
    try:
        return trending.run_scan()
    except Exception as e:
        raise HTTPException(500, f"Quét lỗi: {e}")


@app.get("/api/frames/{name}")
def get_frame(name: str) -> FileResponse:
    """Phục vụ file khung .png trong frames/ (để xem trước trong editor)."""
    p = config.FRAMES_DIR / os.path.basename(name)   # basename → chặn path traversal
    if p.suffix.lower() != ".png" or not p.is_file():
        raise HTTPException(404, "Không có khung này")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})


class ExpandBody(BaseModel):
    text: str


@app.post("/api/expand")
def expand(body: ExpandBody) -> dict:
    """Bung nhiều link / playlist thành danh sách video (không tạo job)."""
    from core import sources
    try:
        entries = sources.expand_text(body.text)
    except Exception as e:
        raise HTTPException(400, f"Không đọc được danh sách: {e}")
    existing = {j["url"] for j in list_jobs()}
    for e in entries:
        e["duplicate"] = e["url"] in existing
    return {"entries": entries,
            "new": sum(1 for e in entries if not e["duplicate"])}


class CheckDupBody(BaseModel):
    url: str


@app.post("/api/check-dup")
def check_dup(body: CheckDupBody) -> dict:
    """Kiểm tra video đã có bản vietsub/lồng tiếng trên YouTube chưa (pre-flight).

    Cổng kiểm tra trước job, KHÔNG phải stage pipeline. dedup.check tự bắt mọi
    lỗi và trả status nên endpoint không bao giờ 500 vì mạng/Claude.
    """
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "Thiếu URL")
    from core import dedup
    return dedup.check(url)


class BatchBody(BaseModel):
    urls: list[str]
    pause_before_render: bool = False
    glossary: str = ""
    series: str = ""


@app.post("/api/jobs/batch")
def create_jobs_batch(body: BatchBody) -> dict:
    _check_glossary(body.glossary)
    series_name = body.series.strip()
    existing = {j["url"] for j in list_jobs()}
    created, skipped = [], 0
    for url in body.urls[:config.BATCH_LIMIT]:
        url = url.strip()
        if not url:
            continue
        if url in existing:
            skipped += 1
            continue
        job = Job.create(url=url, pause_before_render=body.pause_before_render,
                         glossary=body.glossary, series=series_name)
        existing.add(url)
        # KHÔNG tự chạy: job ở trạng thái "Chờ chạy", dùng nút Chạy tất cả để chạy.
        created.append(job.id)
    return {"created": created, "skipped_duplicates": skipped}


@app.post("/api/jobs/run-all")
def run_all_pending() -> dict:
    """Xếp hàng đợi MỌI job đang 'Chờ chạy' (pending, chưa chạy lần nào).

    Phục vụ nút 'Chạy tất cả' — tiện khi vừa thêm cả playlist. Bỏ qua job đang chạy
    hoặc đã trong hàng đợi để không xếp trùng."""
    started: list[str] = []
    if not config.JOBS_DIR.exists():
        return {"started": started, "count": 0}
    for d in sorted(config.JOBS_DIR.iterdir()):
        sp = d / "state.json"
        if not sp.exists():
            continue
        try:
            state = json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        jid = state.get("id")
        # _enqueue tự bỏ qua job đã đang chờ/đang chạy (atomic, không xếp trùng)
        if (state.get("stage") == "pending" and not state.get("completed_stages")
                and jid and _enqueue(jid)):
            started.append(jid)
    return {"started": started, "count": len(started)}


@app.post("/api/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict:
    _check_job_id(job_id)
    job_dir = config.JOBS_DIR / job_id
    if not (job_dir / "state.json").exists():
        raise HTTPException(404, "Không có job này")
    with _lock:
        if job_id in _active:
            raise HTTPException(409, "Job đang chạy hoặc đã trong hàng đợi")
    try:
        job = Job.load(job_id)
        if job.stage == Stage.PAUSED:
            job.pause_before_render = False
            job.save()
    except Exception:
        pass
    _enqueue(job_id)   # atomic: nếu vừa bị xếp bởi request khác thì bỏ qua, không trùng
    return _job_summary(job_dir)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    """Hủy job đang chạy (kill cây tiến trình) hoặc còn trong hàng đợi (rút khỏi hàng).
    Job dừng giữa chừng vẫn còn checkpoint → có thể bấm Chạy tiếp sau.

    Đặt cờ _cancel dưới _lock làm chốt chặn CHUNG cho mọi tình huống tranh chấp với
    worker (đang chạy / vừa pull / còn chờ); tùy trạng thái mà kill trực tiếp, rút hàng,
    hoặc để worker tự reap theo cờ. Giữ bất biến 'job trong hàng ⇔ job trong _active'."""
    _check_job_id(job_id)
    proc = None
    with _lock:
        if job_id not in _active:
            raise HTTPException(409, "Job không đang chạy/chờ")
        _cancel.add(job_id)              # chốt: worker tôn trọng cờ này ở mọi nhánh
        _retries.pop(job_id, None)       # hủy tay → không tự thử lại
        if job_id == worker._running_id and worker._current_proc is not None:
            proc = worker._current_proc  # đang chạy → kill; worker.wait() sẽ dọn _active
        elif _drain_remove(job_id):      # còn trong hàng đợi → rút ra, dọn ngay
            _active.discard(job_id)
            _cancel.discard(job_id)      # đã rời hàng, worker không gặp lại → gỡ chốt
        # else: worker vừa pull (chưa kịp set _running_id/_current_proc) → để nguyên cờ
        #       _cancel; worker sẽ tự reap ở đầu vòng lặp hoặc qua kill_now.
    if proc is not None:
        res = _kill_proc_tree(proc)
        if res != "ok":
            print(f"[cancel] {job_id}: {res}")
    return {"cancelled": job_id}


class QueuePauseBody(BaseModel):
    paused: bool


@app.get("/api/queue")
def queue_state() -> dict:
    with _lock:
        return {"paused": worker._queue_paused}


@app.post("/api/queue/pause")
def queue_pause(body: QueuePauseBody) -> dict:
    """⏸/▶ Tạm dừng/mở lại hàng đợi. Job đang chạy chạy nốt; job kế chờ mở lại."""
    with _lock:
        worker._queue_paused = body.paused   # gán qua module — biến vô hướng của worker
    return {"paused": body.paused}


@app.post("/api/jobs/{job_id}/prioritize")
def prioritize_job(job_id: str) -> dict:
    """⬆ Đưa job đang CHỜ lên đầu hàng đợi (chạy ngay sau job hiện tại)."""
    _check_job_id(job_id)
    with _lock:
        if job_id not in _active or job_id == worker._running_id:
            raise HTTPException(409, "Job không nằm trong hàng đợi")
        # múc hết hàng ra, xếp lại: job này TRƯỚC, còn lại giữ nguyên thứ tự
        items = []
        while True:
            try:
                items.append(_pending.get_nowait())
            except queue.Empty:
                break
        if job_id not in items:      # worker vừa pull đúng lúc → không đổi được nữa
            for it in items:
                _pending.put(it)
            raise HTTPException(409, "Job vừa được lấy ra chạy — không đổi thứ tự được")
        _pending.put(job_id)
        for it in items:
            if it != job_id:
                _pending.put(it)
    return {"prioritized": job_id}


@app.get("/api/jobs/{job_id}/thumb")
def job_thumb(job_id: str) -> FileResponse:
    path = config.JOBS_DIR / job_id / "thumbnail.jpg"
    if not path.exists():
        raise HTTPException(404, "Chưa có thumbnail")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


@app.post("/api/jobs/{job_id}/thumbnail")
def regen_thumbnail(job_id: str) -> dict:
    """Tạo lại metadata + thumbnail (đồng bộ, ~30 giây)."""
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    if not (job.dir / "transcript_vi.json").exists():
        raise HTTPException(409, "Job chưa dịch xong — chưa tạo được metadata")

    from core.stages import s9_metadata
    (job.dir / "thumbnail.jpg").unlink(missing_ok=True)
    (job.dir / "metadata.json").unlink(missing_ok=True)
    s9_metadata.run(job)
    return _job_summary(job.dir)


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str) -> FileResponse:
    _check_job_id(job_id)   # audit #11: chặn path traversal (2 endpoint này từng thiếu)
    path = config.JOBS_DIR / job_id / "final.mp4"
    if not path.exists():
        raise HTTPException(404, "Chưa có final.mp4")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/srt")
def job_srt(job_id: str) -> FileResponse:
    _check_job_id(job_id)
    path = config.JOBS_DIR / job_id / "sub_vi.srt"
    if not path.exists():
        raise HTTPException(404, "Chưa có sub_vi.srt")
    return FileResponse(path, media_type="text/plain", filename=f"{job_id}_vi.srt")


@app.get("/api/jobs/{job_id}/source")
def job_source(job_id: str) -> FileResponse:
    """Video gốc (chưa lồng tiếng) — editor dùng khi job chưa có final.mp4."""
    _check_job_id(job_id)
    job_dir = config.JOBS_DIR / job_id
    for p in sorted(job_dir.glob("source.*")):
        if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".flv"}:
            return FileResponse(p, media_type="video/mp4")
    raise HTTPException(404, "Chưa có video nguồn")


@app.get("/api/jobs/{job_id}/dub")
def job_dub(job_id: str) -> FileResponse:
    """Audio lồng tiếng Việt (dub + nhạc nền) — editor phát đè lên video gốc để nghe
    thử trước khi render (lúc job dừng trước render đã có dubbed_audio.wav)."""
    _check_job_id(job_id)
    path = config.JOBS_DIR / job_id / "dubbed_audio.wav"
    if not path.exists():
        raise HTTPException(404, "Chưa có bản lồng tiếng")
    return FileResponse(path, media_type="audio/wav")


# ---------- #task "Chỉnh giao diện" (job.mode=="visual"): editor khung/logo/watermark
# thuần túy, không transcript/segments — panel nhẹ hơn hẳn editor lồng tiếng ----------

@app.get("/api/jobs/{job_id}/visual")
def get_visual_job(job_id: str) -> dict:
    """Dữ liệu cho editor 'Chỉnh giao diện': cài đặt render đã lưu + danh sách khung
    PNG khả dụng + trạng thái final/audio. KHÔNG cần transcript (job này chưa từng
    dịch/nhận dạng thoại)."""
    _check_job_id(job_id)
    job_dir = config.JOBS_DIR / job_id
    if not job_dir.is_dir():
        raise HTTPException(404, "Không có job này")
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    from core import brand, frames
    source = job.find_source()
    return {"render": job.render or {},
            "frames": frames.list_png(),
            "has_final": (job_dir / "final.mp4").exists(),
            "has_audio": bool(source) and brand._has_audio(source),
            "has_source": bool(source)}


# ---------- Editor lời thoại: xem + sửa text/giọng từng câu ----------

@app.get("/api/jobs/{job_id}/qc")
def job_qc(job_id: str) -> dict:
    """#13 Soát lỗi: câu dịch nghi ngờ (rỗng/còn chữ Trung/giống nguyên bản) +
    cảnh báo timing tràn (giọng Việt dài hơn khoảng trống, từ mix_report.json)."""
    _check_job_id(job_id)
    jd = config.JOBS_DIR / job_id
    tv = jd / "transcript_vi.json"
    if not tv.exists():
        raise HTTPException(404, "Job chưa dịch xong")
    try:
        segs = json.loads(tv.read_text(encoding="utf-8"))["segments"]
    except (json.JSONDecodeError, KeyError, OSError):
        raise HTTPException(422, "transcript_vi.json hỏng — chạy lại bước dịch")
    suspects = []
    _QC_CJK = re.compile(r"[㐀-鿿]")   # chữ Trung còn sót trong bản dịch
    for s in segs:
        if s.get("mute"):
            continue
        t = (s.get("text_vi") or "").strip()
        src = (s.get("text") or "").strip()
        reason = None
        if not t:
            reason = "chưa dịch (rỗng)"
        elif _QC_CJK.search(t):
            reason = "còn chữ Trung/nước ngoài"
        elif src and t == src:
            reason = "giống hệt nguyên bản"
        if reason:
            suspects.append({"id": s["id"], "start": s.get("start", 0),
                             "text": src, "text_vi": t, "reason": reason})
    overflow = []
    mr = jd / "mix_report.json"
    if mr.exists():
        try:
            for w in json.loads(mr.read_text(encoding="utf-8")).get("overflow_warnings", []):
                overflow.append({"id": w.get("id"), "overflow_ms": w.get("overflow_ms", 0),
                                 "text_vi": w.get("text_vi", "")})
        except (json.JSONDecodeError, OSError):
            pass
    overflow.sort(key=lambda w: -w.get("overflow_ms", 0))
    return {"total": len(segs), "suspects": suspects, "overflow": overflow}


@app.get("/api/jobs/{job_id}/log")
def job_log(job_id: str, lines: int = 200) -> dict:
    """Đuôi run.log của job (log per-job do worker ghi) — soi lỗi ngay trên UI."""
    _check_job_id(job_id)
    p = config.JOBS_DIR / job_id / "run.log"
    if not p.exists():
        raise HTTPException(404, "Job chưa có log (chưa chạy lần nào từ khi có tính năng log)")
    lines = max(10, min(2000, lines))
    try:
        with p.open("rb") as f:           # chỉ đọc ~256KB cuối, log dài không nghẽn
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 256_000))
            text = f.read().decode("utf-8", errors="replace")
    except OSError as e:
        raise HTTPException(500, f"Đọc log lỗi: {e}")
    tail = text.splitlines()[-lines:]
    return {"log": "\n".join(tail), "size": size}


# File trung gian có thể dọn sau khi job XONG (giữ final/sub/transcript/tts mp3/nguồn).
# Xoá audio bed → gỡ luôn các stage sinh ra chúng khỏi completed_stages để lần
# "Sửa lời thoại" sau pipeline tự tách audio lại từ source (chậm hơn chút, không hỏng).
_CLEAN_FILES = ["audio_16k.wav", "audio_full.wav", "vocals.wav", "no_vocals.wav",
                "ducked.wav", "dubbed_audio.wav", "dubbed_render.wav",
                "vf_auto.txt", "ocr_raw.json",
                "final_io.mp4"]   # bug #15: bản ghép intro/outro dở từ code cũ
_CLEAN_STAGES = {"extracting", "bgm", "mixing"}


def _clean_job_files(job: Job) -> int:
    """Xóa file trung gian của 1 job (WAV các loại, sped, artifact) + gỡ stage sinh
    ra chúng khỏi completed để lần 'Chỉnh sửa' sau tự dựng lại từ source. Trả bytes."""
    freed = 0
    for name in _CLEAN_FILES:
        p = job.dir / name
        try:
            sz = p.stat().st_size if p.exists() else 0
        except OSError:
            sz = 0
        if _unlink_quiet(p) and sz:       # dubbed có thể đang phát trong editor → retry/bỏ
            freed += sz
    for sped in (job.dir / "tts").glob("seg_*_sped.wav"):
        try:
            freed += sped.stat().st_size
            sped.unlink()
        except OSError:
            pass
    job.completed_stages = [s for s in job.completed_stages if s not in _CLEAN_STAGES]
    job.save()
    return freed


@app.post("/api/jobs/{job_id}/clean")
def clean_job(job_id: str) -> dict:
    """🧹 Dọn file trung gian của job đã XONG — thường lấy lại 200–500MB/job."""
    _check_job_id(job_id)
    with _lock:
        if job_id in _active:
            raise HTTPException(409, "Job đang chạy/chờ — không dọn được")
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    if job.stage != Stage.DONE:
        raise HTTPException(409, "Chỉ dọn job đã hoàn thành (tránh hỏng job dở dang)")
    return {"freed_mb": round(_clean_job_files(job) / 1e6, 1)}


@app.post("/api/cleanup")
def cleanup_all(dry: bool = False) -> dict:
    """🧹 Dọn dẹp TOÀN CỤC (audit #2): (1) file trung gian của MỌI job đã xong,
    (2) bản final-*.mp4 TRÙNG NGUYÊN VẸN trong output/ (giữ bản mới nhất mỗi nhóm).
    dry=true chỉ đếm, không xóa — để UI hiện trước số MB sẽ lấy lại."""
    freed_jobs = 0
    n_jobs = 0
    skipped_running = 0
    if config.JOBS_DIR.exists():
        for d in config.JOBS_DIR.iterdir():
            if not d.is_dir():
                continue
            with _lock:
                if d.name in _active:
                    skipped_running += 1
                    continue
            try:
                job = Job.load(d.name)
            except Exception:
                continue
            if job.stage != Stage.DONE:
                continue
            if dry:
                for name in _CLEAN_FILES:
                    p = job.dir / name
                    try:
                        freed_jobs += p.stat().st_size if p.exists() else 0
                    except OSError:
                        pass
                for sped in (job.dir / "tts").glob("seg_*_sped.wav"):
                    try:
                        freed_jobs += sped.stat().st_size
                    except OSError:
                        pass
                n_jobs += 1
            else:
                got = _clean_job_files(job)
                if got:
                    n_jobs += 1
                freed_jobs += got

    # output/: gom file cùng KÍCH THƯỚC rồi mới hash (đỡ hash cả GB) — trùng md5
    # nguyên vẹn thì giữ bản mtime mới nhất, xóa phần còn lại
    import hashlib
    freed_out = 0
    n_out = 0
    if config.OUTPUT_DIR.exists():
        by_size: dict[int, list[Path]] = {}
        for p in config.OUTPUT_DIR.glob("*.mp4"):
            try:
                by_size.setdefault(p.stat().st_size, []).append(p)
            except OSError:
                pass
        for size, group in by_size.items():
            if len(group) < 2:
                continue
            by_hash: dict[str, list[Path]] = {}
            for p in group:
                try:
                    h = hashlib.md5(p.read_bytes()).hexdigest()
                except OSError:
                    continue
                by_hash.setdefault(h, []).append(p)
            for dupes in by_hash.values():
                if len(dupes) < 2:
                    continue
                dupes.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for p in dupes[1:]:   # giữ bản mới nhất
                    freed_out += size
                    n_out += 1
                    if not dry:
                        try:
                            p.unlink()
                        except OSError:
                            freed_out -= size
                            n_out -= 1
    return {"dry": dry,
            "jobs_cleaned": n_jobs, "jobs_freed_mb": round(freed_jobs / 1e6, 1),
            "output_dupes_removed": n_out, "output_freed_mb": round(freed_out / 1e6, 1),
            "skipped_running": skipped_running,
            "total_freed_mb": round((freed_jobs + freed_out) / 1e6, 1)}


# ---------- Font tùy biến: liệt kê fonts/ + phục vụ file cho preview ----------

_FONT_EXTS = {".ttf", ".otf", ".ttc"}
_BUILTIN_FONTS = ["Arial", "Tahoma", "Verdana", "Segoe UI", "Calibri", "Times New Roman"]


@app.get("/api/fonts")
def list_fonts() -> dict:
    """Font cho dropdown phụ đề: built-in hệ thống + font tùy biến trong fonts/.
    Đọc TÊN HỌ font từ file (libass khớp theo tên này), không phải tên file."""
    fonts = [{"name": n, "file": None, "builtin": True} for n in _BUILTIN_FONTS]
    seen = {f["name"] for f in fonts}
    config.FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for p in sorted(config.FONTS_DIR.iterdir()):
        if p.suffix.lower() not in _FONT_EXTS or not p.is_file():
            continue
        name = p.stem
        try:
            from fontTools.ttLib import TTFont
            tt = TTFont(str(p), fontNumber=0, lazy=True)
            name = (tt["name"].getDebugName(1)
                    or tt["name"].getBestFamilyName() or p.stem)
            tt.close()
        except Exception:
            pass
        if name in seen:
            continue
        seen.add(name)
        fonts.append({"name": name, "file": p.name, "builtin": False})
    return {"fonts": fonts}


@app.get("/api/fonts/file/{filename}")
def font_file(filename: str) -> FileResponse:
    """Phục vụ file font cho preview @font-face trên trình duyệt."""
    # resolve + is_relative_to: chặn cả traversal lẫn cú pháp ổ đĩa Windows 'C:x'
    p = (config.FONTS_DIR / filename).resolve()
    if (not p.is_relative_to(config.FONTS_DIR.resolve())
            or p.suffix.lower() not in _FONT_EXTS or not p.is_file()):
        raise HTTPException(404, "Không có font này")
    return FileResponse(p, media_type="font/sfnt",
                        headers={"Cache-Control": "max-age=86400"})


# ---------- Glossary mặc định: lưu/đọc bảng tên riêng tái dùng theo bộ ----------
# Nằm trong series/ (git theo dõi) → đồng bộ 2 máy; di trú 1 lần từ data/ cũ.

_GLOSSARY_DEFAULT = config.BASE_DIR / "series" / "_glossary_default.txt"
_GLOSSARY_DEFAULT_OLD = config.DATA_DIR / "glossary_default.txt"


def _glossary_default_path() -> Path:
    _GLOSSARY_DEFAULT.parent.mkdir(parents=True, exist_ok=True)
    if _GLOSSARY_DEFAULT_OLD.exists() and not _GLOSSARY_DEFAULT.exists():
        try:
            _GLOSSARY_DEFAULT_OLD.replace(_GLOSSARY_DEFAULT)
        except OSError:
            pass
    return _GLOSSARY_DEFAULT


@app.get("/api/glossary-default")
def get_glossary_default() -> dict:
    p = _glossary_default_path()
    return {"glossary": p.read_text(encoding="utf-8") if p.exists() else ""}


class GlossaryBody(BaseModel):
    glossary: str


@app.post("/api/glossary-default")
def set_glossary_default(body: GlossaryBody) -> dict:
    _check_glossary(body.glossary)
    _glossary_default_path().write_text(body.glossary, encoding="utf-8")
    return {"saved": True}


# ---------- #15 Glossary theo JOB: gợi ý tên riêng từ chính video + sửa/dịch lại ----------

@app.get("/api/jobs/{job_id}/glossary-suggest")
def glossary_suggest(job_id: str) -> dict:
    """Tên riêng Claude trích từ transcript của job. Ưu tiên cache glossary_auto.json
    (S4 đã lưu khi dịch); chưa có thì trích ngay (1 call ngắn) rồi cache lại."""
    _check_job_id(job_id)
    jd = config.JOBS_DIR / job_id
    cache = jd / "glossary_auto.json"
    if cache.exists():
        try:
            return {"pairs": json.loads(cache.read_text(encoding="utf-8")),
                    "cached": True}
        except (OSError, json.JSONDecodeError):
            pass
    tz = jd / "transcript_zh.json"
    if not tz.exists():
        raise HTTPException(409, "Job chưa có transcript (chạy tới bước nhận dạng đã)")
    try:
        segments = json.loads(tz.read_text(encoding="utf-8"))["segments"]
    except (OSError, json.JSONDecodeError, KeyError):
        raise HTTPException(422, "transcript hỏng")
    import anthropic
    from core import glossary, langs
    aux = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                              timeout=60.0, max_retries=1)
    donghua_vi = config.CONTENT_STYLE == "donghua" and langs.is_vi()
    pairs = glossary.auto_extract(aux, segments,
                                  generic=not donghua_vi, lang_name=langs.name())
    out = [{"zh": z, "vi": v} for z, v in pairs]
    if out:
        cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {"pairs": out, "cached": False}


class JobGlossaryBody(BaseModel):
    glossary: str
    save_series: bool = False   # gộp thêm vào glossary DÙNG CHUNG của series (nếu job có)
    retranslate: bool = False   # xoá bản dịch + TTS → chạy lại từ bước dịch với glossary mới


@app.post("/api/jobs/{job_id}/glossary")
def set_job_glossary(job_id: str, body: JobGlossaryBody) -> dict:
    """Cập nhật glossary của job (#15). retranslate=True: reset về sau bước transcript
    để dịch lại với glossary mới (client tự bấm/gọi resume sau khi reset xong)."""
    _check_job_id(job_id)
    _check_glossary(body.glossary)
    with _lock:
        if job_id in _active:
            raise HTTPException(409, "Job đang chạy — chờ xong/Hủy rồi sửa glossary")
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    job.glossary = body.glossary
    added_series = 0
    if body.save_series and job.series:
        # gộp vào series: chỉ THÊM cặp có tên gốc CHƯA có (không đè bản series đang có)
        from core import glossary as g, series
        s = series.load(job.series) or {"glossary": "", "casting": {}}
        have = {z for z, _ in g.parse(s.get("glossary", ""))}
        new_lines = [f"{z}={v}" if v else z
                     for z, v in g.parse(body.glossary) if z not in have]
        if new_lines:
            merged = (s.get("glossary", "").rstrip() + "\n" + "\n".join(new_lines)).strip()
            if len(merged) > 20000:
                raise HTTPException(400, "Glossary series vượt 20000 ký tự sau khi gộp")
            series.save(job.series, merged, s.get("casting") or {})
            added_series = len(new_lines)

    reset = False
    if body.retranslate:
        # các file stage sau "có thì bỏ qua" — phải xoá TRƯỚC (Windows có thể khoá → 409
        # sớm, chưa đổi state, người dùng dừng phát rồi thử lại; xem save_segments)
        gating = ["transcript_vi.json", "sub_vi.srt", "dubbed_audio.wav", "final.mp4"]
        locked = [n for n in gating if not _unlink_quiet(job.dir / n)]
        if locked:
            raise HTTPException(409, "Tệp đang được phát/khoá: " + ", ".join(locked)
                                + ". Dừng phát rồi thử lại.")
        _unlink_quiet(job.dir / "mix_report.json")
        _unlink_quiet(job.dir / "ducked.wav")
        _unlink_quiet(job.dir / "metadata.json")   # title/desc theo bản dịch cũ → làm lại
        shutil.rmtree(job.dir / "tts", ignore_errors=True)  # text đổi → toàn bộ mp3 cũ sai
        keep = ("downloading", "extracting", "transcribing")
        job.completed_stages = [s for s in job.completed_stages if s in keep]
        job.stage = Stage.PENDING
        job.error = None
        from core import progress
        progress.clear(job.dir)
        reset = True
    job.save()
    return {"saved": True, "series_added": added_series, "reset": reset}


# ---------- Thư viện giọng viXTTS: liệt kê voices/ + nghe thử clip mẫu ----------

_VOICE_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


@app.get("/api/voices")
def list_voices() -> dict:
    """Các clip giọng mẫu trong voices/ (cho viXTTS nhân bản) + giọng nam/nữ đang đặt."""
    config.VOICES_DIR.mkdir(parents=True, exist_ok=True)
    out = [{"file": p.name, "name": p.stem}
           for p in sorted(config.VOICES_DIR.iterdir())
           if p.suffix.lower() in _VOICE_EXTS and p.is_file()]
    return {"voices": out, "nam": config.VIXTTS_VOICE_NAM, "nu": config.VIXTTS_VOICE_NU}


# ---------- Series (#7/#8): glossary + casting giọng dùng chung nhiều tập ----------

class SeriesBody(BaseModel):
    name: str
    glossary: str = ""
    casting: dict = {}   # {tên nhân vật: tên file giọng trong voices/}


@app.get("/api/series")
def list_series() -> dict:
    """Danh sách series đã lưu (cho dropdown thêm job + trang quản lý)."""
    from core import series
    return {"series": series.list_all()}


@app.get("/api/series/one")
def get_series(name: str) -> dict:
    """Chi tiết 1 series theo tên (query param). Chưa có → trả khung rỗng để tạo mới."""
    from core import series
    s = series.load(name)
    if not s:
        return {"name": name, "glossary": "", "casting": {}, "exists": False}
    return {**s, "exists": True}


@app.post("/api/series")
def save_series(body: SeriesBody) -> dict:
    """Tạo/cập nhật series (glossary chung + bảng casting)."""
    from core import series
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Thiếu tên series")
    _check_glossary(body.glossary)
    if len(body.casting) > 500:
        raise HTTPException(400, "Bảng casting quá lớn (tối đa 500 nhân vật)")
    try:
        return series.save(name, body.glossary, body.casting)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/voices/file/{filename}")
def voice_file(filename: str) -> FileResponse:
    """Phục vụ clip giọng mẫu để nghe thử trên trình duyệt."""
    p = (config.VOICES_DIR / filename).resolve()
    if (not p.is_relative_to(config.VOICES_DIR.resolve())
            or p.suffix.lower() not in _VOICE_EXTS or not p.is_file()):
        raise HTTPException(404, "Không có giọng này")
    return FileResponse(p, headers={"Cache-Control": "no-store"})


@app.post("/api/voices/open")
def open_voices_folder() -> dict:
    config.VOICES_DIR.mkdir(parents=True, exist_ok=True)
    os.startfile(config.VOICES_DIR)
    return {"opened": True}


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
    _check_job_id(job_id)
    with _lock:
        if job_id in _active:
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
    _check_job_id(job_id)
    job_dir = config.JOBS_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(404, "Không có job này")
    os.startfile(job_dir)  # server chạy local nên mở Explorer ngay trên máy
    return {"opened": job_id}


# _read_env đã dời sang webui/envfile.py (#16 giai đoạn 1) — import ở đầu file.


# ---------- #1 Đăng YouTube: gói xuất sẵn (kéo-thả) + đăng thẳng OAuth ----------

def _youtube_ready() -> bool:
    try:
        from core import youtube_upload
        return youtube_upload.is_ready()
    except Exception:
        return False


@app.post("/api/jobs/{job_id}/package")
def make_package(job_id: str) -> dict:
    """Gom video + metadata + thumbnail ra 1 thư mục output/ để đăng tay (mở luôn folder)."""
    _check_job_id(job_id)
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    from core import youtube_upload
    try:
        folder = youtube_upload.build_package(job)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    if os.name == "nt":
        try:
            os.startfile(str(folder))   # mở thư mục cho người dùng
        except OSError:
            pass
    return {"folder": str(folder)}


@app.post("/api/jobs/{job_id}/shorts")
def make_shorts(job_id: str) -> dict:
    """PLAN 12 #4: cắt Shorts cao trào từ final.mp4 (chạy nền — re-encode vài clip).
    Xong sẽ tự mở thư mục shorts/ của job."""
    _check_job_id(job_id)
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    if not (job.dir / "final.mp4").exists():
        raise HTTPException(409, "Chưa có final.mp4 (job chưa render xong)")
    from core import shorts as shorts_mod

    def _work() -> None:
        try:
            made = shorts_mod.generate(job)
            print(f"[shorts] {job_id}: tạo {len(made)} clip")
            if made and os.name == "nt":
                try:
                    os.startfile(str(job.dir / "shorts"))
                except OSError:
                    pass
        except Exception as e:
            print(f"[shorts] {job_id} lỗi: {e}")

    threading.Thread(target=_work, daemon=True, name="flowapp-shorts").start()
    n = getattr(config, "SHORTS_COUNT", 2)
    return {"started": True,
            "note": f"Đang cắt ~{n} short (re-encode, mất khoảng 1 phút) — "
                    f"xong sẽ tự mở thư mục shorts/."}


@app.post("/api/jobs/{job_id}/upload-youtube")
def upload_youtube(job_id: str) -> dict:
    """Đăng thẳng lên YouTube (OAuth). Lần đầu sẽ mở trình duyệt để bạn cho phép.
    Mặc định privacy=private cho an toàn — bạn tự đổi khi muốn công khai."""
    _check_job_id(job_id)
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")
    from core import youtube_upload
    try:
        return youtube_upload.upload(job)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(400, f"Đăng YouTube lỗi: {e}")


@app.get("/api/config")
def get_config() -> dict:
    from core import brand
    env = _read_env()
    defaults = {k: str(getattr(config, k, "")) for k in SAFE_ENV_KEYS}
    return {
        "values": {k: env.get(k, defaults[k]) for k in SAFE_ENV_KEYS},
        "api_key_set": bool(env.get("ANTHROPIC_API_KEY") or config.ANTHROPIC_API_KEY),
        # khóa bí mật: chỉ báo đã đặt hay chưa, KHÔNG trả giá trị
        "telegram_token_set": bool(env.get("TELEGRAM_BOT_TOKEN") or config.TELEGRAM_BOT_TOKEN),
        "hf_token_set": bool(env.get("HF_TOKEN") or config.HF_TOKEN),
        "gemini_key_set": bool(env.get("GEMINI_API_KEY") or config.GEMINI_API_KEY),
        "elevenlabs_key_set": bool(env.get("ELEVENLABS_API_KEY") or config.ELEVENLABS_API_KEY),
        "vbee_token_set": bool(env.get("VBEE_TOKEN") or config.VBEE_TOKEN),
        "fpt_key_set": bool(env.get("FPT_TTS_API_KEY") or config.FPT_TTS_API_KEY),
        "youtube_ready": _youtube_ready(),
        "music_files": brand.list_music(),
        "logo_files": brand.list_logo(),
        "clip_files": brand.list_clips(),
    }


# rỗng = giá trị hợp lệ (cho phép XÓA), không phải "bỏ qua giữ giá trị cũ"
_EMPTY_OK = {"VIXTTS_VOICE_NAM", "VIXTTS_VOICE_NU", "TRANSLATE_STYLE_EXTRA",
             "SUBSCRIBE_TEXT", "TELEGRAM_CHAT_ID", "YOUTUBE_CLIENT_SECRETS"}


@app.post("/api/config")
def set_config(body: dict) -> dict:
    updates = {}
    for k, v in body.items():
        if k not in SAFE_ENV_KEYS and k not in SECRET_ENV_KEYS:
            continue
        v = str(v).strip()
        if not v and k not in _EMPTY_OK:
            continue  # bỏ qua rỗng cho khóa không cho rỗng (giữ giá trị cũ, gồm cả secret)
        if "\n" in v or len(v) > 500:
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
    # ghi nguyên tử (tmp + replace) — .env là single source, ghi dở giữa lúc worker
    # con load_dotenv sẽ mất key; cùng pattern với state.json/series.json
    tmp = ENV_PATH.with_name(f".env.{uuid.uuid4().hex}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, ENV_PATH)
    return {"saved": sorted(updates), "note": "Áp dụng cho job chạy mới"}


@app.get("/")
def index() -> HTMLResponse:
    html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)
