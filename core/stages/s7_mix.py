"""S7: mix giọng TTS lên nền ducked.wav → dubbed_audio.wav.

Mỗi segment TTS đặt vào đúng timestamp gốc. Nếu audio TTS dài hơn slot
(khoảng trống đến câu tiếp theo) thì tăng tốc bằng ffmpeg atempo, tối đa
MAX_SPEEDUP; vượt nữa thì chấp nhận tràn và ghi cảnh báo vào mix_report.json.
"""
from __future__ import annotations

import json

from pydub import AudioSegment

import config
from core import ffmpeg
from core.job import Job


def run(job: Job) -> None:
    out_path = job.dir / "dubbed_audio.wav"
    if out_path.exists():
        return

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    segments = [s for s in data["segments"] if s["text_vi"].strip()]
    bed = AudioSegment.from_wav(job.dir / "ducked.wav")
    total_ms = len(bed)

    warnings = []
    for i, seg in enumerate(segments):
        mp3 = job.dir / "tts" / f"seg_{seg['id']:04d}.mp3"
        voice = AudioSegment.from_file(mp3)

        start_ms = int(seg["start"] * 1000)
        next_start_ms = (int(segments[i + 1]["start"] * 1000)
                         if i + 1 < len(segments) else total_ms)
        slot_ms = max(300, next_start_ms - start_ms)

        if len(voice) > slot_ms:
            factor = min(config.MAX_SPEEDUP, len(voice) / slot_ms)
            sped = job.dir / "tts" / f"seg_{seg['id']:04d}_sped.wav"
            if not sped.exists():
                ffmpeg.run("-i", str(mp3), "-filter:a", f"atempo={factor:.4f}", str(sped))
            voice = AudioSegment.from_wav(sped)
            if len(voice) > slot_ms:
                warnings.append({
                    "id": seg["id"],
                    "overflow_ms": len(voice) - slot_ms,
                    "text_vi": seg["text_vi"],
                })

        bed = bed.overlay(voice, position=start_ms)

    bed.export(out_path, format="wav")
    (job.dir / "mix_report.json").write_text(
        json.dumps({"segments": len(segments), "overflow_warnings": warnings},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
