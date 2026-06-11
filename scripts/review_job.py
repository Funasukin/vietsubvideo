"""Chạy vòng review dịch trên job đã xong, TTS lại các câu bị sửa rồi mix + render lại.

    python scripts/review_job.py <job_id>
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import anthropic  # noqa: E402

import config  # noqa: E402
from core.stages.s4_translate import review_pass  # noqa: E402

job_dir = BASE / "data" / "jobs" / sys.argv[1]
vi_path = job_dir / "transcript_vi.json"
data = json.loads(vi_path.read_text(encoding="utf-8"))
segments = data["segments"]

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
changed = review_pass(client, segments)

if not changed:
    print("Review: bản dịch đã nhất quán, không có gì cần sửa")
    sys.exit(0)

vi_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
by_id = {s["id"]: s for s in segments}
print(f"Review sửa {len(changed)} câu:")
for i in changed:
    print(f"  [{i}|{by_id[i].get('voice')}] {by_id[i]['text_vi']}")

# TTS lại các câu đã sửa + mix/render lại (giữ ducked.wav — timestamp không đổi)
for i in changed:
    (job_dir / "tts" / f"seg_{i:04d}.mp3").unlink(missing_ok=True)
    (job_dir / "tts" / f"seg_{i:04d}_sped.wav").unlink(missing_ok=True)
for name in ["dubbed_audio.wav", "final.mp4", "sub_vi.srt", "mix_report.json", "metadata.json"]:
    (job_dir / name).unlink(missing_ok=True)

state_path = job_dir / "state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
state["completed_stages"] = ["downloading", "extracting", "transcribing",
                             "translating", "bgm"]
state["stage"] = "translating"
state["error"] = None
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("Đã reset state — resume để TTS câu sửa + mix + render lại")
