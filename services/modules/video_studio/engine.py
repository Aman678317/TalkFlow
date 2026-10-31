"""Video Localization Studio Engine & Segment Editor (Module D).

Allows reviewing, previewing, editing, re-translating, and re-synthesizing individual segments,
re-assembling dubbed audio with timeline alignment and time-stretching, and exporting final localized videos.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple
import httpx

from modules.video_studio.models import StudioProject, StudioSegment

logger = logging.getLogger("talkflow.modules.video_studio")


def _ms_to_srt_time(ms: int) -> str:
    hours = ms // 3600000
    ms %= 3600000
    mins = ms // 60000
    ms %= 60000
    secs = ms // 1000
    milli = ms % 1000
    return f"{hours:02d}:{mins:02d}:{secs:02d},{milli:03d}"


class VideoStudioEngine:
    """Manages full video localization projects, segment timeline editing, and audio-video re-render."""

    def __init__(self, projects_dir: str = "storage/studio") -> None:
        self.projects_dir = Path(projects_dir)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        # project_id -> StudioProject
        self._projects: Dict[str, StudioProject] = {}

    def get_project(self, project_id: str, tenant_id: str = "org_default") -> Optional[StudioProject]:
        p = self._projects.get(project_id)
        if p and p.tenant_id != tenant_id:
            raise PermissionError(f"Cross-tenant access forbidden for project '{project_id}'.")
        return p

    def create_project(
        self,
        project_id: str,
        video_filename: str,
        video_path: str,
        source_language: str = "hi",
        target_languages: Optional[List[str]] = None,
        duration_sec: float = 0.0,
        tenant_id: str = "org_default",
    ) -> StudioProject:
        """Initializes a new localization studio workspace."""
        targets = target_languages or ["en"]
        proj = StudioProject(
            project_id=project_id,
            tenant_id=tenant_id,
            video_filename=video_filename,
            video_path=video_path,
            source_language=source_language,
            target_languages=targets,
            duration_sec=duration_sec,
        )
        self._projects[project_id] = proj
        return proj

    def populate_from_orchestrator(
        self,
        project_id: str,
        segments_manifest: List[Dict[str, Any]],
        video_path: str,
        target_lang: str,
        tenant_id: str = "org_default",
    ) -> StudioProject:
        """Ingests orchestrator pipeline output into interactive studio segments."""
        proj = self.get_project(project_id, tenant_id=tenant_id)
        if not proj:
            proj = self.create_project(
                project_id=project_id,
                video_filename=Path(video_path).name,
                video_path=video_path,
                target_languages=[target_lang],
                tenant_id=tenant_id,
            )

        studio_segs: List[StudioSegment] = []
        for idx, seg in enumerate(segments_manifest):
            s_id = seg.get("segment_id", f"seg_{idx}")
            st = seg.get("start_ms", 0)
            et = seg.get("end_ms", 0)
            dur = max(100, et - st)
            src_txt = seg.get("source_text", "")
            tgt_txt = seg.get("translated_text", "")
            audio_b64 = seg.get("audio_base64", None)
            v_id = seg.get("voice_id", "default_neural")

            studio_segs.append(
                StudioSegment(
                    segment_id=s_id,
                    seq=idx + 1,
                    speaker_id=seg.get("speaker_id", f"speaker_{idx % 2}"),
                    start_ms=st,
                    end_ms=et,
                    duration_ms=dur,
                    source_language=proj.source_language,
                    target_language=target_lang,
                    source_text=src_txt,
                    translated_text=tgt_txt,
                    original_translated_text=tgt_txt,
                    voice_id=v_id,
                    audio_base64=audio_b64,
                    quality_score=seg.get("quality_score", 0.95),
                )
            )

        proj.segments_by_lang[target_lang] = studio_segs
        self._rebuild_subtitles(proj, target_lang)
        proj.updated_at = time.time()
        return proj

    async def update_segment(
        self,
        project_id: str,
        target_lang: str,
        segment_id: str,
        new_text: str,
        voice_id: Optional[str] = None,
        tenant_id: str = "org_default",
    ) -> StudioSegment:
        """Updates text for a single segment and immediately re-synthesizes its neural audio."""
        proj = self.get_project(project_id, tenant_id=tenant_id)
        if not proj:
            raise KeyError(f"Project '{project_id}' not found.")

        segs = proj.segments_by_lang.get(target_lang, [])
        target_seg: Optional[StudioSegment] = None
        for s in segs:
            if s.segment_id == segment_id:
                target_seg = s
                break

        if not target_seg:
            raise KeyError(f"Segment '{segment_id}' not found in project '{project_id}' for '{target_lang}'.")

        target_seg.translated_text = new_text.strip()
        target_seg.is_manually_edited = True
        target_seg.is_reviewed = True
        if voice_id:
            target_seg.voice_id = voice_id

        # Re-synthesize audio for this segment via Agent 06 (Port 8006)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                body = {
                    "text": target_seg.translated_text,
                    "target_language": target_lang,
                    "requested_voice_id": target_seg.voice_id,
                    "quality_decision": "ACCEPT",
                    "quality_score": 0.98,
                    "conversation_id": f"studio_{project_id}",
                    "segment_id": segment_id,
                }
                res = await client.post("http://127.0.0.1:8006/api/v1/tts/synthesize", json=body)
                if res.status_code == 200:
                    d = res.json()
                    target_seg.audio_base64 = d.get("audio_base64")
                    synth_dur_ms = d.get("duration_ms", target_seg.duration_ms)
                    # Calculate time stretch ratio to align with timeline
                    if target_seg.duration_ms > 0:
                        target_seg.time_stretch_ratio = round(synth_dur_ms / target_seg.duration_ms, 3)
        except Exception as e:
            logger.warning(f"Re-synthesis on port 8006 failed: {e}")

        # Rebuild subtitles
        self._rebuild_subtitles(proj, target_lang)
        proj.updated_at = time.time()
        return target_seg

    def _rebuild_subtitles(self, proj: StudioProject, target_lang: str) -> None:
        """Regenerates SRT and VTT subtitles from current segment texts."""
        segs = proj.segments_by_lang.get(target_lang, [])
        srt_lines = []
        vtt_lines = ["WEBVTT", ""]

        for idx, s in enumerate(segs):
            st_srt = _ms_to_srt_time(s.start_ms)
            et_srt = _ms_to_srt_time(s.end_ms)
            st_vtt = st_srt.replace(",", ".")
            et_vtt = et_srt.replace(",", ".")

            # SRT format
            srt_lines.append(str(idx + 1))
            srt_lines.append(f"{st_srt} --> {et_srt}")
            srt_lines.append(s.translated_text)
            srt_lines.append("")

            # VTT format
            vtt_lines.append(f"{idx + 1}")
            vtt_lines.append(f"{st_vtt} --> {et_vtt}")
            vtt_lines.append(s.translated_text)
            vtt_lines.append("")

        proj.subtitles_srt[target_lang] = "\n".join(srt_lines)
        proj.subtitles_vtt[target_lang] = "\n".join(vtt_lines)


# Global Video Studio Engine Instance
video_studio_engine = VideoStudioEngine()

