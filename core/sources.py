"""Bung input người dùng thành danh sách video: link lẻ, nhiều dòng, playlist/kênh.

Dùng yt-dlp extract_flat nên chỉ đọc danh sách, không tải gì.
"""
from __future__ import annotations

import gzip
import html
import ipaddress
import re
import socket
import urllib.request
import zlib
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

import config


def validate_remote_url(url: str) -> None:
    """Chặn SSRF: chỉ cho http/https tới host công khai. Raise ValueError nếu không.

    Dùng cho các URL người dùng nộp trước khi đưa vào yt-dlp — tránh truy vấn tới
    dịch vụ nội bộ (localhost, 169.254.169.254...) khi dashboard bị lộ ra LAN.
    """
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"Chỉ chấp nhận URL http/https (nhận: '{p.scheme}')")
    host = p.hostname
    if not host:
        raise ValueError("URL thiếu host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Không phân giải được host '{host}': {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"Host trỏ tới địa chỉ nội bộ/bị cấm: {ip}")


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


_TITLE_SUFFIXES = ("_哔哩哔哩_bilibili", "_bilibili", " - YouTube", " - bilibili")


def _scrape_title(url: str) -> str | None:
    """Lấy tiêu đề từ og:title/<title> của trang — fallback khi yt-dlp bị chặn
    (vd Bilibili trả HTTP 412 vì thiếu chữ ký WBI/cookie). Dedup check chỉ cần
    tiêu đề nên đủ; gọi sau validate_remote_url nên đã qua chặn SSRF."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                      " (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data, enc = resp.read(), resp.headers.get("Content-Encoding", "")
    if enc == "gzip":
        data = gzip.decompress(data)
    elif enc == "deflate":
        data = zlib.decompress(data)
    raw = data.decode("utf-8", "replace")
    m = (re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', raw)
         or re.search(r"<title[^>]*>(.*?)</title>", raw, re.S))
    if not m:
        return None
    title = html.unescape(m.group(1)).strip()
    for suf in _TITLE_SUFFIXES:
        if title.endswith(suf):
            title = title[:-len(suf)].strip()
    return title or None


def cookie_opts() -> dict:
    """Opts cookie cho yt-dlp từ .env — giúp qua mặt chặn 412 của Bilibili.

    Áp vào MỌI lệnh yt-dlp (tải, lấy meta, expand). Cookie theo domain nên truyền
    cookie Bilibili sang lệnh YouTube vô hại.
    """
    f = config.YTDLP_COOKIES_FILE
    if f and Path(f).is_file():
        return {"cookiefile": f}
    if config.YTDLP_COOKIES_BROWSER:
        return {"cookiesfrombrowser": (config.YTDLP_COOKIES_BROWSER,)}
    return {}


def fetch_meta(url: str) -> dict:
    """Metadata 1 video (title, duration, channel) — full extract, không tải.

    yt-dlp lỗi (vd Bilibili 412) → fallback cào tiêu đề từ HTML (đủ cho dedup).
    """
    validate_remote_url(url)  # chặn SSRF trước khi truy cập
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True, "socket_timeout": 20, **cookie_opts()}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        try:
            title = _scrape_title(url)
        except Exception:
            title = None
        if title:
            return {"title": title, "duration": None, "channel": None, "url": url}
        raise  # cả hai cách đều thất bại → ném lỗi yt-dlp gốc
    return {
        "title": info.get("title") or "",
        "duration": info.get("duration"),
        "channel": info.get("channel") or info.get("uploader") or "",
        "url": info.get("webpage_url") or url,
    }


def search_youtube(query: str, n: int = 6) -> list[dict]:
    """ytsearch → [{title, channel, views, duration, url}] (flat, không tải)."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": True, "playlist_items": f"1:{n}",
            "socket_timeout": 20, **cookie_opts()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        res = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    out = []
    for e in res.get("entries") or []:
        if not e:
            continue
        vid = e.get("id")
        u = e.get("url") or e.get("webpage_url")
        if vid and (not u or not u.startswith("http")):
            u = f"https://www.youtube.com/watch?v={vid}"
        out.append({
            "title": e.get("title") or "",
            "channel": e.get("channel") or e.get("uploader") or "",
            "views": e.get("view_count"),
            "duration": e.get("duration"),
            "url": u,
        })
    return out


def _expand_one(url: str, remaining: int) -> list[dict]:
    opts = {
        "extract_flat": "in_playlist",
        "playlist_items": f"1:{remaining}",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        **cookie_opts(),
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
