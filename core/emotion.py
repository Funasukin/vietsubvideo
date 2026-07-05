"""Nhãn CẢM XÚC từng câu → giọng đọc có sắc thái (PLAN 11 mức 2 = A+B chung mạch).

A. Claude gắn nhãn khi dịch (S4, field "emotion"): binhthuong | gap | gian | buon |
   thitham — bắt sắc thái mà phép đo audio (prosody mức 1) không thấy được (mỉa mai,
   đe dọa nói nhỏ...). Nhãn lưu trên segment (chỉ khi != binhthuong).
B. S5 map nhãn theo engine:
   - edge-tts: offset rate/pitch/volume CỘNG THÊM vào prosody đo audio, kẹp trần
     (hai nguồn bổ trợ: đo audio = khách quan, nhãn text = ngữ nghĩa).
   - viXTTS: chọn CLIP MẪU trong voices/ hợp cảm xúc (giận→nhanh, buồn→chậm...) —
     XTTS bắt chước cả ngữ điệu clip mẫu. KHÔNG đè voice_ref (casting = danh tính
     nhân vật, thắng cảm xúc).
Nhãn đi vào chữ ký .sig của TTS → đổi nhãn/bật tắt là câu bị ảnh hưởng tự đọc lại.
Bật/tắt: config.EMOTION (mặc định bật).
"""
from __future__ import annotations

import config

LABELS = ("binhthuong", "gap", "gian", "buon", "thitham")

# offset edge-tts theo nhãn: (rate %, pitch Hz, volume %) — NHẸ, cộng vào prosody
_EDGE = {
    "gap":     (12,  4,   6),   # gấp gáp: nhanh hơn, hơi to
    "gian":    (8,   10,  10),  # giận: nhanh + cao + to
    "buon":    (-10, -8,  -6),  # buồn: chậm + trầm + nhỏ
    "thitham": (-8,  -5, -20),  # thì thầm: chậm + trầm + nhỏ hẳn
}
# trần SAU KHI cộng prosody — rộng hơn trần prosody một chút nhưng vẫn giữ tự nhiên
_R_MAX, _P_MAX, _V_MAX = 25, 30, 25

# viXTTS: nhãn → từ khóa tên clip mẫu trong voices/ theo thứ tự ưu tiên
# (bộ mẫu hiện có: mau-nam-{calm,cham,nhanh,truyen-cam}, mau-nu-{calm,cham,luu-loat,nhan-nha,nhe-nhang})
_VIX = {
    "gap":     {"nam": ["nhanh", "truyen-cam"], "nu": ["luu-loat", "calm"]},
    "gian":    {"nam": ["nhanh", "truyen-cam"], "nu": ["luu-loat"]},
    "buon":    {"nam": ["cham", "calm"],        "nu": ["nhe-nhang", "cham"]},
    "thitham": {"nam": ["cham", "calm"],        "nu": ["nhe-nhang", "nhan-nha"]},
}


def enabled() -> bool:
    return str(getattr(config, "EMOTION", "1")).strip().lower() not in ("0", "false", "")


def label(seg: dict) -> str:
    """Nhãn hiệu lực của câu ('' nếu bình thường/không hợp lệ/tắt tính năng)."""
    if not enabled():
        return ""
    e = (seg.get("emotion") or "").strip().lower()
    return e if e in LABELS and e != "binhthuong" else ""


def sig_tag(seg: dict) -> str:
    """Đuôi chữ ký TTS: đổi nhãn cảm xúc → .sig lệch → tự đọc lại câu đó."""
    e = label(seg)
    return f":e{e}" if e else ""


def edge_kwargs(seg: dict) -> dict:
    """Tham số edge_tts.Communicate = prosody (đo audio) + offset cảm xúc, kẹp trần.
    Thay thế prosody.edge_kwargs trong S5 — nhãn tắt/bình thường thì y hệt bản cũ.
    Pitch prosody lấy qua prosody.pitch_hz() (chế độ 1 giọng → 0, giữ giọng đồng nhất);
    pitch CẢM XÚC nhỏ vẫn cộng (diễn cảm theo câu, không đổi "danh tính" giọng)."""
    from core import prosody as _pro
    p = seg.get("prosody") or {}
    r, pi, v = p.get("rate_pct", 0), _pro.pitch_hz(seg), p.get("vol_pct", 0)
    e = label(seg)
    if e:
        er, ep, ev = _EDGE[e]
        r, pi, v = r + er, pi + ep, v + ev
    r = max(-_R_MAX, min(_R_MAX, r))
    pi = max(-_P_MAX, min(_P_MAX, pi))
    v = max(-_V_MAX, min(_V_MAX, v))
    kw = {}
    if r:
        kw["rate"] = f"{r:+d}%"
    if pi:
        kw["pitch"] = f"{pi:+d}Hz"
    if v:
        kw["volume"] = f"{v:+d}%"
    return kw


# cache danh sách mẫu theo giới — S5 gọi mỗi câu (hàng trăm lần/job); tiến trình
# cli.py sống 1 job nên không lo file mới thêm giữa chừng
_files_cache: dict[str, list[str]] = {}


def _sample_files(g: str) -> list[str]:
    if g not in _files_cache:
        try:
            _files_cache[g] = sorted(p.name for p in config.VOICES_DIR.glob(f"mau-{g}-*")
                                     if p.is_file())
        except OSError:
            _files_cache[g] = []
    return _files_cache[g]


def vixtts_sample(seg: dict) -> str | None:
    """Tên clip mẫu voices/ hợp cảm xúc cho câu (None = dùng giọng mặc định).
    Chỉ gọi cho câu KHÔNG có voice_ref — casting/chỉnh tay luôn thắng."""
    e = label(seg)
    if not e:
        return None
    # Chế độ 1 giọng (config.TTS_SINGLE_VOICE): mọi câu lấy clip mẫu NAM để không lòi
    # giọng nữ ra — khớp với s5_tts._seg_nu.
    g = "nu" if (seg.get("voice") == "nu" and not config.TTS_SINGLE_VOICE) else "nam"
    for cand in _VIX.get(e, {}).get(g, []):
        for f in _sample_files(g):
            if cand in f:
                return f
    return None
