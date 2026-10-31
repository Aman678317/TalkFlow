"""High-level transcription service orchestrating engine and session states."""
from __future__ import annotations

import uuid
from typing import Optional
from app.audio.conversion import wav_bytes_to_pcm16
from app.audio.ingestion import AudioIngestionEngine
from app.core.logging import get_logger
from app.models.schemas import TranscribeResponse
from app.services.session_manager import STTSessionManager
from app.stt.engine import STTEngine

log = get_logger("services.transcription_service")


class TranscriptionService:
    """Service coordinator for speech-to-text batch and streaming jobs."""

    def __init__(self, engine: Optional[STTEngine] = None):
        self.engine = engine or STTEngine()
        self.session_manager = STTSessionManager()
        self.ingestion = AudioIngestionEngine()

    async def transcribe_audio_file(
        self,
        file_bytes: bytes,
        filename: str = "audio.wav",
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        speaker_id: str = "user_001",
        language_hint: Optional[str] = None,
    ) -> TranscribeResponse:
        """Processes and transcribes an uploaded WAV or PCM audio file."""
        pcm16, sample_rate, _ = self.ingestion.ingest_wav_file(file_bytes)

        sess_id = session_id or f"sess_{uuid.uuid4().hex[:10]}"
        conv_id = conversation_id or sess_id
        utt_id = f"utt_{uuid.uuid4().hex[:12]}"
        seg_id = f"seg_{uuid.uuid4().hex[:12]}"

        log.info(f"Transcribing audio file {filename} ({len(pcm16)} bytes, {sample_rate}Hz)")

        resp = await self.engine.transcribe_segment_async(
            audio_pcm16=pcm16,
            session_id=sess_id,
            conversation_id=conv_id,
            speaker_id=speaker_id,
            utterance_id=utt_id,
            segment_id=seg_id,
            seq=1,
            start_ms=0,
            sample_rate=sample_rate,
            language_hint=language_hint,
            word_timestamps=True,
        )

        # Automatically forward finalized transcript to Agent 03 (Language Intelligence Agent)
        if resp.text.strip():
            import asyncio
            from app.integration.agent03_publisher import publisher_to_agent03
            asyncio.create_task(publisher_to_agent03.forward_transcript_to_agent03(resp))

        return resp

    async def transcribe_agent01_segment(
        self,
        pcm16_bytes: bytes,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        utterance_id: str,
        segment_id: str,
        seq: int = 1,
        start_ms: int = 0,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None,
    ) -> TranscribeResponse:
        """Transcribes a clean segment received from Agent 01."""
        resp = await self.engine.transcribe_segment_async(
            audio_pcm16=pcm16_bytes,
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            utterance_id=utterance_id,
            segment_id=segment_id,
            seq=seq,
            start_ms=start_ms,
            sample_rate=sample_rate,
            language_hint=language_hint,
            word_timestamps=True,
        )

        # Automatically forward finalized transcript to Agent 03 (Language Intelligence Agent)
        if resp.text.strip():
            import asyncio
            from app.integration.agent03_publisher import publisher_to_agent03
            asyncio.create_task(publisher_to_agent03.forward_transcript_to_agent03(resp))

        return resp


transcription_service = TranscriptionService()

