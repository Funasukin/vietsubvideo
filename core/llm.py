"""Bộ điều phối LLM cho các bước dịch/soát/trích glossary (S4) — Claude hoặc Gemini.

structured_json(system, user, schema) trả CHUỖI JSON theo `schema` (JSON Schema kiểu
Anthropic). Chọn nhà cung cấp theo config.TRANSLATE_PROVIDER:
  - claude: gọi Anthropic (structured output json_schema) — mặc định.
  - gemini: gọi Google Gemini (responseSchema). LỖI/hết quota (429...) → TỰ fallback
    về Claude cho ĐÚNG call đó → job không bao giờ chết vì rate limit Gemini.

Gemini gọi bằng urllib (không thêm dependency). Free tier ~10 req/phút → GEMINI_MIN_INTERVAL
giãn nhịp nếu cần. Schema Anthropic được chuyển sang schema Gemini (kiểu HOA, bỏ key
không hỗ trợ) tự động.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import config

_anthropic_client = None
_anthropic_lock = threading.Lock()
_gem_lock = threading.Lock()
_gem_last = [0.0]   # thời điểm call Gemini gần nhất (giãn nhịp free tier)


# ---------- Claude ----------
def _claude(system: str, user: str, schema: dict, max_tokens: int, client) -> str:
    global _anthropic_client
    if client is None:
        with _anthropic_lock:          # khởi tạo lười an toàn nếu có nhiều luồng
            if _anthropic_client is None:
                import anthropic
                _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        client = _anthropic_client
    resp = client.messages.create(
        model=config.CLAUDE_MODEL, max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    return next((b.text for b in resp.content if b.type == "text"), "")


# ---------- Gemini ----------
_GEM_TYPES = {"object": "OBJECT", "array": "ARRAY", "string": "STRING",
              "integer": "INTEGER", "number": "NUMBER", "boolean": "BOOLEAN"}


def _to_gemini_schema(s: dict) -> dict:
    """JSON Schema (Anthropic) → Schema Gemini: kiểu HOA, bỏ additionalProperties,
    giữ properties/required/items/enum. propertyOrdering giữ đúng thứ tự required."""
    out: dict = {}
    t = s.get("type")
    if t in _GEM_TYPES:
        out["type"] = _GEM_TYPES[t]
    for k in ("description", "minimum", "maximum"):   # Gemini hỗ trợ, giữ lại nếu có
        if k in s:
            out[k] = s[k]
    if "enum" in s:
        out["enum"] = s["enum"]
    if s.get("type") == "object":
        props = s.get("properties", {})
        out["properties"] = {k: _to_gemini_schema(v) for k, v in props.items()}
        if s.get("required"):
            out["required"] = s["required"]
            out["propertyOrdering"] = s["required"]
    if s.get("type") == "array" and "items" in s:
        out["items"] = _to_gemini_schema(s["items"])
    return out


def _gemini(system: str, user: str, schema: dict, max_tokens: int) -> str:
    if config.GEMINI_MIN_INTERVAL > 0:   # giãn nhịp cho free tier
        with _gem_lock:
            wait = config.GEMINI_MIN_INTERVAL - (time.monotonic() - _gem_last[0])
            if wait > 0:
                time.sleep(wait)
            _gem_last[0] = time.monotonic()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}")
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _to_gemini_schema(schema),
            "maxOutputTokens": max_tokens,
            "temperature": 0.7,
        },
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise RuntimeError(f"Gemini HTTP {e.code}: {detail or e.reason}")
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError(f"Gemini không trả kết quả: {json.dumps(data)[:200]}")
    parts = cands[0].get("content", {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def use_gemini() -> bool:
    return config.TRANSLATE_PROVIDER == "gemini" and bool(config.GEMINI_API_KEY)


def structured_json(system: str, user: str, schema: dict,
                    max_tokens: int = 8000, client=None) -> str:
    """Trả CHUỖI JSON theo schema. Gemini lỗi → fallback Claude (không để job chết)."""
    if use_gemini():
        try:
            return _gemini(system, user, schema, max_tokens)
        except Exception as e:
            print(f"  Gemini lỗi ({e}) → dùng Claude cho câu này")
    return _claude(system, user, schema, max_tokens, client)
