"""Provider registry and factory for Language Intelligence Agent."""
from __future__ import annotations

from typing import Dict, List, Optional
from app.core.config import settings
from app.core.exceptions import ProviderUnavailable
from app.core.logging import get_logger
from app.providers.base import LanguageDetectionProvider
from app.providers.fasttext.provider import FastTextProvider
from app.providers.langdetect.provider import LangDetectProvider
from app.providers.whisper_lid.provider import WhisperLIDProvider

log = get_logger("providers")

_PROVIDER_INSTANCES: Dict[str, LanguageDetectionProvider] = {}


def get_language_provider(provider_name: Optional[str] = None) -> LanguageDetectionProvider:
    """Returns initialized singleton language detection provider."""
    name = (provider_name or settings.detection.primary_provider).lower()

    if name in _PROVIDER_INSTANCES:
        return _PROVIDER_INSTANCES[name]

    provider: LanguageDetectionProvider

    if name in ("fasttext", "fast-text", "ft"):
        provider = FastTextProvider(
            model_path=settings.detection.fasttext_model_path,
            auto_download=True,
        )
    elif name in ("langdetect", "ld"):
        provider = LangDetectProvider()
    elif name in ("whisper", "whisper-lid", "stt"):
        provider = WhisperLIDProvider()
    else:
        raise ProviderUnavailable(f"Unsupported language provider '{name}'", details={"requested": name})

    _PROVIDER_INSTANCES[name] = provider
    log.info(f"Initialized language provider: {provider.name} (model: {provider.model_name})")
    return provider


def get_all_providers() -> List[LanguageDetectionProvider]:
    """Returns list of all supported and configured provider instances."""
    names = ["fasttext", "langdetect", "whisper-lid"]
    providers = []
    for n in names:
        try:
            providers.append(get_language_provider(n))
        except Exception as exc:
            log.warning(f"Could not initialize provider '{n}': {exc}")
    return providers
