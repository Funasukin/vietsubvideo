"""PLAN 12 #4 — SHORTS TỰ ĐỘNG: cắt 2–3 đoạn CAO TRÀO từ final.mp4 → video dọc ≤60s.

Chấm điểm cao trào cho từng câu bằng tín hiệu ĐÃ CÓ SẴN trong transcript
(không tốn call API nào):
  - nhãn cảm xúc (PLAN 11 mức 2): gấp/giận = kịch tính (+2), buồn/thì thầm (+1)
  - tông giọng đo audio (mức 1): nói to (+vol) / lên giọng (+pitch) / dồn dập (+rate)
  - mật độ thoại: nhiều câu sát nhau = phân cảnh sôi động
Trượt cửa sổ SHORTS_LEN giây trên timeline → chọn SHORTS_COUNT cửa sổ điểm cao
nhất KHÔNG chồng lấn (cách nhau ≥15s), mép cắt bám mép câu thoại (không cắt
ngang câu). Job cũ không có nhãn/tông giọng → điểm chỉ còn mật độ thoại (vẫn chạy).

Xuất: <job>/shorts/short_N.mp4 + info.txt (mốc thời gian + caption gợi ý kèm
#Shorts). SHORTS_STYLE=vertical: 9:16 1080x1920 — video gốc thu vào giữa, nền là
chính nó phóng to + làm mờ (kiểu Shorts phổ biến); original: giữ nguyên khung hình.
Cắt từ final.mp4 (đã lồng tiếng + phụ đề) nên Shorts có sẵn tiếng Việt + sub.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import config
from core import ffmpeg

_MIN_GAP_S = 15.0     # hai short phải cách nhau tối thiểu (tránh 2 clip na ná)
_PAD_S = 0.75         # nới mép cắt quanh câu thoại


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _seg_score(seg: dict) -> float:
    """Điểm 'cao trào' của 1 câu từ nhãn cảm xúc + tông giọng đo audio."""
    if not (seg.get("text_vi") or "").strip():
        return 0.0
    score = 1.0                                   # có thoại = có nhịp
    emo = (seg.get("emotion") or "").strip().lower()
    if emo in ("gap", "gian"):
        score += 2.0                              # kịch tính rõ
    elif emo in ("buon", "thitham"):
        score += 1.0                              # cao trào cảm xúc trầm
    pro = seg.get("prosody") or {}
    if pro.get("vol_pct", 0) >= 8:
        score += 1.5                              # quát/gào
    if pro.get("pitch_hz", 0) >= 10:
        score += 1.0                              # lên giọng
    if pro.get("rate_pct", 0) >= 8:
        score += 0.5                              # nói dồn
    return score


def pick_windows(segments: list[dict], duration: float,
                 count: int, length: float) -> list[dict]:
    """Chọn `count` cửa sổ `length` giây điểm cao nhất, không chồng lấn.
    Trả [{start, end, score, text}] theo thứ tự thời gian."""
    segs = [s for s in segments if (s.get("text_vi") or "").strip()
            and not s.get("mute")]
    if not segs:
        return []
    scores = [(s, _seg_score(s)) for s in segs]

    # ứng viên: cửa sổ bắt đầu tại mỗi câu (trừ lead-in) — mép bám thoại tự nhiên
    cands = []
    for i, (anchor, _) in enumerate(scores):
        w_start = max(0.0, anchor["start"] - _PAD_S)
        w_end = min(duration, w_start + length)
        if w_end - w_start < min(15.0, length * 0.6):
            continue                              # sát cuối video, quá ngắn
        inside = [(s, sc) for s, sc in scores
                  if s["start"] >= w_start and s["end"] <= w_end + 0.01]
        if not inside:
            continue
        total = sum(sc for _, sc in inside)
        last_end = max(s["end"] for s, _ in inside)
        cands.append({"start": round(w_start, 2),
                      "end": round(min(duration, last_end + _PAD_S), 2),
                      "score": round(total, 2),
                      "text": " ".join((s.get("text_vi") or "") for s, _ in inside[:3])})
    if not cands:
        return []

    # tham lam: điểm cao trước, bỏ ứng viên chồng lấn/quá gần cái đã chọn
    cands.sort(key=lambda c: -c["score"])
    chosen: list[dict] = []
    for c in cands:
        if len(chosen) >= count:
            break
        if all(c["start"] >= p["end"] + _MIN_GAP_S or c["end"] <= p["start"] - _MIN_GAP_S
               for p in chosen):
            chosen.append(c)
    chosen.sort(key=lambda c: c["start"])
    return chosen


# 9:16 kiểu Shorts phổ biến: nền = chính video phóng to + mờ, hình chính thu giữa
_VERTICAL_VF = ("split[a][b];"
                "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,gblur=sigma=18[bg];"
                "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def _cut(src: Path, start: float, dur: float, out: Path, vertical: bool) -> None:
    base = ["-ss", f"{start:.2f}", "-i", str(src), "-t", f"{dur:.2f}"]
    vf = ["-filter_complex", _VERTICAL_VF] if vertical else []
    tail = ["-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero", str(out)]
    try:
        ffmpeg.run(*base, *vf, *ffmpeg.h264_args(), *tail)   # NVENC/QSV/x264 dò theo máy
    except RuntimeError:
        ffmpeg.run(*base, *vf, "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "21", *tail)


def generate(job) -> list[Path]:
    """Tạo Shorts cho job đã render. Trả list file đã tạo (ghi đè bộ cũ)."""
    final = job.dir / "final.mp4"
    if not final.exists():
        raise RuntimeError("Chưa có final.mp4 (job chưa render xong)")
    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    duration = _duration(final)
    count = max(1, min(5, int(getattr(config, "SHORTS_COUNT", 2))))
    length = max(20.0, min(60.0, float(getattr(config, "SHORTS_LEN", 45))))
    vertical = str(getattr(config, "SHORTS_STYLE", "vertical")).lower() != "original"

    wins = pick_windows(data["segments"], duration, count, length)
    if not wins:
        raise RuntimeError("Không tìm được đoạn thoại nào để cắt Shorts")

    out_dir = job.dir / "shorts"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("short_*.mp4"):
        old.unlink(missing_ok=True)

    # caption gợi ý: lấy title metadata nếu có
    title = ""
    meta_p = job.dir / "metadata.json"
    if meta_p.exists():
        try:
            title = json.loads(meta_p.read_text(encoding="utf-8")).get("title", "")
        except (OSError, json.JSONDecodeError):
            pass

    made, lines = [], []
    for i, w in enumerate(wins, 1):
        out = out_dir / f"short_{i}.mp4"
        _cut(final, w["start"], w["end"] - w["start"], out, vertical)
        if out.exists() and out.stat().st_size > 10_000:
            made.append(out)
            mm = lambda t: f"{int(t) // 60}:{int(t) % 60:02d}"
            cap = (title + " — " if title else "") + (w["text"][:80] or "đoạn cao trào")
            lines.append(f"short_{i}.mp4  [{mm(w['start'])}–{mm(w['end'])}]  "
                         f"điểm {w['score']}\n  caption gợi ý: {cap} #Shorts\n")
        else:
            out.unlink(missing_ok=True)
    if made:
        (out_dir / "info.txt").write_text(
            "SHORTS tự cắt từ final.mp4 (đã có lồng tiếng + phụ đề)\n\n"
            + "\n".join(lines), encoding="utf-8")
    return made
