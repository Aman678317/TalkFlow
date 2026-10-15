"""Azure Speech REST TTS adapter returning 24 kHz mono PCM WAV."""
from __future__ import annotations

import html
import io
import wave
from collections.abc import AsyncIterator

import httpx

from gt_ai.base import BaseProvider
from gt_ai.registry import register
from gt_ai.types import AudioChunk, ProviderUnavailable


_LOCALES = {
    "ar": "ar-SA", "bn": "bn-IN", "de": "de-DE", "en": "en-US", "es": "es-ES",
    "fr": "fr-FR", "gu": "gu-IN", "hi": "hi-IN", "it": "it-IT", "ja": "ja-JP",
    "kn": "kn-IN", "ko": "ko-KR", "ml": "ml-IN", "mr": "mr-IN", "nl": "nl-NL",
    "pa": "pa-IN", "pl": "pl-PL", "pt": "pt-BR", "ru": "ru-RU", "ta": "ta-IN",
    "te": "te-IN", "tr": "tr-TR", "ur": "ur-PK", "zh": "zh-CN",
}
_DEFAULT_VOICES = {
    "en": "en-US-JennyNeural", "hi": "hi-IN-SwaraNeural", "mr": "mr-IN-AarohiNeural",
    "bn": "bn-IN-TanishaaNeural", "ta": "ta-IN-PallaviNeural", "te": "te-IN-ShrutiNeural",
    "ur": "ur-PK-UzmaNeural",
}


def _locale(lang: str) -> str:
    value = (lang or "").strip().replace("_", "-")
    return _LOCALES.get(value.lower(), value if "-" in value else _LOCALES.get(value.lower(), "en-US"))


def _parse_voice_map(raw: str | dict[str, str] | None) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k).strip().lower(): str(v).strip() for k, v in raw.items() if str(k).strip() and str(v).strip()}
    result: dict[str, str] = {}
    for part in (raw or "").split(","):
        lang, sep, voice = part.partition("=")
        if sep and lang.strip() and voice.strip():
            result[lang.strip().lower()] = voice.strip()
    return result


@register("tts", "azure_speech_tts")
@register("tts", "azure_tts")
@register("tts", "azure_speech")
class AzureSpeechTtsProvider(BaseProvider):
    name = "azure_speech_tts"
    task = "tts"
    private = False
    quality_tier = 90
    cost_tier = 75
    latency_class = "fast"

    def __init__(self, key: str = "", region: str = "", voice_map: str | dict[str, str] | None = None,
                 endpoint: str = "", subscription_key: str | None = None,
                 timeout_s: float = 30.0, api_key: str | None = None) -> None:
        supplied_key = subscription_key if subscription_key is not None else api_key
        self.key = (supplied_key if supplied_key is not None else key).strip()
        self.region = region.strip()
        self.endpoint = endpoint.strip().rstrip("/")
        self.voice_map = _parse_voice_map(voice_map)
        self.timeout_s = timeout_s

    def _unavailable(self) -> ProviderUnavailable | None:
        if not self.key:
            return ProviderUnavailable("AZURE_SPEECH_KEY not configured")
        if not self.region:
            return ProviderUnavailable("AZURE_SPEECH_REGION not configured")
        return None

    def _voice(self, lang: str, requested: str | None) -> str:
        if requested and requested.strip():
            return requested.strip()
        code = (lang or "").strip().replace("_", "-").split("-", 1)[0].lower()
        voice = self.voice_map.get(lang.lower()) or self.voice_map.get(code) or _DEFAULT_VOICES.get(code)
        if not voice:
            raise ProviderUnavailable(f"no Azure Speech voice configured for lang={lang}")
        return voice

    async def healthcheck(self) -> bool:
        return self._unavailable() is None

    async def synthesize(self, text: str, lang: str, voice: str | None = None) -> AudioChunk:
        unavailable = self._unavailable()
        if unavailable is not None:
            raise unavailable
        if not text.strip():
            raise ProviderUnavailable("Azure Speech TTS received empty text")
        selected_voice = self._voice(lang, voice)
        locale = _locale(lang)
        endpoint = self.endpoint or f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = (
            f"<speak version='1.0' xml:lang='{html.escape(locale, quote=True)}'>"
            f"<voice name='{html.escape(selected_voice, quote=True)}' "
            f"xml:lang='{html.escape(locale, quote=True)}'>{html.escape(text)}</voice></speak>"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
            "User-Agent": "TalkFlow/azure-speech-tts",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(endpoint, content=ssml.encode("utf-8"), headers=headers)
                response.raise_for_status()
                data = response.content
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Azure Speech TTS failed: {exc}") from exc
        if not data:
            raise ProviderUnavailable("Azure Speech TTS returned empty audio")
        sample_rate = 24000
        frames = max(0, len(data) - 44) // 2
        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                sample_rate = wav.getframerate() or sample_rate
                frames = wav.getnframes()
        except (wave.Error, EOFError):
            pass
        return AudioChunk(
            data=data, sample_rate=sample_rate, encoding="pcm_s16le", format="wav",
            provider=self.name, model=selected_voice,
            duration_ms=frames / sample_rate * 1000,
        )

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None) -> AsyncIterator[AudioChunk]:
        yield await self.synthesize(text, lang, voice)
