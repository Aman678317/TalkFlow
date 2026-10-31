"""Piper TTS Adapter for Agent 06.

Provides high-efficiency per-language ONNX neural voices for Hindi, Marathi,
Bengali, English, and other regional languages.
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import time
import wave
from typing import Any, AsyncIterator, Dict, List, Optional
import numpy as np

from app.core.exceptions import ProviderUnavailableError
from app.core.logging import get_logger
from app.providers.base import BaseTTSProvider, TTSChunk, TTSResult

logger = get_logger(__name__)


class PiperProvider(BaseTTSProvider):
    """Piper ONNX neural speech synthesis provider."""

    name = "piper"
    is_local = True
    supported_languages = ["en", "hi", "mr", "bn", "es"]

    def __init__(self, model_dir: str = "model_cache/piper") -> None:
        self.model_dir = model_dir
        self._voices: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def _get_model_path(self, voice_id: str) -> str:
        stem = voice_id.replace(".onnx", "")
        return os.path.join(self.model_dir, f"{stem}.onnx")

    def _is_voice_present(self, voice_id: str) -> bool:
        path = self._get_model_path(voice_id)
        return os.path.isfile(path) and os.path.isfile(f"{path}.json")

    async def _load_voice(self, voice_id: str) -> Any:
        if voice_id in self._voices:
            return self._voices[voice_id]

        async with self._lock:
            if voice_id in self._voices:
                return self._voices[voice_id]

            model_path = self._get_model_path(voice_id)
            if not self._is_voice_present(voice_id):
                raise ProviderUnavailableError(
                    f"Piper voice model '{voice_id}' not found at '{model_path}'."
                )

            def _load():
                from piper.voice import PiperVoice
                return PiperVoice.load(model_path)

            voice = await asyncio.to_thread(_load)
            self._voices[voice_id] = voice
            return voice

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 22050,
        **kwargs,
    ) -> TTSResult:
        """Synthesize text using Piper ONNX."""
        voice = await self._load_voice(voice_id)
        t0 = time.perf_counter()

        def _run_synth():
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                voice.synthesize(text, wf)
            wav_bytes = wav_buf.getvalue()

            # Parse PCM
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                raw_pcm = wf.readframes(n_frames)

            duration_ms = (len(raw_pcm) / (sr * 2)) * 1000.0
            return wav_bytes, raw_pcm, sr, duration_ms

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
            model=voice_id,
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
        sample_rate: int = 22050,
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
                model=voice_id,
                voice=voice_id,
                is_dev=False,
                synthetic=True,
                chunk_index=idx,
                is_last=(idx == total - 1),
            )

    async def is_healthy(self) -> bool:
        return os.path.isdir(self.model_dir) and any(f.endswith(".onnx") for f in os.listdir(self.model_dir))

