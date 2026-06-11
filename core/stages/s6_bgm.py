"""S6: tạo nền audio → ducked.wav.

Duck mode: hạ DUCK_GAIN_DB âm lượng audio gốc trong các khoảng có thoại
(theo timestamp transcript) để giọng TTS nổi lên, ngoài khoảng đó giữ nguyên
nhạc nền/hiệu ứng. Thao tác numpy trực tiếp trên PCM (nhanh với video dài).
Phase 4 sẽ thay bằng Demucs tách hẳn vocal khi có GPU.
"""
from __future__ import annotations

import json

import config
from core import audio_np
from core.job import Job

# nới mỗi đầu một chút để duck không cắt phụ âm đầu/cuối
PAD_MS = 120


def run(job: Job) -> None:
    out_path = job.dir / "ducked.wav"
    if out_path.exists():
        return

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    bed, rate = audio_np.read_wav(job.dir / "audio_full.wav")
    total = len(bed)
    gain = 10 ** (config.DUCK_GAIN_DB / 20)

    def to_idx(ms: float) -> int:
        return max(0, min(total, int(ms * rate / 1000)))

    # gộp các khoảng thoại chồng lấn thành danh sách [start_idx, end_idx]
    windows: list[list[int]] = []
    for seg in data["segments"]:
        s = to_idx(seg["start"] * 1000 - PAD_MS)
        e = to_idx(seg["end"] * 1000 + PAD_MS)
        if windows and s <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], e)
        else:
            windows.append([s, e])

    for s, e in windows:
        bed[s:e] = (bed[s:e].astype("float32") * gain).astype("int16")

    audio_np.write_wav(out_path, bed, rate)
