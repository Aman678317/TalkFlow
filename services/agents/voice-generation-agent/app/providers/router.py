"""Provider Router and Fallback Engine for Agent 06.

Routes synthesis requests to the appropriate TTS provider, monitors provider health,
and handles automatic graceful degradation to local/deterministic fallbacks.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Dict, List, Optional

from app.core.config import get_settings
from app.core.exceptions import ProviderUnavailableError
from app.core.logging import get_logger
from app.models.voice_profile import VoiceCapability
from app.providers.azure_provider import AzureTTSProvider
from app.providers.base import BaseTTSProvider, TTSChunk, TTSResult
from app.providers.dev_tone_provider import DevToneProvider
from app.providers.edge_tts_provider import EdgeTTSProvider
from app.providers.kokoro_provider import KokoroProvider
from app.providers.piper_provider import PiperProvider
from app.providers.system_provider import SystemTTSProvider

logger = get_logger(__name__)


class ProviderRouter:
    """Manages TTS provider lifecycle, routing, and fallback execution."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.dev_tone = DevToneProvider()
        self.edge = EdgeTTSProvider()
        self.system = SystemTTSProvider()
        self.kokoro = KokoroProvider(
            model_path=self.settings.kokoro_model_path,
            voices_path=self.settings.kokoro_voices_path,
        )
        self.piper = PiperProvider(model_dir=self.settings.piper_model_dir)
        self.azure = AzureTTSProvider()

        self._providers: Dict[str, BaseTTSProvider] = {
            "edge": self.edge,
            "edge_tts": self.edge,
            "dev_tone": self.dev_tone,
            "system": self.system,
            "kokoro": self.kokoro,
            "piper": self.piper,
            "azure": self.azure,
        }

    def get_provider(self, name: str) -> Optional[BaseTTSProvider]:
        """Lookup provider by name."""
        return self._providers.get(name.lower())

    async def check_health(self) -> Dict[str, bool]:
        """Check availability of all registered providers."""
        status = {}
        for name, provider in self._providers.items():
            try:
                status[name] = await provider.is_healthy()
            except Exception:
                status[name] = False
        return status

    async def synthesize(
        self,
        voice: VoiceCapability,
        text: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> TTSResult:
        """Synthesize text using the provider associated with the voice, with automatic fallback."""
        primary_name = voice.provider.lower()
        primary_prov = self.get_provider(primary_name)

        if primary_prov and primary_name not in ("dev_tone",):
            try:
                if await primary_prov.is_healthy():
                    return await primary_prov.synthesize(
                        text=text,
                        voice_id=voice.voice_id,
                        language=language,
                        sample_rate=sample_rate,
                        **kwargs,
                    )
            except Exception as e:
                logger.warning(
                    "Primary provider failed, attempting fallback",
                    extra={"provider": primary_name, "voice": voice.voice_id, "error": str(e)},
                )

        # Fallback 1: High-fidelity Multilingual Neural Speech (Edge TTS with gTTS fallback)
        try:
            if await self.edge.is_healthy():
                logger.info("Using Edge Neural TTS provider for natural speech", extra={"lang": language})
                return await self.edge.synthesize(
                    text=text,
                    voice_id=voice.voice_id,
                    language=language,
                    sample_rate=sample_rate,
                    **kwargs,
                )
        except Exception as e:
            logger.warning("Edge TTS fallback failed", extra={"error": str(e)})

        # Fallback 2: System SAPI (if English)
        lang_base = language.lower().split("-")[0].split("_")[0]
        if lang_base == "en":
            try:
                if await self.system.is_healthy():
                    logger.info("Using System SAPI fallback for English synthesis")
                    return await self.system.synthesize(
                        text=text,
                        voice_id="system-default",
                        language=language,
                        sample_rate=sample_rate,
                        **kwargs,
                    )
            except Exception as e:
                logger.warning("System SAPI fallback failed", extra={"error": str(e)})

        # Fallback 3: DevTone formant tone synthesizer (strictly last-resort baseline)
        logger.info("Using TalkFlow DevTone fallback synthesizer")
        return await self.dev_tone.synthesize(
            text=text,
            voice_id=f"dev-tone-{lang_base}",
            language=language,
            sample_rate=sample_rate,
            **kwargs,
        )

    async def synthesize_stream(
        self,
        voice: VoiceCapability,
        text: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> AsyncIterator[TTSChunk]:
        """Synthesize streaming audio using the primary provider or fallback."""
        primary_name = voice.provider.lower()
        primary_prov = self.get_provider(primary_name)

        usable_prov = None
        voice_id_to_use = voice.voice_id

        if primary_prov and primary_name not in ("dev_tone",) and (await primary_prov.is_healthy()):
            usable_prov = primary_prov
        elif await self.edge.is_healthy():
            usable_prov = self.edge
            voice_id_to_use = voice.voice_id
        else:
            lang_base = language.lower().split("-")[0].split("_")[0]
            if lang_base == "en" and (await self.system.is_healthy()):
                usable_prov = self.system
                voice_id_to_use = "system-default"
            else:
                usable_prov = self.dev_tone
                voice_id_to_use = f"dev-tone-{lang_base}"

        async for chunk in usable_prov.synthesize_stream(
            text=text,
            voice_id=voice_id_to_use,
            language=language,
            sample_rate=sample_rate,
            **kwargs,
        ):
            yield chunk

