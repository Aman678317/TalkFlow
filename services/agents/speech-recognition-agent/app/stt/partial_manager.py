"""Streaming partial transcription manager with revision and generation tracking."""
from __future__ import annotations

import asyncio
from typing import Dict, Optional, Tuple
from app.models.events import TranscriptPartialEvent
from app.models.schemas import STTResult
from app.providers.base import STTProvider


class PartialManager:
    """Manages streaming partial transcription with monotonic revisions and stale cancellation."""

    def __init__(
        self,
        provider: STTProvider,
        partial_interval_ms: int = 500,
        min_duration_ms: int = 250,
        max_duration_ms: int = 30000,
    ):
        self.provider = provider
        self.partial_interval_ms = partial_interval_ms
        self.min_duration_ms = min_duration_ms
        self.max_duration_ms = max_duration_ms

        # State tracking: session_id -> {utterance_id, generation, revision, last_transcribed_ms, buffer}
        self._states: Dict[str, Dict] = {}

    def init_utterance(self, session_id: str, utterance_id: str, segment_id: str) -> None:
        """Initializes or resets tracking for an utterance."""
        cur = self._states.get(session_id)
        gen = (cur["generation"] + 1) if cur else 1
        self._states[session_id] = {
            "utterance_id": utterance_id,
            "segment_id": segment_id,
            "generation": gen,
            "revision": 0,
            "last_partial_time_ms": 0,
            "buffer": bytearray(),
            "in_flight": False,
        }

    def append_audio(self, session_id: str, pcm16_chunk: bytes) -> None:
        """Appends audio chunk to the utterance buffer."""
        if session_id in self._states:
            self._states[session_id]["buffer"].extend(pcm16_chunk)

    def should_emit_partial(self, session_id: str, elapsed_ms: int) -> bool:
        """Checks if enough audio and time has elapsed to generate a partial."""
        state = self._states.get(session_id)
        if not state or state["in_flight"]:
            return False

        buf_len = len(state["buffer"])
        audio_dur_ms = int((buf_len / 32.0))  # 32 bytes/ms at 16kHz 16-bit mono

        if audio_dur_ms < self.min_duration_ms:
            return False

        time_since_last = elapsed_ms - state["last_partial_time_ms"]
        return time_since_last >= self.partial_interval_ms

    async def generate_partial(
        self,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        current_time_ms: int,
        language_hint: Optional[str] = None,
    ) -> Optional[TranscriptPartialEvent]:
        """Generates a partial transcript event if utterance is active."""
        state = self._states.get(session_id)
        if not state or state["in_flight"]:
            return None

        state["in_flight"] = True
        audio_snapshot = bytes(state["buffer"])
        gen_snapshot = state["generation"]
        utt_id = state["utterance_id"]
        seg_id = state["segment_id"]

        try:
            # Run inference in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            result: STTResult = await loop.run_in_executor(
                None,
                lambda: self.provider.transcribe(
                    audio_snapshot,
                    sample_rate=16000,
                    language_hint=language_hint,
                    word_timestamps=False,  # faster for partials
                ),
            )

            # Check for stale cancellation (generation changed while transcribing)
            cur_state = self._states.get(session_id)
            if not cur_state or cur_state["generation"] != gen_snapshot:
                return None  # Stale partial discarded

            cur_state["revision"] += 1
            cur_state["last_partial_time_ms"] = current_time_ms

            if not result.text.strip():
                return None

            return TranscriptPartialEvent(
                session_id=session_id,
                conversation_id=conversation_id,
                speaker_id=speaker_id,
                utterance_id=utt_id,
                segment_id=seg_id,
                revision=cur_state["revision"],
                text=result.text.strip(),
                language_hint=result.language,
                language_probability=result.language_probability,
                is_final=False,
                provider=self.provider.name,
                model=self.provider.model_name,
            )

        finally:
            if session_id in self._states:
                self._states[session_id]["in_flight"] = False

    def close_utterance(self, session_id: str) -> None:
        """Closes and frees utterance state."""
        self._states.pop(session_id, None)

