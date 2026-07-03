"""#8 Nhận diện NGƯỜI NÓI từ audio thật (diarization — pyannote) → casting theo nhân vật.

Trả lời "câu nào do CÙNG một người nói?" bằng chính giọng trong audio gốc thay vì
để Claude đoán từ chữ. Dùng cho 2 việc:
  1. S4: gắn seg["speaker"] = "S1".."Sn" và đưa nhãn vào batch dịch → Claude gán
     character/voice nhất quán (các câu cùng speaker chắc chắn là một người).
     Cuối S4: giới tính tính theo CỤM (trung vị F0 cả cụm — nhiều dữ liệu hơn từng
     câu) đồng bộ nhãn voice toàn cụm.
  2. S5 (engine viXTTS): cụm chưa được cast theo tên nhân vật tự nhận MỘT clip
     giọng riêng trong voices/ (đúng giới tính cụm) → phim nhiều nhân vật ra nhiều
     giọng mà không phải cast tay. Casting series/chỉnh tay luôn THẮNG.

Cài đặt (khuyến nghị desktop GPU, CPU chạy được nhưng chậm):
    pip install pyannote.audio
Cần HF_TOKEN trong .env + chấp nhận điều khoản 2 model trên huggingface.co:
    pyannote/segmentation-3.0  và  pyannote/speaker-diarization-3.1
Bật bằng DIARIZE=1. Thiếu bất cứ thứ gì → bỏ qua êm, pipeline chạy như cũ.

Kết quả lưu trong job dir:
  diar_turns.json — lượt nói thô [{"start","end","speaker"}] (cache, chạy lại free)
  speakers.json   — hồ sơ cụm {"S1": {"gender","f0","seconds","segments","voice_ref"}}
                    voice_ref sửa tay được; chạy lại TTS là áp (sig đổi → đọc lại).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import config

# Nhắc thêm vào system prompt dịch khi có nhãn speaker (S4)
SPEAKER_HINT = (
    "\n\nNHÃN NGƯỜI NÓI: một số segment có trường \"speaker\" (S1, S2...) — nhận từ "
    "phân tích GIỌNG trong audio gốc: các câu cùng nhãn chắc chắn do CÙNG một người "
    "nói. Dùng nhãn này để gán \"voice\" và \"character\" nhất quán (cùng speaker → "
    "cùng nhân vật, cùng voice), nhất là khi ngữ cảnh chữ không đủ rõ.")

# Segment khớp lượt nói khi trùng ≥ 0.3s hoặc ≥ 50% thời lượng câu (câu ngắn)
_MIN_OVERLAP_S = 0.3


def enabled() -> bool:
    return str(config.DIARIZE).strip().lower() in ("1", "true")


def diarize(job_dir, audio_path) -> list[dict] | None:
    """Chạy pyannote → lượt nói [{"start","end","speaker"}]; cache diar_turns.json
    (resume/dịch lại không tốn diarize lần nữa). None nếu tắt/thiếu điều kiện."""
    if not enabled():
        return None
    cache = Path(job_dir) / "diar_turns.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    token = (config.HF_TOKEN or "").strip()
    if not token:
        print("  Người nói: DIARIZE=1 nhưng thiếu HF_TOKEN trong .env — bỏ qua")
        return None
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError:
        print("  Người nói: chưa cài pyannote.audio (xem requirements.txt) — bỏ qua")
        return None
    try:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
                                        use_auth_token=token)
        if torch.cuda.is_available():
            pipe.to(torch.device("cuda"))
        kw = {}
        if config.DIARIZE_MAX_SPK > 0:
            kw["max_speakers"] = config.DIARIZE_MAX_SPK
        ann = pipe(str(audio_path), **kw)
        turns = []
        for turn, _, label in ann.itertracks(yield_label=True):
            # SPEAKER_00 → S1 (nhãn ngắn cho prompt đỡ tốn token)
            s = str(label)
            if s.startswith("SPEAKER_"):
                s = f"S{int(s.rsplit('_', 1)[-1]) + 1}"
            turns.append({"start": round(float(turn.start), 3),
                          "end": round(float(turn.end), 3), "speaker": s})
        cache.write_text(json.dumps(turns, ensure_ascii=False), encoding="utf-8")
        return turns
    except Exception as e:
        print(f"  Người nói: diarize lỗi ({e}) — bỏ qua, pipeline chạy như cũ")
        return None


def assign(segments: list[dict], turns: list[dict]) -> int:
    """Gắn seg["speaker"] = lượt nói trùng thời gian NHIỀU NHẤT. Trả số câu gán được."""
    if not turns:
        return 0
    n = 0
    for seg in segments:
        best, best_ov = None, 0.0
        for t in turns:
            ov = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
            if ov > best_ov:
                best_ov, best = ov, t["speaker"]
        dur = max(0.001, seg["end"] - seg["start"])
        if best and best_ov >= min(_MIN_OVERLAP_S, 0.5 * dur):
            seg["speaker"] = best
            n += 1
    return n


def profiles(job_dir, audio_path, segments: list[dict]) -> dict:
    """Hồ sơ từng cụm: giây thoại, số câu, F0 trung vị cụm → gender. Không đủ dữ
    liệu F0 thì lấy theo ĐA SỐ nhãn voice hiện có của cụm. Ghi speakers.json,
    GIỮ voice_ref người dùng đã sửa tay/lần chạy trước."""
    from core import gender
    spk: dict[str, dict] = {}
    f0s: dict[str, list[float]] = {}
    votes: dict[str, list[str]] = {}
    try:
        samples, sr = gender._read_mono(audio_path)
    except Exception:
        samples, sr = None, 0

    for seg in segments:
        s = seg.get("speaker")
        if not s:
            continue
        p = spk.setdefault(s, {"seconds": 0.0, "segments": 0})
        p["seconds"] += max(0.0, seg["end"] - seg["start"])
        p["segments"] += 1
        if seg.get("voice") in ("nam", "nu"):
            votes.setdefault(s, []).append(seg["voice"])
        if samples is not None:
            a = max(0, int(seg["start"] * sr))
            b = min(len(samples), int(seg["end"] * sr))
            if b - a >= int(0.15 * sr):
                f0 = gender._segment_f0(samples[a:b], sr)
                if f0 and f0 <= gender.NU_CEIL:
                    f0s.setdefault(s, []).append(f0)

    for s, p in spk.items():
        med = float(np.median(f0s[s])) if f0s.get(s) else None
        p["f0"] = round(med, 1) if med else None
        g = None
        if med:
            g = "nam" if med < gender.NAM_MAX else "nu" if med > gender.NU_MIN else None
        if g is None and votes.get(s):   # F0 mơ hồ → theo đa số nhãn sẵn có của cụm
            v = votes[s]
            g = "nu" if v.count("nu") > len(v) / 2 else "nam"
        p["gender"] = g
        p["seconds"] = round(p["seconds"], 1)

    path = Path(job_dir) / "speakers.json"
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            for s, p in spk.items():
                vr = (old.get(s) or {}).get("voice_ref")
                if vr:
                    p["voice_ref"] = vr
        except (json.JSONDecodeError, OSError):
            pass
    path.write_text(json.dumps(spk, ensure_ascii=False, indent=2), encoding="utf-8")
    return spk


def assign_pool_refs(job, segments: list[dict]) -> int:
    """S5, chỉ khi TTS_ENGINE=vixtts: cụm chưa có voice_ref → chia clip voices/ theo
    giới tính cụm (round-robin theo thứ hạng thời lượng thoại — nhân vật nói nhiều
    nhận clip đầu tiên). KHÔNG đè voice_ref đã có trên segment (casting tên/chỉnh
    tay thắng). Trả số câu vừa gán."""
    if config.TTS_ENGINE != "vixtts":
        return 0
    path = job.dir / "speakers.json"
    if not path.exists():
        return 0
    try:
        prof = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    if not prof:
        return 0

    wavs = sorted(p.name for p in config.VOICES_DIR.glob("*.wav"))
    pool = {"nam": [n for n in wavs if "nam" in n.lower()],
            "nu": [n for n in wavs if "nu" in n.lower()]}
    # thiếu pool theo giới → dùng giọng mặc định engine, rồi mới tới toàn bộ voices/
    fallback = [n for n in (config.VIXTTS_VOICE_NAM, config.VIXTTS_VOICE_NU) if n] or wavs
    changed = False
    idx = {"nam": 0, "nu": 0}
    for s in sorted(prof, key=lambda k: -float(prof[k].get("seconds") or 0)):
        p = prof[s]
        if p.get("voice_ref"):
            continue
        g = p.get("gender") or "nam"
        cand = pool.get(g) or fallback
        if not cand:
            return 0            # voices/ trống — không có gì để chia
        p["voice_ref"] = cand[idx.get(g, 0) % len(cand)]
        idx[g] = idx.get(g, 0) + 1
        changed = True

    n = 0
    for seg in segments:
        vr = (prof.get(seg.get("speaker") or "") or {}).get("voice_ref")
        if vr and not seg.get("voice_ref"):
            seg["voice_ref"] = vr
            n += 1
    if changed:
        path.write_text(json.dumps(prof, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return n
