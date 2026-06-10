"""Áp segtools lên transcript có sẵn của 1 job và reset các stage sau S3.

    python scripts/refix_job.py <job_id>

Dùng khi đổi bộ lọc/gộp segment mà không muốn OCR lại từ đầu.
"""
import json
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from core import segtools  # noqa: E402

job_dir = BASE / "data" / "jobs" / sys.argv[1]
tz_path = job_dir / "transcript_zh.json"

data = json.loads(tz_path.read_text(encoding="utf-8"))
before = len(data["segments"])
data["segments"] = segtools.clean_and_merge(data["segments"])
after = len(data["segments"])
tz_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Segment: {before} → {after} (lọc rác + gộp)")

for name in ["transcript_vi.json", "ducked.wav", "dubbed_audio.wav",
             "final.mp4", "sub_vi.srt", "mix_report.json", "metadata.json"]:
    (job_dir / name).unlink(missing_ok=True)
shutil.rmtree(job_dir / "tts", ignore_errors=True)

state_path = job_dir / "state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
state["completed_stages"] = ["downloading", "extracting", "transcribing"]
state["stage"] = "transcribing"
state["error"] = None
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("Đã reset state — resume sẽ chạy lại từ bước dịch")
