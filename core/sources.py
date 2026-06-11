"""Bung input người dùng thành danh sách video: link lẻ, nhiều dòng, playlist/kênh.

Dùng yt-dlp extract_flat nên chỉ đọc danh sách, không tải gì.
"""
from __future__ import annotations

from pathlib import Path

import yt_dlp

import config


def expand_text(text: str, limit: int | None = None) -> list[dict]:
    """→ [{"url", "title"}] đã bung playlist, bỏ trùng, cắt ở limit."""
    limit = limit or config.BATCH_LIMIT
    entries: list[dict] = []
    seen: set[str] = set()

    for token in text.split():
        if len(entries) >= limit:
            break
        if Path(token).is_file():  # file local
            if token not in seen:
                seen.add(token)
                entries.append({"url": token, "title": Path(token).name})
            continue
        for e in _expand_one(token, limit - len(entries)):
            if e["url"] not in seen:
                seen.add(e["url"])
                entries.append(e)
    return entries


def _expand_one(url: str, remaining: int) -> list[dict]:
    opts = {
        "extract_flat": "in_playlist",
        "playlist_items": f"1:{remaining}",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist":
        out = []
        for e in info.get("entries") or []:
            if not e:
                continue
            u = e.get("url") or e.get("webpage_url")
            if u and not u.startswith("http") and e.get("ie_key") == "Youtube":
                u = f"https://www.youtube.com/watch?v={u}"
            if u:
                out.append({"url": u, "title": e.get("title") or u})
        return out
    return [{"url": info.get("webpage_url") or url,
             "title": info.get("title") or url}]
