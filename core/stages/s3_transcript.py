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


def _ocr_segments(job: Job, crop_top: float | None = None) -> list[dict]:
    return ocr_subs.extract(job.find_source(), job.dir, crop_top=crop_top)


def _add_cuda_dll_dirs() -> None:
    """Windows: cho CTranslate2 tìm thấy cublas/cudnn (cài qua pip nvidia-*-cu12)
    mà KHÔNG cần CUDA Toolkit. Phải chạy TRƯỚC khi import faster_whisper.
    Thêm vào CẢ os.add_dll_directory LẪN os.environ['PATH'] — CTranslate2 nạp DLL
    lúc runtime không theo user-dirs nên add_dll_directory một mình KHÔNG đủ.
    No-op nếu không cài gói nvidia (chế độ CPU)."""
    import os
    if os.name != "nt":
        return
    dirs = []
    try:
        import nvidia
        for root in list(nvidia.__path__):
            for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
                b = os.path.join(root, sub, "bin")
                if os.path.isdir(b):
                    dirs.append(b)
    except Exception:
        return
    for b in dirs:
        try:
            os.add_dll_directory(b)
        except OSError:
            pass
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")


def _whisper_segments(job: Job, duration: float = 0.0) -> tuple[list[dict], str]:
    import time as _time
    from core import progress
    _add_cuda_dll_dirs()
    _t0 = _time.perf_counter()
    from faster_whisper import WhisperModel  # import muộn: model nặng

    try:
        model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE,
                             compute_type=config.WHISPER_COMPUTE)
        _dev = config.WHISPER_DEVICE
    except Exception as e:
        # GPU/CUDA không sẵn (thiếu cublas...) → CPU int8 luôn chạy được
        print(f"  Whisper {config.WHISPER_DEVICE} lỗi ({e}); fallback CPU int8")
        model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        _dev = "cpu"
    # Telemetry W-0: chi phí nạp (gồm import) — dữ liệu quyết định model host
    print(f"MODEL backend=whisper event=load seconds={_time.perf_counter() - _t0:.1f} "
          f"model={config.WHISPER_MODEL} device={_dev}")
    from core import glossary, series
    # glossary tập + glossary DÙNG CHUNG của series (nếu có) → Whisper nghe đúng tên riêng
    gloss_text = (series.glossary_for(job.series) + "\n" + job.glossary).strip()
    segments_iter, info = model.transcribe(
        str(job.dir / "audio_16k.wav"),
        language=config.WHISPER_LANGUAGE or None,
        vad_filter=True,
        initial_prompt=glossary.whisper_prompt(gloss_text),  # nghe đúng tên riêng
    )
    total = int(duration) or 1
    segments = []
    for i, seg in enumerate(segments_iter, start=1):
        text = seg.text.strip()
        if text:
            segments.append({
                "id": i, "text": text,
                "start": round(seg.start, 3), "end": round(seg.end, 3),
            })
        if i % 5 == 0:   # Whisper stream: tiến độ theo mốc thời gian đã nghe
            progress.write(job.dir, "transcribing", min(int(seg.end), total), total)
    progress.write(job.dir, "transcribing", total, total)
    return segments, info.language


def run(job: Job) -> None:
    out_path = job.dir / "transcript_zh.json"
    if out_path.exists():
        return

    mode = config.TRANSCRIPT_SOURCE
    segments: list[dict] = []
    source = language = None

    duration = _video_duration(job.find_source())
    # auto: video dài thì OCR (2fps) quá chậm → đi thẳng Whisper. "ocr" luôn OCR.
    too_long = duration > config.OCR_MAX_MINUTES * 60
    try_ocr = mode == "ocr" or (mode == "auto" and not too_long)
    if mode == "auto" and too_long:
        print(f"  Video {duration / 60:.0f} phút > {config.OCR_MAX_MINUTES} phút "
              f"→ bỏ OCR, dùng Whisper cho nhanh")

    # Audit #4 — CỬA SƠ LOẠI cho auto: dò ~16 frame trước; KHÔNG thấy dải phụ đề ổn
    # định → video không có hardsub → khỏi OCR full (từng quét cả nghìn frame rồi vứt
    # vì "quá thưa"), đi thẳng Whisper. Chỉ áp khi OCR_CROP_TOP=auto (user ép số tay
    # nghĩa là họ BIẾT video có sub ở đó → tôn trọng, không sơ loại). mode="ocr" ép
    # buộc cũng không sơ loại.
    probed_crop: float | None = None
    raw_crop = str(config.OCR_CROP_TOP).strip().lower()
    if try_ocr and mode == "auto" and raw_crop == "auto":
        probed_crop = ocr_subs.probe_crop_top(job.find_source(), job.dir)
        if probed_crop is None:
            print("  auto: dò nhanh không thấy hardsub → bỏ OCR, dùng Whisper")
            try_ocr = False

    if try_ocr:
        segments = _ocr_segments(job, crop_top=probed_crop)
        # video không có hardsub → OCR chỉ nhặt được vài mẩu rời rạc
        dense_enough = len(segments) >= max(3, duration / 30)
        if dense_enough or mode == "ocr":
            segments = segtools.clean_and_merge(segments)
            source, language = "ocr", "zh"
        else:
            segments = []
            # OCR bị loại → xóa box kẻo S8 che mờ "tự động" theo dữ liệu rác
            (job.dir / "sub_boxes.json").unlink(missing_ok=True)

    if not segments:
        if mode == "ocr":
            raise RuntimeError("OCR không tìm thấy phụ đề hardsub nào")
        segments, language = _whisper_segments(job, duration)
        source = "whisper"

    if not segments:
        raise RuntimeError("Không lấy được câu thoại nào (OCR lẫn whisper)")

    out_path.write_text(
        json.dumps({"language": language, "source": source, "segments": segments},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
