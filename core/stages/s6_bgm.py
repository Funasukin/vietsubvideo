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
    no_vocals_path = job.dir / "no_vocals.wav"
    # Âm lượng nền: override theo JOB (chỉnh từ editor) thắng cấu hình chung
    gain_db = job.bed_gain_db if job.bed_gain_db is not None else config.DUCK_GAIN_DB
    # ducked.wav phải KHỚP mode hiện tại (demucs? hạ đều hay theo thoại? gain nào?) —
    # đổi bất kỳ tham số nào rồi chạy lại là dựng lại nền, không kẹt bản cũ.
    mode = f"{int(config.KEEP_BGM)}:{'all' if config.DUCK_ALL else 'speech'}:{gain_db:g}"
    marker = job.dir / "ducked.mode"
    try:
        if out_path.exists() and marker.read_text(encoding="utf-8") == mode:
            return
    except OSError:
        pass   # thiếu marker (job cũ) → dựng lại một lần cho chắc

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    # KEEP_BGM: tách giọng gốc bằng demucs → nền chỉ còn nhạc+SFX (sạch tiếng Trung).
    # Best-effort: gồm CẢ lúc đọc kết quả; bất kỳ lỗi nào (kể cả SystemExit do demucs
    # gọi sys.exit khi thiếu ffmpeg/model) → quay về duck audio gốc.
    bed = rate = None
    if config.KEEP_BGM:
        try:
            from core import separate
            bed, rate = audio_np.read_wav(separate.no_vocals(job))
        except (Exception, SystemExit) as e:
            print(f"  demucs lỗi ({e}); duck audio gốc thay thế")
            bed = None
    if bed is None:
        no_vocals_path.unlink(missing_ok=True)  # marker: nền = audio gốc (duck)
        bed, rate = audio_np.read_wav(job.dir / "audio_full.wav")
    total = len(bed)
    gain = 10 ** (gain_db / 20)

    if config.DUCK_ALL:
        # Hạ ĐỀU suốt video: âm gốc nhỏ ổn định, không "bơm" to-nhỏ theo thoại
        # (kiểu bơm khiến nhạc nền lúc thoại nhỏ lúc trống thoại to gây khó chịu)
        bed = (bed.astype("float32") * gain).astype("int16")
    else:
        def to_idx(ms: float) -> int:
            return max(0, min(total, int(ms * rate / 1000)))

        # gộp các khoảng thoại chồng lấn thành danh sách [start_idx, end_idx]. Chỉ hạ nhạc
        # ở câu CÓ lồng tiếng Việt — bỏ qua câu rỗng và câu bị "Mute" (giữ nguyên tiếng gốc).
        windows: list[list[int]] = []
        for seg in data["segments"]:
            if not seg.get("text_vi", "").strip() or seg.get("mute"):
                continue
            s = to_idx(seg["start"] * 1000 - PAD_MS)
            e = to_idx(seg["end"] * 1000 + PAD_MS)
            if windows and s <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], e)
            else:
                windows.append([s, e])

        for s, e in windows:
            bed[s:e] = (bed[s:e].astype("float32") * gain).astype("int16")

    audio_np.write_wav(out_path, bed, rate)
    marker.write_text(mode, encoding="utf-8")
