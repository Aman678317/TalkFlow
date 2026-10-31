"""FastAPI HTTP service for TalkFlow Central Multi-Agent Orchestrator (Port 8000)."""
from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from orchestrator.benchmark import BenchmarkEngine
from orchestrator.jobs import JobManager, JobRecord
from orchestrator.models import RecordingManifest
from orchestrator.pipeline import TalkFlowOrchestrator
from rag.service import router as rag_router
from modules.service import router as expansion_router

app = FastAPI(
    title="TalkFlow Central Multi-Agent Orchestrator",
    description="Coordinates 7-agent sequential handoffs, multi-format media extraction, long-duration audio/video processing, complete reassembly, and enterprise expansion modules.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount TalkFlow Shared RAG, Autonomous Research & Long-Term Memory
app.include_router(rag_router)
# Mount TalkFlow Advanced Product Expansion (Modules A - K)
app.include_router(expansion_router)

orchestrator = TalkFlowOrchestrator()


@app.get("/", response_class=FileResponse)
@app.get("/pipeline", response_class=FileResponse)
async def serve_pipeline_dashboard():
    """Serve the complete TalkFlow 7-Agent Full-Duration Pipeline Studio."""
    dashboard_path = Path("I:/vioces agent/pipeline_dashboard.html")
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard file not found.")
    return FileResponse(dashboard_path, media_type="text/html")


class SegmentRequest(BaseModel):
    session_id: str
    conversation_id: str
    speaker_id: str = "speaker_aman"
    target_languages: List[str]
    audio_base64: str
    segment_id: Optional[str] = None


class EstimateRequest(BaseModel):
    audio_duration_sec: float
    target_languages: List[str]
    parallel_languages: bool = True


@app.get("/health")
@app.get("/api/v1/orchestrator/health")
async def health_check():
    """Verify health of Orchestrator and all 7 downstream agent services."""
    agent_status = await orchestrator.check_all_agents_health()
    all_healthy = all(agent_status.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "talkflow-central-orchestrator",
        "port": 8000,
        "agents": agent_status,
        "all_agents_operational": all_healthy
    }


@app.post("/api/v1/orchestrator/estimate")
async def estimate_processing_time(req: EstimateRequest):
    """Predict execution time, latency, and Real-Time Factor (RTF) before execution."""
    return BenchmarkEngine.estimate_job(
        audio_duration_sec=req.audio_duration_sec,
        target_languages=req.target_languages,
        parallel_languages=req.parallel_languages
    )


@app.post("/api/v1/orchestrator/pipeline/segment")
async def process_live_segment(req: SegmentRequest):
    """Process a single real-time speech segment through Agents 01 -> 07."""
    try:
        raw_wav = base64.b64decode(req.audio_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid audio base64 payload: {e}")

    try:
        res = await orchestrator.process_single_segment(
            audio_wav_bytes=raw_wav,
            target_languages=req.target_languages,
            session_id=req.session_id,
            conversation_id=req.conversation_id,
            speaker_id=req.speaker_id,
            segment_id=req.segment_id
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orchestration pipeline failed: {e}")


# -----------------------------------------------------------------------------
# Enterprise Full-Duration Background Jobs API (Audio & Video, 5s to 2h)
# -----------------------------------------------------------------------------

@app.post("/api/v1/orchestrator/jobs/create", status_code=202)
async def create_translation_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_languages: str = Form("en,mr,gu"),
    session_id: str = Form("session_studio"),
    conversation_id: str = Form("conv_studio"),
    speaker_id: str = Form("speaker_aman"),
    chunk_duration_sec: float = Form(15.0),
    job_id: Optional[str] = Form(None)
):
    """Accept any full-duration audio or video file, create persistent job, and process in background."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    target_lang_list = [t.strip().lower() for t in target_languages.split(",") if t.strip()]
    if not target_lang_list:
        raise HTTPException(status_code=400, detail="At least one target language must be specified.")

    jid = job_id or f"job_{int(time.time()*1000)}"
    dest_dir = Path("I:/vioces agent/storage/orchestrator/jobs") / jid
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    file_ext = Path(file.filename or "media.wav").suffix or ".wav"
    saved_source_file = dest_dir / f"source_original{file_ext}"
    saved_source_file.write_bytes(data)

    job = JobManager.create_job(
        job_id=jid,
        source_filename=file.filename or "media.wav",
        source_file_path=saved_source_file,
        target_languages=target_lang_list,
        session_id=session_id,
        conversation_id=conversation_id,
        speaker_id=speaker_id,
        chunk_duration_sec=chunk_duration_sec
    )

    # Launch background task for full-duration non-blocking execution
    background_tasks.add_task(orchestrator.execute_job, job)

    return {
        "job_id": jid,
        "status": job.status,
        "current_stage": job.current_stage,
        "file_name": job.source_filename,
        "target_languages": job.target_languages,
        "created_at": job.created_at,
        "poll_url": f"/api/v1/orchestrator/jobs/{jid}"
    }


@app.get("/api/v1/orchestrator/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Query live execution status, stage, chunk progress, and download links."""
    job = JobManager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job.model_dump()


@app.get("/api/v1/orchestrator/jobs")
async def list_jobs(limit: int = 15):
    """List recent translation jobs."""
    jobs = JobManager.list_jobs(limit=limit)
    return [j.model_dump() for j in jobs]


@app.get("/api/v1/orchestrator/jobs/{job_id}/download/{target_lang}/{artifact_type}")
async def download_job_artifact(job_id: str, target_lang: str, artifact_type: str):
    """Download specific deliverable (mp3, wav, srt, vtt, txt, json, mp4)."""
    job = JobManager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    tgt = target_lang.lower()
    art_map = job.artifacts.get(tgt)
    if not art_map:
        raise HTTPException(status_code=404, detail=f"No deliverables for language '{tgt}' in job '{job_id}'.")

    file_path_str = art_map.get(artifact_type.lower())
    if not file_path_str:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact type '{artifact_type}' not found for '{tgt}'. Available: {list(art_map.keys())}"
        )

    fp = Path(file_path_str)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing from storage.")

    media_types = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "mp4": "video/mp4",
        "srt": "text/plain",
        "vtt": "text/vtt",
        "txt": "text/plain",
        "json": "application/json"
    }

    return FileResponse(
        path=fp,
        media_type=media_types.get(artifact_type.lower(), "application/octet-stream"),
        filename=fp.name
    )


# -----------------------------------------------------------------------------
# Backward-Compatible Endpoints
# -----------------------------------------------------------------------------

@app.post("/api/v1/orchestrator/pipeline/long-audio")
async def process_full_length_recording(
    file: UploadFile = File(...),
    target_languages: str = Form(...),
    session_id: str = Form("session_full_rec"),
    conversation_id: str = Form("conv_full_rec"),
    speaker_id: str = Form("speaker_aman"),
    chunk_duration_sec: float = Form(15.0),
    recording_id: Optional[str] = Form(None)
):
    """Process complete audio recording synchronously through all 7 agents without truncation."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    target_lang_list = [t.strip().lower() for t in target_languages.split(",") if t.strip()]
    if not target_lang_list:
        raise HTTPException(status_code=400, detail="Must provide at least one target language.")

    try:
        manifest = await orchestrator.process_full_length_recording(
            audio_wav_bytes=audio_bytes,
            target_languages=target_lang_list,
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            chunk_duration_sec=chunk_duration_sec,
            recording_id=recording_id
        )
        return manifest
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Full-length audio processing failed: {e}")


@app.get("/api/v1/orchestrator/manifest/{recording_id}")
async def get_recording_manifest(recording_id: str):
    """Query progress and results of a full recording manifest."""
    manifest = orchestrator.manifest_store.get(recording_id)
    if not manifest:
        # Check job store
        job = JobManager.get_job(recording_id)
        if job:
            return job.model_dump()
        raise HTTPException(status_code=404, detail=f"Recording manifest '{recording_id}' not found.")
    return manifest


@app.get("/api/v1/orchestrator/download/{recording_id}/{target_lang}")
async def download_reassembled_track(recording_id: str, target_lang: str):
    """Download the complete reassembled translated WAV audio track."""
    manifest = orchestrator.manifest_store.get(recording_id)
    if manifest:
        result = manifest.per_language_results.get(target_lang.lower())
        if result and Path(result.output_audio_path).exists():
            return FileResponse(
                path=Path(result.output_audio_path),
                media_type="audio/wav",
                filename=f"{recording_id}_{target_lang}_full.wav"
            )

    job = JobManager.get_job(recording_id)
    if job and target_lang.lower() in job.artifacts:
        wav_path = job.artifacts[target_lang.lower()].get("wav")
        if wav_path and Path(wav_path).exists():
            return FileResponse(
                path=Path(wav_path),
                media_type="audio/wav",
                filename=f"{recording_id}_{target_lang}_full.wav"
            )

    raise HTTPException(status_code=404, detail=f"Target language '{target_lang}' not found for '{recording_id}'.")
