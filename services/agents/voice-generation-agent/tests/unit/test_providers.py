"""Unit tests for DevTone and System TTS providers."""
import pytest
from app.providers.dev_tone_provider import DevToneProvider
from app.providers.system_provider import SystemTTSProvider


@pytest.mark.asyncio
async def test_dev_tone_provider():
    provider = DevToneProvider()
    assert await provider.is_healthy() is True

    res = await provider.synthesize(
        text="Hello TalkFlow audio pipeline test.",
        voice_id="dev-tone-en",
        language="en",
        sample_rate=24000,
    )

    assert res.audio_data.startswith(b"RIFF")
    assert len(res.pcm_data) > 0
    assert res.sample_rate == 24000
    assert res.synthetic is True
    assert res.is_dev is True
    assert res.duration_ms > 0


@pytest.mark.asyncio
async def test_dev_tone_streaming():
    provider = DevToneProvider()
    chunks = []
    async for chunk in provider.synthesize_stream(
        text="First sentence. Second sentence! Third sentence?",
        voice_id="dev-tone-en",
        language="en",
    ):
        chunks.append(chunk)

    assert len(chunks) == 3
    assert chunks[0].chunk_index == 0
    assert chunks[-1].is_last is True


@pytest.mark.asyncio
async def test_system_provider():
    provider = SystemTTSProvider()
    if not (await provider.is_healthy()):
        pytest.skip("System SAPI not available in environment")

    res = await provider.synthesize(
        text="Testing system voice synthesis.",
        voice_id="system-david",
        language="en",
        sample_rate=24000,
    )
    assert len(res.pcm_data) > 0
    assert res.synthetic is True

