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

    # Chặn sớm video CÂM (chỉ có track hình): hay gặp khi tải bằng extension bắt
    # video từ web Douyin/Bilibili — web phát hình và tiếng TÁCH RỜI nên tool chỉ
    # vớ được hình. Không có audio thì không transcribe/lồng tiếng được; báo rõ
    # thay vì để ffmpeg chết với "Output file does not contain any stream".
    if not brand._has_audio(source):
        raise RuntimeError(
            "Video KHÔNG có luồng âm thanh (file chỉ có hình — thường do tool tải "
            "từ web chỉ bắt được track hình, thiếu track tiếng). Cách sửa: dán LINK "
            "video vào ô Thêm video để app tự tải đủ hình+tiếng, hoặc tải lại file "
            "bằng yt-dlp/tool có gộp sẵn audio rồi upload lại.")

    asr_wav = job.dir / "audio_16k.wav"
    full_wav = job.dir / "audio_full.wav"

    # Audit #5: gộp thành MỘT lệnh ffmpeg nhiều output — decode video nguồn 1 lần
    # thay vì 2 (trước đây 2 lệnh riêng = 2 lần decode + 2 lần spawn). Tuỳ chọn -ac/
    # -ar/-af đứng TRƯỚC path output nào thì áp cho output đó.
    args: list[str] = ["-i", str(source)]
    if not asr_wav.exists():
        args += ["-vn", "-ac", "1", "-ar", "16000"]
        if config.DENOISE:  # nguồn chắc chắn có audio (đã chặn video câm ở trên)
            args += ["-af", _DENOISE_AF]
        args += [str(asr_wav)]
    if not full_wav.exists():
        args += ["-vn", "-ac", "2", "-ar", "44100", str(full_wav)]
    if len(args) > 2:   # có ít nhất 1 output cần tạo
        ffmpeg.run(*args)
