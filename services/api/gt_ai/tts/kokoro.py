"""Kokoro TTS adapter (kokoro-onnx, real CPU/GPU multilingual voices).

Supports en/es/fr/hi/it/ja/pt/zh voice sets. Model + voices.json download
instructions in docs/AI.md. Lazy-loaded.
"""
from __future__ import annotations

import asyncio
import logging
import struct
import time
import wave
import io
from typing import Any, AsyncIterator

import numpy as np

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk, ProviderUnavailable

log = logging.getLogger("gt_ai.tts.kokoro")


@register("tts", "kokoro")
class KokoroProvider(BaseProvider):
    name = "kokoro"
    task = "tts"
    private = True
    quality_tier = 88
    cost_tier = 40
    latency_class = "fast"
    requires_gpu = False
    SAMPLE_RATE = 24000

    LANG_CODES = {"en": "en-us", "es": "es", "fr": "fr-fr", "hi": "hi",
                  "it": "it", "ja": "jp", "pt": "pt-br", "zh": "zh"}

    def __init__(self, model_path: str = "model_cache/kokoro-v1.0.onnx",
                 voices_path: str = "model_cache/kokoro-voices.json",
                 default_voice: str = "af_heart") -> None:
        self.model_path = model_path
        self.voices_path = voices_path
        self.default_voice = default_voice
        self._tts: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self) -> None:
        if self._tts is not None:
            return
        async with self._lock:
            if self._tts is not None:
                return
            def _load():
                try:
                    from kokoro_onnx import Kokoro
                except ImportError as e:
                    raise ProviderUnavailable("kokoro requires `pip install gt-ai[tts]`") from e
                import os
                if not os.path.isfile(self.model_path) or not os.path.isfile(self.voices_path):
                    raise ProviderUnavailable(
                        f"kokoro model files missing ({self.model_path}, {self.voices_path}); "
                        "see docs/AI.md")
                return Kokoro(self.model_path, self.voices_path)
            self._tts = await asyncio.to_thread(_load)
            log.info("kokoro TTS loaded")

    async def warmup(self) -> None:
        await self._ensure_loaded()

    async def healthcheck(self) -> bool:
        try:
            await self._ensure_loaded()
            return True
        except Exception:
            return False

    def _synth_sync(self, text: str, voice: str, lang: str) -> tuple[np.ndarray, float]:
        speed = 1.0
        samples, rate = self._tts.create(text, voice=voice, speed=speed, lang=self.LANG_CODES.get(lang, "en-us"))
        return samples, rate

    @staticmethod
    def _to_wav(samples: np.ndarray, rate: int) -> bytes:
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    async def synthesize(self, text: str, lang: str, voice: str | None = None) -> AudioChunk:
        await self._ensure_loaded()
        voice = voice or self.default_voice
        t0 = time.perf_counter()
        samples, rate = await asyncio.to_thread(self._synth_sync, text, voice, lang)
        wav = await asyncio.to_thread(self._to_wav, samples, rate)
        duration_ms = len(samples) / rate * 1000
        return AudioChunk(
            data=wav, sample_rate=int(rate), encoding="pcm_s16le", format="wav",
            provider=self.name, model=f"kokoro/{voice}",
            duration_ms=duration_ms,
        )

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None) -> AsyncIterator[AudioChunk]:
        # sentence-chunked streaming: first audio out before full text done
        import re
        sentences = re.split(r"(?<=[.!?।。])\s+", text.strip())
        sentences = [s for s in sentences if s]
        if not sentences:
            sentences = [text]
        t_first = time.perf_counter()
        for i, sent in enumerate(sentences):
            chunk = await self.synthesize(sent, lang, voice)
            if i == 0:
                log.debug("kokoro first audio chunk after %.0fms",
                          (time.perf_counter() - t_first) * 1000)
            yield chunk
