"""Dịch lại các câu sót chữ Hán trong transcript_vi của 1 job, dọn artifact để mix lại.

    python scripts/fix_leak_job.py <job_id>
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import anthropic  # noqa: E402

import config  # noqa: E402
from core.stages.s4_translate import fix_leaks  # noqa: E402

job_dir = BASE / "data" / "jobs" / sys.argv[1]
vi_path = job_dir / "transcript_vi.json"
data = json.loads(vi_path.read_text(encoding="utf-8"))
segments = data["segments"]

by_id = {s["id"]: s for s in segments}
translated = {s["id"]: s["text_vi"] for s in segments}
bad_before = [i for i, v in translated.items() if re.search(r"[一-鿿]", v)]
print(f"Câu sót chữ Hán: {bad_before}")

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
fix_leaks(client, by_id, translated)

changed = [i for i in bad_before if translated[i] != by_id[i]["text_vi"]]
for s in segments:
    s["text_vi"] = translated[s["id"]]
vi_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Đã dịch lại {len(changed)} câu: {changed}")

for i in changed:
    (job_dir / "tts" / f"seg_{i:04d}.mp3").unlink(missing_ok=True)
    (job_dir / "tts" / f"seg_{i:04d}_sped.wav").unlink(missing_ok=True)
for name in ["dubbed_audio.wav", "final.mp4", "sub_vi.srt", "mix_report.json", "metadata.json"]:
    (job_dir / name).unlink(missing_ok=True)

state_path = job_dir / "state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
state["completed_stages"] = ["downloading", "extracting", "transcribing", "translating", "bgm"]
state["stage"] = "translating"
state["error"] = None
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("Đã reset state — resume sẽ TTS các câu mới rồi mix + render lại")
