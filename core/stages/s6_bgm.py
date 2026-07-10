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


def apply_duck(bed, rate: int, segments: list[dict], gain_db: float,
               duck_all: bool, t0_s: float = 0.0):
    """Hạ nền theo mode lên mảng bed (int16, sửa TẠI CHỖ + trả về) — logic DUY NHẤT
    dùng bởi run() (cả track, t0_s=0) và /mix-preview (slice, t0_s = mốc cắt).
    duck_all=True: hạ đều; False: chỉ hạ trong cửa sổ thoại (±PAD_MS)."""
    import numpy as np
    total = len(bed)
    gain = 10 ** (gain_db / 20)
    if duck_all:
        return (bed.astype(np.float32) * gain).astype(np.int16)

    def to_idx(ms: float) -> int:
        return max(0, min(total, int(ms * rate / 1000)))

    # gộp các khoảng thoại chồng lấn thành [start_idx, end_idx]. Chỉ hạ nhạc ở câu
    # CÓ lồng tiếng Việt — bỏ câu rỗng và câu bị "Mute" (giữ nguyên tiếng gốc).
    windows: list[list[int]] = []
    for seg in segments:
        if not seg.get("text_vi", "").strip() or seg.get("mute"):
            continue
        s = to_idx((seg["start"] - t0_s) * 1000 - PAD_MS)
        e = to_idx((seg["end"] - t0_s) * 1000 + PAD_MS)
        if e <= s:
            continue
        if windows and s <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], e)
        else:
            windows.append([s, e])
    for s, e in windows:
        bed[s:e] = (bed[s:e].astype(np.float32) * gain).astype(np.int16)
    return bed


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
    # Hạ đều (DUCK_ALL) hoặc theo cửa sổ thoại — logic ở apply_duck (dùng chung
    # với /mix-preview để bản nghe thử 10s dựng ĐÚNG như render thật)
    bed = apply_duck(bed, rate, data["segments"], gain_db, config.DUCK_ALL)

    audio_np.write_wav(out_path, bed, rate)
    marker.write_text(mode, encoding="utf-8")
