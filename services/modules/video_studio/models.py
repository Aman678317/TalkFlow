"""Data models for Video Localization Studio & Segment Editor (Module D)."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class StudioSegment(BaseModel):
    """An individual editable localized segment within a video timeline."""
    segment_id: str
    seq: int
    speaker_id: str = "speaker_0"
    start_ms: int
    end_ms: int
    duration_ms: int
    source_language: str
    target_language: str
    source_text: str
    translated_text: str
    original_translated_text: str
    voice_id: str
    audio_path: Optional[str] = None
    audio_base64: Optional[str] = None
    is_reviewed: bool = False
    is_manually_edited: bool = False
    time_stretch_ratio: float = 1.0
    quality_score: float = 0.95


class StudioProject(BaseModel):
    """Localization project state holding media, segments, subtitles, and export artifacts."""
    project_id: str
    tenant_id: str = "org_default"
    video_filename: str
    video_path: str
    source_language: str = "auto"
    target_languages: List[str] = Field(default_factory=lambda: ["en"])
    duration_sec: float = 0.0
    segments_by_lang: Dict[str, List[StudioSegment]] = Field(default_factory=dict)
    subtitles_srt: Dict[str, str] = Field(default_factory=dict)
    subtitles_vtt: Dict[str, str] = Field(default_factory=dict)
    dubbed_video_paths: Dict[str, str] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

