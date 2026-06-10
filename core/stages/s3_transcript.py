"""S3: lấy transcript nguồn → transcript_zh.json [{id, text, start, end}].

Hai nguồn, chọn qua TRANSCRIPT_SOURCE:
- "ocr"     : đọc phụ đề hardsub bằng RapidOCR (chính xác nhất với donghua)
- "whisper" : faster-whisper ASR (video không có phụ đề gắn cứng)
- "auto"    : OCR trước; nếu kết quả quá thưa (video không có hardsub)
              thì tự fallback sang whisper.
"""
from __future__ import annotations

import json
import subprocess

import config
from core import ocr_subs, segtools
from core.job import Job


def _video_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _ocr_segments(job: Job) -> list[dict]:
    return ocr_subs.extract(job.find_source(), job.dir)


def _whisper_segments(job: Job) -> tuple[list[dict], str]:
    from faster_whisper import WhisperModel  # import muộn: model nặng

    model = WhisperModel(config.WHISPER_MODEL, device="auto", compute_type="int8")
    segments_iter, info = model.transcribe(
        str(job.dir / "audio_16k.wav"),
        language=config.WHISPER_LANGUAGE or None,
        vad_filter=True,
    )
    segments = []
    for i, seg in enumerate(segments_iter, start=1):
        text = seg.text.strip()
        if text:
            segments.append({
                "id": i, "text": text,
                "start": round(seg.start, 3), "end": round(seg.end, 3),
            })
    return segments, info.language


def run(job: Job) -> None:
    out_path = job.dir / "transcript_zh.json"
    if out_path.exists():
        return

    mode = config.TRANSCRIPT_SOURCE
    segments: list[dict] = []
    source = language = None

    if mode in ("auto", "ocr"):
        segments = _ocr_segments(job)
        # video không có hardsub → OCR chỉ nhặt được vài mẩu rời rạc
        duration = _video_duration(job.find_source())
        dense_enough = len(segments) >= max(3, duration / 30)
        if dense_enough or mode == "ocr":
            segments = segtools.clean_and_merge(segments)
            source, language = "ocr", "zh"
        else:
            segments = []

    if not segments:
        if mode == "ocr":
            raise RuntimeError("OCR không tìm thấy phụ đề hardsub nào")
        segments, language = _whisper_segments(job)
        source = "whisper"

    if not segments:
        raise RuntimeError("Không lấy được câu thoại nào (OCR lẫn whisper)")

    out_path.write_text(
        json.dumps({"language": language, "source": source, "segments": segments},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
