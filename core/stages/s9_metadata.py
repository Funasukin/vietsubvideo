"""S9: sinh metadata đăng bài + thumbnail → metadata.json + thumbnail.jpg.

Metadata do Claude viết từ bản dịch: title giật view, description + CHƯƠNG (timestamp)
+ hashtag, tags, 2 dòng hook cho thumbnail. Văn phong theo CONTENT_STYLE (donghua vs
mọi thể loại). Thumbnail: core/thumbnail.py. Chạy cho mọi job (kit đăng tay/tự động).
"""
from __future__ import annotations

import json

import anthropic

import config
from core import thumbnail
from core.job import Job

# Văn phong metadata theo kiểu nội dung
SYSTEM_DONGHUA = """Bạn làm metadata YouTube cho kênh donghua (phim hoạt hình Trung) lồng tiếng Việt.
Văn phong giật gân kiểu truyện tu tiên/hệ thống. hook_lines viết hoa kiểu "TA LÀ THẠCH HẦU ĐẠI VƯƠNG" / "PHẾ VẬT THỨC TỈNH"."""

SYSTEM_GENERAL = """Bạn làm metadata YouTube cho video lồng tiếng Việt, thể loại BẤT KỲ (phim, hoạt hình, tài liệu, vlog, giải trí...).
Văn phong hấp dẫn, tự nhiên, ĐÚNG thể loại nội dung (không ép giọng kiếm hiệp). hook_lines ngắn gọn, gây tò mò, viết hoa."""

_COMMON = """
Từ bản dịch (kèm mốc thời gian [phút:giây]) hãy viết:
- title: tiêu đề YouTube 50-90 ký tự, giật view, gây tò mò, KHÔNG khô khan.
- description: 3-5 câu tóm tắt hấp dẫn, KHÔNG spoil kết.
- tags: 10-15 tag tiếng Việt liên quan (+ tên gốc/pinyin nếu nhận ra).
- hashtags: 3-6 hashtag (không kèm dấu #, mình tự thêm), vd "phimhay", "longtiengviet".
- chapters: 3-6 chương chia theo nội dung, mỗi chương {start (GIÂY, số nguyên, chương ĐẦU = 0), title ngắn}. start phải TĂNG DẦN và nằm trong độ dài video.
- hook_lines: ĐÚNG 2 dòng in lên thumbnail, mỗi dòng ≤ 22 ký tự, viết hoa.
- summary: 1 câu tóm tắt nội dung (để chọn frame thumbnail)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"start": {"type": "integer"}, "title": {"type": "string"}},
                "required": ["start", "title"],
                "additionalProperties": False,
            },
        },
        "hook_lines": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["title", "description", "tags", "hashtags", "chapters",
                 "hook_lines", "summary"],
    "additionalProperties": False,
}


def _mmss(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def _timed_dialogue(segments: list[dict], limit: int = 6000) -> str:
    """Thoại kèm [phút:giây] để Claude chia chương đúng mốc; lấy thưa nếu quá dài."""
    lines = [f"[{_mmss(s['start'])}] {s['text_vi']}" for s in segments if s.get("text_vi")]
    text = "\n".join(lines)
    if len(text) <= limit and len(lines) <= 240:
        return text
    step = max(1, len(lines) // 240)   # lấy thưa đều để giữ trải thời gian
    return "\n".join(lines[::step])[:limit]


def _compose_description(meta: dict, duration: float) -> str:
    """Ghép mô tả + CHƯƠNG (timestamp, để YouTube tự nhận) + hashtag."""
    parts = [meta.get("description", "").strip()]

    chapters = []
    for c in meta.get("chapters", []):
        try:
            st = int(c.get("start", 0))
        except (TypeError, ValueError):
            continue
        title = (c.get("title") or "").strip()
        if title and 0 <= st < max(1, duration):
            chapters.append((st, title))
    chapters = sorted(set(chapters))
    # YouTube cần chương ĐẦU = 0:00 và ≥ 3 chương mới hiện; đảm bảo mốc đầu là 0
    if chapters and chapters[0][0] != 0:
        chapters = [(0, chapters[0][1])] + chapters[1:]
    if len(chapters) >= 3:
        parts.append("⏱ Nội dung:\n" + "\n".join(f"{_mmss(st)} {t}" for st, t in chapters))

    tags = meta.get("hashtags", [])
    if isinstance(tags, list) and tags:
        hs = " ".join("#" + t.strip().lstrip("#").replace(" ", "") for t in tags if t.strip())
        if hs:
            parts.append(hs)

    from core import langs
    parts.append("Video được dịch và lồng tiếng tự động." if langs.is_vi()
                 else "Auto-translated & dubbed video.")
    return "\n\n".join(p for p in parts if p)


def run(job: Job) -> None:
    meta_path = job.dir / "metadata.json"
    thumb_path = job.dir / "thumbnail.jpg"
    if meta_path.exists() and thumb_path.exists():
        return

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    segments = data["segments"]
    duration = max((s.get("end", 0) for s in segments), default=0)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
    if not meta_path.exists() or "title" not in meta:
        from core import langs
        system = SYSTEM_DONGHUA if config.CONTENT_STYLE == "donghua" else SYSTEM_GENERAL
        if not langs.is_vi():   # #16 metadata cùng ngôn ngữ với bản lồng tiếng
            system = SYSTEM_GENERAL + (f"\nQUAN TRỌNG: viết TOÀN BỘ title, description, "
                                       f"tags, hashtags, hook_lines, chapters, summary "
                                       f"bằng {langs.name()} (khớp ngôn ngữ lồng tiếng).")
        resp = client.messages.create(
            model=config.METADATA_MODEL,
            max_tokens=2500,
            system=system + _COMMON,
            messages=[{"role": "user", "content":
                       f"Độ dài video ~{_mmss(duration)}. Thoại tập phim:\n"
                       + _timed_dialogue(segments)}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        meta = json.loads(text)
        # ghép mô tả đầy đủ (chương + hashtag) để đăng tay/tự động dùng thẳng
        meta["description"] = _compose_description(meta, duration)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    if not thumb_path.exists():
        thumbnail.generate(
            video=job.find_source(),
            work_dir=job.dir,
            hook_lines=meta.get("hook_lines", [])[:2],
            summary=meta.get("summary", meta.get("title", "")),
            client=client,
            avoid_spans=[(s["start"], s["end"]) for s in segments],
        )
