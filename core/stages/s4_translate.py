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


def _leak_note(lang_name: str) -> str:
    if lang_name == "tiếng Việt":
        return _LEAK_NOTE
    return ("\nLƯU Ý ĐẶC BIỆT: lần dịch trước các câu này còn SÓT ký tự của ngôn ngữ "
            f"gốc. Dịch lại HOÀN TOÀN sang {lang_name}, không để sót từ chưa dịch.")

SYSTEM = """Bạn là dịch giả chuyên nghiệp chuyên dịch phim/truyện Trung Quốc (tu tiên, hệ thống, đô thị) và video tiếng nước ngoài sang tiếng Việt để lồng tiếng kiểu thuyết minh.

Quy tắc:
- Dịch tự nhiên như lời nói, KHÔNG dịch word-by-word. Câu ngắn gọn vì sẽ được đọc bằng TTS theo timing gốc.
- XƯNG HÔ: bối cảnh cổ trang/tu tiên dùng nhất quán "ngươi/ta" (ngang hàng), "ngài/tại hạ" (kính trọng), "huynh/đệ/muội". TUYỆT ĐỐI không dùng "bạn/tôi/anh ấy" trong bối cảnh cổ trang.
- Tên riêng Trung Quốc chuyển sang âm Hán-Việt (叶凡 → Diệp Phàm, 萧炎 → Tiêu Viêm, 萧公子 → Tiêu công tử).
- Tên phiên âm pinyin trong sub tiếng Anh cũng chuyển về Hán-Việt quen thuộc: Wukong → Ngộ Không, Tang Monk/Tang Seng → Đường Tăng, Bajie → Bát Giới, Wujing → Ngộ Tĩnh, Nezha → Na Tra, Erlang → Nhị Lang.
- Hán-Việt chuẩn kiếm hiệp: 刀 → đao (KHÔNG phải "dao"), 剑 → kiếm, 无赖 → vô lại, 灵气 → linh khí, 突破 → đột phá, 废物 → phế vật, SSS级 → cấp SSS.
- Giữ nguyên số, tên cấp bậc dạng chữ cái (E, SSS...).
- Tuyệt đối không để sót ký tự Trung/Anh trong bản dịch (trừ tên cấp bậc).
- Mỗi segment dịch độc lập đúng theo id, không gộp, không tách.
- Mỗi segment xác định người nói qua trường "voice": "nam" hoặc "nu" — suy từ ngữ cảnh (tên nhân vật, xưng hô, nội dung thoại). Lời dẫn chuyện, tiêu đề, credit, hoặc không chắc chắn → "nam"."""

# Văn phong CHUNG: mọi thể loại / mọi ngôn ngữ nguồn (không ép Hán-Việt/cổ trang)
GENERAL_SYSTEM = """Bạn là dịch giả chuyên nghiệp, dịch phụ đề/thoại video sang tiếng Việt để lồng tiếng kiểu thuyết minh. Nội dung có thể là BẤT KỲ thể loại (phim, hoạt hình, tài liệu, vlog, tin tức, giải trí, giáo dục...) và BẤT KỲ ngôn ngữ nguồn nào.

Quy tắc:
- Dịch TỰ NHIÊN như lời nói người Việt, KHÔNG dịch word-by-word. Câu ngắn gọn vì sẽ đọc bằng TTS theo timing gốc.
- Xưng hô HIỆN ĐẠI, phù hợp ngữ cảnh (tôi/bạn/anh/chị/em/ông/bà/mình/cậu...), suy từ quan hệ nhân vật. Chỉ dùng lối cổ trang/kiếm hiệp nếu nội dung RÕ RÀNG là cổ trang.
- Tên riêng, thương hiệu, địa danh, thuật ngữ nước ngoài: giữ NGUYÊN gốc hoặc phiên âm quen thuộc với người Việt; KHÔNG ép sang Hán-Việt.
- Dịch đúng nghĩa thuật ngữ chuyên ngành; giữ nguyên số, đơn vị, mã/cấp bậc dạng chữ-số.
- Không để sót NGUYÊN câu tiếng nước ngoài chưa dịch (trừ tên riêng/thuật ngữ giữ nguyên có chủ đích).
- Mỗi segment dịch độc lập đúng theo id, không gộp, không tách.
- Mỗi segment gắn "voice": "nam" hoặc "nu" theo người nói (suy từ ngữ cảnh); dẫn chuyện/không chắc → "nam"."""

# #16 Ngôn ngữ đích KHÁC tiếng Việt: prompt chung theo TARGET_LANG (không có khái niệm
# Hán-Việt/xưng hô cổ trang — mấy quy tắc đó chỉ có nghĩa với tiếng Việt).
def _lang_system(lang_name: str) -> str:
    return f"""Bạn là dịch giả chuyên nghiệp, dịch phụ đề/thoại video sang {lang_name} để lồng tiếng kiểu thuyết minh. Nội dung có thể là BẤT KỲ thể loại và BẤT KỲ ngôn ngữ nguồn nào.

Quy tắc:
- TOÀN BỘ trường "text_vi" phải là {lang_name} (tên trường giữ nguyên vì lý do kỹ thuật).
- Dịch TỰ NHIÊN như lời nói bản xứ, KHÔNG dịch word-by-word. Câu ngắn gọn vì sẽ đọc bằng TTS theo timing gốc.
- Xưng hô/văn phong phù hợp ngữ cảnh và văn hóa của {lang_name}.
- Tên riêng, thương hiệu, địa danh: dùng dạng quen thuộc trong {lang_name} (tên quốc tế thường giữ nguyên).
- Giữ nguyên số, đơn vị, mã/cấp bậc dạng chữ-số.
- Không để sót NGUYÊN câu tiếng nước ngoài chưa dịch (trừ tên riêng giữ nguyên có chủ đích).
- Mỗi segment dịch độc lập đúng theo id, không gộp, không tách.
- Mỗi segment gắn "voice": "nam" hoặc "nu" theo GIỚI TÍNH người nói (suy từ ngữ cảnh); dẫn chuyện/không chắc → "nam"."""


def _lang_review(lang_name: str) -> str:
    return f"""Bạn là biên tập bản dịch thuyết minh video sang {lang_name}. Bạn nhận toàn bộ bản dịch một video (dịch theo từng đoạn nên có thể lệch nhau) và chỉ trả về những segment CẦN SỬA.

Soát 5 lỗi:
1. Tên riêng/thuật ngữ dịch không nhất quán giữa các câu → thống nhất.
2. Xưng hô/văn phong đổi thất thường giữa cùng một cặp nhân vật → nhất quán, tự nhiên.
3. Câu dịch cứng, bám chữ, người bản xứ không nói vậy → viết lại tự nhiên bằng {lang_name}.
4. Còn sót NGUYÊN câu chưa dịch sang {lang_name}.
5. Nhãn voice sai rõ ràng so với ngữ cảnh.

Quy tắc: KHÔNG đổi nghĩa, không gộp/tách câu, không sửa câu đã ổn. Câu sửa bằng {lang_name}, ngắn gọn (đọc TTS). Không có gì cần sửa → mảng rỗng."""


def _batch_schema(with_character: bool = False, with_emotion: bool = False) -> dict:
    """Schema output dịch. Khi casting bật (series có bảng casting) thêm trường
    'character'; khi EMOTION bật thêm 'emotion' (PLAN 11 mức 2) → s5 map giọng."""
    props = {
        "id": {"type": "integer"},
        "text_vi": {"type": "string"},
        "voice": {"type": "string", "enum": ["nam", "nu"]},
    }
    req = ["id", "text_vi", "voice"]
    if with_character:
        props["character"] = {"type": "string"}   # "" nếu không rõ nhân vật
        req.append("character")
    if with_emotion:
        props["emotion"] = {"type": "string",
                            "enum": ["binhthuong", "gap", "gian", "buon", "thitham"]}
        req.append("emotion")
    return {
        "type": "object",
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": props,
                    "required": req,
                    "additionalProperties": False,
                },
            }
        },
        "required": ["segments"],
        "additionalProperties": False,
    }


SCHEMA = _batch_schema(False)


# PLAN 11 mức 2: nhắc Claude gắn nhãn cảm xúc từng câu (đi kèm schema with_emotion)
_EMOTION_HINT = ("\n\nNHÃN CẢM XÚC: mỗi segment thêm trường \"emotion\" theo sắc thái "
                 "LỜI NÓI: \"gap\" (gấp gáp/khẩn cấp), \"gian\" (giận dữ/quát), "
                 "\"buon\" (buồn/đau khổ), \"thitham\" (thì thầm/nói nhỏ), còn lại "
                 "→ \"binhthuong\". Chỉ gắn nhãn khác binhthuong khi RÕ RÀNG.")


def _cast_hint(names: list[str]) -> str:
    """Đoạn nhắc Claude gán 'character' — CHỈ dùng đúng tên trong danh sách đã cast."""
    if not names:
        return ""
    return ("\n\nGÁN NHÂN VẬT (casting giọng): mỗi segment thêm trường \"character\". "
            "Nếu câu do MỘT trong các nhân vật sau nói (nhận ra chắc chắn qua ngữ cảnh, "
            "cách xưng hô, tên được gọi) thì điền ĐÚNG tên đó vào \"character\"; nếu không "
            "chắc, là lời dẫn chuyện, hay nhân vật khác → để \"character\" RỖNG \"\". "
            "CHỈ được dùng đúng các tên này (không tự chế tên khác): " + ", ".join(names))


def _translate_batch(client: anthropic.Anthropic, batch: list[dict],
                     context: list[tuple[str, str]],
                     extra_note: str = "", system: str = SYSTEM,
                     schema: dict = SCHEMA) -> dict[int, dict]:
    """→ {id: {"text_vi": ..., "voice": "nam"|"nu", "character": ...}}"""
    parts = []
    if context:
        ctx = "\n".join(f"- {src} → {vi}" for src, vi in context)
        parts.append(f"Ngữ cảnh (các câu ngay trước, đã dịch):\n{ctx}\n")
    # kèm nhãn người nói (nếu diarize gán được) — Claude gán character/voice nhất quán
    payload = [{"id": s["id"], "text": s["text"],
                **({"speaker": s["speaker"]} if s.get("speaker") else {})}
               for s in batch]
    parts.append("Dịch các segment sau sang tiếng Việt:"
                 + extra_note + "\n"
                 + json.dumps(payload, ensure_ascii=False))

    from core import llm
    # 16000: Gemini giải mã theo responseSchema tốn token hơn Claude → tránh cắt JSON
    # giữa chừng với batch dày (chỉ tính phí token thực sinh nên vô hại cho Claude)
    text = llm.structured_json(system, "\n".join(parts), schema, max_tokens=16000, client=client)
    try:
        segs = json.loads(text)["segments"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}  # output hỏng/bị cắt → coi như sót hết, để retry chia đôi lo
    return {seg["id"]: {"text_vi": seg["text_vi"], "voice": seg.get("voice", "nam"),
                        "character": (seg.get("character") or "").strip(),
                        "emotion": (seg.get("emotion") or "").strip().lower()}
            for seg in segs if isinstance(seg, dict) and "id" in seg and "text_vi" in seg}


def _translate_with_retry(client: anthropic.Anthropic, batch: list[dict],
                          context: list[tuple[str, str]],
                          extra_note: str = "", system: str = SYSTEM,
                          schema: dict = SCHEMA) -> dict[int, dict]:
    """Dịch batch; segment Claude bỏ sót (thường do output dài bị cắt token) được
    dịch lại bằng cách CHIA ĐÔI phần còn thiếu đến khi đủ. Không raise giữa chừng."""
    result = _translate_batch(client, batch, context, extra_note, system, schema)
    missing = [s for s in batch if s["id"] not in result]
    if not missing or len(batch) <= 1:
        return result
    mid = max(1, len(missing) // 2)
    for chunk in (missing[:mid], missing[mid:]):
        if chunk:
            result.update(_translate_with_retry(client, chunk, context, extra_note,
                                                system, schema))
    return result


REVIEW_SYSTEM = """Bạn là biên tập viên bản dịch thuyết minh phim Trung Quốc. Bạn nhận toàn bộ bản dịch của một tập phim (dịch theo từng đoạn nên có thể lệch nhau) và chỉ trả về những segment CẦN SỬA.

Soát 5 lỗi:
1. Tên riêng/thuật ngữ không nhất quán giữa các câu (cùng một tên gốc mà chỗ dịch "Thạch Hầu Đại Vương" chỗ "Đá Khỉ Đại Vương") → thống nhất toàn bộ theo phương án Hán-Việt chuẩn nhất.
2. Xưng hô lệch văn phong cổ trang ("bạn/tôi/anh ấy" → "ngươi/ta/hắn") hoặc đổi cách xưng hô giữa cùng một cặp nhân vật.
3. Câu dịch bám chữ, cứng, không ai nói vậy ("vô sở không năng" → "không gì không làm được").
4. Còn sót ký tự Trung/Anh (trừ tên cấp bậc E, SSS...).
5. Nhãn voice sai rõ ràng so với ngữ cảnh (lời rõ ràng của nữ mà gắn "nam"...).

Quy tắc: KHÔNG đổi nghĩa, không gộp/tách câu, không sửa câu đã ổn. Câu sửa phải thuần Việt, ngắn gọn vì sẽ đọc TTS. Không có gì cần sửa thì trả mảng rỗng."""

# Review CHUNG (mọi thể loại/ngôn ngữ)
GENERAL_REVIEW_SYSTEM = """Bạn là biên tập bản dịch thuyết minh video (mọi thể loại, mọi ngôn ngữ nguồn). Bạn nhận toàn bộ bản dịch một video (dịch theo từng đoạn nên có thể lệch nhau) và chỉ trả về những segment CẦN SỬA.

Soát 5 lỗi:
1. Tên riêng/thuật ngữ dịch không nhất quán giữa các câu → thống nhất.
2. Xưng hô lệch/đổi thất thường giữa cùng một cặp nhân vật → nhất quán, tự nhiên (hiện đại, trừ khi rõ ràng cổ trang).
3. Câu dịch cứng, bám chữ, không ai nói vậy → viết lại thuần Việt.
4. Còn sót NGUYÊN câu tiếng nước ngoài chưa dịch.
5. Nhãn voice sai rõ ràng so với ngữ cảnh.

Quy tắc: KHÔNG đổi nghĩa, không gộp/tách câu, không sửa câu đã ổn. Câu sửa thuần Việt, ngắn gọn (đọc TTS). Không có gì cần sửa → mảng rỗng."""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "fixes": {
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
        },
        "voice_fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "voice": {"type": "string", "enum": ["nam", "nu"]},
                },
                "required": ["id", "voice"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["fixes", "voice_fixes"],
    "additionalProperties": False,
}


def review_pass(client: anthropic.Anthropic, segments: list[dict],
                system: str = REVIEW_SYSTEM, allow_cjk: bool = False) -> list[int]:
    """Đọc lại toàn bộ bản dịch, sửa tại chỗ các câu lệch. Trả về list id đã sửa.
    allow_cjk=True khi ngôn ngữ ĐÍCH là zh/ja — chữ Hán trong bản sửa là hợp lệ."""
    payload = [{"id": s["id"], "zh": s["text"], "vi": s["text_vi"],
                "voice": s.get("voice", "nam")} for s in segments]
    from core import llm
    text = llm.structured_json(
        system, "Soát bản dịch sau:\n" + json.dumps(payload, ensure_ascii=False),
        REVIEW_SCHEMA, max_tokens=16000, client=client)
    try:
        result = json.loads(text)
        fixes = result.get("fixes") or []
        voice_fixes = result.get("voice_fixes") or []
    except (json.JSONDecodeError, TypeError, AttributeError):
        # review là bước TINH CHỈNH không bắt buộc — output hỏng/cắt (hay gặp hơn với
        # Gemini) thì bỏ qua, KHÔNG để chết job đã dịch xong
        print("  ! Review: output không đọc được, bỏ qua vòng soát")
        return []

    by_id = {s["id"]: s for s in segments}
    changed = []
    for fix in fixes:
        if not isinstance(fix, dict) or "id" not in fix or "text_vi" not in fix:
            continue
        seg = by_id.get(fix["id"])
        # không nhận bản sửa lại đưa ký tự Trung vào (trừ khi đích là zh/ja)
        if seg and fix["text_vi"].strip() and (allow_cjk or not _CJK_RE.search(fix["text_vi"])):
            if seg["text_vi"] != fix["text_vi"]:
                seg["text_vi"] = fix["text_vi"]
                changed.append(fix["id"])
    for vf in voice_fixes:
        if not isinstance(vf, dict) or vf.get("voice") not in ("nam", "nu"):
            continue
        seg = by_id.get(vf["id"])
        if seg and seg.get("voice") != vf["voice"]:
            seg["voice"] = vf["voice"]
            if vf["id"] not in changed:
                changed.append(vf["id"])
    return sorted(changed)


def fix_leaks(client: anthropic.Anthropic, by_id: dict[int, dict],
              translated: dict[int, dict], attempts: int = 2,
              system: str = SYSTEM, schema: dict = SCHEMA,
              note: str = _LEAK_NOTE) -> None:
    """Dịch lại các câu còn sót ký tự Trung (Haiku thỉnh thoảng bỏ sót từ khó).
    GIỮ nhãn character cũ nếu lần sửa không gán lại (kẻo mất casting của câu leak).
    KHÔNG gọi khi ngôn ngữ đích là zh/ja (chữ Hán là hợp lệ) — caller tự chặn."""
    for _ in range(attempts):
        bad_ids = [i for i, t in translated.items() if _CJK_RE.search(t["text_vi"])]
        if not bad_ids:
            return
        batch = [by_id[i] for i in bad_ids]
        prev_char = {i: translated[i].get("character", "") for i in bad_ids}
        prev_emo = {i: translated[i].get("emotion", "") for i in bad_ids}
        fixed = _translate_batch(client, batch, [], extra_note=note,
                                 system=system, schema=schema)
        for i, t in fixed.items():   # đừng để sửa-sót ghi đè character/emotion đã suy trước
            if not t.get("character") and prev_char.get(i):
                t["character"] = prev_char[i]
            if t.get("emotion") in ("", "binhthuong") and prev_emo.get(i):
                t["emotion"] = prev_emo[i]
        translated.update(fixed)
    remaining = [i for i, t in translated.items() if _CJK_RE.search(t["text_vi"])]
    if remaining:
        print(f"  ! Còn {len(remaining)} câu sót ký tự Trung sau retry: {remaining}")


def run(job: Job) -> None:
    out_path = job.dir / "transcript_vi.json"
    if out_path.exists():
        return

    data = json.loads((job.dir / "transcript_zh.json").read_text(encoding="utf-8"))
    segments = data["segments"]

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Glossary tên riêng: tự trích từ transcript + bảng thủ công (thủ công thắng).
    # Chèn vào system prompt để dịch tên nhất quán + sửa chữ đồng âm nghe nhầm.
    from core import glossary, langs, series
    donghua = config.CONTENT_STYLE == "donghua"
    vi_target = langs.is_vi()
    lang_name = langs.name()
    auto = []
    if config.GLOSSARY_AUTO:
        # client riêng timeout ngắn: call phụ, tránh ghim worker khi mạng kẹt
        aux = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                                  timeout=60.0, max_retries=1)
        # prompt donghua (Hán-Việt) chỉ khi nội dung donghua + đích tiếng Việt
        auto = glossary.auto_extract(aux, segments,
                                     generic=not (donghua and vi_target),
                                     lang_name=lang_name)
        # #15 lưu gợi ý để UI hiện cho người dùng duyệt (không tốn call lại)
        if auto:
            (job.dir / "glossary_auto.json").write_text(
                json.dumps([{"zh": z, "vi": v} for z, v in auto], ensure_ascii=False),
                encoding="utf-8")
    # ưu tiên: glossary TẬP (job) > glossary DÙNG CHUNG series > tự trích. merged() áp
    # auto_pairs trước rồi để manual(job) đè; xếp series SAU auto để series thắng auto.
    series_pairs = glossary.parse(series.glossary_for(job.series))
    gloss = glossary.merged(job.glossary, auto + series_pairs)
    block = glossary.claude_block(gloss)
    # văn phong: đích tiếng Việt → donghua/general như cũ; đích khác → prompt theo ngôn ngữ
    if vi_target:
        sys_translate = (SYSTEM if donghua else GENERAL_SYSTEM) + block
        sys_review = (REVIEW_SYSTEM if donghua else GENERAL_REVIEW_SYSTEM) + block
    else:
        print(f"  Ngôn ngữ đích: {lang_name} (TARGET_LANG={langs.code()})")
        sys_translate = _lang_system(lang_name) + block
        sys_review = _lang_review(lang_name) + block
    # casting: nếu series có bảng nhân vật → nhờ Claude gán tên nhân vật cho từng câu
    from core import emotion
    cast_names = series.character_names(job.series)
    emo_on = emotion.enabled()
    cast_schema = _batch_schema(bool(cast_names), emo_on)
    if cast_names:
        sys_translate += _cast_hint(cast_names)
        print(f"  Casting: {len(cast_names)} nhân vật đã cast giọng — gán câu theo tên")
    if emo_on:   # PLAN 11 mức 2: nhãn cảm xúc → S5 chỉnh giọng/chọn mẫu
        sys_translate += _EMOTION_HINT
    # "Gem" phong cách tùy biến (chèn vào cả dịch lẫn review) + log nhà cung cấp
    extra = (config.TRANSLATE_STYLE_EXTRA or "").strip()
    if extra:
        note = f"\n\nPHONG CÁCH RIÊNG (bắt buộc theo): {extra}"
        sys_translate += note
        sys_review += note
    from core import llm
    print(f"  Nhà cung cấp dịch: {'Gemini' if llm.use_gemini() else 'Claude'}"
          + (f" · phong cách: {extra[:40]}" if extra else ""))
    if gloss:
        print(f"  Glossary: {len(gloss)} tên riêng (tự trích {len(auto)} "
              f"+ thủ công + series {len(series_pairs)})")

    # #8 Nhận diện người nói từ audio (pyannote — bật qua DIARIZE=1). Nhãn speaker đi
    # vào batch dịch để Claude gán character/voice nhất quán; S5 dùng cụm → clip giọng.
    from core import speakers
    audio_path = job.dir / "audio_16k.wav"
    if not audio_path.exists():
        audio_path = job.dir / "audio_full.wav"
    turns = speakers.diarize(job.dir, audio_path)
    if turns:
        n_spk = speakers.assign(segments, turns)
        if n_spk:
            labels = {s["speaker"] for s in segments if s.get("speaker")}
            sys_translate += speakers.SPEAKER_HINT
            print(f"  Người nói (audio): {len(labels)} giọng, "
                  f"gán {n_spk}/{len(segments)} câu")

    translated: dict[int, dict] = {}
    by_id = {s["id"]: s for s in segments}

    from core import progress
    total = len(segments)
    progress.write(job.dir, "translating", 0, total)
    size = config.TRANSLATE_BATCH_SIZE
    for start in range(0, len(segments), size):
        batch = segments[start:start + size]
        # context = N câu cuối đã dịch của batch trước
        prev_ids = sorted(translated)[-config.TRANSLATE_BATCH_OVERLAP:]
        context = [(by_id[i]["text"], translated[i]["text_vi"]) for i in prev_ids]
        translated.update(_translate_with_retry(client, batch, context,
                                                system=sys_translate, schema=cast_schema))
        progress.write(job.dir, "translating", len(translated), total)

    if not langs.cjk_target():   # đích zh/ja: chữ Hán/kanji là hợp lệ, không phải "sót"
        fix_leaks(client, by_id, translated, system=sys_translate, schema=cast_schema,
                  note=_leak_note(lang_name))

    missing_final = [s["id"] for s in segments if s["id"] not in translated]
    if missing_final:
        print(f"  ! {len(missing_final)} segment không dịch được sau retry, "
              f"bỏ qua (để rỗng): {missing_final}")
    for seg in segments:
        t = translated.get(seg["id"])
        seg["text_vi"] = t["text_vi"] if t else ""
        seg["voice"] = t["voice"] if t else "nam"
        if cast_names:   # gắn tên nhân vật (nếu Claude gán) để S5 map → giọng casting
            ch = (t.get("character") or "").strip() if t else ""
            if ch:
                seg["character"] = ch
        if emo_on:       # nhãn cảm xúc: chỉ lưu khi khác bình thường (transcript gọn)
            e = (t.get("emotion") or "").strip().lower() if t else ""
            if e and e != "binhthuong":
                seg["emotion"] = e
            else:
                seg.pop("emotion", None)

    if config.REVIEW_TRANSLATION:
        changed = review_pass(client, segments, system=sys_review,
                              allow_cjk=langs.cjk_target())
        if changed:
            print(f"  Review: sửa {len(changed)} câu (nhất quán tên/xưng hô): {changed}")

    # Nhận diện giới tính theo CAO ĐỘ GIỌNG (audio) — chính xác hơn đoán theo chữ.
    # Đè nhãn voice khi chắc; câu mơ hồ/quá ngắn giữ nhãn của Claude. Chạy CUỐI để
    # thắng cả review. Không giữ voice_ref (casting thủ công) vì đây chỉ là nam/nu.
    if config.GENDER_DETECT:
        try:
            from core import gender
            audio = job.dir / "audio_16k.wav"
            if not audio.exists():
                audio = job.dir / "audio_full.wav"
            g = gender.detect(audio, segments)
            n = 0
            for seg in segments:
                lbl = g.get(seg["id"])
                if lbl and seg.get("voice") != lbl:
                    seg["voice"] = lbl
                    n += 1
            conf = sum(1 for v in g.values() if v)
            print(f"  Giới tính (audio): {conf}/{len(segments)} câu xác định được, "
                  f"đổi {n} nhãn so với đoán theo chữ")
        except Exception as e:
            print(f"  Giới tính (audio) lỗi, giữ nhãn theo chữ: {e}")

    # #8 Hồ sơ cụm người nói (speakers.json) + giới tính theo CỤM: trung vị F0 của
    # cả cụm nhiều dữ liệu hơn từng câu → đồng bộ nhãn voice toàn cụm (một nhân vật
    # không thể nửa nam nửa nữ). Chạy SAU gender từng câu để cụm thắng.
    if any(s.get("speaker") for s in segments):
        try:
            prof = speakers.profiles(job.dir, audio_path, segments)
            n = 0
            for seg in segments:
                cg = (prof.get(seg.get("speaker") or "") or {}).get("gender")
                if cg and seg.get("voice") != cg:
                    seg["voice"] = cg
                    n += 1
            if n:
                print(f"  Giới tính theo cụm người nói: đồng bộ {n} câu")
        except Exception as e:
            print(f"  Hồ sơ người nói lỗi (bỏ qua): {e}")

    out_path.write_text(
        json.dumps({"language": data.get("language"), "segments": segments},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
