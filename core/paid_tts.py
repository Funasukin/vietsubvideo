"""PLAN 11 C/D — Engine TTS TRẢ PHÍ: ElevenLabs (C), VBee + FPT.AI (D).

Vì sao đáng tiền: chất giọng giống người nhất (ElevenLabs) / chuẩn giọng đọc
truyện VN (VBee, FPT) — và là đường AN TOÀN BẢN QUYỀN để bật kiếm tiền
(edge-tts/viXTTS không được dùng thương mại — xem ghi chú license).

Key nhập ở tab Cấu hình (lưu .env, che như bot token):
  - ELEVENLABS_API_KEY  (elevenlabs.io — ~$22/tháng gói Creator)
  - VBEE_TOKEN + VBEE_APP_ID  (vbee.vn/console)
  - FPT_TTS_API_KEY  (fpt.ai — TTS v5)
Giọng nam/nữ từng dịch vụ đặt trong Cấu hình. ElevenLabs (multilingual v2) đọc
được đa ngôn ngữ (dùng cả khi TARGET_LANG ≠ vi); VBee/FPT CHỈ tiếng Việt.

Toàn bộ gọi bằng urllib (không thêm dependency). Lỗi ném RuntimeError message
tiếng Việt rõ ràng → hiện thẳng trong run.log/j.error. LƯU Ý: VBee/FPT viết theo
docs công khai, chưa test đầu-cuối vì cần tài khoản trả phí — sai schema thì
message lỗi sẽ nói rõ server trả gì.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import config

ENGINES = ("elevenlabs", "vbee", "fpt")
VI_ONLY = ("vbee", "fpt")     # ElevenLabs multilingual đọc được nhiều ngôn ngữ


def is_paid(engine: str) -> bool:
    return engine in ENGINES


def ready(engine: str) -> tuple[bool, str]:
    """(đủ điều kiện chạy?, lý do thiếu) — kiểm TRƯỚC khi bắt đầu đọc cả job."""
    if engine == "elevenlabs":
        if not config.ELEVENLABS_API_KEY:
            return False, "Chưa nhập ELEVENLABS_API_KEY (tab Cấu hình)"
    elif engine == "vbee":
        if not (config.VBEE_TOKEN and config.VBEE_APP_ID):
            return False, "Chưa nhập VBEE_TOKEN + VBEE_APP_ID (tab Cấu hình)"
    elif engine == "fpt":
        if not config.FPT_TTS_API_KEY:
            return False, "Chưa nhập FPT_TTS_API_KEY (tab Cấu hình)"
    else:
        return False, f"Engine lạ: {engine}"
    return True, ""


def voice_pair(engine: str) -> tuple[str, str]:
    """(giọng nam, giọng nữ) đã cấu hình của engine."""
    return {
        "elevenlabs": (config.ELEVENLABS_VOICE_NAM, config.ELEVENLABS_VOICE_NU),
        "vbee": (config.VBEE_VOICE_NAM, config.VBEE_VOICE_NU),
        "fpt": (config.FPT_VOICE_NAM, config.FPT_VOICE_NU),
    }[engine]


def _http(req: urllib.request.Request, timeout: float = 60.0) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {body or e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"mạng lỗi: {e.reason}")


def _synth_elevenlabs(text: str, voice: str, out_path) -> None:
    if not voice:
        raise RuntimeError("Chưa đặt voice id ElevenLabs (tab Cấu hình)")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        data=json.dumps({
            "text": text,
            "model_id": config.ELEVENLABS_MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }).encode("utf-8"),
        headers={"xi-api-key": config.ELEVENLABS_API_KEY,
                 "Content-Type": "application/json"},
        method="POST")
    audio = _http(req, timeout=120)
    if len(audio) < 500:
        raise RuntimeError(f"ElevenLabs trả dữ liệu quá ngắn ({len(audio)} byte)")
    out_path.write_bytes(audio)


def _synth_fpt(text: str, voice: str, out_path) -> None:
    """FPT.AI TTS v5: trả link async → chờ file sẵn rồi tải về."""
    req = urllib.request.Request(
        "https://api.fpt.ai/hmi/tts/v5",
        data=text.encode("utf-8"),
        headers={"api-key": config.FPT_TTS_API_KEY, "voice": voice or "banmai",
                 "speed": "0"},
        method="POST")
    meta = json.loads(_http(req, timeout=60).decode("utf-8", errors="replace"))
    url = meta.get("async") or ""
    if int(meta.get("error", -1)) != 0 or not url.startswith("https://"):
        raise RuntimeError(f"FPT.AI từ chối: {json.dumps(meta, ensure_ascii=False)[:200]}")
    # file được dựng nền — thử tải tới ~20 giây
    last = None
    for _ in range(10):
        try:
            audio = _http(urllib.request.Request(url), timeout=30)
            if len(audio) > 500:
                out_path.write_bytes(audio)
                return
        except RuntimeError as e:
            last = e
        time.sleep(2)
    raise RuntimeError(f"FPT.AI: file audio không sẵn sàng sau 20s ({last})")


def _synth_vbee(text: str, voice: str, out_path) -> None:
    """VBee TTS v1 (viết theo docs công khai — chưa test vì cần token trả phí)."""
    if not voice:
        raise RuntimeError("Chưa đặt voice_code VBee (tab Cấu hình)")
    req = urllib.request.Request(
        "https://vbee.vn/api/v1/tts",
        data=json.dumps({
            "app_id": config.VBEE_APP_ID,
            "input_text": text,
            "voice_code": voice,
            "audio_type": "mp3",
            "speed_rate": "1.0",
            "response_type": "direct",
        }).encode("utf-8"),
        headers={"Authorization": "Bearer " + config.VBEE_TOKEN,
                 "Content-Type": "application/json"},
        method="POST")
    meta = json.loads(_http(req, timeout=120).decode("utf-8", errors="replace"))
    result = meta.get("result") or meta.get("data") or {}
    url = result.get("audio_link") or result.get("audio_url") or ""
    if not url.startswith("http"):
        raise RuntimeError(f"VBee không trả audio_link: "
                           f"{json.dumps(meta, ensure_ascii=False)[:200]}")
    audio = _http(urllib.request.Request(url), timeout=60)
    if len(audio) < 500:
        raise RuntimeError(f"VBee trả file quá ngắn ({len(audio)} byte)")
    out_path.write_bytes(audio)


def synth(engine: str, text: str, voice: str, out_path) -> None:
    """Đọc 1 câu bằng engine trả phí → mp3 out_path. Raise RuntimeError khi lỗi."""
    {"elevenlabs": _synth_elevenlabs,
     "vbee": _synth_vbee,
     "fpt": _synth_fpt}[engine](text, voice, out_path)
