"""Orchestrator: chạy các stage theo thứ tự, checkpoint sau mỗi stage.

Stage đã nằm trong job.completed_stages sẽ bị bỏ qua khi chạy lại,
nên job chết giữa chừng chỉ cần gọi run() lại là tiếp tục đúng chỗ.
"""
from __future__ import annotations

from typing import Callable

from core import progress
from core.job import PIPELINE_STAGES, Job, Stage
from core.stages import (
    s1_download,
    s2_extract,
    s3_transcript,
    s4_translate,
    s5_tts,
    s6_bgm,
    s7_mix,
    s8_render,
    s9_metadata,
)

# Stage.UPLOADING không nằm ở đây: worker gọi uploaders riêng (Phase 3)
# vì upload cần xử lý kết quả từng nền tảng và không nên làm hỏng job khi fail.
STAGE_RUNNERS: dict[Stage, Callable[[Job], None]] = {
    Stage.DOWNLOADING: s1_download.run,
    Stage.EXTRACTING: s2_extract.run,
    Stage.TRANSCRIBING: s3_transcript.run,
    Stage.TRANSLATING: s4_translate.run,
    Stage.TTS: s5_tts.run,
    Stage.BGM: s6_bgm.run,
    Stage.MIXING: s7_mix.run,
    Stage.RENDERING: s8_render.run,
    Stage.METADATA: s9_metadata.run,
}

ProgressCallback = Callable[[Job, Stage], None]


def run(job: Job, on_stage: ProgressCallback | None = None) -> Job:
    for stage in PIPELINE_STAGES:
        if stage not in STAGE_RUNNERS:
            continue
        if stage.value in job.completed_stages:
            continue

        if stage == Stage.RENDERING and job.pause_before_render:
            job.stage = Stage.PAUSED
            job.save()
            return job

        job.stage = stage
        job.error = None
        job.save()
        if on_stage:
            on_stage(job, stage)

        try:
            STAGE_RUNNERS[stage](job)
        except Exception as e:
            job.error = f"{stage.value}: {e}"
            job.stage = Stage.FAILED
            job.save()
            progress.clear(job.dir)   # bỏ tiến độ dở của stage lỗi (khỏi treo thanh cũ)
            raise

        job.completed_stages.append(stage.value)
        job.save()

    job.stage = Stage.DONE
    job.save()
    progress.clear(job.dir)           # xong hẳn → dọn file tiến độ trong-stage
    return job
