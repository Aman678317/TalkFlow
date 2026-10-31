"""Persistent background job store and lifecycle manager for long audio/video translations."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("talkflow.orchestrator.jobs")

JOB_STORAGE_DIR = Path("I:/vioces agent/storage/orchestrator/jobs")
JOB_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class JobRecord(BaseModel):
    """Complete persistent state record for a full-duration translation job."""
    job_id: str
    session_id: str
    conversation_id: str
    speaker_id: str
    status: str = "QUEUED"  # QUEUED, VALIDATING, EXTRACTING, SEGMENTING, TRANSCRIBING, QUALITY_CHECK, TRANSLATING, SYNTHESIZING, ASSEMBLING, VERIFYING, COMPLETED, FAILED
    current_stage: str = "VALIDATING"
    source_filename: str
    source_file_path: str
    media_type: str = "audio"  # audio or video
    duration_sec: float = 0.0
    duration_ms: int = 0
    checksum_sha256: str = ""
    target_languages: List[str] = Field(default_factory=list)
    chunk_duration_sec: float = 15.0
    total_chunks: int = 0
    completed_chunks: int = 0
    progress_percent: float = 0.0
    source_language: str = "auto"
    full_source_transcript: str = ""
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    wall_clock_time_sec: float = 0.0
    rtf: float = 0.0
    error: Optional[str] = None
    chunks: List[Dict[str, Any]] = Field(default_factory=list)
    per_language_results: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    artifacts: Dict[str, Dict[str, str]] = Field(default_factory=dict)  # lang -> {type: file_path}

    def job_dir(self) -> Path:
        p = JOB_STORAGE_DIR / self.job_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_checkpoint(self) -> None:
        """Persist current job state atomically to disk."""
        self.updated_at = time.time()
        job_file = self.job_dir() / "manifest.json"
        temp_file = self.job_dir() / "manifest.json.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
            if temp_file.exists():
                temp_file.replace(job_file)
        except Exception as e:
            logger.error(f"Failed to persist checkpoint for job {self.job_id}: {e}")

    @classmethod
    def load(cls, job_id: str) -> Optional[JobRecord]:
        """Load job from disk by ID."""
        job_file = JOB_STORAGE_DIR / job_id / "manifest.json"
        if not job_file.exists():
            return None
        try:
            with open(job_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            logger.error(f"Failed to load job {job_id} from disk: {e}")
            return None


class JobManager:
    """Enterprise manager for active and historical translation jobs."""
    _memory_cache: Dict[str, JobRecord] = {}

    @classmethod
    def create_job(
        cls,
        job_id: str,
        source_filename: str,
        source_file_path: Path,
        target_languages: List[str],
        session_id: str = "session_default",
        conversation_id: str = "conv_default",
        speaker_id: str = "speaker_aman",
        chunk_duration_sec: float = 15.0
    ) -> JobRecord:
        job = JobRecord(
            job_id=job_id,
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            source_filename=source_filename,
            source_file_path=str(source_file_path),
            target_languages=target_languages,
            chunk_duration_sec=chunk_duration_sec
        )
        job.save_checkpoint()
        cls._memory_cache[job_id] = job
        return job

    @classmethod
    def get_job(cls, job_id: str) -> Optional[JobRecord]:
        if job_id in cls._memory_cache:
            return cls._memory_cache[job_id]
        job = JobRecord.load(job_id)
        if job:
            cls._memory_cache[job_id] = job
        return job

    @classmethod
    def list_jobs(cls, limit: int = 20) -> List[JobRecord]:
        jobs = []
        if not JOB_STORAGE_DIR.exists():
            return []
        for d in sorted(JOB_STORAGE_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir() and (d / "manifest.json").exists():
                j = cls.get_job(d.name)
                if j:
                    jobs.append(j)
            if len(jobs) >= limit:
                break
        return jobs

