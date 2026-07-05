"""Model Job: trạng thái pipeline, checkpoint qua state.json trong thư mục job."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path

import config


class Stage(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    TTS = "tts"
    BGM = "bgm"
    MIXING = "mixing"
    RENDERING = "rendering"
    METADATA = "metadata"
    UPLOADING = "uploading"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"


# Thứ tự chạy thực tế (không gồm trạng thái kết thúc done/failed)
PIPELINE_STAGES = [
    Stage.DOWNLOADING,
    Stage.EXTRACTING,
    Stage.TRANSCRIBING,
    Stage.TRANSLATING,
    Stage.TTS,
    Stage.BGM,
    Stage.MIXING,
    Stage.RENDERING,
    Stage.METADATA,
    Stage.UPLOADING,
]

_VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".flv"}


@dataclass
class Job:
    id: str
    url: str
    stage: Stage = Stage.PENDING
    completed_stages: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    # override cài đặt render theo job: subtitle_mode, cover, cover_top
    # (thiếu key nào thì S8 dùng giá trị trong config)
    render: dict = field(default_factory=dict)
    pause_before_render: bool = False
    glossary: str = ""  # bảng tên riêng "中文=Hán-Việt" cho Whisper + Claude
    series: str = ""    # tên series (nhiều tập cùng phim) → dùng chung glossary + casting
    # override âm lượng NỀN GỐC (dB, vd -20.0) chỉnh từ editor; None = theo DUCK_GAIN_DB
    bed_gain_db: float | None = None

    @property
    def dir(self) -> Path:
        return config.JOBS_DIR / self.id

    @property
    def state_path(self) -> Path:
        return self.dir / "state.json"

    def find_source(self) -> Path | None:
        """Video gốc do S1 tải về — đuôi file không cố định nên tìm theo tên."""
        for p in sorted(self.dir.glob("source.*")):
            if p.suffix.lower() in _VIDEO_EXTS:
                return p
        return None

    @classmethod
    def create(cls, url: str,
               pause_before_render: bool = False, glossary: str = "",
               series: str = "") -> Job:
        job_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        job = cls(id=job_id, url=url,
                  pause_before_render=pause_before_render, glossary=glossary,
                  series=series)
        job.dir.mkdir(parents=True, exist_ok=True)
        job.save()
        return job

    @classmethod
    def load(cls, job_id: str) -> Job:
        state_path = config.JOBS_DIR / job_id / "state.json"
        data = json.loads(state_path.read_text(encoding="utf-8"))
        # chỉ nhận field Job biết → state.json từ bản MỚI HƠN (có key lạ) không làm
        # cls(**data) nổ TypeError khi rollback; thiếu key thì default lo (glossary/series)
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in data.items() if k in known}
        data["stage"] = Stage(data["stage"])
        return cls(**data)

    def save(self) -> None:
        data = {
            "id": self.id,
            "url": self.url,
            "stage": self.stage.value,
            "completed_stages": self.completed_stages,
            "error": self.error,
            "created_at": self.created_at,
            "render": self.render,
            "pause_before_render": self.pause_before_render,
            "glossary": self.glossary,
            "series": self.series,
            "bed_gain_db": self.bed_gain_db,
        }
        # ghi nguyên tử: file tạm (tên duy nhất) rồi os.replace → không để state.json bị
        # torn/nửa vời khi bị kill giữa lúc ghi (đọc lại sẽ JSONDecodeError, mất job khỏi UI)
        tmp = self.state_path.with_name(f"state.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)
