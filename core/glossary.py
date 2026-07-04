"""Bảng tên riêng (glossary) — sửa lỗi nghe nhầm tên/tông môn/công pháp/cảnh giới.

Dùng ở 2 chốt:
  1) initial_prompt cho Whisper → ASR nghe ĐÚNG chữ Hán gốc thay vì đồng âm.
  2) chèn vào prompt dịch Claude → dùng tên Hán-Việt nhất quán + tự sửa đồng âm.

glossary lưu dạng text nhiều dòng: "中文=Hán-Việt" (mỗi dòng 1 cặp). Dòng chỉ có
tên Hán (không "=") vẫn dùng cho Whisper. Dòng trống / bắt đầu '#' bị bỏ qua.
"""
from __future__ import annotations

import json
import re

import anthropic

_CJK = re.compile(r"[一-鿿㐀-䶿]")


def parse(text: str) -> list[tuple[str, str]]:
    """text → list[(zh, vi)]; vi='' nếu dòng chỉ có tên Hán."""
    pairs: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            zh, vi = line.split("=", 1)
            zh, vi = zh.strip(), vi.strip()
        else:
            zh, vi = line, ""
        if zh:
            pairs.append((zh, vi))
    return pairs


def whisper_prompt(text: str) -> str | None:
    """initial_prompt cho Whisper: liệt kê tên Hán để ASR nghe đúng (None nếu rỗng)."""
    zhs = [z for z, _ in parse(text) if _CJK.search(z)]
    zhs = list(dict.fromkeys(zhs))  # bỏ trùng, giữ thứ tự
    if not zhs:
        return None
    return "本视频包含以下专有名词：" + "、".join(zhs) + "。"


def claude_block(pairs: list[tuple[str, str]]) -> str:
    """list[(zh,vi)] → đoạn chèn vào system prompt dịch (rỗng nếu không có cặp đủ)."""
    lines = [f"{z} = {v}" for z, v in pairs if v][:300]  # cap phòng glossary rác
    if not lines:
        return ""
    return ("\n\nBẢNG TÊN RIÊNG (BẮT BUỘC dùng đúng và nhất quán toàn bộ; nếu gặp "
            "chữ gần-ĐỒNG ÂM với một tên trong bảng — do nghe nhầm — hãy SỬA về "
            "tên trong bảng):\n" + "\n".join(lines))


def merged(manual_text: str, auto_pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Gộp tự-trích + thủ công; cùng zh thì THỦ CÔNG (người nhập) thắng."""
    out: dict[str, str] = {}
    for z, v in auto_pairs:
        if v:
            out[z] = v
    for z, v in parse(manual_text):
        if v:
            out[z] = v  # thủ công ghi đè tự trích
    return list(out.items())


# ---------- Tự trích bằng Claude ----------

_AUTO_SYSTEM = """Bạn trích DANH TỪ RIÊNG từ transcript phim hoạt hình Trung Quốc (donghua tu tiên/huyền huyễn): tên nhân vật, tông môn/gia tộc, công pháp/chiêu thức, cảnh giới/cấp bậc, pháp bảo, địa danh.

Với mỗi mục cho:
- zh: tên gốc tiếng Trung đúng như xuất hiện.
- vi: tên Hán-Việt chuẩn mà cộng đồng dịch donghua hay dùng (叶凡→Diệp Phàm, 斗气→đấu khí, 武魂→vũ hồn).

Chỉ lấy danh từ riêng QUAN TRỌNG/LẶP LẠI, bỏ từ thường. Tối đa 40 mục. Bỏ qua nếu transcript không phải tiếng Trung."""

# Bản CHUNG: nguồn mọi ngôn ngữ, đích theo TARGET_LANG (không ép Hán-Việt/donghua)
_AUTO_SYSTEM_GENERIC = """Bạn trích DANH TỪ RIÊNG từ transcript video (bất kỳ ngôn ngữ nguồn nào): tên người, nhân vật, tổ chức/thương hiệu, địa danh, thuật ngữ riêng lặp lại.

Với mỗi mục cho:
- zh: tên gốc ĐÚNG như xuất hiện trong transcript (giữ nguyên ngôn ngữ gốc).
- vi: cách dịch/phiên âm chuẩn, quen thuộc sang {LANG} (tên quốc tế thường giữ nguyên).

Chỉ lấy danh từ riêng QUAN TRỌNG/LẶP LẠI, bỏ từ thường. Tối đa 40 mục."""

_AUTO_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "zh": {"type": "string"},
                    "vi": {"type": "string"},
                },
                "required": ["zh", "vi"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["terms"],
    "additionalProperties": False,
}


def auto_extract(client: anthropic.Anthropic,
                 segments: list[dict], generic: bool = False,
                 lang_name: str = "tiếng Việt") -> list[tuple[str, str]]:
    """Claude đọc transcript → trích tên riêng + bản dịch. Lỗi thì trả [].
    generic=True: nguồn mọi ngôn ngữ, đích lang_name (không CJK gate/không ép Hán-Việt)."""
    text = "\n".join(s.get("text", "") for s in segments)
    if not generic and not _CJK.search(text):
        return []  # prompt donghua chỉ hợp transcript tiếng Trung → bỏ
    text = text[:20000]  # đủ để bắt tên lặp lại, giữ chi phí thấp
    system = (_AUTO_SYSTEM_GENERIC.replace("{LANG}", lang_name) if generic
              else _AUTO_SYSTEM)
    try:
        from core import llm
        out = llm.structured_json(
            system, "Trích danh từ riêng từ transcript sau:\n" + text,
            _AUTO_SCHEMA, max_tokens=2000, client=client)
        terms = json.loads(out)["terms"]
    except Exception as e:
        print(f"  ! auto_extract glossary lỗi (bỏ qua): {e}")
        return []
    return [(t["zh"].strip(), t["vi"].strip()) for t in terms
            if t.get("zh", "").strip() and t.get("vi", "").strip()]
