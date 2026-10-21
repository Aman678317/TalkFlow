"""Optional Azure Speech recognize-once adapter for raw PCM16 utterances."""
from __future__ import annotations

import asyncio
from typing import Any

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import ProviderUnavailable, TranscriptChunk

_LOCALES = {
    "ar": "ar-SA", "bn": "bn-IN", "de": "de-DE", "en": "en-US", "es": "es-ES",
    "fr": "fr-FR", "gu": "gu-IN", "hi": "hi-IN", "it": "it-IT", "ja": "ja-JP",
    "kn": "kn-IN", "ko": "ko-KR", "ml": "ml-IN", "mr": "mr-IN", "nl": "nl-NL",
    "pa": "pa-IN", "pl": "pl-PL", "pt": "pt-BR", "ru": "ru-RU", "ta": "ta-IN",
    "te": "te-IN", "tr": "tr-TR", "ur": "ur-PK", "zh": "zh-CN",
}

_DEFAULT_AUTO_DETECT = (
    "en-US", "hi-IN", "bn-IN", "mr-IN", "ta-IN", "te-IN", "gu-IN",
    "kn-IN", "ml-IN", "pa-IN", "ur-PK", "zh-CN",
)


def _locale(value: str | None, default: str) -> str:
    value = (value or "").strip().replace("_", "-")
    if not value or value.lower() == "auto":
        return ""
    return _LOCALES.get(value.lower(), value if "-" in value else default)


@register("stt", "azure_speech")
@register("stt", "azure_stt")
@register("stt", "azure_speech_stt")
class AzureSpeechSttProvider(BaseProvider):
    name = "azure_speech"
    task = "stt"
    private = False
    quality_tier = 90
    cost_tier = 75
    latency_class = "realtime"

    def __init__(self, key: str = "", region: str = "", default_language: str = "en-US",
                 auto_detect_languages: str | list[str] | tuple[str, ...] = (),
                 subscription_key: str | None = None, api_key: str | None = None,
                 timeout_s: float = 30.0) -> None:
        supplied_key = subscription_key if subscription_key is not None else api_key
        self.key = (supplied_key if supplied_key is not None else key).strip()
        self.region = region.strip()
        self.default_language = default_language.strip() or "en-US"
        if isinstance(auto_detect_languages, str):
            auto_detect_languages = tuple(
                item.strip() for item in auto_detect_languages.split(",") if item.strip()
            )
        self.auto_detect_languages = tuple(auto_detect_languages) or _DEFAULT_AUTO_DETECT
        self.timeout_s = timeout_s

    def _unavailable(self) -> ProviderUnavailable | None:
        if not self.key:
            return ProviderUnavailable("AZURE_SPEECH_KEY not configured")
        if not self.region:
            return ProviderUnavailable("AZURE_SPEECH_REGION not configured")
        try:
            import azure.cognitiveservices.speech  # noqa: F401
        except ImportError as exc:
            error = ProviderUnavailable(
                "Azure Speech STT requires `pip install azure-cognitiveservices-speech`"
            )
            error.__cause__ = exc
            return error
        return None

    async def healthcheck(self) -> bool:
        return self._unavailable() is None

    @staticmethod
    def _recognize_sync(speechsdk: Any, audio: bytes, sample_rate: int,
                       locale: str, auto_detect_languages: tuple[str, ...],
                       key: str, region: str) -> tuple[str, str | None]:
        config = speechsdk.SpeechConfig(subscription=key, region=region)
        stream_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=sample_rate, bits_per_sample=16, channels=1)
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=stream_format)
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        if locale:
            config.speech_recognition_language = locale
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=config, audio_config=audio_config)
        else:
            auto_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(
                languages=list(auto_detect_languages))
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=config, audio_config=audio_config,
                auto_detect_source_language_config=auto_config)
        push_stream.write(audio)
        push_stream.close()
        result = recognizer.recognize_once()
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            detected = None
            if not locale:
                try:
                    detected = result.properties.get(
                        speechsdk.PropertyId.SpeechServiceConnection_AutoDetectSourceLanguageResult)
                except (AttributeError, KeyError):
                    detected = None
            return result.text or "", detected
        if result.reason == speechsdk.ResultReason.NoMatch:
            return "", None
        if result.reason == speechsdk.ResultReason.Canceled:
            details = getattr(result, "cancellation_details", None)
            detail = getattr(details, "error_details", None) or getattr(details, "reason", None)
            raise ProviderUnavailable(f"Azure Speech recognition canceled{': ' + str(detail) if detail else ''}")
        raise ProviderUnavailable(f"Azure Speech recognition returned {result.reason!s}")

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None) -> TranscriptChunk:
        unavailable = self._unavailable()
        if unavailable is not None:
            raise unavailable
        if sample_rate <= 0 or len(audio) % 2:
            raise ProviderUnavailable("Azure Speech STT requires valid raw PCM16 audio")
        import azure.cognitiveservices.speech as speechsdk
        locale = _locale(lang_hint, self.default_language)
        try:
            text = await asyncio.wait_for(asyncio.to_thread(
                self._recognize_sync, speechsdk, audio, sample_rate, locale, self.key, self.region),
                timeout=self.timeout_s)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable(f"Azure Speech STT failed: {exc}") from exc
        text, detected_locale = text
        resolved_locale = detected_locale or locale or self.default_language
        language = (lang_hint or resolved_locale).replace("_", "-").split("-", 1)[0].lower()
        return TranscriptChunk(text=text.strip(), language=language, is_final=True,
                               model="azure-speech-recognize-once", provider=self.name)
