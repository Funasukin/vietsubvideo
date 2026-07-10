"""Helper dùng CHUNG giữa server.py và các module route (#16 giai đoạn 2).
Tách NGUYÊN VĂN từ webui/server.py — hành vi không đổi."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import HTTPException

import config
from webui import worker
from webui.worker import _active, _lock

_JOB_ID_RE = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{6}$")


def _check_job_id(job_id: str) -> None:
    """Chặn path traversal: job_id phải đúng định dạng Job.create sinh ra
    (vd 20260614_014525_56d6d6) — loại bỏ '..', '/', '\\', đường dẫn tuyệt đối."""
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(404, "Không có job này")



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
        state["queued"] = state["id"] in _active and state["id"] != worker._running_id
        state["running"] = state["id"] == worker._running_id

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


