"""Đo tốc độ đọc edge-tts theo nền TTS_BASE_SPEED (đợt T — DEXUAT_TOCDO_GIONGDOC).

Corpus 16 câu × 4 nhóm (ngắn / vừa / dài / số-tên riêng) × các mức nền × 2 giọng
→ đo âm tiết/giây trên thước ĐÃ CẮT LẶNG (duration.trimmed_dur_s — cùng thước
pipeline). In bảng median + phân tán để chọn mức kênh bằng số liệu thay vì 1 câu.

Chạy:  .venv\\Scripts\\python.exe -X utf8 scripts\\bench_speech_rate.py
       thêm --samples để sinh bộ NGHE MÙ A/B/C (1.2/1.3/1.4 xáo trộn)
       vào voice_samples/nghe_mu/ (mapping giấu trong _dapan.txt).
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import edge_tts

from core import duration

# 4 nhóm câu theo checklist Codex (mục 6 TONGHOP): ngắn, vừa, dài, số/tên/dấu câu
CORPUS = {
    "ngắn": [
        "Đi đâu?",
        "Có bất thường.",
        "Niệm Bảo, nhanh lên!",
        "Sao lại là cậu!",
    ],
    "vừa": [
        "Vợ tôi chạy trốn, có tính là bất thường không?",
        "Cứ mặt lạnh tanh như chết, trông như ai nợ anh tiền vậy.",
        "Đúng lúc để trốn thoát, cổng thành đêm nay không khóa.",
        "Để tôi giúp bạn tìm người, chuyện nhỏ thôi mà.",
    ],
    "dài": [
        "Tạ Chuẩn An và Tạ Hoài Cẩm đã đi Kim Ngô Vệ trực đêm, chúng ta đi ngay bây giờ kẻo không kịp.",
        "Tôi vất vả lắm mới kiếm được số châu báu và tiền bạc này, lũ trộm vặt lại dám không làm mà hưởng.",
        "Nếu ngày mai trời không mưa thì cả đoàn sẽ xuất phát từ sáng sớm, băng qua cánh rừng phía bắc để đến trấn cũ.",
        "Chuyện này nói ra thì dài, nhưng tóm lại là không ai trong số họ chịu nhận trách nhiệm về mình cả.",
    ],
    "số-tên": [
        "Năm 2026, Tạ Chuẩn An thu về 1500 lượng bạc.",
        "Cấp SSS chỉ có 3 người: Diệp Phàm, Tiêu Viêm và Na Tra.",
        "Đúng 7 giờ 30 phút sáng ngày 15 tháng 8, đoàn xe rời khỏi Kim Ngô Vệ.",
        "Mật khẩu là B7, nhắc lại, B7, không phải D3.",
    ],
}
VOICES = ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"]
LEVELS = [1.0, 1.2, 1.3, 1.4, 1.5]
OUT = Path(__file__).resolve().parents[1] / "voice_samples" / "nghe_mu"


async def _synth(text: str, voice: str, level: float, path: Path) -> float | None:
    rate = duration.edge_total_rate(0, level)
    await edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(str(path))
    return duration.trimmed_dur_s(path)


async def bench() -> None:
    tmp = OUT.parent / "_bench_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(6)
    results: dict = {}   # (voice, level) -> list[(nhóm, syll/s)]

    async def one(text: str, group: str, voice: str, level: float) -> None:
        p = tmp / f"b_{abs(hash((text, voice, level))) % 10**10}.mp3"
        async with sem:
            for attempt in range(3):
                try:
                    d = await _synth(text, voice, level, p)
                    break
                except Exception:
                    if attempt == 2:
                        return
                    await asyncio.sleep(2)
        if d:
            syl = duration.syllables(text)
            results.setdefault((voice, level), []).append((group, syl / d))
        p.unlink(missing_ok=True)

    tasks = [one(t, g, v, lv) for g, ts in CORPUS.items() for t in ts
             for v in VOICES for lv in LEVELS]
    await asyncio.gather(*tasks)

    print(f"{'giọng':<24}{'mức':>5} {'median':>7} {'min':>6} {'max':>6} "
          f"{'phân tán':>9}  âm tiết/giây (16 câu)")
    for v in VOICES:
        for lv in LEVELS:
            rows = [r[1] for r in results.get((v, lv), [])]
            if not rows:
                continue
            med = statistics.median(rows)
            spread = statistics.pstdev(rows)
            print(f"{v:<24}{lv:>5} {med:>7.2f} {min(rows):>6.2f} "
                  f"{max(rows):>6.2f} {spread:>9.2f}")
        # nhóm câu ngắn riêng — nơi Codex cảnh báo cụt phụ âm
        for lv in LEVELS:
            rows = [r[1] for r in results.get((v, lv), []) if r[0] == "ngắn"]
            if rows:
                print(f"    câu NGẮN mức {lv}: median {statistics.median(rows):.2f} âm/s")


async def samples() -> None:
    """Bộ nghe mù: 1 đoạn ghép (ngắn+vừa+dài+số) × 3 mức 1.2/1.3/1.4, nhãn A/B/C
    xáo trộn cố định — đáp án trong _dapan.txt (đừng mở trước khi nghe!)."""
    import random
    OUT.mkdir(parents=True, exist_ok=True)
    text = " ".join(CORPUS["ngắn"][:2] + [CORPUS["vừa"][0], CORPUS["dài"][0],
                                          CORPUS["số-tên"][0]])
    levels = [1.2, 1.3, 1.4]
    labels = ["A", "B", "C"]
    rng = random.Random(20260712)          # cố định để tái lập
    order = levels[:]
    rng.shuffle(order)
    lines = []
    for voice_tag, voice in (("HoaiMy", "vi-VN-HoaiMyNeural"),
                             ("NamMinh", "vi-VN-NamMinhNeural")):
        for lab, lv in zip(labels, order):
            p = OUT / f"{voice_tag}_{lab}.mp3"
            await _synth(text, voice, lv, p)
            lines.append(f"{voice_tag}_{lab}.mp3 = nền {lv}")
            print("  đã tạo", p.name)
    (OUT / "_dapan.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ {OUT} (đáp án: _dapan.txt — nghe xong hãy mở)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", action="store_true", help="sinh bộ nghe mù A/B/C")
    args = ap.parse_args()
    asyncio.run(samples() if args.samples else bench())
