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


def _win_sig(segments: list[dict]) -> str:
    """Vân tay CỬA SỔ THOẠI (câu có lồng tiếng, mốc thời gian) — bug #13 audit:
    marker cũ không chứa phần này nên dịch lại/đổi Mute xong stage bgm chạy lại
    mà marker vẫn khớp → nền duck theo cửa sổ CŨ (hạ nhạc sai chỗ) không ai hay."""
    import hashlib
    key = ";".join(f"{s['start']:.2f}-{s['end']:.2f}" for s in segments
                   if s.get("text_vi", "").strip() and not s.get("mute"))
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:10]


def run(job: Job) -> None:
    out_path = job.dir / "ducked.wav"
    no_vocals_path = job.dir / "no_vocals.wav"
    # Âm lượng nền: override theo JOB (chỉnh từ editor) thắng cấu hình chung
    gain_db = job.bed_gain_db if job.bed_gain_db is not None else config.DUCK_GAIN_DB
    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    # ducked.wav phải KHỚP trạng thái hiện tại: mode + gain + CỬA SỔ THOẠI (đổi
    # transcript/Mute là vân tay lệch) — đổi bất kỳ thứ gì là dựng lại, không kẹt bản cũ.
    mode = (f"{int(config.KEEP_BGM)}:{'all' if config.DUCK_ALL else 'speech'}"
            f":{gain_db:g}:w{_win_sig(data['segments'])}")
    marker = job.dir / "ducked.mode"
    try:
        old = marker.read_text(encoding="utf-8")
        # đuôi ':src=' ghi NGUỒN NỀN THẬT của lần dựng trước (bug #13): muốn demucs
        # mà lần trước rơi về audio gốc (GPU lỗi...) → phải thử tách lại, không tái dùng
        if (out_path.exists() and old.startswith(mode + ":src=")
                and not (config.KEEP_BGM and old.endswith(":src=full"))):
            return
    except OSError:
        pass   # thiếu marker (job cũ) → dựng lại một lần cho chắc

    # KEEP_BGM: tách giọng gốc bằng demucs → nền chỉ còn nhạc+SFX (sạch tiếng Trung).
    # Best-effort: gồm CẢ lúc đọc kết quả; bất kỳ lỗi nào (kể cả SystemExit do demucs
    # gọi sys.exit khi thiếu ffmpeg/model) → quay về duck audio gốc.
    bed = rate = None
    src_tag = "full"
    if config.KEEP_BGM:
        try:
            from core import separate
            bed, rate = audio_np.read_wav(separate.no_vocals(job))
            src_tag = "nv"
        except (Exception, SystemExit) as e:
            print(f"  demucs lỗi ({e}); duck audio gốc thay thế")
            bed = None
    if bed is None:
        no_vocals_path.unlink(missing_ok=True)  # nền = audio gốc (duck)
        bed, rate = audio_np.read_wav(job.dir / "audio_full.wav")
    # Hạ đều (DUCK_ALL) hoặc theo cửa sổ thoại — logic ở apply_duck (dùng chung
    # với /mix-preview để bản nghe thử 10s dựng ĐÚNG như render thật)
    bed = apply_duck(bed, rate, data["segments"], gain_db, config.DUCK_ALL)

    audio_np.write_wav(out_path, bed, rate)
    marker.write_text(mode + ":src=" + src_tag, encoding="utf-8")
