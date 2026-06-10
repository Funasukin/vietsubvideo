"""Chạy pipeline cho 1 video không qua bot (dev/test).

    python cli.py <url-hoặc-file>
    python cli.py --resume <job_id>
"""
import argparse
import sys

from core import pipeline
from core.job import Job

# Console Windows mặc định cp1258 không in được tiếng Việt
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="FlowApp pipeline CLI")
    parser.add_argument("url", nargs="?", help="Link video (YouTube/Bilibili/Douyin...) hoặc file local")
    parser.add_argument("--resume", metavar="JOB_ID", help="Chạy tiếp job dở dang trong data/jobs/")
    args = parser.parse_args()

    if args.resume:
        job = Job.load(args.resume)
        print(f"Resume job {job.id} từ stage {job.stage.value}")
    elif args.url:
        job = Job.create(url=args.url)
        print(f"Job mới {job.id} — {job.url}")
    else:
        parser.error("cần <url> hoặc --resume <job_id>")

    pipeline.run(job, on_stage=lambda j, s: print(f"  → {s.value} ..."))
    print(f"✓ Xong: {job.dir / 'final.mp4'}")


if __name__ == "__main__":
    main()
