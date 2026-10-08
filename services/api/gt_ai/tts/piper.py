"""Piper TTS adapter (per-language ONNX voices, real self-hosted TTS).

Good coverage path for languages Kokoro lacks (e.g. mr/bn/ta via community
voices). Model dir contains <lang>-<voice>.onnx + .onnx.json.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk, ProviderUnavailable

log = logging.getLogger("gt_ai.tts.piper")


@register("tts", "piper")
class PiperProvider(BaseProvider):
    name = "piper"
    task = "tts"
    private = True
    quality_tier = 70
    cost_tier = 25
    latency_class = "fast"

    def __init__(self, model_dir: str = "model_cache/piper", voice_map: dict[str, str] | None = None) -> None:
        self.model_dir = model_dir
        # lang -> voice file basename; extend via config as voices are validated
        self.voice_map = voice_map or {
            "en": "en_US-lessac-medium",
            "hi": "hi_IN-pratham-medium",
        }
        self._voices: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def _load_voice_sync(self, lang: str) -> Any:
        import os
        base = self.voice_map.get(lang)
        if not base:
            raise ProviderUnavailable(f"no piper voice configured for lang={lang}")
        path = os.path.join(self.model_dir, base + ".onnx")
        if not os.path.isfile(path):
            raise ProviderUnavailable(f"piper voice missing: {path}")
        try:
            from piper import PiperVoice
        except ImportError as e:
            raise ProviderUnavailable("piper requires `pip install piper-tts`") from e
        return PiperVoice.load(path)

    async def _voice(self, lang: str) -> Any:
        if lang in self._voices:
            return self._voices[lang]
        async with self._lock:
            if lang not in self._voices:
                self._voices[lang] = await asyncio.to_thread(self._load_voice_sync, lang)
        return self._voices[lang]

    async def healthcheck(self) -> bool:
        try:
            await self._voice("en")
            return True
        except Exception:
            return False

    async def synthesize(self, text: str, lang: str, voice: str | None = None) -> AudioChunk:
        import io
        import wave
        v = await self._voice(lang)

        def _do() -> tuple[bytes, int]:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                v.synthesize_wav(text, wf)
                rate = wf.getframerate()
            return buf.getvalue(), rate

        t0 = time.perf_counter()
        wav, rate = await asyncio.to_thread(_do)
        return AudioChunk(
            data=wav, sample_rate=rate, encoding="pcm_s16le", format="wav",
            provider=self.name, model=f"piper/{self.voice_map.get(lang, lang)}",
            duration_ms=(len(wav) - 44) / (rate * 2) * 1000,
        )

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None) -> AsyncIterator[AudioChunk]:
        yield await self.synthesize(text, lang, voice)
