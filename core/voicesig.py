"""Resolver chữ ký giọng THUẦN DỮ LIỆU (đợt U-2 — AUDIT_GIONG_TUYCHON_TONGHOP.md).

Trước đây `_voice_sig` của S5 đọc thẳng module `config` — muốn tính "đổi tùy chọn
này thì bao nhiêu câu phải đọc lại?" là phải đổi tạm config trong tiến trình
server (race, nhiều luồng dùng chung — Codex chỉ ra). Module này tách phần tính
chữ ký thành hàm thuần: mọi tham số gói trong `TtsSettings`, dựng được từ BẤT KỲ
dict env nào (env thật + override giả lập) mà không đụng trạng thái toàn cục.

S5 (`s5_tts._voice_sig`) và endpoint `/override-impact` cùng gọi một hàm —
không còn 2 bản logic để lệch nhau.
"""
from __future__ import annotations

from dataclasses import dataclass

# Bảng giọng edge theo ngôn ngữ đích lấy từ core/langs.py (import muộn trong
# from_env để tránh vòng import config ↔ langs lúc khởi động).

PAID_ENGINES = ("elevenlabs", "vbee", "fpt")
VI_ONLY = ("vbee", "fpt")
# key .env của cặp giọng từng engine trả phí — DÙNG CHUNG với paid_tts.voice_pair
PAID_VOICE_KEYS = {
    "elevenlabs": ("ELEVENLABS_VOICE_NAM", "ELEVENLABS_VOICE_NU"),
    "vbee": ("VBEE_VOICE_NAM", "VBEE_VOICE_NU"),
    "fpt": ("FPT_VOICE_NAM", "FPT_VOICE_NU"),
}

EDGE_RATE_MAX = 50   # khớp duration.EDGE_RATE_MAX (trần rate edge cho fit budget)


def fit_budget(max_speedup: float) -> int:
    """Ngân sách tăng tốc vì khớp thoại (%) — deterministic, nằm trong .sig."""
    return max(0, min(EDGE_RATE_MAX, round((max_speedup - 1) * 100)))


def base_tag(base_speed: float) -> str:
    """Tag nền tốc độ đọc (đợt T) cho .sig — RỖNG khi 1.0 để mp3 của job cũ
    (sinh trước tính năng) không bị coi là lệch giọng và re-TTS oan."""
    return f":b{base_speed:g}" if base_speed > 1.001 else ""


def _truthy(v: str, default: bool) -> bool:
    s = str(v).strip().lower()
    if not s:
        return default
    return s not in ("0", "false")


@dataclass(frozen=True)
class TtsSettings:
    """Ảnh chụp mọi tham số cấu hình ảnh hưởng chữ ký giọng của MỘT job."""
    engine: str
    lang: str                 # mã ngôn ngữ đích đã chuẩn hoá ('vi' nếu lạ)
    single_voice: bool
    edge_nam: str             # giọng edge hiệu lực theo lang (vi → TTS_VOICE/_NU)
    edge_nu: str
    vix_nam: str
    vix_nu: str
    paid_nam: str
    paid_nu: str
    budget: int               # fit_budget(MAX_SPEEDUP)
    pt: str                   # ":pt1" | "" (PROSODY_TRANSFER)
    emotion_on: bool
    base_speed: float = 1.0   # TTS_BASE_SPEED — nền gu đọc (đợt T)

    @property
    def is_vi(self) -> bool:
        return self.lang == "vi"

    @classmethod
    def from_env(cls, env: dict) -> "TtsSettings":
        """Dựng từ dict env PHẲNG (str→str): .env thật + override đề xuất.
        Key thiếu → default ĐÚNG NHƯ config.py để chữ ký khớp pipeline thật."""
        from core import langs
        g = lambda k, d="": str(env.get(k, d) or d).strip()
        lang = g("TARGET_LANG", "vi").lower() or "vi"
        if lang not in langs.LANGS:
            lang = "vi"
        if lang == "vi":
            e_nam = g("TTS_VOICE", "vi-VN-NamMinhNeural")
            e_nu = g("TTS_VOICE_NU", "vi-VN-HoaiMyNeural")
        else:
            _, e_nam, e_nu = langs.LANGS[lang]
        eng = g("TTS_ENGINE", "edge").lower()
        pk = PAID_VOICE_KEYS.get(eng)
        # default cặp giọng paid khớp config.py (chỉ dùng khi engine là paid đó)
        paid_defaults = {"elevenlabs": ("pNInz6obpgDQGcFmaJgB", "21m00Tcm4TlvDq8ikWAM"),
                         "vbee": ("hn_male_manhdung_news_48k-fhg",
                                  "hn_female_ngochuyen_full_48k-fhg"),
                         "fpt": ("leminh", "banmai")}
        p_nam = p_nu = ""
        if pk:
            d_nam, d_nu = paid_defaults[eng]
            p_nam, p_nu = g(pk[0], d_nam), g(pk[1], d_nu)
        try:
            ms = float(g("MAX_SPEEDUP", "1.4") or "1.4")
        except ValueError:
            ms = 1.4
        try:   # clamp Y HỆT config.py — sig phải khớp pipeline thật từng byte
            bs = min(1.5, max(1.0, float(g("TTS_BASE_SPEED", "1.0") or "1.0")))
        except ValueError:
            bs = 1.0
        return cls(
            engine=eng, lang=lang,
            single_voice=_truthy(g("TTS_SINGLE_VOICE"), True),
            edge_nam=e_nam, edge_nu=e_nu,
            vix_nam=g("VIXTTS_VOICE_NAM"), vix_nu=g("VIXTTS_VOICE_NU"),
            paid_nam=p_nam, paid_nu=p_nu,
            budget=fit_budget(ms),
            pt=":pt1" if _truthy(g("PROSODY_TRANSFER"), False) else "",
            emotion_on=_truthy(g("EMOTION"), False),
            base_speed=bs,
        )


def _emotion_tag(seg: dict, st: TtsSettings) -> str:
    """Bản thuần của emotion.sig_tag — cùng format ':e{label}[1]'."""
    if not st.emotion_on:
        return ""
    e = (seg.get("emotion") or "").strip().lower()
    if e not in ("gap", "gian", "buon", "thitham"):
        return ""
    return f":e{e}" + ("1" if st.single_voice else "")


def _prosody_tag(seg: dict, st: TtsSettings) -> str:
    """Bản thuần của prosody.sig_tag — pitch=0 khi 1 giọng (khớp prosody.pitch_hz)."""
    p = seg.get("prosody") or {}
    pitch = 0 if st.single_voice else int(p.get("pitch_hz", 0))
    return f":r{p.get('rate_pct', 0)}p{pitch}v{p.get('vol_pct', 0)}"


def voice_signature(seg: dict, st: TtsSettings) -> str:
    """Chữ ký giọng DỰ KIẾN của 1 câu — PHẢI khớp từng byte với những gì S5 ghi
    ra .sig (parity test trong đợt U-2). Đổi logic ở đây nhớ đổi cả chỗ S5 ghi
    sig edge trực tiếp trong _tts_one."""
    nu = seg.get("voice") == "nu" and not st.single_voice
    # base_tag CHỈ gắn nhánh EDGE (đợt T): engine nào honor nền tốc độ thì sig
    # mới mang tag — vix/paid chưa áp (T-4/T-5), gắn sớm là đổi knob re-TTS
    # (paid = tốn tiền thật) mà âm thanh không đổi.
    if st.is_vi and seg.get("voice_ref"):
        return "vix:ref:" + seg["voice_ref"] + f":f{st.budget}" + st.pt
    if st.engine in PAID_ENGINES and not (st.engine in VI_ONLY and not st.is_vi):
        return f"{st.engine}:" + (st.paid_nu if nu else st.paid_nam) + st.pt
    if st.is_vi and st.engine == "vixtts":
        return ("vix:def:" + (st.vix_nu if nu else st.vix_nam)
                + _emotion_tag(seg, st) + f":f{st.budget}" + st.pt)
    return ("edge:" + (st.edge_nu if nu else st.edge_nam)
            + _prosody_tag(seg, st) + _emotion_tag(seg, st)
            + f":f{st.budget}" + st.pt + base_tag(st.base_speed))
