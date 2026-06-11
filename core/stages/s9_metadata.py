"""S9: sinh metadata đăng bài + thumbnail → metadata.json + thumbnail.jpg.

Metadata do Claude viết từ bản dịch (title giật đúng thể loại, description,
tags, 2 dòng chữ hook cho thumbnail). Thumbnail: core/thumbnail.py.
Chạy cho mọi job (kit đăng tay khi chưa có Phase 3 upload tự động).
"""
from __future__ import annotations

import json

import anthropic

import config
from core import thumbnail
from core.job import Job

SYSTEM = """Bạn làm metadata YouTube cho kênh donghua lồng tiếng Việt.
Từ bản dịch tập phim, viết:
- title: tiêu đề YouTube giật đúng kiểu kênh truyện tu tiên/hệ thống, 60-90 ký tự, có thể dùng cấu trúc "Bị Coi Thường..., Ta ..." / cliffhanger; KHÔNG dùng tên tập khô khan.
- description: 3-5 câu tóm tắt hấp dẫn + dòng "Video được dịch và lồng tiếng tự động." Không spoil kết.
- tags: 10-15 tag tiếng Việt + pinyin tên phim nếu nhận ra.
- hook_lines: ĐÚNG 2 dòng chữ in lên thumbnail, mỗi dòng ≤ 22 ký tự, viết hoa, giật gân kiểu "TA LÀ THẠCH HẦU ĐẠI VƯƠNG" / "PHẾ VẬT THỨC TỈNH"."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "hook_lines": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["title", "description", "tags", "hook_lines", "summary"],
    "additionalProperties": False,
}


def run(job: Job) -> None:
    meta_path = job.dir / "metadata.json"
    thumb_path = job.dir / "thumbnail.jpg"
    if meta_path.exists() and thumb_path.exists():
        return

    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    dialogue = " | ".join(s["text_vi"] for s in data["segments"])[:6000]

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not meta_path.exists() or "title" not in meta:
        resp = client.messages.create(
            model=config.METADATA_MODEL,
            max_tokens=2000,
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       "Toàn bộ thoại tập phim:\n" + dialogue
                       + "\n\nThêm trường summary: 1 câu tóm tắt nội dung để chọn frame thumbnail."}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        meta = json.loads(text)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                             encoding="utf-8")

    if not thumb_path.exists():
        thumbnail.generate(
            video=job.find_source(),
            work_dir=job.dir,
            hook_lines=meta.get("hook_lines", [])[:2],
            summary=meta.get("summary", meta.get("title", "")),
            client=client,
            avoid_spans=[(s["start"], s["end"]) for s in data["segments"]],
        )
