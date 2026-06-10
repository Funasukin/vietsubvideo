"""Render lại final.mp4 của 1 job (vd đổi cài đặt phụ đề) — giữ nguyên mọi bước trước.

    python scripts/rerender.py <job_id>
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parents[1]

job_dir = BASE / "data" / "jobs" / sys.argv[1]
for name in ["final.mp4", "sub_vi.srt", "metadata.json"]:
    (job_dir / name).unlink(missing_ok=True)

state_path = job_dir / "state.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
state["completed_stages"] = [s for s in state["completed_stages"]
                             if s not in ("rendering", "metadata")]
state["error"] = None
state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
print("OK — resume để render lại")
