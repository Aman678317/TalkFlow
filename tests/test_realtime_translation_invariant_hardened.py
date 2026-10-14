"""Phase 5: the canonical-source invariant under an upstream outage.

The fan-out mechanics (one call per distinct target, no chaining, stale/barge-in
handling) are pinned elsewhere — see tests/test_realtime_pipeline_hardened.py and
tests/unit/test_realtime_agents_trace.py. What this file pins is the part a real
outage exercises:

  1. A production meeting never receives a synthetic stand-in as a translation.
     The router's implicit failover chain must not end at `dev_echo` /
     `dev_text` / `dev_tone`, and the streaming synthesizer must not fall back to
     a test tone.
  2. An operator who explicitly registers a dev provider still gets it. The gate
     removes a *silent* substitution, not a declared configuration.
  3. When a provider declares that it did not translate
     (`untranslated_fallback`), the realtime stage reports failure instead of
     sending the source text onward wearing the target language's clothes.
  4. Every fan-out translation references the canonical segment id it came from.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from unittest.mock import patch

from app.ai import AIFacade
from app.config import settings
from app.db import models as M
from app.db.session import db_session
from app.realtime import pipeline as pl
from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import Stage, TranscriptSegment
from app.realtime.agents.translation import ProviderTranslation, TranslationAgent
from app.realtime.protocol import ServerEventType
from app.realtime.session_manager import RtParticipant, manager
from app.services.translation_service import TranslateOutput
from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.types import TranslationResult


def _facade(specs: dict) -> AIFacade:
    facade = AIFacade()
    facade.router = ModelRouter(specs, gpu_available=False)
    return facade


def _candidate_names(facade: AIFacade, task) -> list[str]:
    return [d.provider for d in facade._ordered_candidates(task, {})]


# --------------------------------------------------------------------------- #
# 1 + 2. routing under an outage
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("task,stand_in", [
    ("mt", "dev_echo"), ("stt", "dev_text"), ("tts", "dev_tone"),
])
def test_production_failover_never_appends_a_dev_stand_in(monkeypatch, task, stand_in):
    from gt_ai.types import Task
    monkeypatch.setattr(settings, "app_env", "production")
    facade = _facade({Task(task): [
        ProviderSpec(name="real_a", task=Task(task)),
        ProviderSpec(name="real_b", task=Task(task)),
    ]})
    names = _candidate_names(facade, Task(task))
    assert stand_in not in names, f"{stand_in} reached a production candidate list"
    assert "real_a" in names and "real_b" in names, "the real failover chain was cut"


def test_non_production_failover_still_offers_the_dev_stand_in(monkeypatch):
    from gt_ai.types import Task
    monkeypatch.setattr(settings, "app_env", "development")
    facade = _facade({Task.MT: [ProviderSpec(name="real_a", task=Task.MT)]})
    assert "dev_echo" in _candidate_names(facade, Task.MT)


def test_explicitly_registered_dev_provider_still_routes_in_production(monkeypatch):
    """The gate removes a silent substitution, not a declared configuration."""
    from gt_ai.types import Task
    monkeypatch.setattr(settings, "app_env", "production")
    facade = _facade({Task.TTS: [ProviderSpec(name="dev_tone", task=Task.TTS)]})
    assert "dev_tone" in _candidate_names(facade, Task.TTS)


class _DeadTone:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome

    async def healthcheck(self) -> bool:
        return False

    def synthesize_stream(self, text, lang, voice=None):  # noqa: ARG002
        if self.outcome == "raise":
            raise RuntimeError("no voice weights on this image")
        return f"tone:{lang}"


@pytest.mark.asyncio
async def test_streaming_synthesis_does_not_emit_a_test_tone_in_production(monkeypatch):
    from gt_ai.types import Task
    monkeypatch.setattr(settings, "app_env", "production")
    requested: list[str] = []
    facade = _facade({Task.TTS: [ProviderSpec(name="kokoro", task=Task.TTS)]})

    def fake_provider(task, name):  # noqa: ARG001
        requested.append(name)
        return _DeadTone("raise")

    monkeypatch.setattr(facade, "provider", fake_provider)
    with pytest.raises(RuntimeError):
        await facade.synthesize_stream("hello", "de")
    assert "dev_tone" not in requested


@pytest.mark.asyncio
async def test_streaming_synthesis_uses_the_test_tone_outside_production(monkeypatch):
    from gt_ai.types import Task
    monkeypatch.setattr(settings, "app_env", "development")
    requested: list[str] = []
    facade = _facade({Task.TTS: [ProviderSpec(name="kokoro", task=Task.TTS)]})

    def fake_provider(task, name):  # noqa: ARG001
        requested.append(name)
        return _DeadTone("tone")

    monkeypatch.setattr(facade, "provider", fake_provider)
    stream, _decision = await facade.synthesize_stream("hello", "de")
    assert stream == "tone:de"


# --------------------------------------------------------------------------- #
# 3. the translation stage rejects a declared non-translation
# --------------------------------------------------------------------------- #

class _ScriptedTranslator:
    """Returns exactly what a provider would: same words, plus its own flags."""

    def __init__(self, text: str, flags: list[str]) -> None:
        self.text = text
        self.flags = flags
        self.calls = 0

    async def translate(self, text, source_lang, target_lang, context=(), *,  # noqa: ARG002
                        segment_id=None, speaker_id=None):
        self.calls += 1
        return ProviderTranslation(text=self.text, provider="dev_echo",
                                   model="dev-echo-v1", quality_flags=list(self.flags))


def _segment(text: str = "Quarterly revenue grew twelve percent") -> TranscriptSegment:
    return TranscriptSegment(correlation_id="corr-1", meeting_id="m", speaker_id="spk-1",
                             segment_id="seg-1", source_language="en",
                             recognized_text=text, is_final=True)


@pytest.mark.asyncio
async def test_untranslated_echo_fails_instead_of_becoming_a_translation():
    bus = AgentBus()
    agent = TranslationAgent(bus, _ScriptedTranslator(
        "Quarterly revenue grew twelve percent", ["untranslated_fallback", "dev_provider"]),
        meeting_id="m")
    with pytest.raises(ValueError):
        await agent.translate_one(_segment(), "de", ["rec-1"])
    types = [e.type for e in bus.trace]
    assert Stage.STAGE_FAILED in types
    assert Stage.TRANSLATION_READY not in types
    failure = next(e for e in bus.trace if e.type == Stage.STAGE_FAILED)
    assert failure.payload["reason"] == "untranslated_output"
    assert failure.payload["target_language"] == "de"
    await bus.close()


@pytest.mark.asyncio
async def test_empty_translation_still_fails():
    bus = AgentBus()
    agent = TranslationAgent(bus, _ScriptedTranslator("   ", ["empty_translation"]),
                             meeting_id="m")
    with pytest.raises(ValueError):
        await agent.translate_one(_segment(), "de", ["rec-1"])
    assert [e.type for e in bus.trace] == [Stage.STAGE_FAILED]
    await bus.close()


@pytest.mark.asyncio
async def test_a_flagged_dev_standin_that_actually_translated_is_still_delivered():
    """`dev_provider` alone means "synthetic engine", not "no translation" — the
    stand-in keeps working for local QA as long as it changed the words."""
    bus = AgentBus()
    agent = TranslationAgent(bus, _ScriptedTranslator(
        "[de] Umsatz wuchs", ["neural_mt", "dev_provider"]), meeting_id="m")
    done = await agent.translate_one(_segment(), "de", ["rec-1"])
    assert done.translated_text == "[de] Umsatz wuchs"
    assert done.source_segment_id == "seg-1"
    assert [e.type for e in bus.trace] == [Stage.TRANSLATION_READY]
    await bus.close()


# --------------------------------------------------------------------------- #
# 3 + 4. the same rules on the wire, through the deployed pipeline
# --------------------------------------------------------------------------- #

@pytest.fixture
async def rt_session(services_app_client, user):
    res = services_app_client.post(
        "/api/v1/meetings", headers=user["headers"],
        json={"title": "Invariant Test", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    session = await manager.create_session(
        meeting_id=uuid.UUID(res.json()["id"]), org_id=uuid.UUID(user["org_id"]),
        room_name=f"inv-{uuid.uuid4().hex[:6]}", mode="ws",
    )
    yield session
    await manager.close_session(session.session_id)


def _participant(hearing: str) -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name=f"Listener {hearing}", speak_lang=hearing,
                         hear_lang=hearing,
                         audio_mode="translated" if hearing != "en" else "original",
                         connected=True)


def _output(text: str, source: str, target: str, flags: list[str]) -> TranslateOutput:
    return TranslateOutput(
        result=TranslationResult(text=text, source_lang=source, target_lang=target,
                                 model="test-model", provider="test-provider",
                                 latency_ms=1.0, quality_flags=flags),
        translation_id=uuid.uuid4(), tm_match=None, source_lang=source)


async def _run_fanout(session, outputs: dict[str, tuple[str, list[str]]]):
    """Commit one English turn into each language in `outputs`, whose value is
    (result template, quality flags). Returns the wire events that were sent."""
    pipe = pl.get_pipeline(session)
    speaker = _participant("en")
    manager.add_participant(session, speaker)
    for lang in outputs:
        manager.add_participant(session, _participant(lang))

    events: list[tuple] = []

    async def capture(_sess, ev_type, data=None, **_kw):
        events.append((ev_type, data or {}))

    async def mock_translate_text(_db, text, source_lang, target_lang, _ctx):
        template, flags = outputs[target_lang]
        return _output(template.format(text=text), source_lang, target_lang, flags)

    with patch("app.realtime.pipeline.translate_text", side_effect=mock_translate_text), \
         patch.object(manager, "broadcast", side_effect=capture):
        await pipe.inject_transcript(speaker, "Quarterly revenue grew", language="en")
        await asyncio.sleep(0.15)
    return events


ECHO = ["untranslated_fallback", "dev_provider"]
TRANSLATED = ["neural_mt"]


@pytest.mark.asyncio
async def test_outage_degrades_honestly_and_leaves_the_original_caption(rt_session):
    """One target echoes, the other translates: the echo must fail alone."""
    events = await _run_fanout(rt_session, {
        "de": ("{text}", ECHO),
        "fr": ("Le chiffre d'affaires a augmenté", TRANSLATED),
    })

    def of(ev_type):
        return [d for t, d in events if t == ev_type]

    assert of(ServerEventType.TRANSCRIPT_FINAL)[0]["text"] == "Quarterly revenue grew", \
        "the human source caption must survive an MT failure"
    failures = of(ServerEventType.TRANSLATION_FAILED)
    assert [f["target_lang"] for f in failures] == ["de"]
    assert failures[0]["recoverable"] is True
    assert failures[0]["source_lang"] == "en"
    succeeded = of(ServerEventType.TRANSLATION_FINAL)
    assert [s["target_lang"] for s in succeeded] == ["fr"], \
        "a failure for one language must not condemn another"
    assert all(s["text"] != "Quarterly revenue grew" for s in succeeded), \
        "the echoed source must never be broadcast as a translation"
    assert of(ServerEventType.TTS_STARTED), "the healthy language still gets audio"


@pytest.mark.asyncio
async def test_every_translation_references_the_canonical_segment_id(rt_session):
    pipe = pl.get_pipeline(rt_session)
    speaker = _participant("en")
    manager.add_participant(rt_session, speaker)
    for lang in ("de", "fr"):
        manager.add_participant(rt_session, _participant(lang))

    seen: list[tuple] = []

    async def mock_translate_text(_db, text, source_lang, target_lang, ctx):
        seen.append((text, source_lang, target_lang, ctx.segment_id))
        return _output(f"[{target_lang}] {text}", source_lang, target_lang, TRANSLATED)

    sent: list[tuple] = []

    async def swallow(_sess, ev_type, data=None, **_kw):
        sent.append((ev_type, data or {}))

    with patch("app.realtime.pipeline.translate_text", side_effect=mock_translate_text), \
         patch.object(manager, "broadcast", side_effect=swallow):
        await pipe.inject_transcript(speaker, "Ship on Friday", language="en")
        await asyncio.sleep(0.15)

    assert [t for t, _d in sent if t == ServerEventType.TRANSLATION_FAILED] == [], \
        "both languages must have translated for real here"

    from sqlalchemy import select
    async with db_session() as db:
        rows = (await db.execute(
            select(M.TranscriptSegment)
            .where(M.TranscriptSegment.meeting_id == rt_session.meeting_id)
        )).scalars().all()
    assert len(rows) == 1, "exactly one canonical source segment per turn"
    canonical = rows[0]

    assert [tgt for (_t, _s, tgt, _i) in seen] == ["de", "fr"]
    for text, _src, _tgt, segment_id in seen:
        assert segment_id == canonical.id, \
            "a translation must name the segment it came from or it cannot be audited"
        assert text == canonical.source_text, \
            "every target translates the human words, never another target's output"
