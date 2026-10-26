"""VoiceStudio OpenAI-compatible TTS sidecar adapter."""
from __future__ import annotations

import io
import time
import wave
from typing import AsyncIterator

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk, ProviderUnavailable


@register("tts", "voicestudio_tts")
class VoiceStudioTtsProvider(BaseProvider):
    name = "voicestudio_tts"
    task = "tts"
    private = True
    quality_tier = 82
    cost_tier = 10
    latency_class = "fast"

    def __init__(self, url: str = "", api_key: str = "",
                 model: str = "tts-1", default_voice: str = "default",
                 response_format: str = "wav", timeout_s: float = 45.0) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.default_voice = default_voice
        self.response_format = response_format
        self.timeout_s = timeout_s

    def runtime_ready(self) -> bool:
        return bool(self.url)

    async def healthcheck(self) -> bool:
        if not self.url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.url}/health")
                return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def synthesize(self, text: str, lang: str,
                         voice: str | None = None) -> AudioChunk:
        if not self.url:
            raise ProviderUnavailable("VoiceStudio TTS URL is not configured")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(
                    f"{self.url}/v1/audio/speech",
                    json={"model": self.model, "input": text,
                          "voice": voice or self.default_voice,
                          "response_format": self.response_format,
                          "language": lang},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.content
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"VoiceStudio TTS failed: {exc}") from exc
        sample_rate = 24000
        duration_ms = 0.0
        if self.response_format == "wav":
            try:
                with wave.open(io.BytesIO(data), "rb") as wav:
                    sample_rate = wav.getframerate()
                    duration_ms = wav.getnframes() / max(1, sample_rate) * 1000
            except (wave.Error, OSError):
                raise ProviderUnavailable("VoiceStudio returned invalid WAV audio")
        else:
            duration_ms = max(0.0, (len(data) - 44) / 48.0)
        return AudioChunk(
            data=data, sample_rate=sample_rate, encoding="pcm_s16le",
            format=self.response_format, provider=self.name, model=self.model,
            duration_ms=duration_ms,
        )

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None) -> AsyncIterator[AudioChunk]:
        yield await self.synthesize(text, lang, voice)
