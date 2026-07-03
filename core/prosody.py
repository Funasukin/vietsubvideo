"""Đo TÔNG GIỌNG GỐC từng câu → chỉnh giọng đọc edge-tts cho khớp (PLAN mục 11, mức 1).

Ba tín hiệu đo từ audio gốc (numpy thuần, mượn bộ đo F0 của core/gender.py):
  - Cao độ F0 trung vị                          → pitch (+/-Hz): câu lên giọng thì
    giọng Việt cũng lên giọng
  - Tốc độ nói (ký tự chữ/giây của text GỐC — chữ Hán ~ 1 âm tiết) → rate (+/-%)
  - Năng lượng RMS các khung không câm (dB)     → volume (+/-%): quát to / thì thầm

So với MỨC NỀN của TỪNG NGƯỜI NÓI (nhãn speaker từ diarize nếu có, không thì cả
video) — "cao" của giọng nữ khác "cao" của giọng nam. Map BẢO THỦ: lệch ít hoặc đo
không chắc (ít khung hữu thanh, nhạc nền lấn) → để 0 — thà trung tính còn hơn sai.

Ưu tiên đo trên vocals.wav (giọng đã tách demucs, nếu có) rồi mới tới audio gốc —
bản trộn nhạc nền làm nhiễu phép đo ở cảnh nhạc to.

Chỉ áp cho edge-tts. viXTTS không nhận rate/pitch — nó bắt chước ngữ điệu clip mẫu
(hướng đó là PLAN 11 B); riêng độ dài thì S7 đã atempo khớp slot gốc sẵn.

Kết quả gắn seg["prosody"] = {"rate_pct","pitch_hz","vol_pct"} (chỉ khi có chỉnh)
và đi vào chữ ký .sig của TTS → đổi cách đo / bật tắt là tự đọc lại đúng câu bị
ảnh hưởng khi chạy lại stage tts.
"""
from __future__ import annotations

import re

import numpy as np

import config
from core import gender

# Cổng (dưới ngưỡng = không chỉnh) và trần mỗi tham số — chỉnh NHẸ mới tự nhiên
_PITCH_SCALE, _PITCH_GATE_HZ, _PITCH_MAX_HZ = 0.5, 8, 25
_RATE_SCALE, _RATE_GATE_PCT, _RATE_MIN, _RATE_MAX = 50.0, 6, -12, 20
_VOL_SCALE, _VOL_GATE_PCT, _VOL_MAX = 3.0, 8, 15
_MIN_GROUP = 3       # cần ít nhất bấy nhiêu câu đo được mới dám lập mức nền
_MIN_DUR_S = 0.3     # câu ngắn hơn → bỏ qua (đo không tin được)

# ký tự "ra tiếng" để đếm tốc độ nói: chữ cái/số + CJK + kana + hangul
_WORDLIKE = re.compile(r"[\w一-鿿぀-ヿ가-힯]")


def enabled() -> bool:
    return str(config.PROSODY).strip().lower() not in ("0", "false", "")


def sig_tag(seg: dict) -> str:
    """Đuôi chữ ký TTS: prosody đổi → .sig đổi → tự đọc lại câu đó."""
    p = seg.get("prosody") or {}
    return f":r{p.get('rate_pct', 0)}p{p.get('pitch_hz', 0)}v{p.get('vol_pct', 0)}"


def edge_kwargs(seg: dict) -> dict:
    """Tham số truyền thẳng vào edge_tts.Communicate cho 1 câu."""
    p = seg.get("prosody") or {}
    kw = {}
    if p.get("rate_pct"):
        kw["rate"] = f"{p['rate_pct']:+d}%"
    if p.get("pitch_hz"):
        kw["pitch"] = f"{p['pitch_hz']:+d}Hz"
    if p.get("vol_pct"):
        kw["volume"] = f"{p['vol_pct']:+d}%"
    return kw


def _audio_path(job):
    for name in ("vocals.wav", "audio_16k.wav", "audio_full.wav"):
        p = job.dir / name
        if p.exists():
            return p
    return None


def _active_rms_db(x: np.ndarray, sr: int) -> float | None:
    """RMS (dB) trên các khung 40ms KHÔNG câm — khoảng lặng đầu/cuối không kéo tụt."""
    flen = int(0.04 * sr)
    if len(x) < flen:
        return None
    nf = len(x) // flen
    fr = x[: nf * flen].reshape(nf, flen)
    rms = np.sqrt((fr * fr).mean(axis=1))
    act = rms[rms > 1e-3]
    if len(act) < 3:
        return None
    return float(20 * np.log10(act.mean() + 1e-9))


def measure(job, segments: list[dict]) -> int:
    """Gắn seg["prosody"] cho các câu lệch tông rõ so với mức nền người nói.
    Trả số câu được chỉnh. Tắt (PROSODY=0) → dọn nhãn cũ, trả 0."""
    if not enabled():
        for s in segments:
            s.pop("prosody", None)
        return 0
    path = _audio_path(job)
    if path is None:
        return 0
    try:
        samples, sr = gender._read_mono(path)
    except Exception as e:
        print(f"  Tông giọng: bỏ qua, không đọc được audio ({e})")
        return 0

    # Pha 1: đo thô từng câu (kể cả câu mute — mức nền người nói chuẩn hơn)
    feats: dict[int, tuple] = {}
    for s in segments:
        dur = s["end"] - s["start"]
        a = max(0, int(s["start"] * sr))
        b = min(len(samples), int(s["end"] * sr))
        if dur < _MIN_DUR_S or b - a < int(_MIN_DUR_S * sr):
            continue
        x = samples[a:b]
        f0 = gender._segment_f0(x, sr)
        if f0 and f0 > gender.NU_CEIL:      # quá cao = nhạc/nhiễu, không phải giọng
            f0 = None
        nch = len(_WORDLIKE.findall(s.get("text") or ""))
        rate = nch / dur if nch >= 4 else None
        feats[s["id"]] = (f0, _active_rms_db(x, sr), rate,
                          s.get("speaker") or "*")

    # Pha 2: mức nền theo người nói (fallback toàn video khi nhóm quá ít câu)
    groups: dict[str, dict[str, list[float]]] = {}
    glob: dict[str, list[float]] = {"f0": [], "db": [], "rt": []}
    for f0, db, rt, g in feats.values():
        d = groups.setdefault(g, {"f0": [], "db": [], "rt": []})
        for key, val in (("f0", f0), ("db", db), ("rt", rt)):
            if val is not None:
                d[key].append(val)
                glob[key].append(val)

    def _med(vals: list[float]) -> float | None:
        return float(np.median(vals)) if len(vals) >= _MIN_GROUP else None

    def _base(g: str, key: str) -> float | None:
        return _med(groups.get(g, {}).get(key, [])) or _med(glob[key])

    # Pha 3: lệch so với nền → tham số, qua cổng + trần
    n = 0
    for s in segments:
        s.pop("prosody", None)
        ft = feats.get(s["id"])
        if not ft:
            continue
        f0, db, rt, g = ft
        pro: dict[str, int] = {}
        b = _base(g, "f0")
        if f0 and b:
            hz = max(-_PITCH_MAX_HZ, min(_PITCH_MAX_HZ,
                                         int(round((f0 - b) * _PITCH_SCALE))))
            if abs(hz) >= _PITCH_GATE_HZ:
                pro["pitch_hz"] = hz
        b = _base(g, "rt")
        if rt and b:
            pct = max(_RATE_MIN, min(_RATE_MAX,
                                     int(round((rt / b - 1) * _RATE_SCALE))))
            if abs(pct) >= _RATE_GATE_PCT:
                pro["rate_pct"] = pct
        b = _base(g, "db")
        if db is not None and b is not None:
            pct = max(-_VOL_MAX, min(_VOL_MAX, int(round((db - b) * _VOL_SCALE))))
            if abs(pct) >= _VOL_GATE_PCT:
                pro["vol_pct"] = pct
        if pro:
            s["prosody"] = pro
            n += 1
    return n
