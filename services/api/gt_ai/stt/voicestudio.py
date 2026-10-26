"""VoiceStudio OpenAI-compatible STT sidecar adapter.

VoiceStudio remains an independently installed AGPL application.  TalkFlow
uses only its documented HTTP contract and keeps the sidecar optional.
"""
from __future__ import annotations

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranscriptChunk


@register("stt", "voicestudio_stt")
class VoiceStudioSttProvider(BaseProvider):
    name = "voicestudio_stt"
    task = "stt"
    private = True
    quality_tier = 80
    cost_tier = 10
    latency_class = "realtime"

    def __init__(self, url: str = "", api_key: str = "",
                 model: str = "whisper-1", timeout_s: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.model = model
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

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None) -> TranscriptChunk:
        if not self.url:
            raise ProviderUnavailable("VoiceStudio STT URL is not configured")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(
                    f"{self.url}/v1/audio/transcriptions",
                    files={"file": ("audio.wav", audio, "audio/wav")},
                    data={"model": self.model, "language": lang_hint or "",
                          "response_format": "json", "sample_rate": str(sample_rate)},
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(f"VoiceStudio STT failed: {exc}") from exc
        return TranscriptChunk(
            text=str(payload.get("text", "")).strip(),
            language=payload.get("language") or lang_hint,
            is_final=True,
            confidence=payload.get("confidence"),
            model=str(payload.get("model") or self.model),
            provider=self.name,
        )
