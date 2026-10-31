"""Unit tests for Voice Selector and 5-Tier Fallback."""
import pytest
from app.core.exceptions import UnsupportedLanguageError, VoiceUnavailableError
from app.voices.consent_manager import VoiceConsentManager
from app.voices.registry import VoiceRegistry
from app.voices.selector import VoiceSelector


def test_voice_selector_auto_language_matching():
    reg = VoiceRegistry()
    cst = VoiceConsentManager()
    selector = VoiceSelector(registry=reg, consent_manager=cst)

    # Hindi should match a Hindi voice, NOT English
    hi_voice = selector.select_voice(target_language="hi")
    assert hi_voice is not None
    assert hi_voice.language in ("hi", "*")

    # Marathi should match a Marathi voice
    mr_voice = selector.select_voice(target_language="mr")
    assert mr_voice is not None
    assert mr_voice.language in ("mr", "*")

    # English should match English voice
    en_voice = selector.select_voice(target_language="en")
    assert en_voice is not None
    assert en_voice.language in ("en", "*")


def test_voice_selector_rejects_cross_language_substitution():
    reg = VoiceRegistry()
    cst = VoiceConsentManager()
    selector = VoiceSelector(registry=reg, consent_manager=cst)

    # Requesting English voice for Hindi text must raise VoiceUnavailableError
    with pytest.raises(VoiceUnavailableError) as exc_info:
        selector.select_voice(target_language="hi", preferred_voice_id="system-david")
    assert "cross-language silent substitution is prohibited" in str(exc_info.value).lower()


def test_voice_selector_unsupported_language():
    reg = VoiceRegistry()
    cst = VoiceConsentManager()
    selector = VoiceSelector(registry=reg, consent_manager=cst)

    with pytest.raises(UnsupportedLanguageError):
        selector.select_voice(target_language="xyz_invalid")

