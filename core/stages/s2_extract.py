"""S2: tách audio từ video gốc.

- audio_16k.wav : mono 16kHz cho ASR (S3)
- audio_full.wav: stereo 44.1kHz làm nền cho duck/mix (S6, S7)
"""
from core import ffmpeg
from core.job import Job


def run(job: Job) -> None:
    source = job.find_source()
    if source is None:
        raise RuntimeError("Không thấy video nguồn (S1 chưa chạy?)")

    asr_wav = job.dir / "audio_16k.wav"
    full_wav = job.dir / "audio_full.wav"

    if not asr_wav.exists():
        ffmpeg.run("-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(asr_wav))
    if not full_wav.exists():
        ffmpeg.run("-i", str(source), "-vn", "-ac", "2", "-ar", "44100", str(full_wav))
