"""Pre-flight: kiểm tra một video đã có người vietsub/lồng tiếng trên YouTube chưa.

Luồng: lấy tiêu đề nguồn (yt-dlp) → Claude chuẩn hóa tên bộ + số tập → ytsearch
các biến thể tiếng Việt → Claude phán xử ứng viên → verdict.

Đây là công cụ CẢNH BÁO, không phải máy dò tuyệt đối: tên kênh reup lộn xộn nên
độ chính xác ~80-90% với bộ nổi tiếng, thấp hơn với bộ ít tiếng. "Không thấy"
chỉ nghĩa là không có trong top kết quả, KHÔNG chắc chắn là chưa ai làm.
"""
from __future__ import annotations

import json
import re

import anthropic

import config
from core import sources

# Ký tự Hán/CJK/fullwidth + ngoặc sách 《》 — phải bỏ khỏi truy vấn YouTube
_CJK = re.compile(r"[　-〿㐀-鿿＀-￯《》]")
_PUNCT = re.compile(r"[?？!！.,，。:：;；\"'`~()\[\]【】|/\\#＃]+")


def _clean_term(t: str) -> str:
    """Bỏ chữ Hán, dấu câu, emoji-ish → cụm từ khóa search được trên YouTube."""
    t = _CJK.sub(" ", t or "")
    t = _PUNCT.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()

# Số kết quả mỗi truy vấn và tổng ứng viên tối đa đưa cho Claude phán xử
PER_QUERY = 6
MAX_CANDIDATES = 10

# ---------- Bước 1: chuẩn hóa tiêu đề thành tên bộ + tập ----------

NORMALIZE_SYSTEM = """Bạn nhận tiêu đề một video phim hoạt hình Trung Quốc (donghua / 漫剧 / anime) — có thể là tiếng Trung, tiếng Việt, tiếng Anh hoặc pinyin, thường lẫn emoji/hashtag/quảng cáo. Nhận diện TÊN BỘ, SỐ TẬP, và TỪ KHÓA TÌM KIẾM tiếng Việt.

- series_vi: tên hiển thị tiếng Việt. Nếu là bộ nổi tiếng có tên cộng đồng chuẩn thì dùng tên đó (斗罗大陆 → "Đấu La Đại Lục"; 凡人修仙传 → "Phàm Nhân Tu Tiên Truyện").
- series_zh: tên gốc tiếng Trung nếu có, không thì rỗng "".
- episode: số tập (số nguyên). Phim lẻ / tổng hợp / không rõ → null.
- kind: "tap" | "tron_bo" (tổng hợp nhiều tập) | "phim" | "khong_ro".
- search_terms: 2-4 cụm TỪ KHÓA NGẮN (3-7 từ) tiếng Việt mà các kênh reup Việt CÓ THỂ đặt tên cho bộ này, để tìm trên YouTube. QUY TẮC QUAN TRỌNG:
  • KHÔNG ký tự Hán, KHÔNG dấu câu (? ! 《》...), KHÔNG emoji/hashtag.
  • Phải NGẮN GỌN và tự nhiên — dịch máy nguyên văn câu dài sẽ tìm KHÔNG RA. Bám vào danh từ/ý chính dễ trùng (nhân vật chính, vật phẩm, năng lực đặc trưng).
  • Nếu biết tên cộng đồng chuẩn → để đầu tiên. Nếu không chắc → đưa vài CÁCH ĐẶT TÊN khác nhau hợp lý của cùng ý chính.
  • Phim mới/AI thường được kênh Việt đặt tên mô tả nội dung — hãy đoán theo hướng đó.
  Ví dụ: 普通弓箭手？我能无限叠加攻击力 → ["Cung Thủ Bình Thường Sức Mạnh Vô Hạn", "Cung thủ vô hạn cộng dồn sát thương", "Cung thủ tăng vô hạn công kích"].

Chỉ trả JSON đúng schema."""

NORMALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "series_vi": {"type": "string"},
        "series_zh": {"type": "string"},
        "episode": {"type": ["integer", "null"]},
        "kind": {"type": "string", "enum": ["tap", "tron_bo", "phim", "khong_ro"]},
        "search_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["series_vi", "series_zh", "episode", "kind", "search_terms"],
    "additionalProperties": False,
}


def normalize_title(client: anthropic.Anthropic, title: str) -> dict:
    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=400,
        system=[{"type": "text", "text": NORMALIZE_SYSTEM}],
        messages=[{"role": "user", "content": f"Tiêu đề video:\n{title}"}],
        output_config={"format": {"type": "json_schema", "schema": NORMALIZE_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def build_queries(norm: dict) -> list[str]:
    """Dựng truy vấn YouTube từ search_terms (ngắn, sạch) — KHÔNG dùng câu dịch dài.

    YouTube khớp tốt với từ khóa ngắn; câu dịch nguyên văn + dấu câu thường ra
    rỗng. Mỗi term tạo 1 truy vấn cốt lõi (+ tập nếu có), thêm 1 biến thể vietsub
    cho term đầu để tăng độ phủ; để judge phân loại sub/dub từ tiêu đề tìm được.
    """
    terms = [_clean_term(t) for t in (norm.get("search_terms") or [])]
    terms.append(_clean_term(norm.get("series_vi") or ""))  # tên hiển thị làm dự phòng

    seen: set[str] = set()
    clean_terms: list[str] = []
    for t in terms:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            clean_terms.append(t)
    clean_terms = clean_terms[:3]
    if not clean_terms:
        return []

    ep = norm.get("episode")
    suffix = f" tập {ep}" if ep is not None else ""
    queries: list[str] = [t + suffix for t in clean_terms]
    queries.append(f"{clean_terms[0]}{suffix} vietsub")

    out: list[str] = []
    qseen: set[str] = set()
    for q in queries:
        if q not in qseen:
            qseen.add(q)
            out.append(q)
    return out[:5]


# ---------- Bước 2: phán xử ----------

JUDGE_SYSTEM = """Bạn xác định liệu một video NGUỒN (phim hoạt hình Trung Quốc sắp được làm tiếng Việt) đã có người vietsub hoặc lồng tiếng/thuyết minh trên YouTube chưa, dựa trên danh sách kết quả tìm kiếm.

Quy tắc CỨNG:
- Chỉ tính KHỚP khi cùng BỘ và cùng TẬP. Số tập là tiêu chí cứng — khác tập = KHÔNG khớp.
- Video "trọn bộ / tập 1-60" tính là khớp NẾU khoảng tập bao trùm tập nguồn.
- Trailer / PV / reaction / AMV / video review tổng hợp = KHÔNG khớp (trừ khi rõ ràng chứa đúng tập đó).
- Phân loại mỗi video khớp: "vietsub" (chỉ phụ đề), "long_tieng" (thuyết minh/lồng tiếng), "khong_ro".
- Nhãn trong tiêu đề có thể sai/thiếu — thiếu thông tin thì để confidence thấp, KHÔNG suy đoán bừa.

Trả: đã tồn tại chưa, loại bao phủ tổng thể, độ tin cậy, các video khớp (theo index), lý do ngắn gọn tiếng Việt."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "already_exists": {"type": "boolean"},
        "coverage": {"type": "string",
                     "enum": ["vietsub", "long_tieng", "ca_hai", "khong_ro", "khong_co"]},
        "confidence": {"type": "string", "enum": ["cao", "trung_binh", "thap"]},
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "type": {"type": "string",
                             "enum": ["vietsub", "long_tieng", "khong_ro"]},
                },
                "required": ["index", "type"],
                "additionalProperties": False,
            },
        },
        "reason": {"type": "string"},
    },
    "required": ["already_exists", "coverage", "confidence", "matches", "reason"],
    "additionalProperties": False,
}


def judge(client: anthropic.Anthropic, source: dict, norm: dict,
          candidates: list[dict]) -> dict:
    payload = {
        "nguon": {
            "tieu_de": source.get("title"),
            "thoi_luong_giay": source.get("duration"),
            "kenh": source.get("channel"),
        },
        "nhan_dien": {"bo": norm.get("series_vi"), "tap": norm.get("episode"),
                      "loai": norm.get("kind")},
        "ung_vien": [
            {"index": i, "tieu_de": c.get("title"), "kenh": c.get("channel"),
             "luot_xem": c.get("views"), "thoi_luong_giay": c.get("duration")}
            for i, c in enumerate(candidates)
        ],
    }
    resp = client.messages.create(
        model=config.METADATA_MODEL,
        max_tokens=1200,
        system=[{"type": "text", "text": JUDGE_SYSTEM}],
        messages=[{"role": "user", "content":
                   "Phán xử dữ liệu sau:\n" + json.dumps(payload, ensure_ascii=False)}],
        output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    result = json.loads(text)

    # map index → ứng viên thật. LƯU Ý bảo mật: title/channel/url là dữ liệu do
    # uploader YouTube đặt (KHÔNG đáng tin dù không phải từ Claude) — UI phải
    # escape khi render. seen_idx để Claude lỡ trả index trùng không thành 2 dòng.
    matches = []
    seen_idx: set[int] = set()
    for m in result.get("matches", []):
        i = m.get("index")
        if isinstance(i, int) and 0 <= i < len(candidates) and i not in seen_idx:
            seen_idx.add(i)
            c = candidates[i]
            matches.append({"title": c.get("title"), "channel": c.get("channel"),
                            "url": c.get("url"), "views": c.get("views"),
                            "type": m.get("type", "khong_ro")})
    result["matches"] = matches
    return result


# ---------- Điều phối ----------

def check(url: str) -> dict:
    """Trả verdict đầy đủ; tự bắt mọi lỗi (mạng/Claude) để không làm sập dashboard.

    status: ok | no_api_key | no_title | error
    """
    out: dict = {"status": "ok", "source": None, "normalized": None,
                 "verdict": None, "candidate_count": 0, "error": None}

    if not config.ANTHROPIC_API_KEY:
        out["status"] = "no_api_key"
        return out

    try:
        meta = sources.fetch_meta(url)
    except Exception as e:
        out["status"] = "error"
        out["error"] = f"Không lấy được metadata video: {e}"
        return out
    out["source"] = meta
    if not (meta.get("title") or "").strip():
        out["status"] = "no_title"
        return out

    try:
        # timeout 30s + 1 retry: gọi nhỏ, tránh ghim slot threadpool khi mạng kẹt
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                                     timeout=30.0, max_retries=1)
        norm = normalize_title(client, meta["title"])
        out["normalized"] = norm

        queries = build_queries(norm)
        seen: set[str] = set()
        candidates: list[dict] = []
        for q in queries:
            if len(candidates) >= MAX_CANDIDATES:
                break
            for c in sources.search_youtube(q, PER_QUERY):
                key = c.get("url") or c.get("title")
                if key and key not in seen and c.get("url") != meta.get("url"):
                    seen.add(key)
                    candidates.append(c)
                    if len(candidates) >= MAX_CANDIDATES:
                        break
        candidates = candidates[:MAX_CANDIDATES]  # đảm bảo count khớp số Claude xét
        out["candidate_count"] = len(candidates)

        if not candidates:
            out["verdict"] = {"already_exists": False, "coverage": "khong_co",
                              "confidence": "thap", "matches": [],
                              "reason": "Không tìm thấy kết quả nào khớp tên bộ."}
            return out

        out["verdict"] = judge(client, meta, norm, candidates)
    except Exception as e:
        out["status"] = "error"
        out["error"] = f"Lỗi khi phân tích: {e}"
    return out
