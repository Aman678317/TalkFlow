from __future__ import annotations

import io
import wave

import httpx
import pytest

from gt_ai.stt.voicestudio import VoiceStudioSttProvider
from gt_ai.tts.voicestudio import VoiceStudioTtsProvider


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x00" * 240)
    return buf.getvalue()


class _Client:
    def __init__(self, handler, **_kwargs):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **kwargs):
        return self.handler("GET", url, kwargs)

    async def post(self, url, **kwargs):
        return self.handler("POST", url, kwargs)


@pytest.mark.asyncio
async def test_voicestudio_stt_uses_openai_transcription_contract(monkeypatch):
    def handler(method, url, kwargs):
        assert method == "POST"
        assert url.endswith("/v1/audio/transcriptions")
        assert kwargs["data"]["model"] == "whisper-1"
        assert kwargs["data"]["language"] == "hi"
        return httpx.Response(
            200,
            json={"text": "नमस्ते", "language": "hi"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _Client(handler, **kwargs))
    result = await VoiceStudioSttProvider("http://voice", "secret").transcribe(
        b"wav", 16000, "hi")
    assert result.text == "नमस्ते"
    assert result.provider == "voicestudio_stt"


@pytest.mark.asyncio
async def test_voicestudio_tts_requests_wav_and_reads_duration(monkeypatch):
    def handler(method, url, kwargs):
        assert method == "POST"
        assert url.endswith("/v1/audio/speech")
        assert kwargs["json"] == {
            "model": "tts-1", "input": "नमस्ते", "voice": "default",
            "response_format": "wav", "language": "hi",
        }
        return httpx.Response(
            200, content=_wav(), request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _Client(handler, **kwargs))
    result = await VoiceStudioTtsProvider("http://voice").synthesize("नमस्ते", "hi")
    assert result.data.startswith(b"RIFF")
    assert result.sample_rate == 24000
    assert result.provider == "voicestudio_tts"
    assert result.duration_ms > 0
