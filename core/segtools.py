"""Hậu xử lý segment OCR: lọc chữ rác trên màn hình + gộp dòng phụ đề liền kề.

Phụ đề (nhất là bản Eng-sub) hay cắt một câu nói thành nhiều dòng nháy nhanh
1-2 giây — TTS tiếng Việt không thể chen vào slot ngắn vậy. Gộp các dòng cách
nhau dưới MERGE_GAP_S thành một segment dài hơn để có slot đọc thực tế.
"""
from __future__ import annotations

import re
from collections import Counter

_CJK = re.compile(r"[一-鿿㐀-䶿]")
_LATIN_LOWER = re.compile(r"[a-zà-ỹ]")  # có chữ thường (kể cả tiếng Việt)

MERGE_GAP_S = 0.35
MERGE_MAX_DUR_S = 8.0
MERGE_MAX_CHARS = 80
# Trần số DÒNG SUB GỐC gộp vào 1 câu đọc. Video thoại bắn nhanh (vlog tua nhanh, sub
# đổi ~0.5s/lần) không có trần này sẽ gộp 6-7 lượt thoại (nhiều NGƯỜI NÓI) thành một
# câu tràng giang — giọng đọc lệch hẳn khỏi hình. 4 dòng ≈ 2-4s slot, vẫn đủ đọc.
MERGE_MAX_PIECES = 4
# V10 audit giọng: câu CỤT (1-2 chữ gọi tên, "叔叔?"...) — TTS không đọc tự nhiên được
# trong slot bé (viXTTS có sàn ~2.3s, đo được 1 từ ngân 3.6s → nén kịch trần vẫn tràn).
# Nhập vào câu bên cạnh khi đủ gần — nới gap rộng hơn MERGE_GAP_S thường.
TINY_CHARS = 2       # ≤ 2 ký tự CJK (bỏ dấu câu) coi là câu cụt
TINY_GAP_S = 0.8     # cách câu bên ≤ 0.8s thì nhập vào


def _is_junk(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if re.fullmatch(r"[\W_\d]+", t):
        return True  # toàn ký hiệu/số
    if t.startswith("[") and t.endswith("]"):
        return True  # chú thích màn hình kiểu [Master of Deception]
    if _CJK.search(t):
        return False  # chưa phân biệt được thoại/trang trí CJK — giữ lại
    # Latin toàn chữ HOA ngắn → logo/tiêu đề (=WUKONG=, HUKONG...)
    if not _LATIN_LOWER.search(t) and len(t) <= 30:
        return True
    return False


def _strip_recurrent_tokens(segments: list[dict]) -> list[dict]:
    """Cụm từ (tách theo khoảng trắng) có mặt trong >20% segment = watermark
    bị OCR ghép vào câu thoại — xóa khỏi mọi câu."""
    if len(segments) < 20:
        return segments
    seg_count = Counter()
    for s in segments:
        for tok in set(s["text"].split()):
            if len(tok) >= 2:
                seg_count[tok] += 1
    watermark = {t for t, c in seg_count.items() if c > 0.2 * len(segments)}
    if not watermark:
        return segments
    out = []
    for s in segments:
        text = " ".join(t for t in s["text"].split() if t not in watermark)
        if text.strip():
            s = dict(s)
            s["text"] = text
            out.append(s)
    return out


def clean_and_merge(segments: list[dict]) -> list[dict]:
    kept = [dict(s) for s in segments if not _is_junk(s["text"])]

    # text lặp y hệt nhiều lần thành segment riêng = logo/watermark trên hình
    # (câu thoại thật hiếm khi lặp nguyên văn ≥3 lần, trừ câu rất ngắn — giữ câu <3 ký tự)
    freq = Counter(s["text"].strip() for s in kept)
    kept = [s for s in kept
            if not (len(s["text"].strip()) >= 3 and freq[s["text"].strip()] >= 3)]

    kept = _strip_recurrent_tokens(kept)

    merged: list[dict] = []
    for seg in kept:
        if merged:
            last = merged[-1]
            gap = seg["start"] - last["end"]
            joined_len = len(last["text"]) + len(seg["text"]) + 1
            if (gap <= MERGE_GAP_S
                    and seg["end"] - last["start"] <= MERGE_MAX_DUR_S
                    and joined_len <= MERGE_MAX_CHARS
                    and len(last.get("pieces", ())) < MERGE_MAX_PIECES):
                # Giữ MỐC THỜI GIAN + độ dài chữ của TỪNG dòng gốc bị gộp — S8 dùng
                # để tách câu Việt hiển thị lại theo đúng nhịp sub gốc (sub_split),
                # trong khi giọng đọc vẫn hưởng câu gộp liền mạch.
                if "pieces" not in last:
                    last["pieces"] = [{"start": last["start"], "end": last["end"],
                                       "len": len(last["text"])}]
                last["pieces"].append({"start": seg["start"], "end": seg["end"],
                                       "len": len(seg["text"])})
                last["text"] = f"{last['text']} {seg['text']}"
                last["end"] = seg["end"]
                continue
        merged.append(seg)

    for i, seg in enumerate(merged, start=1):
        seg["id"] = i
    return merged


def _tiny(seg: dict) -> bool:
    """Câu cụt: ≤ TINY_CHARS ký tự thực (bỏ dấu câu/khoảng trắng)."""
    return len(re.sub(r"[\W_]", "", seg["text"])) <= TINY_CHARS


def absorb_tiny(segments: list[dict]) -> list[dict]:
    """V10 audit giọng: nhập câu CỤT vào câu hàng xóm gần nhất (gap ≤ TINY_GAP_S) rồi
    đánh lại id. Gọi ở S4 SAU speakers.assign (review đối kháng chỉ ra: đặt trong
    clean_and_merge của S3 thì seg chưa có key 'speaker' — guard chống trộn 2 người
    nói thành code chết). DIARIZE tắt → không speaker nào → nhập theo gap như thường;
    có speaker → cả 2 phía đều KHÁC người nói thì giữ nguyên câu cụt."""
    out = _absorb_tiny([dict(s) for s in segments])
    for i, seg in enumerate(out, start=1):
        seg["id"] = i
    return out


def _absorb_tiny(merged: list[dict]) -> list[dict]:
    out: list[dict] = []
    i = 0
    while i < len(merged):
        seg = merged[i]
        if not _tiny(seg):
            out.append(seg)
            i += 1
            continue

        def _same_spk(a: dict, b: dict) -> bool:
            return (a.get("speaker") or "") == (b.get("speaker") or "")

        prev = out[-1] if out else None
        nxt = merged[i + 1] if i + 1 < len(merged) else None
        gap_p = seg["start"] - prev["end"] if prev is not None else 99.0
        gap_n = nxt["start"] - seg["end"] if nxt is not None else 99.0
        ok_p = (prev is not None and gap_p <= TINY_GAP_S and _same_spk(prev, seg)
                and seg["end"] - prev["start"] <= MERGE_MAX_DUR_S)
        ok_n = (nxt is not None and gap_n <= TINY_GAP_S and _same_spk(seg, nxt)
                and nxt["end"] - seg["start"] <= MERGE_MAX_DUR_S)
        if ok_p and (not ok_n or gap_p <= gap_n):     # nhập về TRƯỚC (gần hơn)
            if "pieces" not in prev:
                prev["pieces"] = [{"start": prev["start"], "end": prev["end"],
                                   "len": len(prev["text"])}]
            prev["pieces"].append({"start": seg["start"], "end": seg["end"],
                                   "len": len(seg["text"])})
            prev["text"] = f"{prev['text']} {seg['text']}"
            prev["end"] = seg["end"]
            i += 1
        elif ok_n:                                    # nhập về SAU
            nxt = dict(nxt)
            pieces = [{"start": seg["start"], "end": seg["end"], "len": len(seg["text"])}]
            pieces += nxt.get("pieces") or [{"start": nxt["start"], "end": nxt["end"],
                                             "len": len(nxt["text"])}]
            nxt["pieces"] = pieces
            nxt["text"] = f"{seg['text']} {nxt['text']}"
            nxt["start"] = seg["start"]
            merged[i + 1] = nxt
            i += 1
        else:
            out.append(seg)
            i += 1
    return out
