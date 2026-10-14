"""Phase 3 — each target language must be spoken in a voice of that language.

"benchmark target-language TTS voices" rests on a premise this tree did not
satisfy: the pipeline asked for speech and never named a voice. ``VoiceAgent``
called ``synthesize_stream(text, lang)`` with ``voice=None`` down a chain that
accepted a voice at every hop. Kokoro's default is ``af_heart`` — an English
voice — so a Hindi, Tamil or Portuguese listener heard their own words read by
the same English speaker, and Piper ignored the argument completely.

Covered here: the choice is a setting; that setting reaches the provider through
the real Agent 3; a provider with no instruction picks a voice *for the language
it is speaking* from the voices that actually exist in its manifest; and a voice
that is not installed is reported rather than quietly replaced by another
language's.
"""
from __future__ import annotations

import pytest
from gt_ai.types import AudioChunk, RouteDecision, Task

from app.config import settings
from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import TranslationSegment
from app.realtime.agents.voice import VoiceAgent
from app.realtime.voices import parse_voice_map, voice_for
from gt_ai.tts.kokoro import KokoroProvider
from gt_ai.tts.piper import PiperProvider
from gt_ai.types import ProviderUnavailable

MEETING = "11111111-1111-1111-1111-111111111111"


# --------------------------------------------------------------------------- #
# the setting
# --------------------------------------------------------------------------- #
def test_the_voice_map_is_pairs_not_a_single_default_voice() -> None:
    assert parse_voice_map("hi=hf_alpha, en=af_heart ") == {
        "hi": "hf_alpha", "en": "af_heart"}


def test_an_unparseable_entry_is_dropped_not_fatal() -> None:
    """A typo in one environment variable must not silence the room."""
    got = parse_voice_map("hi=hf_alpha,oops,en=af_heart")
    assert got == {"hi": "hf_alpha", "en": "af_heart"}


@pytest.mark.parametrize("raw,lang,expected", [
    ("", "hi", None),                       # unset: the provider decides
    ("hi=hf_alpha", "hi", "hf_alpha"),
    ("hi=hf_alpha", "en", None),            # unlisted language is not an error
])
def test_voice_for_reads_the_setting_and_inherits_its_changes(
        monkeypatch, raw: str, lang: str, expected: str | None) -> None:
    monkeypatch.setattr(settings, "tts_voice_map", raw, raising=False)
    assert voice_for(lang) == expected


# --------------------------------------------------------------------------- #
# the setting reaches the provider, through the real Agent 3
# --------------------------------------------------------------------------- #
class RecordingTts:
    """Stands in for ``RealtimeTtsProvider`` and keeps what it was asked for."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        self.calls.append((lang, voice))

        async def one_chunk():
            yield AudioChunk(data=b"\x00\x00" * 80, sample_rate=24000,
                             provider="recording", model=f"recording/{voice or 'default'}",
                             duration_ms=20.0)

        return one_chunk(), RouteDecision(provider="recording", model="recording",
                                          task=Task.TTS, reason="test")


def _translation(target: str = "hi") -> TranslationSegment:
    return TranslationSegment(
        correlation_id="corr-1", meeting_id=MEETING, speaker_id="spk-1",
        recipient_id="rec-1", source_segment_id="seg-1", source_language="en",
        target_language=target, translated_text="नमस्ते दोस्तों")


async def _run(agent: VoiceAgent, target: str = "hi") -> int:
    async def deliver(_ready, _audio, _recipients) -> None:
        return None

    return await agent.synthesize(_translation(target), recipients=["rec-1"],
                                  deliver=deliver)


@pytest.mark.asyncio
async def test_the_configured_voice_is_the_one_the_provider_is_asked_for() -> None:
    tts = RecordingTts()
    agent = VoiceAgent(AgentBus(), tts, meeting_id=MEETING,
                       voice_for=lambda lang: "hf_alpha" if lang == "hi" else None)
    assert await _run(agent) == 1
    assert tts.calls == [("hi", "hf_alpha")]


@pytest.mark.asyncio
async def test_no_voice_policy_means_the_provider_default_untouched() -> None:
    """Back-compat: an agent built without a resolver behaves exactly as before."""
    tts = RecordingTts()
    agent = VoiceAgent(AgentBus(), tts, meeting_id=MEETING)
    await _run(agent, target="pt")
    assert tts.calls == [("pt", None)]


@pytest.mark.asyncio
async def test_each_language_of_one_utterance_gets_its_own_voice() -> None:
    """The fan-out is per language; a single global voice would be the old bug
    wearing a new hat."""
    tts = RecordingTts()
    agent = VoiceAgent(AgentBus(), tts, meeting_id=MEETING,
                       voice_for=lambda lang: {"hi": "hf_alpha", "ta": None}[lang])
    for target in ("hi", "ta"):
        await _run(agent, target=target)
    assert tts.calls == [("hi", "hf_alpha"), ("ta", None)]


# --------------------------------------------------------------------------- #
# Piper: an explicit voice is honoured, and a missing one is admitted
# --------------------------------------------------------------------------- #
def test_piper_names_a_default_voice_per_language_it_can_actually_load() -> None:
    """Every name here exists in the upstream ``voices.json``. Tamil, Gujarati and
    Kannada are *absent from that dataset*, so they are absent here — that is a
    finding about the available voices, not an omission to paper over."""
    p = PiperProvider()
    assert p._stem("en", None) == "en_US-lessac-medium"
    assert p._stem("hi", None) == "hi_IN-pratham-medium"
    assert p._stem("mr", None) == "mr_IN-google-medium"
    assert p._stem("ur", None) == "ur_PK-fasih-medium"


def test_piper_refuses_a_language_it_has_no_voice_for_instead_of_guessing() -> None:
    with pytest.raises(ProviderUnavailable, match="no piper voice"):
        PiperProvider()._stem("ta", None)


def test_an_explicit_voice_overrides_the_language_default() -> None:
    assert PiperProvider()._stem("hi", "hi_IN-priyamvada-medium") == "hi_IN-priyamvada-medium"


@pytest.mark.asyncio
async def test_a_voice_that_is_not_installed_is_reported_by_name(tmp_path) -> None:
    """Silent substitution is how a Hindi listener ends up with English audio and
    nobody notices."""
    p = PiperProvider(model_dir=str(tmp_path))
    with pytest.raises(ProviderUnavailable, match="missing_voice"):
        await p._voice("en", "missing_voice")


def test_an_import_failure_is_not_reported_as_a_missing_package(tmp_path, monkeypatch) -> None:
    """Observed on a real machine: piper was installed, onnxruntime could not load
    its native library, and the provider told the operator to `pip install
    piper-tts`. A diagnosis that sends someone to reinstall what they already
    have is worse than no diagnosis."""
    import sys
    import types

    broken = types.ModuleType("piper")

    def _no_attribute(name: str):
        raise ImportError("DLL load failed while importing onnxruntime_pybind11_state")

    broken.__getattr__ = _no_attribute
    monkeypatch.setitem(sys.modules, "piper", broken)
    (tmp_path / "hi_IN-pratham-medium.onnx").write_bytes(b"not really a model")

    with pytest.raises(ProviderUnavailable, match="cannot load"):
        PiperProvider(model_dir=str(tmp_path))._load_voice_sync("hi_IN-pratham-medium")


@pytest.mark.asyncio
async def test_two_voices_of_one_language_are_two_loaded_models(tmp_path) -> None:
    loaded: list[str] = []
    p = PiperProvider(model_dir=str(tmp_path))

    def fake_load(stem: str):
        loaded.append(stem)
        return object()

    p._load_voice_sync = fake_load
    await p._voice("hi", "hi_IN-pratham-medium")
    await p._voice("hi", "hi_IN-priyamvada-medium")
    await p._voice("hi", "hi_IN-pratham-medium")
    assert loaded == ["hi_IN-pratham-medium", "hi_IN-priyamvada-medium"]


# --------------------------------------------------------------------------- #
# Kokoro: with no instruction it still must not speak Hindi in an English voice
# --------------------------------------------------------------------------- #
class FakeManifest:
    """Stands in for the loaded ``kokoro_onnx.Kokoro`` object."""

    def __init__(self, voices, exposes_listing: bool = True) -> None:
        self._voices = voices
        if exposes_listing:
            self.list_voices = lambda: [{"name": v} for v in voices]


def _kokoro(voices: list[str]) -> KokoroProvider:
    k = KokoroProvider()
    k._tts = FakeManifest(voices)
    return k


def test_kokoro_picks_a_voice_that_speaks_the_target_language() -> None:
    k = _kokoro(["af_heart", "am_adam", "hf_alpha", "hm_omega", "zf_xiaoxiao"])
    assert k._default_voice_for("en") == "af_heart"
    assert k._default_voice_for("hi") == "hf_alpha"
    assert k._default_voice_for("zh") == "zf_xiaoxiao"


def test_a_language_kokoro_offers_no_voice_for_keeps_the_configured_default() -> None:
    """No invented voice names: if the manifest does not carry one, the provider
    says so and uses what it was configured with."""
    k = _kokoro(["af_heart", "hf_alpha"])
    assert k._default_voice_for("mr") == "af_heart"
    assert k._default_voice_for("ta") == "af_heart"


def test_a_manifest_without_the_language_is_admitted_in_logs_and_still_works(caplog) -> None:
    k = _kokoro(["af_heart", "bf_emma"])
    with caplog.at_level("WARNING"):
        assert k._default_voice_for("hi") == "af_heart"
    assert "no hi voice" in caplog.text


def test_a_build_that_cannot_list_its_voices_degrades_to_the_default() -> None:
    k = KokoroProvider()
    k._tts = FakeManifest(["hf_alpha"], exposes_listing=False)
    assert k._voice_names() == []
    assert k._default_voice_for("hi") == k.default_voice


@pytest.mark.asyncio
async def test_synthesize_reports_the_voice_it_actually_used() -> None:
    k = _kokoro(["af_heart", "hf_alpha"])
    asked: list[tuple[str, str]] = []

    def fake_synth(text: str, voice: str, lang: str):
        asked.append((voice, lang))
        import numpy as np
        return np.zeros(2400, dtype="float32"), 24000

    k._synth_sync = fake_synth
    chunk = await k.synthesize("नमस्ते", "hi")
    assert asked == [("hf_alpha", "hi")]
    assert chunk.model == "kokoro/hf_alpha"


@pytest.mark.asyncio
async def test_an_explicit_voice_beats_the_language_pick() -> None:
    k = _kokoro(["af_heart", "hf_alpha", "hm_omega"])
    asked: list[str] = []

    def fake_synth(text: str, voice: str, lang: str):
        asked.append(voice)
        import numpy as np
        return np.zeros(240, dtype="float32"), 24000

    k._synth_sync = fake_synth
    await k.synthesize("नमस्ते", "hi", voice="hm_omega")
    assert asked == ["hm_omega"]
