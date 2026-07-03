"""Đăng YouTube (#1) — TÙY CHỌN, không tự đăng hộ; người dùng bấm nút mới chạy.

Hai chế độ (làm CẢ HAI theo yêu cầu):
  - build_package(job): gom final.mp4 + thumbnail + tiêu đề/mô tả/tags ra 1 thư mục
    output/ để KÉO-THẢ lên YouTube Studio thủ công. KHÔNG cần OAuth — dùng được ngay.
  - upload(job): đăng thẳng bằng YouTube Data API v3. Cần google-api + client_secrets
    OAuth do người dùng tạo ở Google Cloud + đăng nhập 1 lần (token lưu ở data/).

Thư viện google-* là TÙY CHỌN: thiếu thì package vẫn chạy, upload báo lỗi rõ ràng.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import config

_TOKEN_PATH = config.DATA_DIR / "youtube_token.json"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_PRIVACY = {"private", "unlisted", "public"}


def _slug(text: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", (text or "").strip()).strip(". ")
    return (s or "video")[:80]


def _meta(job) -> dict:
    p = job.dir / "metadata.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def libs_available() -> bool:
    try:
        import googleapiclient.discovery  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        return True
    except Exception:
        return False


def is_ready() -> bool:
    """Đủ điều kiện đăng thẳng: có thư viện + file client_secrets tồn tại."""
    cs = config.YOUTUBE_CLIENT_SECRETS
    return bool(cs) and Path(cs).is_file() and libs_available()


def build_package(job) -> Path:
    """Gom video + metadata + thumbnail vào output/<id>_<title>/ để đăng tay. Trả thư mục."""
    final = job.dir / "final.mp4"
    if not final.exists():
        raise FileNotFoundError("Chưa có final.mp4 (job chưa render xong)")
    meta = _meta(job)
    title = meta.get("title") or job.url
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    folder = config.OUTPUT_DIR / f"{job.id}_{_slug(title)}"
    folder.mkdir(parents=True, exist_ok=True)

    shutil.copy2(final, folder / "video.mp4")
    thumb = job.dir / "thumbnail.jpg"
    if thumb.exists():
        shutil.copy2(thumb, folder / "thumbnail.jpg")

    tags = meta.get("tags", [])
    lines = [
        "TIÊU ĐỀ:", title, "",
        "MÔ TẢ:", meta.get("description", ""), "",
        "TAGS:", ", ".join(tags) if isinstance(tags, list) else str(tags), "",
        f"(FlowApp — kéo video.mp4 + thumbnail.jpg lên YouTube Studio, dán tiêu đề/mô tả/tags ở trên)",
    ]
    (folder / "upload_info.txt").write_text("\n".join(lines), encoding="utf-8")
    return folder


def _load_credentials():
    """Nạp/nâng cấp OAuth credentials; chạy consent nếu chưa có token. Chỉ gọi khi upload."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.YOUTUBE_CLIENT_SECRETS, _SCOPES)
            creds = flow.run_local_server(port=0)  # mở trình duyệt cho người dùng cho phép
        _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload(job) -> dict:
    """Đăng final.mp4 lên YouTube. Trả {video_id, url}. Raise nếu thiếu điều kiện/lỗi."""
    if not config.YOUTUBE_CLIENT_SECRETS or not Path(config.YOUTUBE_CLIENT_SECRETS).is_file():
        raise RuntimeError("Chưa cấu hình YOUTUBE_CLIENT_SECRETS (file OAuth client của bạn)")
    if not libs_available():
        raise RuntimeError("Thiếu thư viện google-api-python-client + google-auth-oauthlib "
                           "(pip install trong .venv)")
    final = job.dir / "final.mp4"
    if not final.exists():
        raise FileNotFoundError("Chưa có final.mp4 (job chưa render xong)")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    meta = _meta(job)
    tags = meta.get("tags", [])
    privacy = config.YOUTUBE_PRIVACY if config.YOUTUBE_PRIVACY in _PRIVACY else "private"
    body = {
        "snippet": {
            "title": (meta.get("title") or job.url)[:100],
            "description": meta.get("description", "")[:5000],
            "tags": tags[:30] if isinstance(tags, list) else [],
            "categoryId": "1",   # Film & Animation
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    creds = _load_credentials()
    yt = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(str(final), chunksize=-1, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = req.execute()
    vid = resp["id"]

    thumb = job.dir / "thumbnail.jpg"
    if thumb.exists():
        try:
            yt.thumbnails().set(videoId=vid,
                                media_body=MediaFileUpload(str(thumb))).execute()
        except Exception:
            pass  # đặt thumbnail cần kênh đã xác minh; bỏ qua nếu lỗi
    return {"video_id": vid, "url": f"https://youtu.be/{vid}", "privacy": privacy}
