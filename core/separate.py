"""Tách giọng gốc khỏi nhạc+SFX bằng demucs (GPU) — để lồng tiếng GIỮ nhạc nền
và hiệu ứng, thay vì hạ nhỏ cả audio gốc (giọng Trung vẫn văng vẳng).

Cần FFmpeg shared (cho torchcodec ghi wav) + ffmpeg.exe trong PATH (demucs đọc).
Lỗi bất kỳ → caller (s6) bắt và quay về cách duck cũ.
"""
from __future__ import annotations

import os
import shutil

import config
from core.job import Job


def _setup_dll_dirs() -> None:
    """torchcodec (torchaudio IO của demucs) cần FFmpeg shared trên Windows."""
    if os.name != "nt":
        return
    binp = config.FFMPEG_SHARED_BIN
    if binp and os.path.isdir(binp):
        try:
            os.add_dll_directory(binp)
        except OSError:
            pass
        os.environ["PATH"] = binp + os.pathsep + os.environ.get("PATH", "")


def no_vocals(job: Job) -> str:
    """Chạy demucs trên audio_full.wav → trả path no_vocals.wav (nhạc+SFX). Cache."""
    out = job.dir / "no_vocals.wav"
    if out.exists():
        return str(out)
    src = job.dir / "audio_full.wav"
    if not src.exists():
        raise RuntimeError("Thiếu audio_full.wav để tách")
    _setup_dll_dirs()

    outroot = job.dir / "_demucs"
    import time as _time
    _t0 = _time.perf_counter()
    from demucs.separate import main
    main(["--two-stems=vocals", "-d", config.VIXTTS_DEVICE,
          "-o", str(outroot), str(src)])
    # Telemetry W-0: load + tách gộp chung (demucs gọi qua CLI, chưa tách được load)
    print(f"MODEL backend=demucs event=run seconds={_time.perf_counter() - _t0:.1f} "
          f"device={config.VIXTTS_DEVICE}")

    produced = outroot / "htdemucs" / src.stem / "no_vocals.wav"
    if not produced.exists():
        raise RuntimeError("demucs không tạo được no_vocals.wav")
    shutil.move(str(produced), str(out))
    # V14 audit giọng (phát hiện của Gemini): GIỮ lại vocals.wav (giọng gốc sạch) —
    # trước đây rmtree xoá luôn, muốn đo prosody trên vocal sạch cũng không có dữ
    # liệu. /api/cleanup đã có sẵn dòng dọn file này nên không lo phình đĩa.
    # File PHỤ TRỢ — lỗi (đích đang bị Windows khoá khi phát...) chỉ được print,
    # tuyệt đối không ném lên kẻo s6 tưởng "demucs lỗi" mà vứt no_vocals vừa tách
    # (review đối kháng bắt được: mất trắng nhiều phút GPU vì một file phụ).
    try:
        voc = outroot / "htdemucs" / src.stem / "vocals.wav"
        if voc.exists():
            os.replace(str(voc), str(job.dir / "vocals.wav"))
    except OSError as e:
        print(f"  không giữ được vocals.wav ({e}) — bỏ qua, không ảnh hưởng tách nền")
    shutil.rmtree(outroot, ignore_errors=True)
    return str(out)
