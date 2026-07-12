"""Trọng tài THỜI LƯỢNG duy nhất cho giọng đọc (đợt B audit giọng — AUDIT_GIONG_TONGHOP.md).

Trước đây 3 điểm chỉnh tốc độ độc lập (S5 edge fit, S7 atempo, engine) dùng 2 thước
đo khác nhau (full mp3 gồm đuôi lặng vs đã cắt lặng) và tiêu MAX_SPEEDUP 2 lần —
tích nén có thể tới 3× dù UI hứa đây là "núm tổng". Module này gom về:

- MỘT thước đo : mọi quyết định dựa trên độ dài ĐÃ CẮT LẶNG 2 đầu (trim_silence
  dùng chung cho S5 lẫn S7 — không còn "tràn giả" do đuôi câm edge 0.5–0.9s).
- MỘT ngân sách: MAX_SPEEDUP là trần NHÂN tổng. S5 (engine) tiêu trước phần nó
  làm được tự nhiên (edge rate / viXTTS speed), S7 chỉ còn atempo trong phần
  ngân sách CÒN LẠI (MAX_SPEEDUP / engine_speed) — ghi nhận qua fit_report.json.
- DEADZONE   : câu đã lọt limit thì không đụng — không "chỉnh khi không cần chỉnh".
- limit < slot: chừa FADE_GUARD cho fade-out ở biên — hết cảnh giọng đè câu kế.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import config

FADE_GUARD_S = 0.10      # chừa cuối slot cho fade-out (S7) — limit = slot − guard
TOL = 1.02               # dung sai 2%: dài hơn limit cỡ này mới coi là tràn
VIXTTS_SPEED_MAX = 1.25  # trần speed synth lại viXTTS (length_scale) — cao hơn vỡ prosody
EDGE_RATE_MAX = 50       # trần TỔNG rate edge (%) — nhanh hơn nữa nghe máy móc
MIN_SLOT_S = 0.3         # sàn slot (đồng bộ S5/S7 — trước đây S4 dùng sàn khác 0.5)

# Ngân sách CHỮ cho tầng dịch (đợt C audit giọng): giọng đọc tiếng Việt tự nhiên
# ~4 âm tiết/giây; quá 4.5/giây-limit là chắc chắn phải nén máy móc.
# (SYL_TARGET_PER_S 4.0 đã xóa đợt T — hằng số chết sau khi bậc 1 bỏ target_s;
#  Codex xác nhận không còn nơi dùng. SYL_MAX giữ nguyên, CHƯA scale theo nền
#  TTS_BASE_SPEED — quyết định TONGHOP: đổi 1 biến/lần, đo 20-30 job rồi tính.)
BREATH_S = 0.25          # đệm thở trừ khỏi slot khi cấp ngân sách cho bản dịch
SYL_MAX_PER_S = 4.5      # trần cứng cho validator — vượt là dịch lại cho ngắn

# Đợt T: trần CHẤT LƯỢNG tuyệt đối cho tốc độ NGHE THẬT của một câu —
# nền(TTS_BASE_SPEED) × nén-engine × atempo ≤ mức này. Nền không tiêu ngân sách
# MAX_SPEEDUP (nó là gu đọc, không phải nén) nhưng tai người thì nghe TÍCH tổng:
# nền 1.5 × nén 2.0 = 3.0× là cháo. Hằng số kỹ thuật, không thêm knob (Codex).
ABS_AUDIBLE_MAX = 2.0


def slots(segments: list[dict]) -> dict:
    """{id: slot giây (tới start câu KẾ theo thời gian, tính cả câu mute/rỗng —
    CÙNG công thức S5/S7); câu cuối → None}. Một nguồn sự thật cho mọi tầng."""
    full = sorted(segments, key=lambda s: s["start"])
    out: dict = {}
    for k, s in enumerate(full):
        if k + 1 < len(full):
            out[s["id"]] = max(MIN_SLOT_S, full[k + 1]["start"] - s["start"])
        else:
            out[s["id"]] = None
    return out


def syllables(text: str) -> int:
    """Đếm âm tiết tiếng Việt ≈ đếm TIẾNG (token cách nhau bởi khoảng trắng, bỏ
    token toàn dấu câu). Xấp xỉ đủ tốt cho ngân sách đọc — số/ký hiệu hiếm gặp."""
    import re
    return sum(1 for t in text.split() if re.search(r"[\wà-ỹÀ-Ỹ]", t))

_REPORT = "fit_report.json"   # tts/fit_report.json: id → đo đạc + engine_speed đã tiêu


def limit_s(slot: float) -> float:
    """Trần CỨNG cho một câu: hết chỗ này là fade — chừa guard cho biên."""
    return max(MIN_SLOT_S, slot - FADE_GUARD_S)


def trim_silence(a: np.ndarray, rate: int, thresh: int = 300, pad_ms: int = 40) -> np.ndarray:
    """Cắt khoảng LẶNG 2 đầu (edge đệm ~0.3–0.9s im lặng cuối file, viXTTS cũng có
    đuôi thở). Dùng CHUNG cho S5 (đo trước fit) và S7 (nạp để đặt lên timeline) —
    hai stage nhìn cùng một con số. Giữ pad_ms đệm tự nhiên."""
    if not len(a):
        return a
    nz = np.nonzero(np.abs(a).max(axis=1) > thresh)[0]
    if not len(nz):
        return a
    pad = int(pad_ms / 1000 * rate)
    return a[max(0, int(nz[0]) - pad): min(len(a), int(nz[-1]) + pad)]


def trimmed_dur_s(path) -> float | None:
    """Độ dài PHẦN TIẾNG (giây) của file TTS = decode + cắt lặng 2 đầu.
    Đây là thước đo chuẩn — KHÔNG dùng ffprobe header (gồm cả đuôi lặng)."""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(path)
        ch = seg.channels
        a = np.array(seg.get_array_of_samples(), dtype=np.int16).reshape(-1, ch)
        a = trim_silence(a, seg.frame_rate)
        return len(a) / seg.frame_rate
    except Exception:
        return None


def fit_speed(trimmed_s: float, slot_s: float) -> float:
    """Hệ số nén CẦN để câu lọt limit. 1.0 = đã lọt (deadzone), không đụng."""
    lim = limit_s(slot_s)
    if trimmed_s <= lim * TOL:
        return 1.0
    return trimmed_s / lim


def edge_total_rate(base_pct: int, k: float) -> int:
    """Rate (%) TỔNG cho lần đọc lại edge để đạt hệ số nén k so với bản hiện tại
    (đang phát ở 1+base/100). Có số hạng chéo (toán Gemini, AUDIT_GIONG_TONGHOP §2):
    (1+total/100) = (1+base/100) × k. Bản cũ thiếu số hạng chéo nên luôn hụt mục
    tiêu → S7 phải atempo THÊM gần như mọi câu.
    round(…, 6) trước ceil: khử nhiễu float (1.1×1.2=1.3200…03 mà ceil thành 33)."""
    return math.ceil(round(((1 + base_pct / 100) * k - 1) * 100, 6))


def budget_left(engine_speed: float, base_speed: float = 1.0) -> float:
    """Ngân sách nén CÒN LẠI cho S7 sau khi engine đã tiêu engine_speed.
    Hai trần TÍCH (đợt T): engine_speed × post_atempo ≤ MAX_SPEEDUP (lời hứa cũ,
    nền KHÔNG tính vào) VÀ nền × engine × atempo ≤ ABS_AUDIBLE_MAX (trần chất
    lượng nghe thật). base_speed là nền THỰC của CHÍNH câu này (style_native
    trong fit_report — chỉ câu edge được áp nền đợt này; review đối kháng T#2:
    đọc config toàn cục là đánh thuế oan câu viXTTS/paid không hề mang nền).
    Với nền 1.0 hai trần trùng nhau → hành vi y như trước."""
    e = max(1.0, engine_speed)
    b = max(1.0, base_speed)
    return max(1.0, min(config.MAX_SPEEDUP / e, ABS_AUDIBLE_MAX / (b * e)))


def load_report(job_dir: Path) -> dict:
    """fit_report.json của job (id-str → {trimmed_ms, engine_speed, ...}).
    Thiếu/hỏng → {} — S7 coi engine_speed=1.0 (đúng cho mp3 cũ chưa qua fit)."""
    try:
        return json.loads((job_dir / "tts" / _REPORT).read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_report(job_dir: Path, data: dict) -> None:
    try:
        (job_dir / "tts").mkdir(exist_ok=True)
        (job_dir / "tts" / _REPORT).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass   # report là phụ trợ — không được làm chết stage
