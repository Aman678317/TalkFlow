"""STT provider factory and router."""
from __future__ import annotations

from typing import Dict
from app.core.config import settings
from app.core.exceptions import ProviderUnavailable
from app.providers.base import STTProvider
from app.providers.faster_whisper.provider import FasterWhisperProvider
from app.providers.fallback.mock_provider import MockSTTProvider

_PROVIDERS: Dict[str, STTProvider] = {}


def get_stt_provider(provider_name: str | None = None) -> STTProvider:
    """Returns requested STT provider or default configured provider."""
    name = (provider_name or settings.stt.primary_provider).lower()

    if name in _PROVIDERS:
        return _PROVIDERS[name]

    if name == "faster-whisper":
        provider = FasterWhisperProvider(
            model_size=settings.stt.model_size,
            device=settings.stt.device,
            compute_type=settings.stt.compute_type,
            cpu_threads=settings.stt.cpu_threads,
            beam_size=settings.stt.beam_size,
            condition_on_previous_text=settings.stt.condition_on_previous_text,
        )
    elif name in ("mock", "mock-stt"):
        provider = MockSTTProvider()
    else:
        raise ProviderUnavailable(name, f"Unknown STT provider {name!r}")

    _PROVIDERS[name] = provider
    return provider

