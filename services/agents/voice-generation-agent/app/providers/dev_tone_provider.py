"""Development Tone Synthesizer Provider for TalkFlow Agent 06.

Deterministic pure-Python formant harmonic synthesizer adapted from TalkFlow's dev_tone.py.
Exercises the entire audio pipeline (PCM framing, chunking, streaming) reliably
without requiring multi-gigabyte neural weight downloads.
"""
from __future__ import annotations

import asyncio
import io
import math
import re
import time
import wave
from typing import AsyncIterator, List, Optional
import numpy as np

from app.core.logging import get_logger
from app.providers.base import BaseTTSProvider, TTSChunk, TTSResult

logger = get_logger(__name__)


def _text_to_pcm(text: str, sample_rate: int = 24000) -> tuple[bytes, bytes, float]:
    """Generate deterministic formant-like PCM and WAV bytes from text.
    
    Returns:
        (wav_bytes, pcm_bytes, duration_ms)
    """
    cleaned = text.strip() or " "
    chunks: List[np.ndarray] = []
    base_freq = 160.0

    for ch in cleaned[:500]:
        if ch == " ":
            chunks.append(np.zeros(int(sample_rate * 0.04), dtype=np.float32))
            continue
        dur = 0.055
        n = int(sample_rate * dur)
        t = np.arange(n, dtype=np.float32) / sample_rate
        f = base_freq + (ord(ch) % 40) * 8
        env = np.hanning(n).astype(np.float32)
        tone = (
            0.5 * np.sin(2 * math.pi * f * t)
            + 0.25 * np.sin(2 * math.pi * f * 2.02 * t)
            + 0.12 * np.sin(2 * math.pi * f * 3.01 * t)
        ) * env
        chunks.append(tone.astype(np.float32))

    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    pcm_array = (np.clip(audio, -1.0, 1.0) * 30000).astype(np.int16)
    pcm_bytes = pcm_array.tobytes()

    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    wav_bytes = wav_buf.getvalue()

    duration_ms = (len(pcm_bytes) / (sample_rate * 2)) * 1000.0
    return wav_bytes, pcm_bytes, duration_ms


class DevToneProvider(BaseTTSProvider):
    """Pure-Python zero-weight harmonic formant speech synthesizer."""

    name = "dev_tone"
    is_local = True
    supported_languages = ["*", "en", "hi", "mr", "bn", "ja", "es", "fr", "de"]

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> TTSResult:
        """Synthesize text into deterministic audible tone waveform."""
        t0 = time.perf_counter()
        wav_bytes, pcm_bytes, duration_ms = await asyncio.to_thread(_text_to_pcm, text, sample_rate)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return TTSResult(
            audio_data=wav_bytes,
            pcm_data=pcm_bytes,
            sample_rate=sample_rate,
            encoding="pcm_s16le",
            format="wav",
            duration_ms=duration_ms,
            provider=self.name,
            model="formant-synthesizer-v1",
            voice=voice_id,
            latency_ms=latency_ms,
            is_dev=True,
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
        """Synthesize text in sentence chunks."""
        # Split on sentence boundaries including Indic danda '।' and Japanese '。'
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?।。\n])\s+", text.strip())
            if s.strip()
        ]
        if not sentences:
            sentences = [text.strip() or " "]

        total = len(sentences)
        for idx, sentence in enumerate(sentences):
            wav_bytes, pcm_bytes, duration_ms = await asyncio.to_thread(_text_to_pcm, sentence, sample_rate)
            yield TTSChunk(
                data=pcm_bytes,
                sample_rate=sample_rate,
                encoding="pcm_s16le",
                format="pcm",
                duration_ms=duration_ms,
                provider=self.name,
                model="formant-synthesizer-v1",
                voice=voice_id,
                is_dev=True,
                synthetic=True,
                chunk_index=idx,
                is_last=(idx == total - 1),
            )

    async def is_healthy(self) -> bool:
        return True

