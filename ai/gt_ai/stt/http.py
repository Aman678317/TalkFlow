"""HTTP STT adapter — self-hosted whisper.cpp / speaches / custom service."""
from __future__ import annotations

import logging
import time

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranscriptChunk

log = logging.getLogger("gt_ai.stt.http")


@register("stt", "stt_http")
class HttpSttProvider(BaseProvider):
    name = "stt_http"
    task = "stt"
    private = True
    quality_tier = 75
    cost_tier = 30
    latency_class = "realtime"

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

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None) -> TranscriptChunk:
        if not self.url:
            raise ProviderUnavailable("STT_HTTP_URL not configured")
        t0 = time.perf_counter()
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.post(
                    f"{self.url}/v1/audio/transcriptions",
                    files={"file": ("audio.wav", audio, "audio/wav")},
                    data={"model": "whisper-1", "language": lang_hint or "",
                          "sample_rate": str(sample_rate)},
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"stt_http failed: {e}") from e
        return TranscriptChunk(
            text=data.get("text", "").strip(),
            language=data.get("language", lang_hint),
            is_final=True,
            confidence=data.get("confidence"),
            model="stt_http",
            provider=self.name,
        )
