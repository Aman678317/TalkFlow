"""Azure Speech REST TTS Provider for Agent 06.

Cloud TTS adapter for high-fidelity multi-lingual neural voices.
Strictly gated by privacy and offline policies: blocked when private_only or offline_only is True.
"""
from __future__ import annotations

import io
import time
import wave
from typing import AsyncIterator, List, Optional
import httpx

from app.core.config import get_settings
from app.core.exceptions import PrivacyViolationError, ProviderUnavailableError
from app.core.logging import get_logger
from app.providers.base import BaseTTSProvider, TTSChunk, TTSResult

logger = get_logger(__name__)


class AzureTTSProvider(BaseTTSProvider):
    """Azure Cognitive Services Speech REST API provider."""

    name = "azure"
    is_local = False
    supported_languages = ["en", "hi", "mr", "bn", "ja", "es", "fr", "de"]

    def __init__(self) -> None:
        self.settings = get_settings()

    def _verify_privacy_allowed(self) -> None:
        if self.settings.offline_only:
            raise PrivacyViolationError("Azure Speech TTS is blocked because offline_only mode is enabled.")
        if self.settings.private_only:
            raise PrivacyViolationError("Azure Speech TTS is blocked because private_only mode is enabled.")
        if not self.settings.azure_speech_key or not self.settings.azure_speech_region:
            raise ProviderUnavailableError("Azure Speech credentials (AZURE_SPEECH_KEY / AZURE_SPEECH_REGION) are not configured.")

    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> TTSResult:
        """Synthesize text via Azure Cognitive Services REST API."""
        self._verify_privacy_allowed()
        t0 = time.perf_counter()

        region = self.settings.azure_speech_region
        url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"

        headers = {
            "Ocp-Apim-Subscription-Key": self.settings.azure_speech_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
            "User-Agent": "TalkFlow-VoiceGenerationAgent/1.0",
        }

        # Build SSML
        ssml = (
            f"<speak version='1.0' xml:lang='{language}'>"
            f"<voice xml:lang='{language}' name='{voice_id}'>{text}</voice>"
            f"</speak>"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, content=ssml)
            if resp.status_code != 200:
                raise RuntimeError(f"Azure Speech TTS error {resp.status_code}: {resp.text}")
            wav_bytes = resp.content

        # Parse PCM
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            pcm_bytes = wf.readframes(n_frames)

        duration_ms = (len(pcm_bytes) / (sr * 2)) * 1000.0
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return TTSResult(
            audio_data=wav_bytes,
            pcm_data=pcm_bytes,
            sample_rate=sr,
            encoding="pcm_s16le",
            format="wav",
            duration_ms=duration_ms,
            provider=self.name,
            model="neural",
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
        """Synthesize streaming chunks via single call."""
        res = await self.synthesize(text, voice_id, language, sample_rate)
        yield TTSChunk(
            data=res.pcm_data,
            sample_rate=res.sample_rate,
            encoding="pcm_s16le",
            format="pcm",
            duration_ms=res.duration_ms,
            provider=self.name,
            model="neural",
            voice=voice_id,
            is_dev=False,
            synthetic=True,
            chunk_index=0,
            is_last=True,
        )

    async def is_healthy(self) -> bool:
        return (
            not self.settings.offline_only
            and not self.settings.private_only
            and bool(self.settings.azure_speech_key)
        )

