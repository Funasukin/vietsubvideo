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


def _trim_silence(a: np.ndarray, rate: int, thresh: int = 300, pad_ms: int = 40) -> np.ndarray:
    """Cắt khoảng LẶNG 2 đầu file TTS (edge hay đệm ~0.3–0.7s im lặng cuối file) —
    hết "tràn giả" do đuôi câm và giọng không đè rớt sang câu sau. Giữ pad_ms đệm."""
    if not len(a):
        return a
    nz = np.nonzero(np.abs(a).max(axis=1) > thresh)[0]
    if not len(nz):
        return a
    pad = int(pad_ms / 1000 * rate)
    return a[max(0, int(nz[0]) - pad): min(len(a), int(nz[-1]) + pad)]


def _load_voice(path, rate: int) -> np.ndarray:
    """Decode mp3/wav TTS → mảng int16 (n, 2) cùng sample rate với nền, đã cắt lặng 2 đầu."""
    seg = AudioSegment.from_file(path).set_frame_rate(rate).set_channels(2)
    a = np.array(seg.get_array_of_samples(), dtype=np.int16).reshape(-1, 2)
    return _trim_silence(a, rate)


def run(job: Job) -> None:
    out_path = job.dir / "dubbed_audio.wav"
    if out_path.exists():
        return

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    # bỏ câu rỗng và câu bị "Mute" → không chèn giọng Việt, để nguyên tiếng gốc chỗ đó
    segments = [s for s in data["segments"] if s["text_vi"].strip() and not s.get("mute")]
    bed, rate = audio_np.read_wav(job.dir / "ducked.wav")
    total = len(bed)

    # Ranh giới kế của mỗi segment = start câu NGAY SAU theo thời gian, TÍNH CẢ câu mute.
    # Nhờ vậy slot câu dub kết thúc trước câu kế (kể cả câu mute) → giọng Việt không tràn
    # sang vùng giữ tiếng gốc của câu mute.
    full = sorted(data["segments"], key=lambda s: s["start"])
    next_bound = {}
    for k, s in enumerate(full):
        next_bound[s["id"]] = int(full[k + 1]["start"] * rate) if k + 1 < len(full) else total

    warnings = []
    for i, seg in enumerate(segments):
        mp3 = job.dir / "tts" / f"seg_{seg['id']:04d}.mp3"
        voice = _load_voice(mp3, rate)

        start = int(seg["start"] * rate)
        next_start = next_bound.get(seg["id"], total)
        slot = max(int(0.3 * rate), next_start - start)

        if len(voice) > slot:
            factor = min(config.MAX_SPEEDUP, len(voice) / slot)
            sped = job.dir / "tts" / f"seg_{seg['id']:04d}_sped.wav"
            # LUÔN tạo lại: factor phụ thuộc slot + mp3 hiện tại — bản _sped của lần
            # chạy trước (text/slot khác) mà tái dùng là sai tốc độ âm thầm
            sped.unlink(missing_ok=True)
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
