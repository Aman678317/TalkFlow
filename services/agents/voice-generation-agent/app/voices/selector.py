"""Deterministic Voice Selection Engine for Agent 06.

Selects the optimal voice capability based on target language, participant preference,
provider availability, privacy constraints, and consent status.
"""
from __future__ import annotations

from typing import Optional
from app.core.config import get_settings
from app.core.exceptions import (
    ConsentRequiredError,
    PrivacyViolationError,
    UnsupportedLanguageError,
    VoiceUnavailableError,
)
from app.core.logging import get_logger
from app.models.voice_profile import VoiceCapability
from app.voices.consent_manager import VoiceConsentManager
from app.voices.registry import VoiceRegistry

logger = get_logger(__name__)


class VoiceSelector:
    """Selects and validates voices for speech synthesis."""

    def __init__(
        self,
        registry: VoiceRegistry,
        consent_manager: VoiceConsentManager,
    ) -> None:
        self.registry = registry
        self.consent_manager = consent_manager
        self.settings = get_settings()

    def select_voice(
        self,
        target_language: str,
        preferred_voice_id: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        speaker_id: Optional[str] = None,
        tenant_id: str = "org_default",
        gender: Optional[str] = None,
        offline_only: Optional[bool] = None,
        private_only: Optional[bool] = None,
    ) -> VoiceCapability:
        """Select a voice strictly compatible with target_language.
        
        5-Tier Resolution:
        1. Explicitly requested preferred_voice_id (if compatible with target_language).
        2. Neural voice matching language (Kokoro / Piper).
        3. Local system voice (pyttsx3 / SAPI).
        4. DevTone deterministic formant voice.
        5. Fail-closed: raise UnsupportedLanguageError.
        """
        is_offline = offline_only if offline_only is not None else self.settings.offline_only
        is_private = private_only if private_only is not None else self.settings.private_only

        lang_base = target_language.lower().split("-")[0].split("_")[0]
        supported = [l.lower() for l in self.settings.supported_languages]
        if lang_base not in supported:
            raise UnsupportedLanguageError(
                f"Target language '{target_language}' is not supported by TalkFlow configured capabilities: {supported}"
            )

        # 1. Tier 1: Check explicitly requested preferred voice
        if preferred_voice_id:
            voice = self.registry.get(preferred_voice_id)
            if not voice:
                raise VoiceUnavailableError(f"Requested voice '{preferred_voice_id}' is not registered.")

            if not voice.is_available:
                raise VoiceUnavailableError(f"Requested voice '{preferred_voice_id}' is currently marked unavailable.")

            if is_offline and not voice.is_local:
                raise PrivacyViolationError(
                    f"Voice '{preferred_voice_id}' is a cloud voice, but offline_only mode is enforced."
                )

            if is_private and not voice.is_local:
                raise PrivacyViolationError(
                    f"Voice '{preferred_voice_id}' is a cloud voice, but private_only mode is enforced."
                )

            # Check language compatibility: Never use an English-only voice for Hindi/Marathi
            voice_lang_base = voice.language.lower().split("-")[0].split("_")[0]
            if voice.language != "*" and voice_lang_base != lang_base:
                logger.warning(
                    "Preferred voice language mismatch",
                    extra={
                        "requested_voice": preferred_voice_id,
                        "voice_language": voice.language,
                        "target_language": target_language,
                    },
                )
                raise VoiceUnavailableError(
                    f"Voice '{preferred_voice_id}' speaks language '{voice.language}', "
                    f"which does not match target language '{target_language}'. "
                    f"Cross-language silent substitution is prohibited."
                )

            # Verify consent if voice is custom/cloned
            is_custom = voice.notes and "cloned" in voice.notes.lower()
            if is_custom and speaker_id:
                self.consent_manager.verify_consent(
                    tenant_id=tenant_id,
                    speaker_id=speaker_id,
                    voice_id=preferred_voice_id,
                    is_cloned_or_custom=True,
                )

            return voice

        # 2. Tier 2: Neural voice matching language (Edge TTS / Azure / Kokoro / Piper)
        neural_providers = ["edge_tts", "edge", "azure", "kokoro", "piper"]
        if preferred_provider and preferred_provider.lower() in neural_providers:
            neural_providers = [preferred_provider.lower()]

        for prov in neural_providers:
            candidate = self.registry.find_best_for_language(
                language=target_language,
                preferred_provider=prov,
                gender=gender,
                offline_only=is_offline,
            )
            if candidate and candidate.is_available:
                return candidate

        # 3. Tier 3: Local System voice (SAPI / pyttsx3)
        candidate = self.registry.find_best_for_language(
            language=target_language,
            preferred_provider="system",
            gender=gender,
            offline_only=is_offline,
        )
        if candidate and candidate.is_available:
            return candidate

        # 4. Tier 4: DevTone deterministic formant tone synthesizer
        candidate = self.registry.find_best_for_language(
            language=target_language,
            preferred_provider="dev_tone",
            gender=gender,
            offline_only=is_offline,
        )
        if candidate and candidate.is_available:
            return candidate

        # Universal DevTone fallback
        universal = self.registry.get("dev-tone-neutral")
        if universal and universal.is_available:
            return universal

        # 5. Tier 5: Fail-closed
        raise UnsupportedLanguageError(
            f"No voice available for language '{target_language}' under active constraints (offline={is_offline})."
        )

