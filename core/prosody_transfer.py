"""PLAN 11 mức 3 — PROSODY TRANSFER: chuyển ĐƯỜNG NÉT NGỮ ĐIỆU câu gốc sang giọng đọc.

Mức 1 (prosody) chỉnh MỨC trung bình (nhanh/chậm, cao/thấp, to/nhỏ cả câu); mức 3 này
chuyển cả HÌNH DÁNG đường cao độ: câu gốc lên giọng cuối câu → giọng Việt cũng lên
giọng cuối câu, gằn từng nhịp → gằn từng nhịp.

Cách làm (DSP, KHÔNG cần model GPU — chạy được cả 2 máy):
  1. Trích đường F0 câu GỐC (ưu tiên vocals.wav đã tách demucs) bằng Praat.
  2. Chuẩn hóa: lệch semitone so với trung vị người nói, lấy dáng 24 điểm (stylize
     — bỏ rung vặt, giữ đường macro), chuẩn thời gian theo khoảng CÓ TIẾNG.
  3. Ép dáng đó lên audio TTS quanh trung vị CỦA GIỌNG ĐỌC (giữ tầm giọng tự nhiên),
     cường độ w=0.7, kẹp ±7 semitone → resynthesis bằng PSOLA (overlap-add, giữ
     nguyên độ dài — không ảnh hưởng atempo của S7).

Vì sao không dùng RVC/OpenVoice như ghi chú cũ trong PLAN: RVC giữ nguyên ÂM VỊ nguồn
(ra tiếng Trung giọng mới — sai bài lồng tiếng); OpenVoice chuyển màu giọng (timbre)
— viXTTS clone đã làm. Cái cần chuyển là NGỮ ĐIỆU → PSOLA là đúng công cụ.

Bảo thủ như mức 1: đo không chắc (ít tiếng, nhạc lấn) → giữ nguyên TTS. Bật/tắt:
PROSODY_TRANSFER (mặc định TẮT — tính năng thử nghiệm, bật trong tab Cấu hình).
Cần praat-parselmouth (đã ghi requirements); thiếu thì tự bỏ qua, không hỏng pipeline.
"""
from __future__ import annotations

import config

_W = 0.7                 # cường độ ép dáng (0..1): 1 = copy nguyên, 0 = giữ TTS
_MAX_SEMI = 7.0          # kẹp biên độ dáng sau khi nhân w (± semitone quanh trung vị)
_N_POINTS = 24           # số điểm dáng (stylize) — đủ đường macro, bỏ rung vặt
_MIN_DUR_S = 0.4         # câu ngắn hơn → bỏ (đo không tin được)
_MIN_VOICED = 0.30       # tỉ lệ khung hữu thanh tối thiểu ở CẢ 2 phía


def enabled() -> bool:
    return str(getattr(config, "PROSODY_TRANSFER", "0")).strip().lower() \
        not in ("0", "false", "")


def sig_tag() -> str:
    """Đuôi chữ ký TTS toàn cục: bật/tắt transfer → .sig lệch → tự đọc/xử lý lại."""
    return ":pt1" if enabled() else ""


def _contour(snd, n: int = _N_POINTS):
    """Dáng ngữ điệu của 1 đoạn âm: n điểm (t chuẩn hóa 0..1 theo khoảng CÓ TIẾNG,
    lệch semitone so với trung vị). None nếu quá ít khung hữu thanh."""
    import numpy as np
    import parselmouth

    pitch = snd.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=500)
    f0 = pitch.selected_array["frequency"]
    times = pitch.xs()
    voiced = f0 > 0
    if voiced.sum() < max(6, _MIN_VOICED * len(f0)):
        return None
    tv, fv = times[voiced], f0[voiced]
    t0, t1 = tv[0], tv[-1]
    if t1 - t0 < 0.2:
        return None
    med = float(np.median(fv))
    semi = 12 * np.log2(fv / med)
    tn = (tv - t0) / (t1 - t0)
    grid = np.linspace(0, 1, n)
    shape = np.interp(grid, tn, semi)
    # làm mượt 3 điểm — PSOLA không thích bậc thang gắt
    if n >= 3:
        shape = np.convolve(np.pad(shape, 1, mode="edge"),
                            np.ones(3) / 3, mode="valid")
    # trả kèm khoảng CÓ TIẾNG (t0..t1) — bên áp dáng phải neo vào khoảng này,
    # không phải cả file (TTS có khoảng lặng đầu/cuối → trải cả file là dạt dáng)
    return grid, shape, med, float(t0), float(t1)


def apply(job, seg: dict, mp3_path) -> bool:
    """Ép dáng ngữ điệu câu gốc lên file TTS (sửa TẠI CHỖ, giữ nguyên độ dài).
    Trả True nếu đã transfer; mọi lỗi/thiếu điều kiện → False, file giữ nguyên."""
    if not enabled():
        return False
    if (seg.get("end", 0) - seg.get("start", 0)) < _MIN_DUR_S:
        return False
    try:
        import numpy as np
        import parselmouth
        from parselmouth.praat import call

        from core import prosody
        src_path = prosody._audio_path(job)
        if src_path is None:
            return False
        # đoạn gốc đúng khoảng thời gian câu
        src = parselmouth.Sound(str(src_path)).extract_part(
            from_time=float(seg["start"]), to_time=float(seg["end"]),
            preserve_times=False)
        got = _contour(src)
        if got is None:
            return False
        grid, shape, _, _, _ = got

        snd = parselmouth.Sound(str(mp3_path))
        tts = _contour(snd, n=8)      # cần trung vị + KHOẢNG CÓ TIẾNG của giọng đọc
        if tts is None:
            return False
        _, _, med_tts, tts_t0, tts_t1 = tts

        # dáng nguồn × cường độ, kẹp biên → PitchTier quanh trung vị giọng đọc,
        # NEO vào khoảng có tiếng của TTS (không trải cả file — lệch vào vùng câm)
        semi = np.clip(shape * _W, -_MAX_SEMI, _MAX_SEMI)
        dur = snd.get_total_duration()
        span = tts_t1 - tts_t0
        manip = call(snd, "To Manipulation", 0.01, 75, 600)
        tier = call("Create PitchTier", "pt", 0, dur)
        for g, s in zip(grid, semi):
            call(tier, "Add point", float(tts_t0 + g * span),
                 float(med_tts * 2 ** (s / 12)))
        call([tier, manip], "Replace pitch tier")
        out = call(manip, "Get resynthesis (overlap-add)")

        # ghi đè mp3 (PSOLA giữ nguyên độ dài nên S7 atempo không bị ảnh hưởng)
        import tempfile
        from pathlib import Path

        from pydub import AudioSegment
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "pt.wav"
            out.save(str(wav), "WAV")
            AudioSegment.from_wav(wav).export(str(mp3_path), format="mp3",
                                              bitrate="48k")
        return True
    except Exception as e:
        print(f"  Prosody transfer: bỏ qua câu {seg.get('id')} ({e})")
        return False
