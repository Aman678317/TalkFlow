import pytest
from app.routers.translate import voice_tts, VoiceTtsRequest

@pytest.mark.asyncio
async def test_voice_tts_direct_synthesis():
    # 1. English synthesis
    res = await voice_tts(VoiceTtsRequest(text="Hello world", language="en"))
    assert res.audio_base64 != ""
    assert res.format in ("mp3", "wav")

    # 2. Hindi synthesis
    res_hi = await voice_tts(VoiceTtsRequest(text="नमस्ते दुनिया", language="hi"))
    assert res_hi.audio_base64 != ""
    assert res_hi.format in ("mp3", "wav")

    # 3. German synthesis
    res_de = await voice_tts(VoiceTtsRequest(text="Hallo Welt", language="de"))
    assert res_de.audio_base64 != ""
    assert res_de.format in ("mp3", "wav")

    # 4. Empty text handling
    res_empty = await voice_tts(VoiceTtsRequest(text="", language="en"))
    assert res_empty.audio_base64 == ""

