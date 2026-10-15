"""Contract tests for the optional Azure realtime provider adapters.

These tests never call Azure. They prove that credentials stay server-side,
request shapes match the documented APIs, and provider failures are explicit.
"""
from __future__ import annotations

import io
import sys
import types
import wave

import pytest

from gt_ai.stt.azure_speech import AzureSpeechSttProvider
from gt_ai.translation.azure_translator import AzureTranslatorProvider
from gt_ai.tts.azure_speech import AzureSpeechTtsProvider
from gt_ai.types import ProviderUnavailable, TranslationRequest


class _Response:
    def __init__(self, *, payload=None, content: bytes = b"") -> None:
        self._payload = payload
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, response: _Response, calls: list[dict]) -> None:
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.response


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24_000)
        out.writeframes(b"\0\0" * 240)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_cloud_adapters_fail_closed_without_credentials():
    stt = AzureSpeechSttProvider()
    mt = AzureTranslatorProvider()
    tts = AzureSpeechTtsProvider()

    assert await stt.healthcheck() is False
    assert await mt.healthcheck() is False
    assert await tts.healthcheck() is False
    with pytest.raises(ProviderUnavailable, match="AZURE_SPEECH_KEY"):
        await stt.transcribe(b"\0\0" * 800, 16_000)
    with pytest.raises(ProviderUnavailable, match="AZURE_TRANSLATOR_KEY"):
        await mt.translate(TranslationRequest("hello", "en", "hi"))
    with pytest.raises(ProviderUnavailable, match="AZURE_SPEECH_KEY"):
        await tts.synthesize("hello", "en")


@pytest.mark.asyncio
async def test_azure_translator_sends_server_side_headers_and_detects_auto_language(monkeypatch):
    calls: list[dict] = []
    response = _Response(payload=[{
        "detectedLanguage": {"language": "hi", "score": 0.99},
        "translations": [{"text": "Hello", "to": "en"}],
    }])
    monkeypatch.setattr(
        "gt_ai.translation.azure_translator.httpx.AsyncClient",
        lambda **_kwargs: _Client(response, calls),
    )
    provider = AzureTranslatorProvider(key="server-secret", region="centralindia")

    result = await provider.translate(TranslationRequest("नमस्ते", "auto", "en"))

    assert result.text == "Hello"
    assert result.source_lang == "hi"
    assert calls[0]["headers"]["Ocp-Apim-Subscription-Key"] == "server-secret"
    assert calls[0]["headers"]["Ocp-Apim-Subscription-Region"] == "centralindia"
    assert "from" not in calls[0]["params"]
    assert calls[0]["json"] == [{"text": "नमस्ते"}]


@pytest.mark.asyncio
async def test_azure_translator_maps_simplified_chinese_and_streams_one_final_result(monkeypatch):
    calls: list[dict] = []
    response = _Response(payload=[{"translations": [{"text": "你好", "to": "zh-Hans"}]}])
    monkeypatch.setattr(
        "gt_ai.translation.azure_translator.httpx.AsyncClient",
        lambda **_kwargs: _Client(response, calls),
    )
    provider = AzureTranslatorProvider(key="key", region="eastus")
    request = TranslationRequest("hello", "en", "zh")

    streamed = [chunk async for chunk in provider.translate_stream(request)]

    assert streamed == ["你好"]
    assert calls[0]["params"]["to"] == "zh-Hans"
    assert calls[0]["params"]["from"] == "en"


@pytest.mark.asyncio
async def test_azure_tts_escapes_ssml_and_returns_wav(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        "gt_ai.tts.azure_speech.httpx.AsyncClient",
        lambda **_kwargs: _Client(_Response(content=_wav()), calls),
    )
    provider = AzureSpeechTtsProvider(
        key="server-secret", region="eastus", voice_map="hi=hi-IN-SwaraNeural",
    )

    chunk = await provider.synthesize("a < b & c", "hi")

    assert chunk.data[:4] == b"RIFF"
    assert chunk.sample_rate == 24_000
    assert chunk.provider == "azure_speech_tts"
    assert "a &lt; b &amp; c" in calls[0]["content"].decode()
    assert "hi-IN-SwaraNeural" in calls[0]["content"].decode()
    assert calls[0]["headers"]["X-Microsoft-OutputFormat"] == "riff-24khz-16bit-mono-pcm"


@pytest.mark.asyncio
async def test_azure_tts_does_not_silently_use_an_english_voice_for_unknown_language():
    provider = AzureSpeechTtsProvider(key="key", region="eastus")

    with pytest.raises(ProviderUnavailable, match="no Azure Speech voice"):
        await provider.synthesize("こんにちは", "ja")


@pytest.mark.asyncio
async def test_azure_stt_auto_detects_from_candidate_languages(monkeypatch):
    class _Reason:
        RecognizedSpeech = "recognized"
        NoMatch = "no-match"
        Canceled = "canceled"

    class _Format:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _PushStream:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.audio = b""

        def write(self, audio):
            self.audio += audio

        def close(self):
            return None

    class _AudioConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _SpeechConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _AutoConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    result = types.SimpleNamespace(
        reason=_Reason.RecognizedSpeech,
        text="नमस्ते",
        properties={"source-language": "hi-IN"},
    )
    holder: dict[str, object] = {}

    class _Recognizer:
        def __init__(self, **kwargs):
            holder["kwargs"] = kwargs

        def recognize_once(self):
            return result

    speech = types.ModuleType("azure.cognitiveservices.speech")
    speech.SpeechConfig = _SpeechConfig
    speech.SpeechRecognizer = _Recognizer
    speech.ResultReason = _Reason
    speech.PropertyId = types.SimpleNamespace(
        SpeechServiceConnection_AutoDetectSourceLanguageResult="source-language",
    )
    speech.audio = types.SimpleNamespace(
        AudioStreamFormat=_Format,
        PushAudioInputStream=_PushStream,
        AudioConfig=_AudioConfig,
    )
    speech.languageconfig = types.SimpleNamespace(
        AutoDetectSourceLanguageConfig=_AutoConfig,
    )
    azure = types.ModuleType("azure")
    cognitiveservices = types.ModuleType("azure.cognitiveservices")
    azure.cognitiveservices = cognitiveservices
    cognitiveservices.speech = speech
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.cognitiveservices", cognitiveservices)
    monkeypatch.setitem(sys.modules, "azure.cognitiveservices.speech", speech)

    provider = AzureSpeechSttProvider(key="key", region="eastus")
    chunk = await provider.transcribe(b"\0\0" * 800, 16_000, lang_hint="auto")

    assert chunk.text == "नमस्ते"
    assert chunk.language == "hi"
    recognizer_kwargs = holder["kwargs"]
    assert "auto_detect_source_language_config" in recognizer_kwargs
    assert recognizer_kwargs["auto_detect_source_language_config"].kwargs["languages"]
