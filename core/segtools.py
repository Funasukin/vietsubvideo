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
                    and joined_len <= MERGE_MAX_CHARS):
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
