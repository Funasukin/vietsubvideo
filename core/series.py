"""Series (#7/#8): nhóm nhiều TẬP cùng một phim/kênh để DÙNG CHUNG cấu hình.

Một series sở hữu:
  - glossary DÙNG CHUNG: sửa 1 lần, áp cho mọi tập (gộp cùng glossary riêng của tập,
    tập thắng khi trùng) → tên riêng nhất quán xuyên tập mà không nhập lại.
  - bảng CASTING: {tên nhân vật → clip giọng trong voices/}. s4 nhờ Claude gán tên
    nhân vật (giới hạn trong danh sách đã cast) cho từng câu; s5 map tên → voice_ref
    → cùng một nhân vật đọc CÙNG một giọng ở mọi tập, không set lại từng tập.

Lưu tại data/series/<key>.json = {"name","glossary","casting":{char: voice_ref}}.
job.series giữ TÊN series (người đọc); tra cứu bằng _key() để ra tên file.
KHÔNG áp đặt donghua — series dùng cho mọi thể loại/ngôn ngữ nhiều tập.
"""
from __future__ import annotations

import json
import os
import re
import uuid

import config

# ký tự cấm trong tên file Windows + ký tự điều khiển → thay '_'
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def _dir():
    """Thư mục series NẰM TRONG repo (git theo dõi) → đồng bộ 2 máy qua push/pull.
    Trước đây ở data/series (data/ bị gitignore) nên casting/glossary series lệch
    giữa desktop/laptop — trái mục đích 'nhất quán xuyên tập'. Tự di trú 1 lần."""
    d = config.BASE_DIR / "series"
    d.mkdir(parents=True, exist_ok=True)
    old = config.DATA_DIR / "series"
    if old.exists():
        for p in old.glob("*.json"):
            dest = d / p.name
            if not dest.exists():      # không đè bản đã sync từ máy kia
                try:
                    p.replace(dest)
                except OSError:
                    pass
        try:
            old.rmdir()                # chỉ xoá được khi đã rỗng
        except OSError:
            pass
    return d


def _key(name: str) -> str:
    """Tên series → khóa file an toàn (giữ Unicode/tiếng Việt, bỏ ký tự cấm)."""
    k = _ILLEGAL.sub("_", (name or "").strip()).strip(". ")
    return k[:120] or "series"


def _path(name: str):
    return _dir() / f"{_key(name)}.json"


def load(name: str) -> dict | None:
    """Đọc series theo tên. None nếu chưa có / hỏng."""
    if not (name or "").strip():
        return None
    p = _path(name)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    d.setdefault("name", name)
    d.setdefault("glossary", "")
    if not isinstance(d.get("casting"), dict):
        d["casting"] = {}
    return d


def save(name: str, glossary: str, casting: dict) -> dict:
    """Ghi series (tạo mới nếu chưa có). Lọc casting: bỏ cặp thiếu tên/giọng."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Thiếu tên series")
    clean = {}
    for char, voice in (casting or {}).items():
        char = (char or "").strip()
        voice = (voice or "").strip()
        # voice phải là TÊN FILE trong voices/ (không cho path/traversal); S5 cũng chặn
        # lần nữa khi tổng hợp, đây là phòng thủ nhiều lớp.
        if char and voice and "/" not in voice and "\\" not in voice and ".." not in voice:
            clean[char] = voice
    data = {"name": name, "glossary": (glossary or "")[:20000], "casting": clean}
    # ghi nguyên tử: viết file tạm (tên duy nhất) rồi os.replace → không torn khi 2 request
    # cùng lưu 1 series (endpoint đã chặn kích thước; đây là lớp lưu trữ)
    target = _path(name)
    tmp = target.with_name(target.name + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return data


def list_all() -> list[dict]:
    """Danh sách series đã lưu (cho dropdown / trang quản lý)."""
    out = []
    d = _dir()   # dùng chung đường dẫn (kèm di trú) với load/save
    for p in sorted(d.glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "name": j.get("name", p.stem),
            "cast_count": len(j.get("casting") or {}),
            "gloss_lines": sum(1 for ln in (j.get("glossary") or "").splitlines()
                               if ln.strip() and not ln.strip().startswith("#")),
        })
    return out


def glossary_for(name: str) -> str:
    """Glossary dùng chung của series ('' nếu không có)."""
    s = load(name)
    return (s or {}).get("glossary", "") if s else ""


def casting_for(name: str) -> dict:
    """Bảng casting đã CHUẨN HÓA khóa về chữ-thường-strip để map câu → giọng."""
    s = load(name)
    if not s:
        return {}
    out = {}
    for char, voice in (s.get("casting") or {}).items():
        k = (char or "").strip().lower()
        if k and voice:
            out[k] = voice
    return out


def character_names(name: str) -> list[str]:
    """Tên nhân vật (giữ nguyên hoa/thường) đã cast — đưa cho Claude gợi ý gán câu."""
    s = load(name)
    if not s:
        return []
    return [c for c in (s.get("casting") or {}) if (c or "").strip()]


def apply_casting(job, segments: list[dict]) -> int:
    """Điền voice_ref theo character + bảng casting của series. KHÔNG đè voice_ref đã
    đặt tay (override thủ công trong editor thắng casting). Trả số câu vừa gán.
    Gọi ở đầu S5: đổi bảng casting rồi chạy lại TTS là áp giọng mới (sig .sig đổi)."""
    cast = casting_for(getattr(job, "series", "") or "")
    if not cast:
        return 0
    n = 0
    for s in segments:
        if s.get("voice_ref"):        # đã cast tay câu này → giữ nguyên
            continue
        ch = (s.get("character") or "").strip().lower()
        vr = cast.get(ch) if ch else None
        if vr:
            s["voice_ref"] = vr
            n += 1
    return n
