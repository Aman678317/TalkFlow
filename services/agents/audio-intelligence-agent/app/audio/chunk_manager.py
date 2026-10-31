"""Audio chunk and segment persistence lifecycle manager."""
from __future__ import annotations

import io
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional
import soundfile as sf
from app.models.schemas import AudioChunk, AudioQualityMetrics


class ChunkManager:
    """Manages audio chunk storage, ephemeral lifecycles, and temporary file sanitization."""

    def __init__(
        self,
        retention_policy: str = "ephemeral",
        temp_dir: str = "temp_audio",
        max_in_memory_history: int = 50,
    ):
        self.retention_policy = retention_policy.lower().strip()
        self.temp_dir = Path(temp_dir)
        self.max_in_memory_history = max_in_memory_history
        self._memory_chunks: Dict[str, List[AudioChunk]] = {}

        if self.retention_policy == "debug_disk":
            self.temp_dir.mkdir(parents=True, exist_ok=True)

    def create_chunk(
        self,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        segment_id: str,
        sequence: int,
        start_ms: int,
        end_ms: int,
        pcm_bytes: bytes,
        quality: AudioQualityMetrics,
        status: str = "final",
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> AudioChunk:
        """Constructs an AudioChunk and handles configured retention."""
        duration_ms = end_ms - start_ms
        storage_ref: Optional[str] = None

        if self.retention_policy == "debug_disk":
            session_folder = self.temp_dir / session_id
            session_folder.mkdir(parents=True, exist_ok=True)
            chunk_file = session_folder / f"{segment_id}_{status}_{sequence}.wav"
            try:
                # Write PCM16 to WAV
                with sf.SoundFile(
                    chunk_file,
                    mode="w",
                    samplerate=sample_rate,
                    channels=channels,
                    subtype="PCM_16",
                ) as f:
                    # int16 buffer to soundfile
                    import numpy as np
                    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
                    f.write(samples)
                storage_ref = str(chunk_file)
            except Exception:
                storage_ref = None

        chunk = AudioChunk(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
            segment_id=segment_id,
            sequence=sequence,
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            channels=channels,
            encoding="pcm_s16le",
            quality=quality,
            status=status,
            storage_ref=storage_ref,
        )

        if self.retention_policy in ("memory_only", "debug_disk"):
            if session_id not in self._memory_chunks:
                self._memory_chunks[session_id] = []
            self._memory_chunks[session_id].append(chunk)
            if len(self._memory_chunks[session_id]) > self.max_in_memory_history:
                self._memory_chunks[session_id].pop(0)

        return chunk

    def cleanup_session(self, session_id: str) -> None:
        """Securely cleans up temporary files and memory for a terminated session."""
        if session_id in self._memory_chunks:
            del self._memory_chunks[session_id]

        if self.retention_policy == "debug_disk":
            session_folder = self.temp_dir / session_id
            if session_folder.exists():
                try:
                    shutil.rmtree(session_folder, ignore_errors=True)
                except Exception:
                    pass

    def get_session_history(self, session_id: str) -> List[AudioChunk]:
        """Returns in-memory historical chunks for a session."""
        return self._memory_chunks.get(session_id, []).copy()

