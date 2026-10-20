"""BidirectionalBridge §306 seat routing — deterministic tests, no carriers.

Zero telephony bridge tests existed before this suite (plan §31). These pin:

- the legacy two-leg behavior is byte-identical when no extra legs are given
  (audio goes only to `receiver`/`caller` via the per-sentence path);
- extra caption seats join through ``TranslationFanOut``: one provider call
  per distinct extra-language, canonical text only, honest per-seat failure,
  `original`-mode seats silent;
- captions are routed as ``call.caption_delivered`` WS events and, when a
  sink is wired, as best-effort `bridge_caption_delivered` ledger rows;
- a fan-out failure NEVER breaks the primary two-leg audio path (plan §7).
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from app.realtime.translation_fanout import TranslationFanOut
from app.telephony.bidirectional_bridge import (
    BidirectionalTranslationBridge,
    BridgeLegSpec,
)


# --------------------------------------------------------------------------- #
# fakes for the app.ai surface the bridge touches
# --------------------------------------------------------------------------- #


class _Chunk:
    def __init__(self, text: str, language: str, confidence: float = 0.97):
        self.text = text
        self.language = language
        self.confidence = confidence


class _GTResult:
    def __init__(self, text: str, target_lang: str):
        self.text = text
        self.source_lang = "hi"
        self.target_lang = target_lang
        self.provider = "simulated"
        self.model = "bridge-fake"


class _AudioChunk:
    def __init__(self) -> None:
        self.data = b"\x01\x02" * 40
        self.sample_rate = 16000


class FakeAI:
    """Stand-in for the ``app.ai`` module surface used by the bridge."""

    def __init__(self, fail_langs: set[str] | None = None) -> None:
        self.translate_calls: list[tuple[str, str, str]] = []  # src,tgt,text
        self.tts_legs: list[tuple[str, str]] = []             # (leg, text)
        self.fail_langs = fail_langs or set()
        #: language the fake STT reports for recognized speech (default hi)
        self.stt_lang = "hi"

    async def transcribe(self, audio: bytes, rate: int, lang_hint=None):
        return _Chunk("hello there everyone", self.stt_lang), None

    async def detect_language(self, text: str):
        class _Det:  # only reached on 'auto' hints — tested path avoids it
            language = "hi"
        return _Det()

    async def translate(self, req, *_a, **_kw):
        self.translate_calls.append(
            (req.source_lang, req.target_lang, req.text))
        if req.target_lang in self.fail_langs:
            raise RuntimeError(f"provider down for {req.target_lang}")
        return (_GTResult(f"{req.target_lang}: {req.text}",
                          req.target_lang), None)

    async def synthesize_stream(self, text: str, lang: str):
        async def _stream():
            await asyncio.sleep(0)
            yield _AudioChunk()
        return _stream(), None


@pytest.fixture
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> FakeAI:
    import app.telephony.bidirectional_bridge as bb

    fake = FakeAI()
    monkeypatch.setattr(bb.ai, "transcribe", fake.transcribe)
    monkeypatch.setattr(bb.ai, "translate", fake.translate)
    monkeypatch.setattr(bb.ai, "synthesize_stream", fake.synthesize_stream)
    monkeypatch.setattr(bb.ai, "detect_language", fake.detect_language)
    return fake


class RecordingSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event_type: str, payload: dict[str, Any]) -> None:
        self.rows.append((event_type, dict(payload)))


def make_bridge(fake_ai: FakeAI, *, extra_legs=None, sink=None,
                mode: str = "human_to_human", caller_lang: str = "hi",
                receiver_lang: str = "ja") -> tuple[Any, list, list]:
    events: list[tuple[str, dict[str, Any]]] = []
    audio: list[tuple[str, bytes]] = []

    async def on_event(event_type: str, data: dict[str, Any]) -> None:
        events.append((event_type, dict(data)))

    async def on_audio_out(leg: str, pcm: bytes) -> None:
        audio.append((leg, bytes(pcm)))

    bridge = BidirectionalTranslationBridge(
        uuid.uuid4(), caller_language=caller_lang,
        receiver_language=receiver_lang,
        mode=mode, on_event=on_event, on_audio_out=on_audio_out,
        extra_legs=extra_legs, caption_sink=sink,
    )
    bridge.is_running = True
    return bridge, events, audio


async def run_caller_turn(bridge: Any) -> None:
    bridge.caller_state.audio_buffer.extend(b"\x00\x01" * 1000)  # >50ms
    await bridge._process_speech_turn(
        bridge.caller_state, bridge.receiver_state, "A->B", force=True)


# --------------------------------------------------------------------------- #
# routing-table validation
# --------------------------------------------------------------------------- #


def test_extra_leg_cannot_shadow_primary_names(fake_ai: FakeAI):
    with pytest.raises(ValueError):
        BidirectionalTranslationBridge(
            uuid.uuid4(), extra_legs=[BridgeLegSpec("caller", "hi")])
    with pytest.raises(ValueError):
        BidirectionalTranslationBridge(
            uuid.uuid4(), extra_legs=[BridgeLegSpec("receiver", "ja")])


def test_bridge_leg_spec_rejects_unknown_mode():
    with pytest.raises(ValueError):
        BridgeLegSpec("obs", "ja", mode="listen_only")


def test_duplicate_extra_leg_name_rejected(fake_ai: FakeAI):
    extra = BridgeLegSpec("dup", "ja")
    with pytest.raises(ValueError):
        BidirectionalTranslationBridge(
            uuid.uuid4(), extra_legs=[extra, extra])


# --------------------------------------------------------------------------- #
# two-leg baseline: unchanged when no extra legs
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_no_extra_legs_no_fanout_calls_and_audio_only_primary(fake_ai: FakeAI):
    bridge, events, audio = make_bridge(fake_ai)

    await run_caller_turn(bridge)

    targets = {t for _s, t, _x in fake_ai.translate_calls}
    assert "ja" in targets                      # per-sentence audio path intact
    assert all(leg == "receiver" for leg, _p in audio)
    assert [e for e, _d in events if e == "call.caption_delivered"] == []
    translation_events = [d for e, d in events if e == "call.translation_final"]
    assert translation_events[0]["target_lang"] == "ja"


# --------------------------------------------------------------------------- #
# §306: extra caption seats via the fan-out core
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_extra_leg_receives_caption_from_canonical_turn(fake_ai: FakeAI):
    fake = fake_ai
    extra = BridgeLegSpec("obs-ja", "ja")
    bridge, events, audio = make_bridge(fake_ai, extra_legs=[extra])

    # count FAN-OUT seam invocations separately from the legacy per-sentence
    # audio path (cross-path dedupe moves the primary legs onto the router in
    # a later slice — the B1 guarantee holds within the fan-out itself)
    fanout_calls: list[tuple[str, str, str]] = []
    original_adapter = bridge._fanout_translate

    async def counting(text: str, src: str, tgt: str, **kw):
        fanout_calls.append((src, tgt, text))
        assert kw.get("speaker_id") == "caller"
        return await original_adapter(text, src, tgt, **kw)

    bridge._fanout = TranslationFanOut(counting)

    await run_caller_turn(bridge)

    delivered = [d for e, d in events if e == "call.caption_delivered"]
    assert len(delivered) == 1
    cap = delivered[0]
    assert cap["seat"] == "obs-ja"
    assert cap["lang"] == "ja"
    assert cap["origin"] == "translated"
    assert cap["audio"] is False                 # honest: no carrier media yet
    assert cap["provider"] == "simulated"
    assert cap["text"].startswith("ja: ")

    # exactly ONE fan-out provider request for this distinct target
    assert fanout_calls == [("hi", "ja", "hello there everyone")]

    # legacy per-sentence path still streams TTS audio to the receiver leg only
    assert audio and all(leg == "receiver" for leg, _p in audio)
    assert fake.translate_calls[-1][0] == "hi"


@pytest.mark.asyncio
async def test_one_provider_call_per_distinct_extra_target(fake_ai: FakeAI):
    extra = [
        BridgeLegSpec("obs-de", "de"),
        BridgeLegSpec("obs-fr", "fr"),
    ]
    bridge, events, _audio = make_bridge(fake_ai, extra_legs=extra)

    await run_caller_turn(bridge)

    for lang in ("de", "fr"):
        calls = [(s, t, x) for s, t, x in fake_ai.translate_calls if t == lang]
        assert len(calls) == 1, f"expected ONE {lang} call, got {len(calls)}"
        assert calls[0][2] == "hello there everyone"   # canonical, not partial

    seats = [d["seat"] for e, d in events if e == "call.caption_delivered"]
    assert seats == ["obs-de", "obs-fr"]


@pytest.mark.asyncio
async def test_original_mode_extra_leg_gets_nothing(fake_ai: FakeAI):
    extra = [
        BridgeLegSpec("obs-raw", "ja", mode="original"),
        BridgeLegSpec("obs-ja", "ja", mode="translated"),
    ]
    bridge, events, _audio = make_bridge(fake_ai, extra_legs=extra)

    await run_caller_turn(bridge)

    delivered = [d for e, d in events if e == "call.caption_delivered"]
    assert [d["seat"] for d in delivered] == ["obs-ja"]


@pytest.mark.asyncio
async def test_failed_extra_target_is_honest_and_isolated(fake_ai: FakeAI):
    extra = [
        BridgeLegSpec("obs-ja", "ja"),
        BridgeLegSpec("obs-de", "de"),
    ]
    bridge, events, audio = make_bridge(fake_ai, extra_legs=extra)

    # only the fan-out translate for 'de' fails
    original_translate = fake_ai.translate

    async def failing_translate(req, *a, **kw):
        if req.target_lang == "de" and req.text == "hello there everyone":
            raise RuntimeError("provider down for de")
        return await original_translate(req, *a, **kw)

    import app.telephony.bidirectional_bridge as bb
    bb.ai.translate = failing_translate

    await run_caller_turn(bridge)

    delivered = [d for e, d in events if e == "call.caption_delivered"]
    assert [d["seat"] for d in delivered] == ["obs-ja"]    # ja unaffected

    unavailable = [d for e, d in events if e == "call.caption_unavailable"]
    assert len(unavailable) == 1
    assert unavailable[0]["seat"] == "obs-de"
    assert unavailable[0]["target_lang"] == "de"
    assert unavailable[0]["call_unaffected"] is True

    # primary audio path fully intact
    assert audio and all(leg == "receiver" for leg, _p in audio)


@pytest.mark.asyncio
async def test_caption_sink_persists_ledger_rows(fake_ai: FakeAI):
    sink = RecordingSink()
    extra = BridgeLegSpec("obs-ja", "ja")
    bridge, _events, _audio = make_bridge(
        fake_ai, extra_legs=[extra], sink=sink)

    await run_caller_turn(bridge)

    assert len(sink.rows) == 1
    event_type, payload = sink.rows[0]
    assert event_type == "bridge_caption_delivered"
    assert payload["seat"] == "obs-ja"
    assert payload["origin"] == "translated"
    assert payload["audio"] is False


@pytest.mark.asyncio
async def test_ai_agent_mode_skips_extra_leg_fanout(fake_ai: FakeAI):
    """Agent replies route to the caller; extra-leg fan-out stays out of the
    way until agent-speech routing is wired (documented next slice)."""
    extra = BridgeLegSpec("obs-ja", "ja")
    bridge, events, _audio = make_bridge(
        fake_ai, extra_legs=[extra], mode="ai_agent")

    await run_caller_turn(bridge)

    delivered = [d for e, d in events if e == "call.caption_delivered"]
    assert delivered == []


# --------------------------------------------------------------------------- #
# §306 close-out: 3-way golden routing + mid-call mode switch
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_three_way_en_speaker_routes_hi_and_ja_off_one_canonical_segment(
        fake_ai: FakeAI):
    """EN speaker → HI + JA seats: both serviced from ONE canonical turn."""
    extra = [
        BridgeLegSpec("seat-hi", "hi"),
        BridgeLegSpec("seat-ja", "ja"),
    ]
    fake_ai.stt_lang = "en"
    bridge, events, audio = make_bridge(
        fake_ai, extra_legs=extra, caller_lang="en", receiver_lang="en")

    await run_caller_turn(bridge)

    delivered = [d for e, d in events if e == "call.caption_delivered"]
    assert [(d["seat"], d["lang"]) for d in delivered] == [
        ("seat-hi", "hi"), ("seat-ja", "ja")]
    assert all(d["origin"] == "translated" for d in delivered)
    assert all("hello there everyone" in d["text"] for d in delivered)

    # one provider request per distinct target, fingerprinted by the seam
    fanout_targets = [(s, t) for s, t, x in fake_ai.translate_calls
                      if t in ("hi", "ja") and x == "hello there everyone"]
    assert sorted(fanout_targets) == [("en", "hi"), ("en", "ja")]

    # the receiver hears the primary audio path (receiver lang == en here, so
    # the per-sentence path still streams; extras stay caption-only)
    assert audio and all(leg == "receiver" for leg, _p in audio)


@pytest.mark.asyncio
async def test_mid_call_mode_switch_flips_seat_routing(fake_ai: FakeAI):
    """A seat flips original→translated→original across turns, live."""
    extra = [BridgeLegSpec("seat-ja", "ja", mode="original")]
    bridge, events, _audio = make_bridge(fake_ai, extra_legs=extra)

    # turn 1: original mode ⇒ silent
    await run_caller_turn(bridge)
    turn1 = [d for e, d in events if e == "call.caption_delivered"]
    assert turn1 == []

    # switch mid-call …
    bridge.set_leg_mode("seat-ja", "translated")

    # turn 2: translated ⇒ caption delivered
    await run_caller_turn(bridge)
    turn2 = [d for e, d in events if e == "call.caption_delivered"]
    assert [(d["seat"], d["lang"], d["origin"]) for d in turn2] == [
        ("seat-ja", "ja", "translated")]

    # … and back mid-call
    bridge.set_leg_mode("seat-ja", "original")

    # turn 3: silent again
    before = len(turn2)
    await run_caller_turn(bridge)
    now = [d for e, d in events if e == "call.caption_delivered"]
    assert len(now) == before


def test_set_leg_mode_rejects_unknown_legs_and_modes(fake_ai: FakeAI):
    bridge, _events, _audio = make_bridge(fake_ai)

    with pytest.raises(KeyError):
        bridge.set_leg_mode("ghost", "translated")
    with pytest.raises(ValueError):
        bridge.set_leg_mode("receiver", "auto")
    with pytest.raises(ValueError):
        bridge.set_leg_mode("caller", "listen_only")


def test_set_leg_mode_keeps_registry_coherent(fake_ai: FakeAI):
    extra = BridgeLegSpec("seat-ja", "ja", mode="original")
    bridge, _events, _audio = make_bridge(fake_ai, extra_legs=[extra])

    bridge.set_leg_mode("seat-ja", "translated")

    assert bridge.extra_legs[0].mode == "translated"
    assert bridge._legs["seat-ja"].mode == "translated"
    assert bridge._legs["seat-ja"].hear_lang == "ja"   # language preserved
