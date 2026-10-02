"""HTTP TTS adapter — any self-hosted TTS service returning WAV bytes."""
from __future__ import annotations

import logging
import time

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk, ProviderUnavailable

log = logging.getLogger("gt_ai.tts.http")


@register("tts", "tts_http")
class HttpTtsProvider(BaseProvider):
    name = "tts_http"
    task = "tts"
    private = True
    quality_tier = 70
    cost_tier = 30
    latency_class = "fast"

    def __init__(self, url: str = "", api_key: str = "", timeout_s: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def healthcheck(self) -> bool:
        if not self.url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{self.url}/health")
                return r.status_code < 500
        except Exception:
            return False

    async def synthesize(self, text: str, lang: str, voice: str | None = None) -> AudioChunk:
        if not self.url:
            raise ProviderUnavailable("TTS_HTTP_URL not configured")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.post(f"{self.url}/v1/tts", json={
                    "text": text, "lang": lang, "voice": voice or "",
                    "format": "wav",
                }, headers=headers)
                r.raise_for_status()
                wav = r.content
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"tts_http failed: {e}") from e
        duration_ms = max(0.0, (len(wav) - 44) / 48.0)  # assume 24kHz s16 mono
        return AudioChunk(
            data=wav, sample_rate=24000, encoding="pcm_s16le", format="wav",
            provider=self.name, model="tts_http", duration_ms=duration_ms,
        )
