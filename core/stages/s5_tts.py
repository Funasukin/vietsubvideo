"""S5: TTS từng segment bằng edge-tts → tts/seg_<id>.mp3.

edge-tts là API async, chạy đồng thời TTS_CONCURRENCY segment một lúc.
Interface output cố định (tts/seg_NNNN.mp3) để sau thay LucyLab/viXTTS dễ dàng.
"""
from __future__ import annotations

import asyncio
import json

import edge_tts

import config
from core.job import Job

RETRIES = 4  # edge-tts hay lỗi NoAudioReceived tạm thời khi gọi song song


def _seg_path(job: Job, seg_id: int):
    return job.dir / "tts" / f"seg_{seg_id:04d}.mp3"


def _voice_sig(seg: dict) -> str:
    """Chữ ký giọng DỰ KIẾN của 1 câu (engine + nguồn giọng). Lưu cạnh mp3 (.sig) để
    resume biết file cũ có đúng giọng hiện tại không — nếu khác (đổi giọng/clip/engine,
    hay mp3 cũ từ trước khi có tính năng) thì đọc lại, không giữ giọng cũ."""
    if seg.get("voice_ref"):
        return "vix:ref:" + seg["voice_ref"]          # cast clip → luôn viXTTS
    nu = seg.get("voice") == "nu"
    if config.TTS_ENGINE == "vixtts":
        return "vix:def:" + (config.VIXTTS_VOICE_NU if nu else config.VIXTTS_VOICE_NAM)
    return "edge:" + (config.TTS_VOICE_NU if nu else config.TTS_VOICE)


def _seg_ready(job: Job, seg: dict) -> bool:
    """mp3 đã tồn tại + đúng giọng hiện tại (chữ ký .sig khớp). 0 byte / thiếu .sig /
    .sig khác → coi như chưa xong, đọc lại."""
    out = _seg_path(job, seg["id"])
    if not (out.exists() and out.stat().st_size > 0):
        return False
    try:
        return out.with_suffix(".sig").read_text(encoding="utf-8") == _voice_sig(seg)
    except OSError:
        return False


def _write_sig(job: Job, seg: dict, sig: str) -> None:
    _seg_path(job, seg["id"]).with_suffix(".sig").write_text(sig, encoding="utf-8")


async def _tts_one(sem: asyncio.Semaphore, job: Job, seg: dict) -> None:
    out = _seg_path(job, seg["id"])
    # bỏ qua nếu mp3 còn đúng giọng (khớp .sig); 0 byte/khác giọng → đọc lại
    if _seg_ready(job, seg):
        return  # resume
    voice = config.TTS_VOICE_NU if seg.get("voice") == "nu" else config.TTS_VOICE
    async with sem:
        for attempt in range(1, RETRIES + 1):
            out.unlink(missing_ok=True)
            try:
                communicate = edge_tts.Communicate(seg["text_vi"], voice)
                await asyncio.wait_for(
                    communicate.save(str(out)), timeout=config.TTS_TIMEOUT_S
                )
            except Exception:
                if attempt == RETRIES:
                    raise
                await asyncio.sleep(2 ** attempt)  # 2s, 4s, 8s
                continue
            if out.exists() and out.stat().st_size > 0:
                _write_sig(job, seg, "edge:" + voice)   # ghi giọng THỰC tế đã đọc
                return
            if attempt == RETRIES:
                raise RuntimeError(
                    f"edge-tts trả file rỗng cho segment {seg['id']} sau {RETRIES} lần thử"
                )
            await asyncio.sleep(2 ** attempt)


async def _tts_all(job: Job, segments: list[dict]) -> None:
    sem = asyncio.Semaphore(config.TTS_CONCURRENCY)
    await asyncio.gather(*(_tts_one(sem, job, s) for s in segments))


def _vixtts_ref(seg: dict) -> str:
    """Chọn clip giọng mẫu cho 1 segment: ưu tiên voice_ref (casting theo nhân vật),
    rồi map nam/nu, cuối cùng mẫu mặc định của model."""
    base = config.VOICES_DIR.resolve()

    def _inside(name: str) -> str | None:
        """Trả path nếu name là file hợp lệ NẰM TRONG voices/ (chặn cả ../ lẫn 'C:x')."""
        if not name:
            return None
        p = (config.VOICES_DIR / name).resolve()
        return str(p) if p.is_relative_to(base) and p.is_file() else None

    ref = _inside(seg.get("voice_ref") or "")
    if ref:
        return ref
    name = config.VIXTTS_VOICE_NU if seg.get("voice") == "nu" else config.VIXTTS_VOICE_NAM
    ref = _inside(name)
    if ref:
        return ref
    return str(config.VIXTTS_DIR / "vi_sample.wav")  # mẫu đi kèm model


def _tts_vixtts(job: Job, segments: list[dict]) -> None:
    """Lồng tiếng bằng viXTTS (GPU, tuần tự). Resume: bỏ câu đã có file."""
    from core import vixtts
    if not vixtts.is_available():
        raise RuntimeError("viXTTS không sẵn sàng")
    # cần giọng mặc định CHỈ khi có câu KHÔNG cast clip riêng (câu cast clip tự đủ giọng);
    # kẻo synth crash giữa chừng → âm thầm về edge
    if (any(not s.get("voice_ref") for s in segments)
            and not (config.VIXTTS_DIR / "vi_sample.wav").is_file()
            and not (config.VIXTTS_VOICE_NAM or config.VIXTTS_VOICE_NU)):
        raise RuntimeError("Thiếu giọng viXTTS mặc định (vi_sample.wav) "
                           "và chưa đặt giọng nam/nữ trong Cấu hình")
    for seg in segments:
        if _seg_ready(job, seg):
            continue   # mp3 còn đúng giọng
        out = _seg_path(job, seg["id"])
        out.unlink(missing_ok=True)   # xoá mp3 giọng cũ (nếu có) trước khi đọc lại
        vixtts.synth(seg["text_vi"], _vixtts_ref(seg), str(out))
        _write_sig(job, seg, _voice_sig(seg))


def run(job: Job) -> None:
    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    # Casting series (#8): điền voice_ref theo character trước MỌI logic chọn giọng bên
    # dưới (sig cache + tách viXTTS/edge đều dựa voice_ref) → cùng nhân vật = cùng giọng
    # mọi tập; đổi bảng casting rồi chạy lại TTS là tự áp giọng mới (sig đổi → đọc lại).
    from core import series
    n_cast = series.apply_casting(job, data["segments"])
    if n_cast:
        print(f"  Casting: gán giọng theo nhân vật cho {n_cast} câu")
    # bỏ câu rỗng và câu bị "Mute" (không lồng tiếng Việt, giữ tiếng gốc)
    segments = [s for s in data["segments"] if s["text_vi"].strip() and not s.get("mute")]
    if not segments:
        if not data["segments"]:
            raise RuntimeError("transcript_vi.json không có segment nào để đọc")
        print("  Tất cả câu rỗng/đã Mute — không đọc giọng nào (giữ tiếng gốc)")
        return

    (job.dir / "tts").mkdir(exist_ok=True)
    if config.TTS_ENGINE == "vixtts":
        try:
            _tts_vixtts(job, segments)
        except Exception as e:
            print(f"  viXTTS lỗi ({e}); fallback edge-tts")
            asyncio.run(_tts_all(job, segments))
    else:
        # Engine mặc định = edge, NHƯNG câu được CAST giọng clip (voice_ref) vẫn phải đọc
        # bằng viXTTS (giọng nhân bản) — casting luôn dùng clone bất kể engine. Câu còn lại
        # (nam/nữ) đọc nhanh bằng edge-tts. Nhờ vậy chọn giọng 🎙 mới có tác dụng khi render.
        ref_segs = [s for s in segments if s.get("voice_ref")]
        plain_segs = [s for s in segments if not s.get("voice_ref")]
        if plain_segs:
            asyncio.run(_tts_all(job, plain_segs))
        if ref_segs:
            try:
                _tts_vixtts(job, ref_segs)
            except Exception as e:
                print(f"  viXTTS lỗi cho câu cast giọng ({e}); đọc bằng edge-tts thay thế")
                asyncio.run(_tts_all(job, ref_segs))

    missing = [
        s["id"] for s in segments
        if not _seg_path(job, s["id"]).exists() or _seg_path(job, s["id"]).stat().st_size == 0
    ]
    if missing:
        raise RuntimeError(f"edge-tts không tạo được file cho segment: {missing}")
