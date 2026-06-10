"""S6: tạo nền audio → ducked.wav.

Duck mode: hạ DUCK_GAIN_DB âm lượng audio gốc trong các khoảng có thoại
(theo timestamp transcript) để giọng TTS nổi lên, ngoài khoảng đó giữ nguyên
nhạc nền/hiệu ứng. Phase 4 sẽ thay bằng Demucs tách hẳn vocal khi có GPU.
"""
from __future__ import annotations

import json

from pydub import AudioSegment

import config
from core.job import Job

# nới mỗi đầu một chút để duck không cắt phụ âm đầu/cuối
PAD_MS = 120


def run(job: Job) -> None:
    out_path = job.dir / "ducked.wav"
    if out_path.exists():
        return

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    bed = AudioSegment.from_wav(job.dir / "audio_full.wav")
    total = len(bed)

    # gộp các khoảng thoại chồng lấn thành danh sách [start_ms, end_ms]
    windows: list[list[int]] = []
    for seg in data["segments"]:
        s = max(0, int(seg["start"] * 1000) - PAD_MS)
        e = min(total, int(seg["end"] * 1000) + PAD_MS)
        if windows and s <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], e)
        else:
            windows.append([s, e])

    pieces = []
    cursor = 0
    for s, e in windows:
        if cursor < s:
            pieces.append(bed[cursor:s])
        pieces.append(bed[s:e].apply_gain(config.DUCK_GAIN_DB))
        cursor = e
    if cursor < total:
        pieces.append(bed[cursor:])

    ducked = sum(pieces[1:], pieces[0]) if pieces else bed
    ducked.export(out_path, format="wav")
