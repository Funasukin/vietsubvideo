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
                 "CONTENT_STYLE", "TARGET_LANG", "MAX_SPEEDUP",
                 "TTS_ENGINE", "TTS_SINGLE_VOICE", "TTS_VOICE", "TTS_VOICE_NU",
                 "VIXTTS_VOICE_NAM", "VIXTTS_VOICE_NU", "KEEP_BGM", "VOICE_FX", "EMOTION",
                 "PROSODY_TRANSFER",
                 "ELEVENLABS_VOICE_NAM", "ELEVENLABS_VOICE_NU", "ELEVENLABS_MODEL",
                 "VBEE_APP_ID", "VBEE_VOICE_NAM", "VBEE_VOICE_NU",
                 "FPT_VOICE_NAM", "FPT_VOICE_NU", "PROSODY",
                 "WHISPER_MODEL", "TRANSCRIPT_SOURCE", "SUBTITLE_MODE", "SUB_SPLIT",
                 "OCR_WORKERS", "OCR_FPS",
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

_pending: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()
# Job đang trong hàng đợi HOẶC đang chạy. Nguồn sự thật duy nhất để chống xếp trùng
# (một job chạy 2 lần): mọi "kiểm tra rồi xếp" đều làm dưới _lock nên atomic.
_active: set[str] = set()
_running_id: str | None = None   # job đang chạy (None nếu rảnh) — chỉ để hiển thị
_current_proc: "subprocess.Popen | None" = None  # tiến trình job đang chạy (để hủy)
_cancel: set[str] = set()        # job_id được yêu cầu hủy (đang chạy hoặc còn chờ)
_retries: dict[str, int] = {}    # job_id → số lần đã tự chạy lại
_queue_paused = False            # ⏸ tạm dừng hàng đợi: job đang chạy chạy nốt,
                                 # job kế KHÔNG được bắt đầu cho tới khi mở lại


def _enqueue(job_id: str) -> bool:
    """Xếp job vào hàng đợi nếu chưa ở trong (đang chờ/đang chạy).

    Trả True nếu vừa xếp, False nếu đã đang chờ/đang chạy. Kiểm tra + đánh dấu
    'active' dưới cùng một lock → hai request gần như đồng thời (bấm Chạy 2 lần,
    hoặc Chạy lẻ trùng Chạy tất cả) không thể cùng xếp một job."""
    with _lock:
        if job_id in _active or job_id in _cancel:
            return False   # đang chờ/chạy, hoặc còn đang dọn dở sau khi bị hủy
        _active.add(job_id)
    # Nếu dashboard đang giữ model viXTTS (do nghe thử giọng nhân bản), nhả GPU ra
    # trước khi worker (tiến trình con) nạp model của nó → tránh tranh chấp VRAM/OOM.
    try:
        from core import vixtts
        vixtts.unload()
    except Exception:
        pass
    _pending.put(job_id)
    return True


def _auto_retry_limit() -> int:
    """Đọc AUTO_RETRY tươi từ .env mỗi lần (sửa từ UI có hiệu lực ngay, khỏi restart)."""
    try:
        return int(_read_env().get("AUTO_RETRY", config.AUTO_RETRY))
    except (ValueError, TypeError):
        return config.AUTO_RETRY


def _kill_proc_tree(proc: "subprocess.Popen") -> str:
    """Hủy cây tiến trình job. Trên Windows cli.py sinh thêm worker OCR (ProcessPool);
    taskkill /T diệt cả con cháu — chạy khi cli.py CÒN sống nên cây tiến trình còn
    nguyên vẹn để liệt kê. Trả 'ok' hoặc mô tả lỗi để caller ghi log."""
    try:
        if os.name == "nt":
            r = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, text=True)
            if r.returncode != 0:
                return f"taskkill rc={r.returncode}: {(r.stderr or r.stdout or '').strip()}"
            return "ok"
        proc.terminate()
        return "ok"
    except Exception as e:
        return f"lỗi kill: {e}"


def _drain_remove(job_id: str) -> bool:
    """Rút job_id khỏi hàng đợi _pending. queue.Queue không xóa phần tử giữa chừng được
    nên múc hết (get_nowait — không block) rồi đổ lại, bỏ job_id. PHẢI gọi khi đang giữ
    _lock. Trả True nếu tìm & rút được (⇒ caller tự dọn _active); False nếu không còn
    trong hàng (worker đã pull ⇒ để worker reap qua cờ _cancel)."""
    items, found = [], False
    while True:
        try:
            items.append(_pending.get_nowait())
        except queue.Empty:
            break
    for it in items:
        if it == job_id and not found:
            found = True          # chỉ bỏ 1 lần (dù _enqueue đã chặn xếp trùng)
        else:
            _pending.put(it)
    return found


def _notify_done(job_id: str, ok: bool) -> None:
    """Báo Telegram khi job kết thúc (best-effort, không làm hỏng worker)."""
    try:
        from core import notify
        if not notify.enabled():
            return
        from core.job import Job
        j = Job.load(job_id)
        notify.job_done(job_id, j.url, ok, j.error or "")
    except Exception:
        pass


def _worker() -> None:
    global _running_id, _current_proc
    while True:
        job_id = _pending.get()          # KHÔNG giữ lock khi chờ (get() blocking)
        # ⏸ hàng đợi tạm dừng → giữ job (vẫn hiện "trong hàng đợi"), chờ mở lại.
        # Hủy trong lúc chờ vẫn ăn (rơi xuống nhánh _cancel bên dưới).
        while True:
            with _lock:
                if not _queue_paused or job_id in _cancel:
                    break
            time.sleep(0.5)
        with _lock:
            if job_id in _cancel:         # hủy khi còn nằm trong hàng đợi → bỏ qua
                _cancel.discard(job_id)
                _active.discard(job_id)
                _retries.pop(job_id, None)
                continue
            _running_id = job_id          # vẫn nằm trong _active từ lúc _enqueue
        # Log per-job: toàn bộ stdout/stderr của cli.py ghi vào <job>/run.log (append,
        # kèm header mỗi lượt) — job lỗi lúc vắng mặt vẫn còn vết, UI đọc qua /log.
        log_f = None
        try:
            log_f = open(config.JOBS_DIR / job_id / "run.log", "ab")
            log_f.write(f"\n===== run {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
                        .encode("utf-8"))
            log_f.flush()
            out_target = log_f
        except OSError:
            out_target = None             # không mở được log → về console như cũ
        proc = subprocess.Popen(
            [sys.executable, str(config.BASE_DIR / "cli.py"), "--resume", job_id],
            cwd=config.BASE_DIR,
            stdout=out_target, stderr=subprocess.STDOUT if out_target else None,
        )
        with _lock:
            _current_proc = proc
            # Hủy có thể ập tới đúng lúc Popen đang khởi động (khi đó _current_proc
            # còn None nên endpoint không kill được) → tự kiểm & kill ngay tại đây.
            kill_now = job_id in _cancel
        if kill_now:
            res = _kill_proc_tree(proc)   # bị hủy ngay lúc khởi động → kill kịp
            if res != "ok":
                print(f"[cancel] {job_id}: {res}")
        proc.wait()
        if log_f is not None:
            try:
                log_f.close()
            except OSError:
                pass
        rc = proc.returncode              # ≠0 ⇒ pipeline lỗi (cli.py để exception thoát)
        with _lock:
            _current_proc = None
            _running_id = None
            cancelled = job_id in _cancel
            _cancel.discard(job_id)
        if cancelled:                     # người dùng bấm Hủy → không thử lại
            with _lock:
                _active.discard(job_id)
                _retries.pop(job_id, None)
        elif rc != 0 and _retries.get(job_id, 0) < _auto_retry_limit():
            n = _retries.get(job_id, 0) + 1
            with _lock:
                _retries[job_id] = n
            print(f"[worker] job {job_id} lỗi (rc={rc}) → tự chạy lại lần {n}")
            _pending.put(job_id)          # giữ trong _active, xếp lại cuối hàng
        else:                             # kết thúc hẳn (xong hoặc lỗi hết lượt thử)
            with _lock:
                _active.discard(job_id)
                _retries.pop(job_id, None)
            _notify_done(job_id, rc == 0)   # #11 báo Telegram (best-effort)


threading.Thread(target=_worker, daemon=True, name="flowapp-worker").start()


@atexit.register
def _kill_running_job() -> None:
    """Server tắt (Ctrl+C / restart) → hạ luôn job đang chạy kẻo thành tiến trình
    mồ côi chiếm CPU/GPU. Checkpoint đã lưu theo stage nên bấm Chạy tiếp là nối lại."""
    with _lock:
        proc = _current_proc
    if proc is not None and proc.poll() is None:
        _kill_proc_tree(proc)


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


class RenderOptions(BaseModel):
    subtitle_mode: str = "soft"   # soft | cover_only | burn | none
    cover: str = "none"           # none | blur | black
    cover_top: float = 0.78       # cạnh TRÊN của băng che (tỉ lệ chiều cao)
    cover_bottom: float = 1.0     # cạnh DƯỚI của băng che (1.0 = dính đáy)
    cover_width: float = 1.0      # độ rộng vùng blur (1.0 = full width, 0.6 = 60% căn giữa)
    style: dict = {}              # font/size/color... — xem DEFAULT_STYLE trong s8_render
    fx: str = "off"               # hậu kỳ giọng: off|canbang|amday|rosang|dienanh|toithieu (core/voice_fx)
    frame: str = "none"           # khung viền: none|solid|double|twocolor|corner|png:<file>
    frame_color: str = "#FFD700"  # màu viền procedural
    frame_color2: str = "#FFFFFF" # màu 2 (kiểu "viền 2 màu")
    frame_width: float = 0.02     # độ dày viền = tỉ lệ chiều cao
    frame_pad: bool = False       # True = "khung ngoài": thu video vào trong, khung không che hình
    sub_split: bool = True        # tách phụ đề hiển thị theo nhịp sub gốc (giọng vẫn câu gộp)
    wm_method: str = "none"       # xóa/che watermark kênh gốc: none|delogo|blur|black|logo
    wm_box: list = []             # vùng watermark [x0,y0,x1,y1] chuẩn hóa 0..1
    crop: list = []               # cắt mép [trái,trên,phải,dưới] tỉ lệ 0..0.2 rồi phóng lại


_JOB_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{6}$")


def _check_job_id(job_id: str) -> None:
    """Chặn path traversal: job_id phải đúng định dạng Job.create sinh ra
    (vd 20260614_014525_56d6d6) — loại bỏ '..', '/', '\\', đường dẫn tuyệt đối."""
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(404, "Không có job này")


def _check_glossary(text: str) -> None:
    """Chặn glossary khổng lồ (paste nhầm) → tránh phình prompt / vỡ context dịch."""
    if len(text or "") > 20000:
        raise HTTPException(400, "Bảng tên riêng quá dài (tối đa 20000 ký tự)")


def _job_summary(job_dir: Path) -> dict | None:
    state_path = job_dir / "state.json"
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None   # state.json hỏng/đang ghi dở → ẩn job này thay vì 500 cả danh sách
    if not isinstance(state, dict) or "id" not in state:
        return None

    state["seg_total"] = _cached_seg_total(job_dir)
    state["tts_done"] = _cached_tts_done(job_dir)
    state["has_final"] = (job_dir / "final.mp4").exists()
    state["has_srt"] = (job_dir / "sub_vi.srt").exists()
    state["has_thumb"] = (job_dir / "thumbnail.jpg").exists()
    state["has_log"] = (job_dir / "run.log").exists()
    meta_p = job_dir / "metadata.json"
    if meta_p.exists():
        try:
            state["yt_title"] = json.loads(
                meta_p.read_text(encoding="utf-8")).get("title")
        except (json.JSONDecodeError, OSError):
            pass
    with _lock:
        state["queued"] = state["id"] in _active and state["id"] != _running_id
        state["running"] = state["id"] == _running_id

    mr = job_dir / "mix_report.json"
    if mr.exists():
        try:
            report = json.loads(mr.read_text(encoding="utf-8"))
            state["overflow"] = len(report.get("overflow_warnings", []))
        except (OSError, json.JSONDecodeError):
            pass
    # tiến độ trong-stage (OCR/Whisper/dịch) — chỉ đọc khi job ĐANG chạy (job xong/chờ
    # thì file này vô nghĩa; đỡ 1 lần mở file mỗi job mỗi nhịp poll 3 giây)
    if state["running"]:
        from core import progress
        prog = progress.read(job_dir)
        if prog and prog.get("stage") == state.get("stage"):
            state["prog_done"] = prog.get("done", 0)
            state["prog_total"] = prog.get("total", 0)
    return state


# Cache theo mtime cho 2 phép đếm đắt nhất của poll 3s: đọc CẢ transcript_vi.json chỉ
# để đếm câu, và glob thư mục tts/. mtime đổi (dịch lại/đọc thêm câu) → tự tính lại.
_seg_cache: dict[str, tuple[float, int]] = {}
_tts_cache: dict[str, tuple[float, int]] = {}


def _cached_seg_total(job_dir: Path) -> int:
    tv = job_dir / "transcript_vi.json"
    try:
        mt = tv.stat().st_mtime
    except OSError:
        _seg_cache.pop(job_dir.name, None)
        return 0
    hit = _seg_cache.get(job_dir.name)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        n = len(json.loads(tv.read_text(encoding="utf-8"))["segments"])
    except (OSError, json.JSONDecodeError, KeyError):
        return 0
    _seg_cache[job_dir.name] = (mt, n)
    return n


def _cached_tts_done(job_dir: Path) -> int:
    td = job_dir / "tts"
    try:
        mt = td.stat().st_mtime   # NTFS đổi mtime thư mục khi thêm/xoá file con
    except OSError:
        _tts_cache.pop(job_dir.name, None)
        return 0
    hit = _tts_cache.get(job_dir.name)
    if hit and hit[0] == mt:
        return hit[1]
    n = len(list(td.glob("seg_????.mp3")))
    _tts_cache[job_dir.name] = (mt, n)
    return n


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
               series: str = Form("")) -> dict:
    """Tạo job từ video UPLOAD ở máy: lưu thẳng thành source.<ext> trong thư mục job.
    Không đặt completed_stages — S1 (download) tự bỏ qua khi đã có source nên job
    vẫn là 'Chờ chạy' bình thường (hiện nút ▶ Chạy, tính vào 'Chạy tất cả')."""
    name = Path(file.filename or "video").name
    ext = Path(name).suffix.lower()
    if ext not in _UPLOAD_EXTS:
        raise HTTPException(400, "Định dạng không hỗ trợ: " + (ext or "(không rõ)")
                            + ". Chấp nhận: " + ", ".join(sorted(_UPLOAD_EXTS)))
    _check_glossary(glossary)
    job = Job.create(url=f"[Upload] {name}",
                     pause_before_render=pause_before_render, glossary=glossary,
                     series=series.strip())
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
        if job_id == _running_id and _current_proc is not None:
            proc = _current_proc         # đang chạy → kill; worker.wait() sẽ dọn _active
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
        return {"paused": _queue_paused}


@app.post("/api/queue/pause")
def queue_pause(body: QueuePauseBody) -> dict:
    """⏸/▶ Tạm dừng/mở lại hàng đợi. Job đang chạy chạy nốt; job kế chờ mở lại."""
    global _queue_paused
    with _lock:
        _queue_paused = body.paused
    return {"paused": body.paused}


@app.post("/api/jobs/{job_id}/prioritize")
def prioritize_job(job_id: str) -> dict:
    """⬆ Đưa job đang CHỜ lên đầu hàng đợi (chạy ngay sau job hiện tại)."""
    _check_job_id(job_id)
    with _lock:
        if job_id not in _active or job_id == _running_id:
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


@app.post("/api/jobs/{job_id}/rerender")
def rerender_job(job_id: str, opts: RenderOptions) -> dict:
    _check_job_id(job_id)
    with _lock:
        if job_id in _active:
            raise HTTPException(409, "Job đang chạy hoặc đã trong hàng đợi")
    try:
        job = Job.load(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "Không có job này")

    job.render = {"subtitle_mode": opts.subtitle_mode,
                  "cover": opts.cover, "cover_top": opts.cover_top,
                  "cover_bottom": opts.cover_bottom,
                  "cover_width": opts.cover_width,
                  "style": opts.style, "fx": opts.fx,
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
    _unlink_quiet(job.dir / "metadata.json")
    job.completed_stages = [s for s in job.completed_stages
                            if s not in ("rendering", "metadata")]
    job.error = None
    job.save()
    _enqueue(job_id)
    return _job_summary(job.dir)


@app.post("/api/jobs/{job_id}/preview")
def preview(job_id: str, opts: RenderOptions) -> FileResponse:
    """Áp vùng che + kiểu chữ + phụ đề mẫu lên 1 frame thật — xem trước không cần render."""
    from core import ffmpeg, frames
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


# ---------- Editor lời thoại: xem + sửa text/giọng từng câu ----------

@app.get("/api/jobs/{job_id}/segments")
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
    return {"segments": segs,
            "engine": config.TTS_ENGINE,
            "voices": {"nam": nam_v, "nu": nu_v},
            "render": render,
            "frames": frames.list_png(),
            "series": job_series,
            "cast_names": series.character_names(job_series),  # gợi ý nhân vật đã cast
            "has_final": (job_dir / "final.mp4").exists(),
            "has_dub": (job_dir / "dubbed_audio.wav").exists()}


_QC_CJK = re.compile(r"[㐀-鿿]")   # chữ Trung còn sót trong bản dịch


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
                "vf_auto.txt", "ocr_raw.json"]
_CLEAN_STAGES = {"extracting", "bgm", "mixing"}


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
    return {"freed_mb": round(freed / 1e6, 1)}


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


def _unlink_quiet(path: Path, retries: int = 8) -> bool:
    """Xoá file, thử lại nếu Windows còn KHOÁ (trình duyệt đang phát/serve dubbed_audio.wav
    hay final.mp4 giữ handle → WinError 32). Trả True nếu file đã KHÔNG còn (xoá được hoặc
    vốn không có), False nếu VẪN còn sau retry. QUAN TRỌNG: stage sau (s7/s8) bỏ qua khi
    file còn tồn tại, nên caller phải kiểm tra kết quả — còn sót = không dựng lại được."""
    import time
    for i in range(retries):
        try:
            path.unlink(missing_ok=True)
            return True
        except PermissionError:
            if i == retries - 1:
                print(f"  unlink bị khoá: {path.name}")
                return not path.exists()
            time.sleep(0.25)
    return True


@app.post("/api/jobs/{job_id}/segments")
def save_segments(job_id: str, body: SegmentEdits) -> dict:
    """Lưu sửa lời thoại + giọng; chỉ đọc lại TTS các câu ĐÃ ĐỔI rồi mix+render lại."""
    _check_job_id(job_id)
    with _lock:
        if job_id in _active:
            raise HTTPException(409, "Job đang chạy — chờ xong rồi sửa")
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
    if not changed and not has_render:
        return {"changed": 0, **(_job_summary(job.dir) or {})}

    # XOÁ TRƯỚC các file mà stage sau "có thì bỏ qua" (s7: dubbed_audio.wav; s8: final.mp4,
    # sub_vi.srt) — chúng có thể đang bị TRÌNH DUYỆT phát giữ khoá. Nếu CÒN khoá → 409 NGAY,
    # khi CHƯA ghi gì (transcript/stages) → người dùng dừng phát rồi thử lại, không mất chỉnh
    # sửa và KHÔNG "thành công giả" với dub/final cũ (nếu xoá hụt, s7/s8 sẽ bỏ qua → dữ liệu cũ).
    gating = []
    if changed:
        gating += ["dubbed_audio.wav", "sub_vi.srt", "final.mp4"]
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

    if has_render:
        # áp dụng cài đặt phụ đề/che rồi dựng lại CHỈ khâu render (S8). Giữ nguyên
        # metadata/thumbnail (không phụ thuộc sub/che) để khỏi tốn thêm 1 call Claude.
        r = body.render
        job.render = {"subtitle_mode": r.subtitle_mode, "cover": r.cover,
                      "cover_top": r.cover_top, "cover_bottom": r.cover_bottom,
                      "cover_width": r.cover_width, "style": r.style, "fx": r.fx,
                      "frame": r.frame, "frame_color": r.frame_color,
                      "frame_color2": r.frame_color2, "frame_width": r.frame_width}
        job.completed_stages = [s for s in job.completed_stages if s != "rendering"]

    # rebuild_only: đọc lại + trộn dub rồi DỪNG trước render (nghe lại trong editor);
    # ngược lại render thẳng ra final.
    job.pause_before_render = bool(body.rebuild_only)
    job.error = None
    job.save()
    _enqueue(job_id)
    return {"changed": len(changed), **(_job_summary(job.dir) or {})}


class TtsPreviewBody(BaseModel):
    text: str
    voice: str = "nam"
    voice_ref: str = ""   # tên clip trong voices/ → đọc câu này bằng viXTTS (nhân bản)
    emotion: str = ""     # nhãn cảm xúc của câu → nghe thử ĐÚNG sắc thái sẽ render


def _resolve_voice_ref(name: str) -> str | None:
    """Đường dẫn clip giọng trong voices/ nếu hợp lệ (chặn ../ và path tuyệt đối).
    Khớp logic _vixtts_ref ở core/stages/s5_tts.py để nghe thử = đúng lúc render."""
    if not name:
        return None
    base = config.VOICES_DIR.resolve()
    p = (config.VOICES_DIR / name).resolve()
    return str(p) if p.is_relative_to(base) and p.is_file() else None


@app.post("/api/tts-preview")
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

    # engine trả phí (PLAN 11 C/D): nghe thử bằng CHÍNH dịch vụ đó (tốn phí ~1 câu)
    from core import langs, paid_tts
    eng = config.TTS_ENGINE
    if paid_tts.is_paid(eng) and not (eng in paid_tts.VI_ONLY and not langs.is_vi()):
        ok, why = paid_tts.ready(eng)
        if not ok:
            raise HTTPException(400, why)
        nam_v, nu_v = paid_tts.voice_pair(eng)
        import uuid as _u   # hàm này có "import uuid" cục bộ bên dưới → tránh UnboundLocalError
        pout = config.DATA_DIR / f"_tts_preview_{_u.uuid4().hex}.mp3"
        pout.parent.mkdir(parents=True, exist_ok=True)
        try:
            paid_tts.synth(eng, text, nu_v if body.voice == "nu" else nam_v, pout)
            data = pout.read_bytes()
        except RuntimeError as e:
            raise HTTPException(502, f"{eng} lỗi: {e}")
        finally:
            pout.unlink(missing_ok=True)
        return Response(content=data, media_type="audio/mpeg",
                        headers={"Cache-Control": "no-store"})

    # giọng theo NGÔN NGỮ ĐÍCH (#16) — nghe thử đúng giọng sẽ render
    from core import emotion as emo
    _nam, _nu = langs.edge_voices()
    voice = _nu if body.voice == "nu" else _nam
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


def _read_env() -> dict[str, str]:
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z_]+)=(.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2)
    return values


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
