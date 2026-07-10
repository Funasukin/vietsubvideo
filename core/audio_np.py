"""Đọc/ghi WAV PCM 16-bit dạng mảng numpy — thay pydub ở các thao tác trên
toàn bộ track (pydub copy cả mảng mỗi phép toán, rất chậm với audio dài)."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """→ (mảng int16 shape (n_mẫu, n_kênh), sample_rate)."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: chỉ hỗ trợ PCM 16-bit")
        n, ch, rate = w.getnframes(), w.getnchannels(), w.getframerate()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).reshape(-1, ch)
    return data.copy(), rate  # copy: frombuffer trả mảng read-only


def read_wav_slice(path: Path, start_s: float, dur_s: float) -> tuple[np.ndarray, int]:
    """Đọc MỘT KHÚC wav (giây) không nạp cả file — /mix-preview cắt 10s giữa video
    dài mà không tốn RAM/IO cho toàn bộ track. → (mảng int16 (n, kênh), rate)."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: chỉ hỗ trợ PCM 16-bit")
        ch, rate, total = w.getnchannels(), w.getframerate(), w.getnframes()
        i0 = max(0, min(total, int(start_s * rate)))
        n = max(0, min(total - i0, int(dur_s * rate)))
        w.setpos(i0)
        data = np.frombuffer(w.readframes(n), dtype=np.int16).reshape(-1, ch)
    return data.copy(), rate


def write_wav(path: Path, data: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.ascontiguousarray(data, dtype=np.int16).tobytes())
