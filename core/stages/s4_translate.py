"""S4: dịch transcript sang tiếng Việt bằng Claude API → transcript_vi.json.

Gửi theo batch, kèm vài câu đã dịch của batch trước làm ngữ cảnh.
Dùng structured output (json_schema) để đảm bảo parse được 100%.
"""
from __future__ import annotations

import json
import re

import anthropic

import config
from core.job import Job

_CJK_RE = re.compile(r"[一-鿿㐀-䶿]")
_LEAK_NOTE = ("\nLƯU Ý ĐẶC BIỆT: lần dịch trước các câu này còn SÓT KÝ TỰ TRUNG QUỐC. "
              "Dịch lại HOÀN TOÀN sang tiếng Việt — mọi từ Hán phải thành nghĩa Việt "
              "hoặc âm Hán-Việt (ví dụ 祭品 → vật tế, 部落 → bộ lạc).")

SYSTEM = """Bạn là dịch giả chuyên nghiệp chuyên dịch phim/truyện Trung Quốc (tu tiên, hệ thống, đô thị) và video tiếng nước ngoài sang tiếng Việt để lồng tiếng kiểu thuyết minh.

Quy tắc:
- Dịch tự nhiên như lời nói, KHÔNG dịch word-by-word. Câu ngắn gọn vì sẽ được đọc bằng TTS theo timing gốc.
- XƯNG HÔ: bối cảnh cổ trang/tu tiên dùng nhất quán "ngươi/ta" (ngang hàng), "ngài/tại hạ" (kính trọng), "huynh/đệ/muội". TUYỆT ĐỐI không dùng "bạn/tôi/anh ấy" trong bối cảnh cổ trang.
- Tên riêng Trung Quốc chuyển sang âm Hán-Việt (叶凡 → Diệp Phàm, 萧炎 → Tiêu Viêm, 萧公子 → Tiêu công tử).
- Tên phiên âm pinyin trong sub tiếng Anh cũng chuyển về Hán-Việt quen thuộc: Wukong → Ngộ Không, Tang Monk/Tang Seng → Đường Tăng, Bajie → Bát Giới, Wujing → Ngộ Tĩnh, Nezha → Na Tra, Erlang → Nhị Lang.
- Hán-Việt chuẩn kiếm hiệp: 刀 → đao (KHÔNG phải "dao"), 剑 → kiếm, 无赖 → vô lại, 灵气 → linh khí, 突破 → đột phá, 废物 → phế vật, SSS级 → cấp SSS.
- Giữ nguyên số, tên cấp bậc dạng chữ cái (E, SSS...).
- Tuyệt đối không để sót ký tự Trung/Anh trong bản dịch (trừ tên cấp bậc).
- Mỗi segment dịch độc lập đúng theo id, không gộp, không tách."""

SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "text_vi": {"type": "string"},
                },
                "required": ["id", "text_vi"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}


def _translate_batch(client: anthropic.Anthropic, batch: list[dict],
                     context: list[tuple[str, str]],
                     extra_note: str = "") -> dict[int, str]:
    parts = []
    if context:
        ctx = "\n".join(f"- {src} → {vi}" for src, vi in context)
        parts.append(f"Ngữ cảnh (các câu ngay trước, đã dịch):\n{ctx}\n")
    payload = [{"id": s["id"], "text": s["text"]} for s in batch]
    parts.append("Dịch các segment sau sang tiếng Việt:"
                 + extra_note + "\n"
                 + json.dumps(payload, ensure_ascii=False))

    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "\n".join(parts)}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    result = {seg["id"]: seg["text_vi"] for seg in json.loads(text)["segments"]}

    missing = [s["id"] for s in batch if s["id"] not in result]
    if missing:
        raise RuntimeError(f"Claude bỏ sót segment id: {missing}")
    return result


def fix_leaks(client: anthropic.Anthropic, by_id: dict[int, dict],
              translated: dict[int, str], attempts: int = 2) -> None:
    """Dịch lại các câu còn sót ký tự Trung (Haiku thỉnh thoảng bỏ sót từ khó)."""
    for _ in range(attempts):
        bad_ids = [i for i, vi in translated.items() if _CJK_RE.search(vi)]
        if not bad_ids:
            return
        batch = [by_id[i] for i in bad_ids]
        translated.update(_translate_batch(client, batch, [], extra_note=_LEAK_NOTE))
    remaining = [i for i, vi in translated.items() if _CJK_RE.search(vi)]
    if remaining:
        print(f"  ! Còn {len(remaining)} câu sót ký tự Trung sau retry: {remaining}")


def run(job: Job) -> None:
    out_path = job.dir / "transcript_vi.json"
    if out_path.exists():
        return

    data = json.loads((job.dir / "transcript_zh.json").read_text(encoding="utf-8"))
    segments = data["segments"]

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    translated: dict[int, str] = {}
    by_id = {s["id"]: s for s in segments}

    size = config.TRANSLATE_BATCH_SIZE
    for start in range(0, len(segments), size):
        batch = segments[start:start + size]
        # context = N câu cuối đã dịch của batch trước
        prev_ids = sorted(translated)[-config.TRANSLATE_BATCH_OVERLAP:]
        context = [(by_id[i]["text"], translated[i]) for i in prev_ids]
        translated.update(_translate_batch(client, batch, context))

    fix_leaks(client, by_id, translated)

    for seg in segments:
        seg["text_vi"] = translated[seg["id"]]

    out_path.write_text(
        json.dumps({"language": data.get("language"), "segments": segments},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
