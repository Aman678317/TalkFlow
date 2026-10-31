"""Kokoro TTS Adapter for Agent 06.

Uses kokoro-onnx for fast, lightweight neural speech synthesis.
Gracefully handles missing weights with explicit health status.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import time
import wave
from typing import Any, AsyncIterator, List, Optional
import numpy as np

from app.core.exceptions import ProviderUnavailableError
from app.core.logging import get_logger
from app.providers.base import BaseTTSProvider, TTSChunk, TTSResult

logger = get_logger(__name__)


class KokoroProvider(BaseTTSProvider):
    """Kokoro ONNX neural speech synthesis provider."""

    name = "kokoro"
    is_local = True
    supported_languages = ["en", "es", "fr", "hi", "it", "ja", "pt", "zh"]

    def __init__(
        self,
        model_path: str = "model_cache/kokoro/kokoro-v0_19.onnx",
        voices_path: str = "model_cache/kokoro/voices.json",
    ) -> None:
        self.model_path = model_path
        self.voices_path = voices_path
        self._engine: Any = None
        self._lock = asyncio.Lock()

    def _is_model_present(self) -> bool:
        return os.path.isfile(self.model_path) and os.path.isfile(self.voices_path)

    async def _ensure_loaded(self) -> None:
        if self._engine is not None:
            return
        async with self._lock:
            if self._engine is not None:
                return

            if not self._is_model_present():
                raise ProviderUnavailableError(
                    f"Kokoro model files not found at '{self.model_path}' and '{self.voices_path}'."
                )

            def _load():
                try:
                    from kokoro_onnx import Kokoro
                    return Kokoro(self.model_path, self.voices_path)
                except Exception as e:
                    raise ProviderUnavailableError(f"Failed to initialize Kokoro ONNX: {e}") from e

            self._engine = await asyncio.to_thread(_load)

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> TTSResult:
        """Synthesize text using Kokoro ONNX."""
        await self._ensure_loaded()
        t0 = time.perf_counter()

        def _run_synth():
            samples, sr = self._engine.create(
                text,
                voice=voice_id,
                speed=1.0,
                lang=language,
            )
            pcm_16 = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
            pcm_bytes = pcm_16.tobytes()

            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm_bytes)
            wav_bytes = wav_buf.getvalue()
            duration_ms = (len(pcm_bytes) / (sr * 2)) * 1000.0
            return wav_bytes, pcm_bytes, sr, duration_ms

        wav_bytes, pcm_bytes, sr, duration_ms = await asyncio.to_thread(_run_synth)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return TTSResult(
            audio_data=wav_bytes,
            pcm_data=pcm_bytes,
            sample_rate=sr,
            encoding="pcm_s16le",
            format="wav",
            duration_ms=duration_ms,
            provider=self.name,
            model="kokoro-v0_19",
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
        """Synthesize stream by sentence chunks."""
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?।。\n])\s+", text.strip())
            if s.strip()
        ]
        if not sentences:
            sentences = [text.strip() or " "]

        total = len(sentences)
        for idx, sentence in enumerate(sentences):
            res = await self.synthesize(sentence, voice_id, language, sample_rate)
            yield TTSChunk(
                data=res.pcm_data,
                sample_rate=res.sample_rate,
                encoding="pcm_s16le",
                format="pcm",
                duration_ms=res.duration_ms,
                provider=self.name,
                model="kokoro-v0_19",
                voice=voice_id,
                is_dev=False,
                synthetic=True,
                chunk_index=idx,
                is_last=(idx == total - 1),
            )

    async def is_healthy(self) -> bool:
        return self._is_model_present()

