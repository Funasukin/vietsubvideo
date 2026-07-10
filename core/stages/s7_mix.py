"""S7: mix giọng TTS lên nền ducked.wav → dubbed_audio.wav.

Mỗi segment TTS đặt vào đúng timestamp gốc. Đợt B audit giọng (trọng tài thời
lượng — core/duration.py): S5 đã fit bằng engine trong ngân sách MAX_SPEEDUP;
S7 chỉ còn atempo phần dư trong ngân sách CÒN LẠI (tích engine×atempo ≤ núm),
và câu vẫn vượt slot sau tất cả thì FADE-OUT rồi cắt tại biên — không bao giờ
đè giọng sang câu kế nữa (trước đây tràn tới 2.2s, hai giọng Việt chồng nhau).

Cộng trực tiếp trên mảng numpy (pydub.overlay copy cả track mỗi lần gọi —
quá chậm với video dài). pydub chỉ còn dùng decode/resample file TTS nhỏ.
"""
from __future__ import annotations

import json

import numpy as np
from pydub import AudioSegment

import config
from core import audio_np, duration, ffmpeg
from core.job import Job


def _load_voice(path, rate: int) -> np.ndarray:
    """Decode mp3/wav TTS → mảng int16 (n, 2) cùng sample rate với nền, đã cắt lặng
    2 đầu bằng THƯỚC CHUNG duration.trim_silence — cùng con số S5 đã đo khi fit."""
    seg = AudioSegment.from_file(path).set_frame_rate(rate).set_channels(2)
    a = np.array(seg.get_array_of_samples(), dtype=np.int16).reshape(-1, 2)
    return duration.trim_silence(a, rate)


def _fade_cut(a: np.ndarray, n_keep: int, rate: int, fade_ms: int = 100) -> np.ndarray:
    """Cắt mảng về n_keep mẫu, fade-out fade_ms cuối cho êm (không 'bụp')."""
    n = min(len(a), n_keep)
    a = a[:n].copy()
    f = min(n, int(fade_ms / 1000 * rate))
    if f > 0:
        ramp = np.linspace(1.0, 0.0, f, dtype=np.float32)[:, None]
        a[n - f:] = (a[n - f:].astype(np.float32) * ramp).astype(np.int16)
    return a


_VOICE_TARGET_DBFS = -16.0   # RMS giọng đọc sau chuẩn hoá — nổi ~+12dB trên nền -20dB
_VOICE_GAIN_CLAMP = 6.0      # chỉnh tối đa ±6dB — không thổi phồng câu cố tình nói nhỏ


def _norm_voice(a: np.ndarray) -> tuple[np.ndarray, float]:
    """Chuẩn hoá RMS giọng về _VOICE_TARGET_DBFS (kẹp ±6dB) → (mảng mới, gain dB đã áp).
    Sửa 2 vấn đề đo được trên job thật: giọng TTS chỉ nổi hơn nền ~+6dB (bị nhạc/âm
    gốc át — user phàn nàn) và câu to câu nhỏ lệch nhau ~2.5dB giữa các segment."""
    if not len(a):
        return a, 0.0
    rms = float(np.sqrt((a.astype(np.float64) ** 2).mean()))
    if rms < 1:   # câu câm/lặng — không chỉnh
        return a, 0.0
    cur_db = 20 * np.log10(rms / 32768)
    gain_db = float(np.clip(_VOICE_TARGET_DBFS - cur_db, -_VOICE_GAIN_CLAMP, _VOICE_GAIN_CLAMP))
    if abs(gain_db) < 0.1:
        return a, 0.0
    g = 10 ** (gain_db / 20)
    out = np.clip(a.astype(np.float32) * g, -32768, 32767).astype(np.int16)
    return out, round(gain_db, 1)


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

    def _ms(n_samples: int) -> int:
        return int(n_samples * 1000 / rate)

    # Sổ đo của S5 (trọng tài): engine đã tiêu bao nhiêu ngân sách nén cho từng câu.
    # Job cũ không có sổ → engine_speed=1.0, S7 dùng trọn núm như trước.
    fit = duration.load_report(job.dir)
    fade_n = int(duration.FADE_GUARD_S * rate)

    warnings = []
    detail = []   # V13 (audit giọng): số đo per-câu để editor tô cảnh báo + so trước/sau
    for i, seg in enumerate(segments):
        mp3 = job.dir / "tts" / f"seg_{seg['id']:04d}.mp3"
        voice = _load_voice(mp3, rate)

        start = int(seg["start"] * rate)
        next_start = next_bound.get(seg["id"], total)
        slot = max(int(0.3 * rate), next_start - start)
        limit = max(int(0.3 * rate), slot - fade_n)   # chừa chỗ fade ở biên
        trimmed_ms = _ms(len(voice))
        espeed = float(fit.get(str(seg["id"]), {}).get("engine_speed") or 1.0)
        factor = 1.0

        mouth = max(1, int((seg["end"] - seg["start"]) * rate))
        if len(voice) > limit * duration.TOL:
            # ngân sách CÒN LẠI sau phần engine đã nén ở S5 — tích ≤ MAX_SPEEDUP
            allowed = duration.budget_left(espeed)
            factor = min(allowed, len(voice) / limit)
            if factor > 1.004:
                sped = job.dir / "tts" / f"seg_{seg['id']:04d}_sped.wav"
                # LUÔN tạo lại: factor phụ thuộc slot + mp3 hiện tại — bản _sped của lần
                # chạy trước (text/slot khác) mà tái dùng là sai tốc độ âm thầm
                sped.unlink(missing_ok=True)
                ffmpeg.run("-i", str(mp3), "-filter:a", f"atempo={factor:.4f}", str(sped))
                voice = _load_voice(sped, rate)
            else:
                factor = 1.0
        elif (config.STRETCH_SHORT and len(voice) < int(0.7 * slot)
                and len(voice) < mouth):
            # V9 (mặc định TẮT): đọc xong quá sớm → kéo CHẬM nhẹ về phía độ dài MIỆNG
            # (không phải slot — slot dư thường là khoảng lặng tự nhiên của phim).
            # atempo < 1 giữ cao độ; sàn 0.92 — chậm hơn nghe rề.
            factor = max(0.92, len(voice) / min(mouth, limit))
            if factor < 0.996:
                sped = job.dir / "tts" / f"seg_{seg['id']:04d}_sped.wav"
                sped.unlink(missing_ok=True)
                ffmpeg.run("-i", str(mp3), "-filter:a", f"atempo={factor:.4f}", str(sped))
                voice = _load_voice(sped, rate)
            else:
                factor = 1.0

        # chuẩn hoá âm lượng giọng SAU mọi xử lý độ dài, TRƯỚC khi đặt lên nền
        voice, vgain = _norm_voice(voice)

        clipped_ms = 0
        if len(voice) > slot:
            # hết ngân sách mà vẫn vượt biên → fade-out rồi cắt tại slot: KHÔNG đè
            # câu kế / thoại gốc chưa duck như trước (V4). Ghi lại để editor cảnh báo.
            clipped_ms = _ms(len(voice) - slot)
            voice = _fade_cut(voice, slot, rate)
            warnings.append({
                "id": seg["id"],
                "overflow_ms": clipped_ms,   # giữ tên key cũ cho UI/QC — giờ = bị cắt
                "text_vi": seg["text_vi"],
            })

        detail.append({
            "id": seg["id"],
            "trimmed_ms": trimmed_ms,                            # bản đọc (đã cắt lặng)
            "target_ms": int((seg["end"] - seg["start"]) * 1000),  # miệng nhân vật
            "slot_ms": _ms(slot),                                # tới câu kế
            "engine_speed": round(espeed, 3),                    # S5 đã nén (edge/viXTTS)
            "post_atempo": round(factor, 3),                     # S7 nén thêm
            "total_speed": round(espeed * factor, 3),            # tích — phải ≤ MAX_SPEEDUP
            "final_ms": _ms(len(voice)),
            "gap_ms": max(0, _ms(slot - len(voice))),
            "clipped_ms": clipped_ms,
            "voice_gain_db": vgain,
        })

        end = min(total, start + len(voice))
        if end <= start:
            continue
        mixed = bed[start:end].astype(np.int32) + voice[: end - start].astype(np.int32)
        bed[start:end] = np.clip(mixed, -32768, 32767).astype(np.int16)

    audio_np.write_wav(out_path, bed, rate)
    (job.dir / "mix_report.json").write_text(
        json.dumps({"segments": len(segments), "overflow_warnings": warnings,
                    "detail": detail},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
