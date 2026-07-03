"""Nhận diện giới tính người nói theo cao độ giọng (F0) → gán nhãn voice nam/nu.

Phân tích audio mono của TỪNG segment, ước lượng F0 trung vị các khung HỮU THANH
bằng autocorrelation (chỉ dùng numpy, không thêm thư viện). Nam ~85-165Hz, nữ
~165-255Hz. Chỉ kết luận khi chắc (F0 < NAM_MAX hoặc > NU_MIN); vùng mơ hồ ở giữa,
quá ít khung hữu thanh, hoặc nhạc nền lấn giọng → trả None để Claude/đoán-theo-chữ lo.

Chạy ở S4 (trước TTS) nên dùng audio gốc đã trộn (audio_16k.wav). Bật demucs tách
giọng sẽ chính xác hơn nhưng demucs chạy sau (S6) nên ở đây dùng bản trộn.
"""
from __future__ import annotations

import numpy as np

# Ngưỡng phân loại (Hz). Để KHOẢNG MƠ HỒ [NAM_MAX, NU_MIN] = None nhằm tránh đoán
# sai gần ranh giới — thà nhường Claude còn hơn gán nhầm giới tính.
NAM_MAX = 155.0
NU_MIN = 185.0
NU_CEIL = 290.0   # F0 trung vị > ngưỡng này: giọng người bình thường hiếm khi vượt
                  # → coi là nhạc nền/nhiễu (artifact), trả None thay vì gán nhầm "nu"
F0_MIN = 70.0     # dải F0 giọng người cần dò
F0_MAX = 400.0
_CLARITY = 0.35   # đỉnh autocorr/đỉnh-0 tối thiểu để coi khung là hữu thanh
_MIN_VOICED = 4   # số khung hữu thanh tối thiểu để dám kết luận


def _frame_f0(frame: np.ndarray, sr: int) -> float | None:
    """F0 (Hz) của 1 khung, hoặc None nếu vô thanh/câm."""
    frame = frame - frame.mean()
    if np.sqrt(np.mean(frame * frame)) < 1e-3:   # gần như im lặng
        return None
    n = len(frame)
    win = frame * np.hanning(n)
    # autocorrelation qua FFT (O(n log n))
    spec = np.fft.rfft(win, 2 * n)
    acf = np.fft.irfft(spec * np.conj(spec))[:n]
    if acf[0] <= 0:
        return None
    lag_min = int(sr / F0_MAX)
    lag_max = min(int(sr / F0_MIN), n - 1)
    if lag_max <= lag_min:
        return None
    seg = acf[lag_min:lag_max] / acf[0]
    gmax = float(seg.max())
    if gmax < _CLARITY:
        return None
    lag = lag_min + int(np.argmax(seg))   # đỉnh nổi bật nhất = chu kỳ cơ bản
    if lag <= 0:
        return None
    return sr / lag


def _segment_f0(samples: np.ndarray, sr: int) -> float | None:
    """F0 trung vị các khung hữu thanh của 1 segment; None nếu không đủ chắc."""
    flen = int(0.04 * sr)   # khung 40ms
    hop = int(0.02 * sr)    # bước 20ms
    if len(samples) < flen:
        return None
    f0s = []
    for st in range(0, len(samples) - flen + 1, hop):
        f = _frame_f0(samples[st:st + flen], sr)
        if f is not None:
            f0s.append(f)
    if len(f0s) < _MIN_VOICED:
        return None
    return float(np.median(f0s))


def _read_mono(path) -> tuple[np.ndarray, int]:
    from core import audio_np
    data, sr = audio_np.read_wav(path)
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)        # về mono
    return arr / 32768.0, sr          # int16 → [-1, 1]


def detect(audio_path, segments: list[dict]) -> dict[int, str | None]:
    """→ {seg_id: "nam"|"nu"|None}. None = không chắc (để khâu khác quyết)."""
    try:
        samples, sr = _read_mono(audio_path)
    except Exception as e:
        print(f"  gender: bỏ qua, không đọc được {audio_path} ({e})")
        return {}
    out: dict[int, str | None] = {}
    min_len = int(0.15 * sr)   # câu quá ngắn (<0.15s) → không dò
    for seg in segments:
        a = max(0, int(seg["start"] * sr))
        b = min(len(samples), int(seg["end"] * sr))
        if b - a < min_len:
            out[seg["id"]] = None
            continue
        f0 = _segment_f0(samples[a:b], sr)
        if f0 is None or f0 > NU_CEIL:
            out[seg["id"]] = None    # không dò được / quá cao (nhạc nền) → không chắc
        elif f0 < NAM_MAX:
            out[seg["id"]] = "nam"
        elif f0 > NU_MIN:
            out[seg["id"]] = "nu"
        else:
            out[seg["id"]] = None    # vùng mơ hồ giữa nam/nữ
    return out
