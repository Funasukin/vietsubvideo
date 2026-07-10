"""W-0 (DEXUAT_WORKER_THUONGTRU_TONGHOP.md): đo cold/warm model để quyết định
worker thường trú / model host BẰNG SỐ thay vì cảm giác.

Kỷ luật đo (theo phản biện Codex): MỖI case chạy trong MỘT SUBPROCESS MỚI —
đo whisper xong đo viXTTS trong cùng tiến trình là torch đã ấm, số đẹp giả.
Kết quả append JSONL (data/bench_models.jsonl — data/ không commit) để so lại
sau khi nâng cấp package; console in bảng median [min–max].

Chạy:  .venv\\Scripts\\python -X utf8 scripts\\bench_models.py
       [--runs 3] [--cases baseline,import,whisper,vixtts,demucs,ocr]
       [--synth]   (viXTTS: đo thêm synth lần 1 / lần 2 cùng ref / ref khác — GPU)
       [--clip path.wav]  (whisper: đo thêm transcribe lần 1/2 trên clip này)
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MARK = "BENCH_JSON:"   # child in 1 dòng JSON có prefix này; parent nhặt ra

# ---------------------------------------------------------------- child cases
# Mỗi case tự đo các bước của nó bằng perf_counter và trả dict {bước: giây}.


def _case_baseline(_a) -> dict:
    return {}   # chỉ để parent đo wall time của một tiến trình Python trống


def _case_import(_a) -> dict:
    t0 = time.perf_counter()
    import core.pipeline  # noqa: F401 — đúng stack cli.py trả mỗi job
    return {"import_pipeline_s": time.perf_counter() - t0}


def _case_whisper(a) -> dict:
    import config
    from core.stages.s3_transcript import _add_cuda_dll_dirs
    _add_cuda_dll_dirs()
    out: dict = {"model": config.WHISPER_MODEL, "device": config.WHISPER_DEVICE,
                 "compute": config.WHISPER_COMPUTE}
    t0 = time.perf_counter()
    from faster_whisper import WhisperModel
    out["import_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    try:
        m = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE,
                         compute_type=config.WHISPER_COMPUTE)
    except Exception:
        m = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        out["device"] = "cpu(fallback)"
    out["load_s"] = time.perf_counter() - t0
    if a.clip:
        for key in ("transcribe1_s", "transcribe2_s"):
            t0 = time.perf_counter()
            segs, _ = m.transcribe(a.clip, vad_filter=True)
            for _ in segs:      # generator — phải duyệt hết mới là chạy thật
                pass
            out[key] = time.perf_counter() - t0
    return out


def _case_vixtts(a) -> dict:
    import config
    if not (config.VIXTTS_DIR / "config.json").exists():
        return {"skipped": "chưa có model viXTTS"}
    out: dict = {"device": config.VIXTTS_DEVICE}
    t0 = time.perf_counter()
    from core import vixtts
    out["import_core_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    vixtts._load()             # gồm import TTS stack + nạp checkpoint lên GPU
    out["load_s"] = time.perf_counter() - t0
    try:
        import torch
        out["vram_mb"] = int(torch.cuda.memory_allocated() / 1e6)
    except Exception:
        pass
    if a.synth:
        ref_a = config.VOICES_DIR / (config.VIXTTS_VOICE_NAM or "x-khong-co.wav")
        ref_b = config.VIXTTS_DIR / "vi_sample.wav"
        if ref_a.is_file():
            import tempfile
            txt = "Đây là câu đo tốc độ tổng hợp giọng nói của hệ thống."
            for key, ref in (("synth1_s", ref_a), ("synth2_same_ref_s", ref_a),
                             ("synth_ref_b_s", ref_b)):
                if not ref.is_file():
                    continue
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.close()
                t0 = time.perf_counter()
                vixtts.synth(txt, str(ref), tmp.name)
                out[key] = time.perf_counter() - t0
                Path(tmp.name).unlink(missing_ok=True)
    return out


def _case_demucs(_a) -> dict:
    out: dict = {}
    t0 = time.perf_counter()
    from core.separate import _setup_dll_dirs
    _setup_dll_dirs()
    from demucs.pretrained import get_model
    out["import_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    get_model("htdemucs")      # nạp weights (không tách) — phần cache được nếu host
    out["load_s"] = time.perf_counter() - t0
    return out


def _case_ocr(_a) -> dict:
    out: dict = {}
    t0 = time.perf_counter()
    from rapidocr_onnxruntime import RapidOCR
    out["import_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    RapidOCR(intra_op_num_threads=2, use_angle_cls=False)
    out["init_s"] = time.perf_counter() - t0
    return out


CASES = {"baseline": _case_baseline, "import": _case_import, "whisper": _case_whisper,
         "vixtts": _case_vixtts, "demucs": _case_demucs, "ocr": _case_ocr}


# ------------------------------------------------------------------- parent
def _run_child(case: str, args, run_idx: int) -> dict:
    cmd = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
           "--child", case]
    if args.synth:
        cmd.append("--synth")
    if args.clip:
        cmd += ["--clip", args.clip]
    t0 = time.perf_counter()
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    wall = time.perf_counter() - t0
    rec: dict = {"case": case, "run": run_idx, "wall_s": round(wall, 2),
                 "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    for ln in (r.stdout or "").splitlines():
        if ln.startswith(MARK):
            rec.update(json.loads(ln[len(MARK):]))
            break
    else:
        rec["error"] = (r.stderr or "")[-400:]
    return rec


def _fmt(vals: list[float]) -> str:
    if not vals:
        return "-"
    med = statistics.median(vals)
    return f"{med:.1f}s [{min(vals):.1f}–{max(vals):.1f}]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--child", help="(nội bộ) chạy 1 case trong tiến trình con")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cases", default="baseline,import,whisper,vixtts,demucs,ocr")
    ap.add_argument("--synth", action="store_true")
    ap.add_argument("--clip", default="")
    ap.add_argument("--out", default=str(BASE / "data" / "bench_models.jsonl"))
    args = ap.parse_args()

    if args.child:   # chế độ tiến trình con: chạy đúng 1 case, in JSON rồi thoát
        sys.path.insert(0, str(BASE))
        result = CASES[args.child](args)
        print(MARK + json.dumps(result, ensure_ascii=False))
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for case in [c.strip() for c in args.cases.split(",") if c.strip() in CASES]:
        for i in range(args.runs):
            rec = _run_child(case, args, i)
            records.append(rec)
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            keys = [k for k in rec if k.endswith("_s") and k != "wall_s"]
            brief = " ".join(f"{k}={rec[k]:.1f}" for k in keys)
            print(f"  {case} #{i + 1}: wall={rec['wall_s']:.1f}s {brief}"
                  + (f"  LỖI: {rec['error'][:120]}" if "error" in rec else ""))

    print("\n===== TỔNG KẾT (median [min–max], mỗi lượt = 1 tiến trình mới) =====")
    by_case: dict[str, list[dict]] = {}
    for r in records:
        by_case.setdefault(r["case"], []).append(r)
    base_wall = statistics.median([r["wall_s"] for r in by_case.get("baseline", [])]) \
        if by_case.get("baseline") else 0.0
    for case, rs in by_case.items():
        parts = [f"wall {_fmt([r['wall_s'] for r in rs])}"]
        for key in sorted({k for r in rs for k in r if k.endswith("_s") and k != "wall_s"}):
            parts.append(f"{key[:-2]} {_fmt([r[key] for r in rs if key in r])}")
        print(f"{case:9}: " + " | ".join(parts))
    if base_wall:
        print(f"\n(wall đã gồm ~{base_wall:.1f}s khởi động Python trống — trừ đi để ra"
              f" chi phí riêng của case; kết quả lưu {out_path})")


if __name__ == "__main__":
    main()
