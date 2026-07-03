"""S2: tách audio từ video gốc.

- audio_16k.wav : mono 16kHz cho ASR (S3) — tuỳ chọn khử ồn (config.DENOISE)
- audio_full.wav: stereo 44.1kHz làm nền cho duck/mix (S6, S7) — GIỮ NGUYÊN, không lọc
"""
import config
from core import brand, ffmpeg
from core.job import Job

# Chuỗi lọc cho ASR khi bật khử ồn: cắt ù tần thấp + khử ồn phổ (afftdn) + giới hạn
# dải tiếng nói. Chỉ áp cho bản 16k để Whisper nghe rõ; KHÔNG dùng cho bản mix.
_DENOISE_AF = "highpass=f=80,afftdn=nf=-25,lowpass=f=7500,dynaudnorm"


def run(job: Job) -> None:
    source = job.find_source()
    if source is None:
        raise RuntimeError("Không thấy video nguồn (S1 chưa chạy?)")

    asr_wav = job.dir / "audio_16k.wav"
    full_wav = job.dir / "audio_full.wav"

    if not asr_wav.exists():
        args = ["-i", str(source), "-vn", "-ac", "1", "-ar", "16000"]
        # chỉ khử ồn khi nguồn CÓ audio (afftdn nổ nếu không có luồng audio)
        if config.DENOISE and brand._has_audio(source):
            args += ["-af", _DENOISE_AF]
        ffmpeg.run(*args, str(asr_wav))
    if not full_wav.exists():
        ffmpeg.run("-i", str(source), "-vn", "-ac", "2", "-ar", "44100", str(full_wav))
