"""Bộ 'khẩu vị' hậu kỳ giọng (chuỗi filter ffmpeg) cho khâu render.

Mỗi setting = highpass (cắt trầm) → EQ → nén động → loudnorm (chuẩn độ to -16 LUFS)
→ aresample 48k (loudnorm tự upsample 192k, ép về 48k cho khớp & né AAC 192k).
Chuỗi GIỐNG HỆT file mẫu trong voice_samples/ để 'nghe sao render vậy'.
"""
from __future__ import annotations

_LN = "loudnorm=I=-16:TP=-1.5:LRA=11"
_AR = "aresample=48000"

CHAINS = {
    "canbang": f"highpass=f=80,equalizer=f=200:t=q:w=1:g=-2,equalizer=f=4500:t=q:w=2:g=2,"
               f"acompressor=threshold=-18dB:ratio=3:attack=10:release=120:makeup=2,{_LN},{_AR}",
    "amday":   f"highpass=f=60,equalizer=f=150:t=q:w=1.2:g=1.5,equalizer=f=400:t=q:w=1.5:g=-1.5,"
               f"equalizer=f=3500:t=q:w=2:g=1.5,"
               f"acompressor=threshold=-20dB:ratio=2.5:attack=15:release=150:makeup=2,{_LN},{_AR}",
    "rosang":  f"highpass=f=100,equalizer=f=250:t=q:w=1:g=-2.5,equalizer=f=5000:t=q:w=2:g=3,"
               f"equalizer=f=7500:t=q:w=2:g=-2,"
               f"acompressor=threshold=-18dB:ratio=3.5:attack=8:release=100:makeup=3,{_LN},{_AR}",
    "dienanh": f"highpass=f=70,equalizer=f=110:t=q:w=1:g=2,equalizer=f=300:t=q:w=1.5:g=-1.5,"
               f"equalizer=f=4000:t=q:w=2:g=2,"
               f"acompressor=threshold=-20dB:ratio=3:attack=12:release=140:makeup=2,"
               f"aecho=0.8:0.9:55:0.12,{_LN},{_AR}",
    "toithieu": f"highpass=f=80,{_LN},{_AR}",
}

# (value, nhãn) cho dropdown UI — 'off' = không xử lý (giữ nguyên hành vi cũ)
OPTIONS = [
    ("off", "Tắt (giữ nguyên)"),
    ("canbang", "Cân bằng"),
    ("amday", "Ấm / dày"),
    ("rosang", "Rõ / sáng"),
    ("dienanh", "Điện ảnh"),
    ("toithieu", "Tối thiểu"),
]


def chain(name: str | None) -> str | None:
    """Trả chuỗi filter ffmpeg cho setting, hoặc None nếu 'off'/không hợp lệ (→ không lọc)."""
    return CHAINS.get((name or "off").strip().lower())
