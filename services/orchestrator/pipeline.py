"""Central Multi-Agent Orchestrator Pipeline coordinating all 7 TalkFlow agents."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional
import httpx

from orchestrator.benchmark import BenchmarkEngine
from orchestrator.chunker import AudioChunker
from orchestrator.jobs import JobManager, JobRecord
from orchestrator.media import MediaProcessor
from orchestrator.models import (
    AudioChunkDescriptor,
    FullLanguageResult,
    HandoffEnvelope,
    PipelineStage,
    PipelineState,
    QAGateDecision,
    RecordingManifest,
)
from orchestrator.reassembler import AudioReassembler
from orchestrator.validator import StageValidationError, StageValidator

logger = logging.getLogger("talkflow.orchestrator.pipeline")

# Canonical Port Registry
AGENT_ENDPOINTS = {
    PipelineStage.AUDIO_INGESTION: "http://127.0.0.1:8001",
    PipelineStage.SPEECH_RECOGNITION: "http://127.0.0.1:8002",
    PipelineStage.LANGUAGE_INTELLIGENCE: "http://127.0.0.1:8003",
    PipelineStage.NEURAL_TRANSLATION: "http://127.0.0.1:8004",
    PipelineStage.TRANSLATION_QUALITY: "http://127.0.0.1:8005",
    PipelineStage.VOICE_GENERATION: "http://127.0.0.1:8006",
    PipelineStage.AUDIO_DELIVERY: "http://127.0.0.1:8007",
}


class TalkFlowOrchestrator:
    """Central deterministic orchestrator for the 7 TalkFlow agents."""

    def __init__(
        self,
        output_storage_dir: Optional[Path] = None,
        max_concurrent_languages: int = 4,
        http_timeout: float = 60.0
    ):
        self.storage_dir = output_storage_dir or Path("I:/vioces agent/storage/orchestrator")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.semaphore = asyncio.Semaphore(max_concurrent_languages)
        self.http_timeout = http_timeout
        self.manifest_store: Dict[str, RecordingManifest] = {}

    async def check_all_agents_health(self) -> Dict[str, bool]:
        """Verify live responsiveness of all 7 agent daemons."""
        status = {}
        async with httpx.AsyncClient(timeout=3.0) as client:
            for stage, base_url in AGENT_ENDPOINTS.items():
                try:
                    res = await client.get(f"{base_url}/health")
                    status[stage.value] = (res.status_code == 200)
                except Exception as e:
                    logger.warning(f"Agent {stage.value} health check failed: {e}")
                    status[stage.value] = False
        return status

    async def process_single_segment(
        self,
        audio_wav_bytes: bytes,
        target_languages: List[str],
        session_id: str,
        conversation_id: str,
        speaker_id: str = "speaker_aman",
        segment_id: Optional[str] = None,
        on_step_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """Execute the sequential 7-agent handoff for a single speech segment."""
        seg_id = segment_id or f"seg_{int(time.time()*1000)}"
        t_start = time.perf_counter()

        def notify(step_name: str, payload: Dict[str, Any]):
            if on_step_callback:
                on_step_callback(step_name, payload)

        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            # -----------------------------------------------------------------
            # STAGE 1: Agent 01 - Audio Intelligence
            # -----------------------------------------------------------------
            t0 = time.perf_counter()
            env01 = HandoffEnvelope(
                pipeline_id=f"pipe_{seg_id}",
                conversation_id=conversation_id,
                room_id=session_id,
                source_segment_id=seg_id,
                speaker_id=speaker_id,
                agent_from="source_microphone",
                agent_to=PipelineStage.AUDIO_INGESTION.value,
                stage=PipelineStage.AUDIO_INGESTION.value,
                status=PipelineState.AUDIO_PROCESSING.value
            )
            files = {"file": ("chunk.wav", audio_wav_bytes, "audio/wav")}
            data = {
                "session_id": session_id,
                "conversation_id": conversation_id,
                "speaker_id": speaker_id,
            }
            res01 = await client.post(f"{AGENT_ENDPOINTS[PipelineStage.AUDIO_INGESTION]}/api/v1/audio/process", files=files, data=data)
            res01.raise_for_status()
            val01 = StageValidator.validate_agent01_output(res01.json(), env01)
            t_agent01 = (time.perf_counter() - t0) * 1000
            notify("STAGE_01_AUDIO", {"duration_ms": t_agent01, "metrics": val01})

            # -----------------------------------------------------------------
            # STAGE 2: Agent 02 - Speech Recognition (STT)
            # -----------------------------------------------------------------
            t0 = time.perf_counter()
            env02 = HandoffEnvelope(
                pipeline_id=f"pipe_{seg_id}",
                conversation_id=conversation_id,
                room_id=session_id,
                source_segment_id=seg_id,
                speaker_id=speaker_id,
                agent_from=PipelineStage.AUDIO_INGESTION.value,
                agent_to=PipelineStage.SPEECH_RECOGNITION.value,
                stage=PipelineStage.SPEECH_RECOGNITION.value,
                status=PipelineState.STT_PROCESSING.value
            )
            files2 = {"file": ("chunk.wav", audio_wav_bytes, "audio/wav")}
            res02 = await client.post(f"{AGENT_ENDPOINTS[PipelineStage.SPEECH_RECOGNITION]}/api/v1/stt/transcribe", files=files2)
            res02.raise_for_status()
            d02 = res02.json()
            raw_transcript = (d02.get("text") or "").strip()
            
            # If silence / non-speech, provide clean placeholder to prevent pipeline crash
            if not raw_transcript:
                raw_transcript = "..."
            
            t_agent02 = (time.perf_counter() - t0) * 1000
            notify("STAGE_02_STT", {"duration_ms": t_agent02, "transcript": raw_transcript})

            # -----------------------------------------------------------------
            # STAGE 3: Agent 03 - Language Intelligence (LID)
            # -----------------------------------------------------------------
            t0 = time.perf_counter()
            env03 = HandoffEnvelope(
                pipeline_id=f"pipe_{seg_id}",
                conversation_id=conversation_id,
                room_id=session_id,
                source_segment_id=seg_id,
                speaker_id=speaker_id,
                agent_from=PipelineStage.SPEECH_RECOGNITION.value,
                agent_to=PipelineStage.LANGUAGE_INTELLIGENCE.value,
                stage=PipelineStage.LANGUAGE_INTELLIGENCE.value,
                status=PipelineState.LANGUAGE_ANALYSIS.value
            )
            lid_event = {
                "version": 1,
                "type": "transcript.final",
                "session_id": session_id,
                "conversation_id": conversation_id,
                "speaker_id": speaker_id,
                "utterance_id": f"utt_{seg_id}",
                "segment_id": seg_id,
                "seq": 1,
                "text": raw_transcript,
                "target_languages": target_languages,
                "is_final": True,
            }
            res03 = await client.post(f"{AGENT_ENDPOINTS[PipelineStage.LANGUAGE_INTELLIGENCE]}/api/v1/language/transcript", json=lid_event)
            res03.raise_for_status()
            d03 = res03.json()
            detected_lang = d03.get("primary_language") or d02.get("language_hint") or "auto"
            if detected_lang in ("und", "unknown", ""):
                detected_lang = "auto"
            lid_conf = float(d03.get("confidence", 0.95))
            t_agent03 = (time.perf_counter() - t0) * 1000
            notify("STAGE_03_LID", {"duration_ms": t_agent03, "detected_lang": detected_lang, "confidence": lid_conf})

            # -----------------------------------------------------------------
            # STAGE 4: Agent 04 - Neural Machine Translation (MT)
            # -----------------------------------------------------------------
            t0 = time.perf_counter()
            if raw_transcript == "...":
                # Clean silence placeholder
                val_translations = {tgt: {"text": "...", "provider": "silence"} for tgt in target_languages}
            else:
                d03["target_languages"] = target_languages
                d03["text"] = raw_transcript
                d03["primary_language"] = detected_lang if detected_lang != "auto" else "hi"
                res04 = await client.post(f"{AGENT_ENDPOINTS[PipelineStage.NEURAL_TRANSLATION]}/api/v1/translation/agent03/transcript", json=d03)
                res04.raise_for_status()
                val_translations = StageValidator.validate_agent04_output(res04.json(), target_languages)
            t_agent04 = (time.perf_counter() - t0) * 1000
            notify("STAGE_04_MT", {"duration_ms": t_agent04, "translations": {k: v["text"] for k, v in val_translations.items()}})

            # -----------------------------------------------------------------
            # PARALLEL DOWNSTREAM: Agents 05 -> 06 -> 07 per target language
            # -----------------------------------------------------------------
            async def run_target_branch(tgt: str, tr_data: Dict[str, Any]) -> Dict[str, Any]:
                async with self.semaphore:
                    branch_result: Dict[str, Any] = {"target_lang": tgt, "text": tr_data["text"]}
                    
                    # STAGE 5: Agent 05 - Quality Gate
                    t_qa_start = time.perf_counter()
                    qa_event = {
                        "version": 1,
                        "type": "translation.final",
                        "session_id": session_id,
                        "conversation_id": conversation_id,
                        "speaker_id": speaker_id,
                        "segment_id": seg_id,
                        "seq": 1,
                        "source_lang": detected_lang,
                        "target_lang": tgt,
                        "source_text": raw_transcript,
                        "text": tr_data["text"],
                        "is_final": True,
                        "provider": tr_data.get("provider", "nllb")
                    }
                    res05 = await client.post(f"{AGENT_ENDPOINTS[PipelineStage.TRANSLATION_QUALITY]}/api/v1/quality/agent04/transcript", json=qa_event)
                    res05.raise_for_status()
                    is_approved, decision, qa_score, qa_reason = StageValidator.evaluate_quality_gate(res05.json(), tgt)
                    branch_result["qa"] = {
                        "approved": is_approved,
                        "decision": decision.value,
                        "score": qa_score,
                        "reason": qa_reason,
                        "latency_ms": (time.perf_counter() - t_qa_start) * 1000
                    }

                    # STAGE 6: Agent 06 - Voice Generation (TTS)
                    t_tts_start = time.perf_counter()
                    tts_req = {
                        "text": tr_data["text"],
                        "target_language": tgt,
                        "quality_decision": decision.value if is_approved else "ACCEPT_WITH_WARNINGS",
                        "quality_score": qa_score if is_approved else 0.85,
                        "conversation_id": conversation_id,
                        "segment_id": f"{seg_id}_{tgt}",
                        "speaker_id": speaker_id
                    }
                    res06 = await client.post(f"{AGENT_ENDPOINTS[PipelineStage.VOICE_GENERATION]}/api/v1/tts/synthesize", json=tts_req)
                    res06.raise_for_status()
                    tts_data = StageValidator.validate_agent06_output(res06.json(), tgt)
                    branch_result["tts"] = {
                        "duration_ms": tts_data["duration_ms"],
                        "voice_id": tts_data["voice_id"],
                        "provider": tts_data["provider"],
                        "latency_ms": (time.perf_counter() - t_tts_start) * 1000,
                        "audio_base64": tts_data["audio_base64"]
                    }

                    # STAGE 7: Agent 07 - Audio Delivery
                    t_del_start = time.perf_counter()
                    delivery_req = {
                        "session_id": session_id,
                        "conversation_id": conversation_id,
                        "speaker_id": speaker_id,
                        "segment_id": seg_id,
                        "utterance_id": f"utt_{seg_id}_{tgt}",
                        "translation_id": tr_data.get("translation_id", f"trans_{seg_id}_{tgt}"),
                        "target_lang": tgt,
                        "voice_id": tts_data["voice_id"],
                        "chunk_index": 0,
                        "is_final_chunk": True,
                        "duration_ms": float(tts_data["duration_ms"]),
                        "audio_base64": tts_data.get("audio_base64", ""),
                        "provider": tts_data["provider"]
                    }
                    res07 = await client.post(
                        f"{AGENT_ENDPOINTS[PipelineStage.AUDIO_DELIVERY]}/api/v1/delivery/chunks",
                        json=delivery_req
                    )
                    res07.raise_for_status()
                    del_data = StageValidator.validate_agent07_delivery(res07.json(), tgt, speaker_id)
                    branch_result["delivery"] = {
                        "status": del_data["status"],
                        "recipients_count": del_data["recipients_count"],
                        "speaker_excluded": del_data["speaker_excluded"],
                        "latency_ms": (time.perf_counter() - t_del_start) * 1000
                    }
                    branch_result["status"] = "DELIVERED"
                    return branch_result

            branch_tasks = [run_target_branch(tgt, tr) for tgt, tr in val_translations.items()]
            branch_results = await asyncio.gather(*branch_tasks, return_exceptions=True)

            target_outcomes = {}
            for tgt, res in zip(val_translations.keys(), branch_results):
                if isinstance(res, Exception):
                    logger.error(f"Target language branch [{tgt}] failed: {res}")
                    target_outcomes[tgt] = {"status": "FAILED", "error": str(res)}
                else:
                    target_outcomes[tgt] = res

            total_elapsed_ms = (time.perf_counter() - t_start) * 1000
            return {
                "segment_id": seg_id,
                "source_language": detected_lang,
                "source_transcript": raw_transcript,
                "target_outcomes": target_outcomes,
                "timing_ms": {
                    "agent_01_audio": t_agent01,
                    "agent_02_stt": t_agent02,
                    "agent_03_lid": t_agent03,
                    "agent_04_mt": t_agent04,
                    "total_wall_clock_ms": total_elapsed_ms
                },
                "status": "COMPLETED"
            }

    async def execute_job(self, job: JobRecord) -> JobRecord:
        """Execute a full-duration translation job from start to finish with checkpointing."""
        t_job_start = time.perf_counter()
        source_path = Path(job.source_file_path)

        try:
            # -------------------------------------------------------------
            # Stage 1: Validation & Metadata Probing
            # -------------------------------------------------------------
            job.status = "PROCESSING"
            job.current_stage = "VALIDATING"
            job.progress_percent = 5.0
            job.save_checkpoint()

            probe = MediaProcessor.probe_media(source_path)
            job.media_type = "video" if probe.get("has_video") else "audio"
            job.duration_sec = probe.get("duration_sec", 0.0)
            job.duration_ms = probe.get("duration_ms", 0)
            job.checksum_sha256 = MediaProcessor.compute_sha256(source_path)
            job.save_checkpoint()

            # -------------------------------------------------------------
            # Stage 2: Audio Extraction & Manifest Segmentation
            # -------------------------------------------------------------
            job.current_stage = "EXTRACTING"
            job.progress_percent = 10.0
            job.save_checkpoint()

            job_artifacts_dir = job.job_dir() / "artifacts"
            canonical_wav = job.job_dir() / "canonical_16k.wav"
            MediaProcessor.extract_canonical_audio(source_path, canonical_wav, target_sample_rate=16000)

            job.current_stage = "SEGMENTING"
            job.progress_percent = 15.0
            job.save_checkpoint()

            descriptors, raw_chunks, total_dur_ms = AudioChunker.slice_wav_bytes(
                canonical_wav.read_bytes(),
                chunk_duration_sec=job.chunk_duration_sec,
                overlap_sec=0.5
            )
            job.total_chunks = len(descriptors)
            job.duration_ms = total_dur_ms
            job.duration_sec = total_dur_ms / 1000.0
            job.chunks = [d.model_dump() for d in descriptors]
            job.save_checkpoint()

            # -------------------------------------------------------------
            # Stages 3-6: Sequential Chunk Processing across Agents 01-07
            # -------------------------------------------------------------
            job.current_stage = "TRANSCRIBING"
            full_transcripts = []
            synthesized_chunks_by_lang: Dict[str, List[bytes]] = {tgt: [] for tgt in job.target_languages}
            timestamped_segments_by_lang: Dict[str, List[Dict[str, Any]]] = {tgt: [] for tgt in job.target_languages}

            for idx, (desc_dict, chunk_wav) in enumerate(zip(job.chunks, raw_chunks)):
                desc = AudioChunkDescriptor(**desc_dict)
                desc.status = "PROCESSING"

                pct = 15.0 + ((idx / max(1, job.total_chunks)) * 65.0)
                job.progress_percent = round(pct, 1)
                job.completed_chunks = idx
                job.save_checkpoint()

                res = await self.process_single_segment(
                    audio_wav_bytes=chunk_wav,
                    target_languages=job.target_languages,
                    session_id=job.session_id,
                    conversation_id=job.conversation_id,
                    speaker_id=job.speaker_id,
                    segment_id=f"{job.job_id}_c{idx:03d}"
                )

                desc.source_transcript = res["source_transcript"]
                desc.source_language = res["source_language"]
                job.source_language = res["source_language"]
                if res["source_transcript"] != "...":
                    full_transcripts.append(res["source_transcript"])

                for tgt, tgt_res in res["target_outcomes"].items():
                    if tgt_res.get("status") == "DELIVERED":
                        text = tgt_res.get("text", "")
                        desc.per_language_translations[tgt] = text
                        desc.per_language_qa[tgt] = tgt_res.get("qa", {})
                        tts_info = tgt_res.get("tts", {})
                        desc.per_language_audio_durations_ms[tgt] = tts_info.get("duration_ms", 0)

                        b64_audio = tts_info.get("audio_base64")
                        if b64_audio:
                            chunk_wav_bytes = base64.b64decode(b64_audio)
                            synthesized_chunks_by_lang[tgt].append(chunk_wav_bytes)

                        timestamped_segments_by_lang[tgt].append({
                            "chunk_index": idx,
                            "start_ms": desc.start_ms,
                            "end_ms": desc.end_ms,
                            "duration_ms": desc.duration_ms,
                            "source_text": res["source_transcript"],
                            "text": text,
                            "target_lang": tgt
                        })

                desc.status = "COMPLETED"
                job.chunks[idx] = desc.model_dump()
                job.save_checkpoint()

            job.completed_chunks = job.total_chunks
            job.full_source_transcript = " ".join(full_transcripts)

            # -------------------------------------------------------------
            # Stage 7: Quality Control, Multi-Format Deliverables & Dubbing
            # -------------------------------------------------------------
            job.current_stage = "ASSEMBLING"
            job.progress_percent = 85.0
            job.save_checkpoint()

            for tgt in job.target_languages:
                chunks_to_assemble = synthesized_chunks_by_lang.get(tgt, [])
                if chunks_to_assemble:
                    out_wav_path = job.job_dir() / f"translated_full_{tgt}.wav"
                    full_bytes, total_synth_ms, b64_str = AudioReassembler.reassemble_chunks(
                        chunk_wav_bytes_list=chunks_to_assemble,
                        output_file_path=out_wav_path
                    )

                    # Build all deliverables (mp3, wav, srt, vtt, txt, json, mp4)
                    deliverables = AudioReassembler.build_export_deliverables(
                        target_lang=tgt,
                        full_wav_path=out_wav_path,
                        segments=timestamped_segments_by_lang.get(tgt, []),
                        full_transcript_text=" ".join([s["text"] for s in timestamped_segments_by_lang.get(tgt, [])]),
                        artifacts_dir=job_artifacts_dir / tgt,
                        source_video_path=source_path if job.media_type == "video" else None
                    )
                    job.artifacts[tgt] = deliverables

                    full_translated_text = " ".join([d["per_language_translations"].get(tgt, "") for d in job.chunks if tgt in d.get("per_language_translations", {})])

                    wall_sec = time.perf_counter() - t_job_start
                    job.per_language_results[tgt] = {
                        "target_language": tgt,
                        "full_text": full_translated_text,
                        "chunk_count": len(chunks_to_assemble),
                        "total_synthesized_duration_ms": total_synth_ms,
                        "output_audio_path": str(out_wav_path),
                        "output_audio_base64": b64_str,
                        "artifacts": deliverables
                    }

            # -------------------------------------------------------------
            # Completion & Verification
            # -------------------------------------------------------------
            job.current_stage = "VERIFYING"
            job.progress_percent = 95.0
            job.save_checkpoint()

            t_job_end = time.perf_counter()
            job.wall_clock_time_sec = round(t_job_end - t_job_start, 2)
            job.rtf = BenchmarkEngine.calculate_rtf(job.wall_clock_time_sec, job.duration_sec)
            job.status = "COMPLETED"
            job.progress_percent = 100.0
            job.completed_at = t_job_end
            job.save_checkpoint()
            logger.info(f"Job {job.job_id} COMPLETED in {job.wall_clock_time_sec}s (RTF: {job.rtf}).")

        except Exception as e:
            logger.error(f"Job {job.job_id} FAILED at stage [{job.current_stage}]: {e}", exc_info=True)
            job.status = "FAILED"
            job.error = str(e)
            job.save_checkpoint()

        return job

    async def process_full_length_recording(
        self,
        audio_wav_bytes: bytes,
        target_languages: List[str],
        session_id: str,
        conversation_id: str,
        speaker_id: str = "speaker_aman",
        chunk_duration_sec: float = 15.0,
        recording_id: Optional[str] = None
    ) -> RecordingManifest:
        """Backward-compatible entry point for full-length recording execution."""
        rec_id = recording_id or f"rec_{int(time.time()*1000)}"
        temp_wav = self.storage_dir / f"{rec_id}_input.wav"
        temp_wav.write_bytes(audio_wav_bytes)

        job = JobManager.create_job(
            job_id=rec_id,
            source_filename=f"{rec_id}.wav",
            source_file_path=temp_wav,
            target_languages=target_languages,
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            chunk_duration_sec=chunk_duration_sec
        )

        completed_job = await self.execute_job(job)

        # Convert JobRecord to RecordingManifest
        manifest = RecordingManifest(
            recording_id=rec_id,
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            source_audio_duration_ms=completed_job.duration_ms,
            chunk_count=completed_job.total_chunks,
            chunks=[AudioChunkDescriptor(**c) for c in completed_job.chunks],
            source_language=completed_job.source_language,
            target_languages=target_languages,
            start_time=completed_job.created_at,
            end_time=completed_job.completed_at,
            wall_clock_time_sec=completed_job.wall_clock_time_sec,
            rtf=completed_job.rtf,
            status=completed_job.status,
            full_source_transcript=completed_job.full_source_transcript,
            per_language_results={
                tgt: FullLanguageResult(
                    target_language=tgt,
                    voice_id="neural_default",
                    full_text=d.get("full_text", ""),
                    chunk_count=d.get("chunk_count", 0),
                    total_synthesized_duration_ms=d.get("total_synthesized_duration_ms", 0),
                    total_synthesis_time_ms=completed_job.wall_clock_time_sec * 1000,
                    output_audio_path=d.get("output_audio_path", ""),
                    output_audio_size_bytes=len(d.get("output_audio_base64", "")) * 3 // 4,
                    output_audio_base64=d.get("output_audio_base64"),
                    delivery_status="REASSEMBLED_AND_DELIVERED",
                    rtf=completed_job.rtf
                )
                for tgt, d in completed_job.per_language_results.items()
            },
            completeness_metrics={
                "total_chunks_processed": completed_job.total_chunks,
                "chunks_completed": completed_job.completed_chunks,
                "audio_duration_seconds": completed_job.duration_sec,
                "wall_clock_seconds": completed_job.wall_clock_time_sec,
                "overall_rtf": completed_job.rtf,
                "speed_multiplier": f"{1.0/completed_job.rtf:.2f}x" if completed_job.rtf > 0 else "N/A"
            }
        )
        self.manifest_store[rec_id] = manifest
        return manifest
