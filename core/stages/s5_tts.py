"""S5: TTS từng segment bằng edge-tts → tts/seg_<id>.mp3.

edge-tts là API async, chạy đồng thời TTS_CONCURRENCY segment một lúc.
Interface output cố định (tts/seg_NNNN.mp3) để sau thay LucyLab/viXTTS dễ dàng.
"""
from __future__ import annotations

import asyncio
import json

import edge_tts

import time

import config
from core import emotion, langs, paid_tts, prosody, prosody_transfer
from core.job import Job

RETRIES = 4  # edge-tts hay lỗi NoAudioReceived tạm thời khi gọi song song


def _seg_path(job: Job, seg_id: int):
    return job.dir / "tts" / f"seg_{seg_id:04d}.mp3"


def _edge_voice(seg: dict) -> str:
    """Giọng edge-tts cho 1 câu theo NGÔN NGỮ ĐÍCH (#16): vi giữ TTS_VOICE/_NU trong
    Cấu hình, ngôn ngữ khác dùng cặp giọng của core/langs.py."""
    nam, nu = langs.edge_voices()
    return nu if seg.get("voice") == "nu" else nam


def _voice_sig(seg: dict) -> str:
    """Chữ ký giọng DỰ KIẾN của 1 câu (engine + nguồn giọng). Lưu cạnh mp3 (.sig) để
    resume biết file cũ có đúng giọng hiện tại không — nếu khác (đổi giọng/clip/engine,
    ĐỔI NGÔN NGỮ ĐÍCH, hay mp3 cũ từ trước khi có tính năng) thì đọc lại."""
    # đích ≠ vi: mọi câu (kể cả cast voice_ref) đọc edge theo ngôn ngữ — viXTTS là
    # finetune tiếng Việt, clone sang ngôn ngữ khác méo giọng. Sig đổi → tự đọc lại.
    pt = prosody_transfer.sig_tag()   # mức 3 bật/tắt → mọi câu tự xử lý lại
    eng = config.TTS_ENGINE
    if langs.is_vi() and seg.get("voice_ref"):
        return "vix:ref:" + seg["voice_ref"] + pt       # cast clip → luôn viXTTS
    nu = seg.get("voice") == "nu"
    # engine trả phí (PLAN 11 C/D): VBee/FPT chỉ tiếng Việt — đích khác rơi về edge
    if paid_tts.is_paid(eng) and not (eng in paid_tts.VI_ONLY and not langs.is_vi()):
        nam_v, nu_v = paid_tts.voice_pair(eng)
        return f"{eng}:" + (nu_v if nu else nam_v) + pt
    if langs.is_vi() and eng == "vixtts":
        # kèm nhãn cảm xúc: nhãn đổi → chọn clip mẫu khác → phải đọc lại
        return ("vix:def:" + (config.VIXTTS_VOICE_NU if nu else config.VIXTTS_VOICE_NAM)
                + emotion.sig_tag(seg) + pt)
    # kèm tông giọng (prosody) + nhãn cảm xúc — đổi là câu bị ảnh hưởng tự đọc lại
    return "edge:" + _edge_voice(seg) + prosody.sig_tag(seg) + emotion.sig_tag(seg) + pt


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
    voice = _edge_voice(seg)
    async with sem:
        for attempt in range(1, RETRIES + 1):
            out.unlink(missing_ok=True)
            try:
                communicate = edge_tts.Communicate(seg["text_vi"], voice,
                                                   **emotion.edge_kwargs(seg))
                await asyncio.wait_for(
                    communicate.save(str(out)), timeout=config.TTS_TIMEOUT_S
                )
            except Exception:
                if attempt == RETRIES:
                    raise
                await asyncio.sleep(2 ** attempt)  # 2s, 4s, 8s
                continue
            if out.exists() and out.stat().st_size > 0:
                prosody_transfer.apply(job, seg, out)   # mức 3: ép dáng ngữ điệu gốc
                # ghi giọng THỰC tế đã đọc (kèm tông giọng + cảm xúc) — giữ "edge:" tường
                # minh vì nhánh fallback vixtts→edge cần sig LỆCH _voice_sig để thử lại
                _write_sig(job, seg, "edge:" + voice + prosody.sig_tag(seg)
                           + emotion.sig_tag(seg) + prosody_transfer.sig_tag())
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
    # PLAN 11 mức 2 (B): câu có nhãn cảm xúc → clip mẫu hợp cảm xúc (giận→nhanh,
    # buồn→chậm...). Chỉ khi KHÔNG cast — danh tính nhân vật thắng cảm xúc.
    es = emotion.vixtts_sample(seg)
    if es:
        ref = _inside(es)
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
        prosody_transfer.apply(job, seg, out)   # mức 3: ép dáng ngữ điệu gốc
        _write_sig(job, seg, _voice_sig(seg))


def _tts_paid(job: Job, segments: list[dict]) -> None:
    """Đọc bằng engine trả phí (PLAN 11 C/D) — tuần tự + retry, resume theo .sig.
    Báo TRƯỚC tổng ký tự sẽ gửi (dịch vụ tính phí theo ký tự)."""
    eng = config.TTS_ENGINE
    ok, why = paid_tts.ready(eng)
    if not ok:
        raise RuntimeError(why)
    nam_v, nu_v = paid_tts.voice_pair(eng)
    todo = [s for s in segments if not _seg_ready(job, s)]
    if not todo:
        return
    total_chars = sum(len(s["text_vi"]) for s in todo)
    print(f"  {eng}: đọc {len(todo)} câu (~{total_chars} ký tự — dịch vụ TÍNH PHÍ theo ký tự)")
    for seg in todo:
        out = _seg_path(job, seg["id"])
        out.unlink(missing_ok=True)
        voice = nu_v if seg.get("voice") == "nu" else nam_v
        for attempt in range(1, 4):
            try:
                paid_tts.synth(eng, seg["text_vi"], voice, out)
                break
            except RuntimeError as e:
                if attempt == 3:
                    raise RuntimeError(f"{eng} lỗi ở câu {seg['id']}: {e}")
                time.sleep(2 * attempt)
        prosody_transfer.apply(job, seg, out)   # mức 3 vẫn áp được (xử lý audio output)
        _write_sig(job, seg, _voice_sig(seg))


def run(job: Job) -> None:
    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    # Casting series (#8): điền voice_ref theo character trước MỌI logic chọn giọng bên
    # dưới (sig cache + tách viXTTS/edge đều dựa voice_ref) → cùng nhân vật = cùng giọng
    # mọi tập; đổi bảng casting rồi chạy lại TTS là tự áp giọng mới (sig đổi → đọc lại).
    from core import series, speakers
    n_cast = series.apply_casting(job, data["segments"])
    if n_cast:
        print(f"  Casting: gán giọng theo nhân vật cho {n_cast} câu")
    # #8 Cụm người nói (diarize) → clip giọng riêng cho từng cụm CHƯA được cast
    # (chỉ engine viXTTS; casting series/chỉnh tay ở trên thắng vì đã set voice_ref)
    n_spk = speakers.assign_pool_refs(job, data["segments"])
    if n_spk:
        print(f"  Người nói → giọng: {n_spk} câu nhận clip theo cụm (speakers.json)")
    # Tông giọng theo audio gốc (PLAN 11 mức 1): đo trên TOÀN BỘ câu (kể cả mute —
    # mức nền người nói chuẩn hơn), chỉ câu đọc edge-tts dùng kết quả. Ghi lại
    # transcript để editor thấy được và lần resume sau đo ra vẫn khớp .sig.
    n_pro = prosody.measure(job, data["segments"])
    if n_pro:
        print(f"  Tông giọng (audio): chỉnh {n_pro} câu theo giọng gốc")
    (job.dir / "transcript_vi.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # bỏ câu rỗng và câu bị "Mute" (không lồng tiếng Việt, giữ tiếng gốc)
    segments = [s for s in data["segments"] if s["text_vi"].strip() and not s.get("mute")]
    if not segments:
        if not data["segments"]:
            raise RuntimeError("transcript_vi.json không có segment nào để đọc")
        print("  Tất cả câu rỗng/đã Mute — không đọc giọng nào (giữ tiếng gốc)")
        return

    (job.dir / "tts").mkdir(exist_ok=True)
    eng = config.TTS_ENGINE
    paid = paid_tts.is_paid(eng)
    if paid and eng in paid_tts.VI_ONLY and not langs.is_vi():
        print(f"  {eng} chỉ đọc tiếng Việt — đích {langs.name()} → dùng edge-tts")
        paid = False
    if paid:
        # câu cast giọng clone (voice_ref, chỉ tiếng Việt) vẫn đọc viXTTS như mọi engine;
        # phần còn lại đọc bằng dịch vụ trả phí. Thiếu key → fail rõ ràng (người dùng
        # đã chủ động chọn engine trả phí, âm thầm rơi về edge là phản bội lựa chọn đó).
        ref_segs = [s for s in segments if langs.is_vi() and s.get("voice_ref")]
        plain_segs = [s for s in segments if s not in ref_segs]
        _tts_paid(job, plain_segs)
        if ref_segs:
            try:
                _tts_vixtts(job, ref_segs)
            except Exception as e:
                print(f"  viXTTS lỗi cho câu cast giọng ({e}); đọc bằng edge-tts thay thế")
                asyncio.run(_tts_all(job, ref_segs))
    elif not langs.is_vi():
        # #16 đích ≠ tiếng Việt: đọc TẤT CẢ bằng edge-tts giọng của ngôn ngữ đó.
        # viXTTS/casting clone là finetune tiếng Việt — bỏ qua, kể cả câu voice_ref.
        if config.TTS_ENGINE == "vixtts" or any(s.get("voice_ref") for s in segments):
            print(f"  Đích {langs.name()}: viXTTS/casting clone tạm không áp dụng — "
                  f"toàn bộ đọc edge-tts ({langs.edge_voices()[0]})")
        asyncio.run(_tts_all(job, segments))
    elif config.TTS_ENGINE == "vixtts":
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
