"""S7: mix giọng TTS lên nền ducked.wav → dubbed_audio.wav.

Mỗi segment TTS đặt vào đúng timestamp gốc. Nếu audio TTS dài hơn slot
(khoảng trống đến câu tiếp theo) thì tăng tốc bằng ffmpeg atempo, tối đa
MAX_SPEEDUP; vượt nữa thì chấp nhận tràn và ghi cảnh báo vào mix_report.json.

Cộng trực tiếp trên mảng numpy (pydub.overlay copy cả track mỗi lần gọi —
quá chậm với video dài). pydub chỉ còn dùng decode/resample file TTS nhỏ.
"""
from __future__ import annotations

import json

import numpy as np
from pydub import AudioSegment

import config
from core import audio_np, ffmpeg
from core.job import Job


def _load_voice(path, rate: int) -> np.ndarray:
    """Decode mp3/wav TTS → mảng int16 (n, 2) cùng sample rate với nền."""
    seg = AudioSegment.from_file(path).set_frame_rate(rate).set_channels(2)
    return np.array(seg.get_array_of_samples(), dtype=np.int16).reshape(-1, 2)


def run(job: Job) -> None:
    out_path = job.dir / "dubbed_audio.wav"
    if out_path.exists():
        return

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    segments = [s for s in data["segments"] if s["text_vi"].strip()]
    bed, rate = audio_np.read_wav(job.dir / "ducked.wav")
    total = len(bed)

    warnings = []
    for i, seg in enumerate(segments):
        mp3 = job.dir / "tts" / f"seg_{seg['id']:04d}.mp3"
        voice = _load_voice(mp3, rate)

        start = int(seg["start"] * rate)
        next_start = (int(segments[i + 1]["start"] * rate)
                      if i + 1 < len(segments) else total)
        slot = max(int(0.3 * rate), next_start - start)

        if len(voice) > slot:
            factor = min(config.MAX_SPEEDUP, len(voice) / slot)
            sped = job.dir / "tts" / f"seg_{seg['id']:04d}_sped.wav"
            if not sped.exists():
                ffmpeg.run("-i", str(mp3), "-filter:a", f"atempo={factor:.4f}", str(sped))
            voice = _load_voice(sped, rate)
            if len(voice) > slot:
                warnings.append({
                    "id": seg["id"],
                    "overflow_ms": int((len(voice) - slot) * 1000 / rate),
                    "text_vi": seg["text_vi"],
                })

        end = min(total, start + len(voice))
        if end <= start:
            continue
        mixed = bed[start:end].astype(np.int32) + voice[: end - start].astype(np.int32)
        bed[start:end] = np.clip(mixed, -32768, 32767).astype(np.int16)

    audio_np.write_wav(out_path, bed, rate)
    (job.dir / "mix_report.json").write_text(
        json.dumps({"segments": len(segments), "overflow_warnings": warnings},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
