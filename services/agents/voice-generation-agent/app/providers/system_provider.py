"""Windows System SAPI / pyttsx3 TTS Provider for Agent 06.

Uses the native Windows speech synthesis subsystem (SAPI5) to provide
real zero-network, local TTS for English (David / Zira) and other installed voices.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import tempfile
import time
import wave
from typing import AsyncIterator, List, Optional
import numpy as np

from app.core.logging import get_logger
from app.providers.base import BaseTTSProvider, TTSChunk, TTSResult

logger = get_logger(__name__)


def _synthesize_sapi_worker(text: str, voice_pref: Optional[str] = None, target_sr: int = 24000) -> tuple[bytes, bytes, float]:
    """Worker function executed in worker thread.
    
    Generates WAV using pyttsx3, parses PCM data, resamples to target_sr if needed.
    """
    import pyttsx3

    engine = pyttsx3.init()
    voices = engine.getProperty("voices")

    if voice_pref:
        pref_lower = voice_pref.lower()
        for v in voices:
            if "david" in pref_lower and "david" in v.name.lower():
                engine.setProperty("voice", v.id)
                break
            elif "zira" in pref_lower and "zira" in v.name.lower():
                engine.setProperty("voice", v.id)
                break

    engine.setProperty("rate", 175)

    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        engine.save_to_file(text, tmp_path)
        engine.runAndWait()

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise RuntimeError("pyttsx3 failed to generate audio output file.")

        with wave.open(tmp_path, "rb") as wf:
            src_sr = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw_data = wf.readframes(n_frames)

        # Parse PCM array
        pcm_16 = np.frombuffer(raw_data, dtype=np.int16)
        if n_channels == 2:
            pcm_16 = pcm_16.reshape(-1, 2).mean(axis=1).astype(np.int16)

        # Resample if sample rate differs
        if src_sr != target_sr:
            from scipy import signal
            num_samples = int(len(pcm_16) * float(target_sr) / src_sr)
            resampled = signal.resample(pcm_16.astype(np.float32), num_samples)
            pcm_16 = np.clip(resampled, -32768, 32767).astype(np.int16)

        pcm_bytes = pcm_16.tobytes()

        # Wrap into standard WAV header
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(target_sr)
            wf_out.writeframes(pcm_bytes)
        wav_bytes = wav_buf.getvalue()

        duration_ms = (len(pcm_bytes) / (target_sr * 2)) * 1000.0
        return wav_bytes, pcm_bytes, duration_ms

    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


class SystemTTSProvider(BaseTTSProvider):
    """Local Windows SAPI5 / pyttsx3 speech provider."""

    name = "system"
    is_local = True
    supported_languages = ["en"]

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> TTSResult:
        """Synthesize text via Windows native SAPI."""
        t0 = time.perf_counter()
        async with self._lock:
            wav_bytes, pcm_bytes, duration_ms = await asyncio.to_thread(
                _synthesize_sapi_worker, text, voice_id, sample_rate
            )
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return TTSResult(
            audio_data=wav_bytes,
            pcm_data=pcm_bytes,
            sample_rate=sample_rate,
            encoding="pcm_s16le",
            format="wav",
            duration_ms=duration_ms,
            provider=self.name,
            model="sapi5",
            voice=voice_id,
            latency_ms=latency_ms,
            is_dev=False,
            synthetic=True,
        )

    async def synthesize_stream(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> AsyncIterator[TTSChunk]:
        """Synthesize text by sentence streaming."""
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?।。\n])\s+", text.strip())
            if s.strip()
        ]
        if not sentences:
            sentences = [text.strip() or " "]

        total = len(sentences)
        for idx, sentence in enumerate(sentences):
            async with self._lock:
                wav_bytes, pcm_bytes, duration_ms = await asyncio.to_thread(
                    _synthesize_sapi_worker, sentence, voice_id, sample_rate
                )
            yield TTSChunk(
                data=pcm_bytes,
                sample_rate=sample_rate,
                encoding="pcm_s16le",
                format="pcm",
                duration_ms=duration_ms,
                provider=self.name,
                model="sapi5",
                voice=voice_id,
                is_dev=False,
                synthetic=True,
                chunk_index=idx,
                is_last=(idx == total - 1),
            )

    async def is_healthy(self) -> bool:
        return True

