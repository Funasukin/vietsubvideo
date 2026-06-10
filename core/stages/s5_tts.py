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


async def _tts_one(sem: asyncio.Semaphore, job: Job, seg: dict) -> None:
    out = _seg_path(job, seg["id"])
    # file 0 byte là tàn dư của lần lỗi trước — không được tính là đã xong
    if out.exists() and out.stat().st_size > 0:
        return  # resume
    async with sem:
        for attempt in range(1, RETRIES + 1):
            out.unlink(missing_ok=True)
            try:
                communicate = edge_tts.Communicate(seg["text_vi"], config.TTS_VOICE)
                await asyncio.wait_for(
                    communicate.save(str(out)), timeout=config.TTS_TIMEOUT_S
                )
            except Exception:
                if attempt == RETRIES:
                    raise
                await asyncio.sleep(2 ** attempt)  # 2s, 4s, 8s
                continue
            if out.exists() and out.stat().st_size > 0:
                return
            if attempt == RETRIES:
                raise RuntimeError(
                    f"edge-tts trả file rỗng cho segment {seg['id']} sau {RETRIES} lần thử"
                )
            await asyncio.sleep(2 ** attempt)


async def _tts_all(job: Job, segments: list[dict]) -> None:
    sem = asyncio.Semaphore(config.TTS_CONCURRENCY)
    await asyncio.gather(*(_tts_one(sem, job, s) for s in segments))


def run(job: Job) -> None:
    data = json.loads((job.dir / "transcript_vi.json").read_text(encoding="utf-8"))
    segments = [s for s in data["segments"] if s["text_vi"].strip()]
    if not segments:
        raise RuntimeError("transcript_vi.json không có segment nào để đọc")

    (job.dir / "tts").mkdir(exist_ok=True)
    asyncio.run(_tts_all(job, segments))

    missing = [
        s["id"] for s in segments
        if not _seg_path(job, s["id"]).exists() or _seg_path(job, s["id"]).stat().st_size == 0
    ]
    if missing:
        raise RuntimeError(f"edge-tts không tạo được file cho segment: {missing}")
