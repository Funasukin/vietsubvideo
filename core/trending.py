"""Quét phim/video AI ĐANG HOT trên Bilibili + (tuỳ chọn) kiểm tra đã có bản trên YouTube.

Phase 1: nguồn Bilibili (search theo từ khoá AI, ẩn danh) + cột YouTube qua YouTube
Data API v3 (chỉ bật khi có YOUTUBE_API_KEY). Kết quả cache ra data/trending.json,
chạy 1 lần/ngày qua scheduler trong server (xem webui/server.py) + nút "Quét ngay".

KHÔNG dùng cho Douyin/Kuaishou (không có API mở; cần dịch vụ trả phí TikHub — Phase 2).
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import config

CACHE = config.JOBS_DIR.parent / "trending.json"
_TAG_RE = re.compile(r"<[^>]+>")
_SCAN_LOCK = threading.Lock()   # chỉ 1 lượt quét tại 1 thời điểm (scheduler + nút + startup)


def _clean(t: str) -> str:
    """Bỏ thẻ HTML highlight (<em class=keyword>) + giải mã entity trong tựa Bilibili."""
    return html.unescape(_TAG_RE.sub("", t or "")).strip()


def _row_from_search(it: dict, kw: str) -> dict:
    aid = it.get("aid")
    bvid = it.get("bvid") or ""
    url = (f"https://www.bilibili.com/video/{bvid}" if bvid
           else f"https://www.bilibili.com/video/av{aid}")
    return {
        "platform": "Bilibili", "aid": aid,
        "title": _clean(it.get("title", "")),
        "author": _clean(it.get("author", "")),
        "play": int(it.get("play") or 0),       # lượt xem
        "like": int(it.get("like") or 0),
        "danmaku": int(it.get("danmaku") or it.get("video_review") or 0),
        "pubdate": int(it.get("pubdate") or 0),
        "duration": str(it.get("duration") or ""),
        "url": url, "keyword": kw,
    }


def _row_from_rank(it: dict, kw: str) -> dict:
    aid = it.get("aid")
    stat = it.get("stat") or {}
    owner = it.get("owner") or {}
    return {
        "platform": "Bilibili", "aid": aid,
        "title": _clean(it.get("title", "")),
        "author": _clean(owner.get("name", "")),
        "play": int(stat.get("view") or 0),
        "like": int(stat.get("like") or 0),
        "danmaku": int(stat.get("danmaku") or 0),
        "pubdate": int(it.get("pubdate") or 0),
        "duration": str(it.get("duration") or ""),
        "url": f"https://www.bilibili.com/video/av{aid}", "keyword": kw,
    }


async def _scan_bilibili(keywords: list[str], per_kw: int) -> list[dict]:
    from bilibili_api import rank, search
    rows: list[dict] = []
    # 1) search từng từ khoá, sắp theo LƯỢT XEM nhiều nhất (pool "hot" tốt hơn)
    for kw in keywords:
        try:
            r = await search.search_by_type(
                kw, search_type=search.SearchObjectType.VIDEO,
                order_type=search.OrderVideo.CLICK, page=1)
        except Exception as e:
            print(f"  Bilibili search '{kw}' lỗi: {e}")
            await asyncio.sleep(1.5)
            continue
        for it in (r.get("result") or [])[:per_kw]:
            if it.get("aid"):
                rows.append(_row_from_search(it, kw))
        await asyncio.sleep(1.2)   # throttle né anti-bot 412
    # 2) bảng xếp hạng tổng (排行榜) → lọc tiêu đề có "AI" để bắt phim AI viral ngoài search
    try:
        rr = await rank.get_rank()
        for it in (rr.get("list") or []):
            if it.get("aid") and "AI" in (it.get("title") or "").upper():
                rows.append(_row_from_rank(it, "🔥 bảng XH"))
    except Exception as e:
        print(f"  Bilibili rank lỗi: {e}")
    # dedup theo aid (giữ bản gặp trước = từ search), sắp theo lượt xem giảm dần
    out: list[dict] = []
    seen: set = set()
    for r in rows:
        if r["aid"] in seen:
            continue
        seen.add(r["aid"])
        out.append(r)
    out.sort(key=lambda x: x["play"], reverse=True)
    return out


def _youtube_check(title: str, key: str) -> dict:
    """Tìm trên YouTube xem tựa này đã có ai làm/reup chưa (khớp GẦN ĐÚNG theo tựa gốc).
    Trả {found, url, channel, yt_title} | {found:False} | {error:...}."""
    q = urllib.parse.urlencode({
        "part": "snippet", "type": "video", "maxResults": "1",
        "q": title, "key": key})
    try:
        with urllib.request.urlopen(
                "https://www.googleapis.com/youtube/v3/search?" + q, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        # 403 + "quota" → hết quota ngày: báo để dừng các lượt sau
        return {"error": "quota" if "quota" in body.lower() else f"http{e.code}"}
    except Exception as e:
        return {"error": str(e)[:120]}
    items = data.get("items") or []
    if not items:
        return {"found": False}
    it = items[0]
    vid = (it.get("id") or {}).get("videoId")
    sn = it.get("snippet") or {}
    if not vid:
        return {"found": False}
    return {"found": True, "url": f"https://www.youtube.com/watch?v={vid}",
            "channel": sn.get("channelTitle", ""), "yt_title": _clean(sn.get("title", ""))}


def run_scan() -> dict:
    """Quét đồng bộ (gọi từ thread/threadpool, KHÔNG từ event loop đang chạy).
    Quét Bilibili → (nếu có key) check YouTube top N → ghi cache → trả kết quả.
    Nếu đang có lượt quét khác chạy → trả cache hiện có (tránh quét trùng 412 + đua ghi file)."""
    if not _SCAN_LOCK.acquire(blocking=False):
        return load_cache()
    try:
        rows = asyncio.run(_scan_bilibili(config.TRENDING_KEYWORDS, config.TRENDING_PER_KW))
        key = config.YOUTUBE_API_KEY
        yt_checked = 0
        if key:
            for row in rows[:config.TRENDING_YT_LIMIT]:
                yt = _youtube_check(row["title"], key)
                row["youtube"] = yt
                yt_checked += 1
                if yt.get("error") == "quota":   # hết quota → ngừng, các dòng sau để trống
                    break
        data = {
            "scanned_at": int(time.time()),
            "count": len(rows),
            "yt_enabled": bool(key),
            "yt_checked": yt_checked,
            "rows": rows,
        }
        # ghi nguyên tử (tmp + os.replace) + đảm bảo thư mục tồn tại → né đua ghi/khoá file Windows
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CACHE)
        return data
    finally:
        _SCAN_LOCK.release()


def load_cache() -> dict:
    if not CACHE.exists():
        return {"scanned_at": 0, "count": 0, "yt_enabled": bool(config.YOUTUBE_API_KEY),
                "yt_checked": 0, "rows": []}
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"scanned_at": 0, "count": 0, "yt_enabled": bool(config.YOUTUBE_API_KEY),
                "yt_checked": 0, "rows": []}
