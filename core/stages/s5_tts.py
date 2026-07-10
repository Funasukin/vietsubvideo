"""S5: TTS từng segment bằng edge-tts → tts/seg_<id>.mp3.

edge-tts là API async, chạy đồng thời TTS_CONCURRENCY segment một lúc.
Interface output cố định (tts/seg_NNNN.mp3) để sau thay LucyLab/viXTTS dễ dàng.
"""
from __future__ import annotations

import asyncio
import json
import os

import edge_tts

import time

import config
from core import duration, emotion, langs, paid_tts, prosody, prosody_transfer
from core.job import Job

RETRIES = 4  # edge-tts hay lỗi NoAudioReceived tạm thời khi gọi song song


def _seg_path(job: Job, seg_id: int):
    return job.dir / "tts" / f"seg_{seg_id:04d}.mp3"


def _seg_nu(seg: dict) -> bool:
    """Câu này đọc giọng NỮ? Chế độ 1 giọng (config.TTS_SINGLE_VOICE) bỏ phân biệt
    nam/nữ → luôn False: mọi câu KHÔNG cast dùng giọng chính. Câu đã cast (voice_ref)
    vẫn giữ giọng riêng vì được xử lý trước, không đi qua nhánh nam/nữ này."""
    return seg.get("voice") == "nu" and not config.TTS_SINGLE_VOICE


def _edge_voice(seg: dict) -> str:
    """Giọng edge-tts cho 1 câu theo NGÔN NGỮ ĐÍCH (#16): vi giữ TTS_VOICE/_NU trong
    Cấu hình, ngôn ngữ khác dùng cặp giọng của core/langs.py."""
    nam, nu = langs.edge_voices()
    return nu if _seg_nu(seg) else nam


def _tts_settings():
    """Ảnh chụp cấu hình giọng HIỆN HÀNH (module config đã áp .env + override job
    qua FLOWAPP_JOB_OVERRIDES trong tiến trình worker). Cache theo lần gọi stage."""
    from core import voicesig
    return voicesig.TtsSettings.from_env({
        "TARGET_LANG": langs.code(),
        "TTS_ENGINE": config.TTS_ENGINE,
        "TTS_SINGLE_VOICE": "1" if config.TTS_SINGLE_VOICE else "0",
        "TTS_VOICE": config.TTS_VOICE, "TTS_VOICE_NU": config.TTS_VOICE_NU,
        "VIXTTS_VOICE_NAM": config.VIXTTS_VOICE_NAM,
        "VIXTTS_VOICE_NU": config.VIXTTS_VOICE_NU,
        "ELEVENLABS_VOICE_NAM": config.ELEVENLABS_VOICE_NAM,
        "ELEVENLABS_VOICE_NU": config.ELEVENLABS_VOICE_NU,
        "VBEE_VOICE_NAM": config.VBEE_VOICE_NAM, "VBEE_VOICE_NU": config.VBEE_VOICE_NU,
        "FPT_VOICE_NAM": config.FPT_VOICE_NAM, "FPT_VOICE_NU": config.FPT_VOICE_NU,
        "MAX_SPEEDUP": str(config.MAX_SPEEDUP),
        "PROSODY_TRANSFER": config.PROSODY_TRANSFER,
        "EMOTION": config.EMOTION,
    })


def _voice_sig(seg: dict) -> str:
    """Chữ ký giọng DỰ KIẾN của 1 câu (engine + nguồn giọng). Lưu cạnh mp3 (.sig) để
    resume biết file cũ có đúng giọng hiện tại không — nếu khác (đổi giọng/clip/engine,
    ĐỔI NGÔN NGỮ ĐÍCH, hay mp3 cũ từ trước khi có tính năng) thì đọc lại.
    Đợt U-2: logic thật nằm ở core/voicesig.voice_signature (resolver thuần dữ liệu,
    endpoint /override-impact dùng CHUNG) — sửa format sig là sửa Ở ĐÓ."""
    from core import voicesig
    return voicesig.voice_signature(seg, _tts_settings())


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


def _fit_budget() -> int:
    """Ngân sách tăng tốc VÌ KHỚP THOẠI (%) theo núm MAX_SPEEDUP — deterministic nên
    nằm được trong .sig: user đổi núm → sig lệch → các câu (edge LẪN viXTTS) tự đọc
    lại đúng mức mới. Logic chung ở core/voicesig.fit_budget (resolver dùng cùng số)."""
    from core import voicesig
    return voicesig.fit_budget(config.MAX_SPEEDUP)


async def _fit_slot(seg: dict, voice: str, out, fit_log: dict) -> None:
    """Chống tràn thoại — bản TRỌNG TÀI (đợt B audit giọng): bản đọc DÀI hơn limit
    (slot − fade guard) → đọc lại MỘT lần với rate tính bằng CÔNG THỨC CHÉO
    (duration.edge_total_rate) trên thước ĐÃ CẮT LẶNG — cùng thước với S7, hết
    "tràn giả" do đuôi câm edge. Phần engine tiêu (engine_speed) ghi vào fit_log
    để S7 chỉ atempo trong ngân sách CÒN LẠI (tích ≤ MAX_SPEEDUP).
    Lỗi ở bước này → giữ bản gốc (S7 lo), không chết job."""
    entry: dict = {"engine_speed": 1.0}
    fit_log[str(seg["id"])] = entry
    dur = duration.trimmed_dur_s(out)
    if dur:
        entry["trimmed_ms"] = int(dur * 1000)
    slot = seg.get("_slot_s")
    if not slot or not dur:
        return
    k = duration.fit_speed(dur, slot)         # 1.0 = đã lọt limit (deadzone)
    if k <= 1.0:
        return
    k = min(k, config.MAX_SPEEDUP)            # ngân sách TỔNG của user
    kw = emotion.edge_kwargs(seg)
    base = int(kw.get("rate", "+0%").rstrip("%"))
    # base (prosody/cảm xúc) là diễn cảm — giữ nguyên; rate mới = base ⊗ k (có số
    # hạng chéo), kẹp trần an toàn giọng +50% (nhanh hơn nghe máy móc).
    total = min(duration.EDGE_RATE_MAX, duration.edge_total_rate(base, k))
    if total <= base:
        return
    kw["rate"] = f"{total:+d}%"
    tmp = out.with_suffix(".fit.mp3")
    try:
        await asyncio.wait_for(
            edge_tts.Communicate(seg["text_vi"], voice, **kw).save(str(tmp)),
            timeout=config.TTS_TIMEOUT_S)
        if tmp.exists() and tmp.stat().st_size > 0:
            dur2 = duration.trimmed_dur_s(tmp)
            if dur2 and dur2 < dur:   # chỉ nhận bản THẬT SỰ ngắn hơn
                os.replace(tmp, out)
                # nén cơ học YÊU CẦU (so với bản đang phát) — variance của engine
                # không tính vào ngân sách (đồng bộ cách tính với nhánh viXTTS)
                k_req = (1 + total / 100) / (1 + base / 100)
                entry["engine_speed"] = round(min(k_req, dur / dur2), 3)
                entry["speed_got"] = round(dur / dur2, 3)
                entry["trimmed_ms"] = int(dur2 * 1000)
                print(f"  ↳ câu {seg['id']}: {dur:.1f}s > slot {slot:.1f}s "
                      f"→ đọc lại rate {total:+d}% → {dur2:.1f}s")
    except Exception:
        pass
    finally:
        tmp.unlink(missing_ok=True)


async def _tts_one(sem: asyncio.Semaphore, job: Job, seg: dict, fit_log: dict) -> None:
    out = _seg_path(job, seg["id"])
    # bỏ qua nếu mp3 còn đúng giọng (khớp .sig); 0 byte/khác giọng → đọc lại
    if _seg_ready(job, seg):
        return  # resume — fit_report cũ của câu này còn nguyên trong file
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
                await _fit_slot(seg, voice, out, fit_log)  # chống tràn: dài quá limit → đọc lại nhanh hơn
                prosody_transfer.apply(job, seg, out)   # mức 3: ép dáng ngữ điệu gốc
                # ghi giọng THỰC tế đã đọc (kèm tông giọng + cảm xúc + ngân sách fit) —
                # giữ "edge:" tường minh vì nhánh fallback vixtts→edge cần sig LỆCH
                # _voice_sig để thử lại
                _write_sig(job, seg, "edge:" + voice + prosody.sig_tag(seg)
                           + emotion.sig_tag(seg) + f":f{_fit_budget()}"
                           + prosody_transfer.sig_tag())
                return
            if attempt == RETRIES:
                raise RuntimeError(
                    f"edge-tts trả file rỗng cho segment {seg['id']} sau {RETRIES} lần thử"
                )
            await asyncio.sleep(2 ** attempt)


async def _tts_all(job: Job, segments: list[dict], fit_log: dict) -> None:
    sem = asyncio.Semaphore(config.TTS_CONCURRENCY)
    await asyncio.gather(*(_tts_one(sem, job, s, fit_log) for s in segments))


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
    name = config.VIXTTS_VOICE_NU if _seg_nu(seg) else config.VIXTTS_VOICE_NAM
    ref = _inside(name)
    if ref:
        return ref
    return str(config.VIXTTS_DIR / "vi_sample.wav")  # mẫu đi kèm model


def _tts_vixtts(job: Job, segments: list[dict], fit_log: dict) -> None:
    """Lồng tiếng bằng viXTTS (GPU, tuần tự). Resume: bỏ câu đã có file.

    Đợt B audit giọng: viXTTS trước đây THẢ NỔI độ dài (median 2.5× thoại gốc, toàn
    bộ khớp nhịp dồn cho atempo S7). Giờ đo bản đọc (đã cắt lặng) — vượt limit thì
    synth LẠI 1 lần với speed của XTTS (nén ngay lúc đọc, tự nhiên hơn atempo);
    phần dư còn lại S7 lo trong ngân sách MAX_SPEEDUP / engine_speed."""
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
            continue   # mp3 còn đúng giọng — fit_report cũ của câu này còn nguyên
        out = _seg_path(job, seg["id"])
        out.unlink(missing_ok=True)   # xoá mp3 giọng cũ (nếu có) trước khi đọc lại
        ref = _vixtts_ref(seg)
        vixtts.synth(seg["text_vi"], ref, str(out))
        entry: dict = {"engine_speed": 1.0}
        fit_log[str(seg["id"])] = entry
        dur = duration.trimmed_dur_s(out)
        if dur:
            entry["trimmed_ms"] = int(dur * 1000)
        slot = seg.get("_slot_s")
        if slot and dur:
            k = duration.fit_speed(dur, slot)   # 1.0 = lọt limit (deadzone) → không đụng
            speed = min(k, duration.VIXTTS_SPEED_MAX, config.MAX_SPEEDUP)
            if speed > 1.03:   # chênh dưới 3% không đáng một lần synth GPU
                tmp = out.with_suffix(".fit.mp3")
                try:
                    vixtts.synth(seg["text_vi"], ref, str(tmp), speed=speed)
                    d2 = duration.trimmed_dur_s(tmp)
                    # XTTS nondeterministic — chỉ nhận bản THẬT SỰ ngắn hơn
                    if d2 and d2 < dur:
                        os.replace(tmp, out)
                        # ngân sách tính theo mức NÉN CƠ HỌC yêu cầu (speed), không
                        # tính phần model tình cờ đọc ngắn hơn (variance tự nhiên,
                        # không phải nén) — kẻo "tổng nén" báo ảo 2.6× dù speed 1.25
                        entry["engine_speed"] = round(min(speed, dur / d2), 3)
                        entry["speed_got"] = round(dur / d2, 3)
                        entry["trimmed_ms"] = int(d2 * 1000)
                        print(f"  ↳ câu {seg['id']}: {dur:.1f}s > slot {slot:.1f}s "
                              f"→ viXTTS speed {speed:.2f} → {d2:.1f}s")
                except Exception as e:   # giữ bản thường, S7 lo phần dư
                    print(f"  ↳ câu {seg['id']}: synth lại speed lỗi ({e}) — giữ bản thường")
                finally:
                    tmp.unlink(missing_ok=True)
        prosody_transfer.apply(job, seg, out)   # mức 3: ép dáng ngữ điệu gốc
        _write_sig(job, seg, _voice_sig(seg))


def _tts_paid(job: Job, segments: list[dict], fit_log: dict) -> None:
    """Đọc bằng engine trả phí (PLAN 11 C/D) — tuần tự + retry, resume theo .sig.
    Báo TRƯỚC tổng ký tự sẽ gửi (dịch vụ tính phí theo ký tự).
    Chưa có fit lúc synth (speed các provider đang cố định) — chỉ ĐO và ghi
    engine_speed=1.0 để S7 dùng trọn ngân sách MAX_SPEEDUP như trước."""
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
        voice = nu_v if _seg_nu(seg) else nam_v
        for attempt in range(1, 4):
            try:
                paid_tts.synth(eng, seg["text_vi"], voice, out)
                break
            except RuntimeError as e:
                if attempt == 3:
                    raise RuntimeError(f"{eng} lỗi ở câu {seg['id']}: {e}")
                time.sleep(2 * attempt)
        entry: dict = {"engine_speed": 1.0}
        dur = duration.trimmed_dur_s(out)
        if dur:
            entry["trimmed_ms"] = int(dur * 1000)
        fit_log[str(seg["id"])] = entry
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
    # Gắn slot GIÂY cho từng câu (đến start câu KẾ, kể cả câu mute — cùng công thức
    # với S7) → edge-tts tự đọc lại nhanh hơn khi bản đọc dài quá slot (_fit_slot).
    # Gắn SAU khi ghi transcript: khóa "_slot_s" chỉ sống trong RAM, không vào file.
    full = sorted(data["segments"], key=lambda s: s["start"])
    for k, s in enumerate(full):
        nxt = full[k + 1]["start"] if k + 1 < len(full) else None
        s["_slot_s"] = max(0.3, nxt - s["start"]) if nxt is not None else None
    # bỏ câu rỗng và câu bị "Mute" (không lồng tiếng Việt, giữ tiếng gốc)
    segments = [s for s in data["segments"] if s["text_vi"].strip() and not s.get("mute")]
    if not segments:
        if not data["segments"]:
            raise RuntimeError("transcript_vi.json không có segment nào để đọc")
        print("  Tất cả câu rỗng/đã Mute — không đọc giọng nào (giữ tiếng gốc)")
        return

    (job.dir / "tts").mkdir(exist_ok=True)
    # Trọng tài thời lượng: sổ đo per-câu (trimmed + engine_speed đã tiêu) cho S7.
    # Nạp bản cũ trước — câu cache (sig khớp, không đọc lại) giữ nguyên số đo cũ.
    fit_log = duration.load_report(job.dir)
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
        _tts_paid(job, plain_segs, fit_log)
        if ref_segs:
            try:
                _tts_vixtts(job, ref_segs, fit_log)
            except Exception as e:
                print(f"  viXTTS lỗi cho câu cast giọng ({e}); đọc bằng edge-tts thay thế")
                asyncio.run(_tts_all(job, ref_segs, fit_log))
    elif not langs.is_vi():
        # #16 đích ≠ tiếng Việt: đọc TẤT CẢ bằng edge-tts giọng của ngôn ngữ đó.
        # viXTTS/casting clone là finetune tiếng Việt — bỏ qua, kể cả câu voice_ref.
        if config.TTS_ENGINE == "vixtts" or any(s.get("voice_ref") for s in segments):
            print(f"  Đích {langs.name()}: viXTTS/casting clone tạm không áp dụng — "
                  f"toàn bộ đọc edge-tts ({langs.edge_voices()[0]})")
        asyncio.run(_tts_all(job, segments, fit_log))
    elif config.TTS_ENGINE == "vixtts":
        try:
            _tts_vixtts(job, segments, fit_log)
        except Exception as e:
            print(f"  viXTTS lỗi ({e}); fallback edge-tts")
            asyncio.run(_tts_all(job, segments, fit_log))
    else:
        # Engine mặc định = edge, NHƯNG câu được CAST giọng clip (voice_ref) vẫn phải đọc
        # bằng viXTTS (giọng nhân bản) — casting luôn dùng clone bất kể engine. Câu còn lại
        # (nam/nữ) đọc nhanh bằng edge-tts. Nhờ vậy chọn giọng 🎙 mới có tác dụng khi render.
        ref_segs = [s for s in segments if s.get("voice_ref")]
        plain_segs = [s for s in segments if not s.get("voice_ref")]
        if plain_segs:
            asyncio.run(_tts_all(job, plain_segs, fit_log))
        if ref_segs:
            try:
                _tts_vixtts(job, ref_segs, fit_log)
            except Exception as e:
                print(f"  viXTTS lỗi cho câu cast giọng ({e}); đọc bằng edge-tts thay thế")
                asyncio.run(_tts_all(job, ref_segs, fit_log))
    duration.save_report(job.dir, fit_log)

    missing = [
        s["id"] for s in segments
        if not _seg_path(job, s["id"]).exists() or _seg_path(job, s["id"]).stat().st_size == 0
    ]
    if missing:
        raise RuntimeError(f"edge-tts không tạo được file cho segment: {missing}")
