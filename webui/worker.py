"""Hàng đợi + vòng đời tiến trình job (#16 tách monolith, giai đoạn 1).

Tách NGUYÊN VĂN từ webui/server.py — hành vi không đổi: 1 worker thread chạy job
tuần tự, mỗi job là 1 subprocess `cli.py --resume <id>` (server restart không hỏng
job — checkpoint theo stage lo phần đó); hủy = kill cây tiến trình; override
per-job truyền qua env FLOWAPP_JOB_OVERRIDES.

Quy ước dùng từ server.py:
- Các OBJECT dùng chung (_pending/_lock/_active/_cancel/_retries) import trực
  tiếp được — chúng chỉ bị MUTATE, không bao giờ bị gán lại.
- Các biến VÔ HƯỚNG bị gán lại trong worker (_running_id, _current_proc,
  _queue_paused) phải đọc/ghi qua module: `worker._running_id` — import from
  sẽ dính bản cũ.
Đây cũng là chỗ model-host manager (W-2) sẽ cắm vào nếu telemetry nói có lãi.
"""
from __future__ import annotations

import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import time

from fastapi import HTTPException

import config
from core.job import Job
from webui.envfile import read_env

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


def _reserve_job(job_id: str) -> None:
    """Bug #12 (audit): GIỮ CHỖ job trong _active TRƯỚC khi endpoint sửa file của nó
    (save_segments/rerender xoá transcript/mp3/final giữa chừng). Trước đây chỉ check
    `in _active` rồi buông lock — 'Chạy tất cả'/resume có thể xếp job chạy ĐÚNG LÚC
    đang xoá dở → cli đọc dữ liệu nửa vời. Caller PHẢI kết thúc bằng
    _enqueue_reserved() (thành công) hoặc _release_job() (mọi đường lỗi/không đổi)."""
    with _lock:
        if job_id in _active or job_id in _cancel:
            raise HTTPException(409, "Job đang chạy hoặc đã trong hàng đợi")
        _active.add(job_id)


def _release_job(job_id: str) -> None:
    with _lock:
        _active.discard(job_id)


def _enqueue_reserved(job_id: str) -> None:
    """Xếp job ĐÃ giữ chỗ (_reserve_job) vào hàng — như _enqueue nhưng bỏ bước
    check/add _active (đã giữ từ trước khi sửa file)."""
    try:
        from core import vixtts
        vixtts.unload()
    except Exception:
        pass
    _pending.put(job_id)


def _auto_retry_limit() -> int:
    """Đọc AUTO_RETRY tươi từ .env mỗi lần (sửa từ UI có hiệu lực ngay, khỏi restart)."""
    try:
        return int(read_env().get("AUTO_RETRY", config.AUTO_RETRY))
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
        # Override cấu hình THEO JOB (editor "⚙️ Tùy chọn video này"): truyền qua env
        # FLOWAPP_JOB_OVERRIDES — config.py của tiến trình con áp SAU .env.
        child_env = None
        try:
            _ov = Job.load(job_id).env_overrides or {}
            # STRETCH_SHORT đã gỡ khỏi app (đợt T) — job cũ còn override thì lọc
            # bỏ tại đây cho tự sạch, khỏi kích cảnh báo config.py mỗi lần chạy
            _ov.pop("STRETCH_SHORT", None)
            if _ov:
                child_env = dict(os.environ)
                child_env["FLOWAPP_JOB_OVERRIDES"] = json.dumps(_ov)
        except Exception:
            pass
        proc = subprocess.Popen(
            [sys.executable, str(config.BASE_DIR / "cli.py"), "--resume", job_id],
            cwd=config.BASE_DIR, env=child_env,
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
