"""Phase 4: a health indicator has to mean the stage actually ran.

The guide's rule is not "report a status", it is "do not report a status you
did not earn". Until now the realtime path did exactly that: `SESSION_CREATED`
sent ``"ai": {"translation": "active"}`` to every participant the moment they
joined, whether or not a single byte had been transcribed, translated or
synthesized — and the two components that *did* know the truth, the bus and the
supervisor, were not reachable from anywhere outside the process.

So every test here asks one question of a supervisor that has watched a
different amount of a meeting, and the answer must never be the word "active":

  did this stage receive work, did it produce anything, did anything fail?

"waiting" — work arrived and nothing came out — is the case that matters most,
because it is what a stalled provider, a dev stand-in that returns empty text,
or an unwired callback all look like from the outside. A hardcoded "active"
reported every one of them as healthy.

Providers are irrelevant here: the supervisor only ever reads the event bus, so
these are pure bookkeeping tests with no I/O.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import RealtimeEvent, Stage
from app.realtime.agents.supervisor import Supervisor

MEETING = str(uuid.uuid4())
SPEAKER = str(uuid.uuid4())


class FakeClock:
    def __init__(self) -> None:
        self.now_ms = 1_000_000

    def __call__(self) -> int:
        return self.now_ms

    def advance(self, ms: int) -> None:
        self.now_ms += ms


def _room():
    """A supervisor attached to a bus, as the pipeline attaches it."""
    clock = FakeClock()
    bus = AgentBus(clock=clock)
    sup = Supervisor(clock=clock, meeting_id=MEETING)
    sup.attach(bus)
    return bus, sup, clock


async def _publish(bus: AgentBus, event_type: Stage, *, corr: str = "utt-1",
                   segment: str = "seg-1", **payload) -> None:
    await bus.publish(RealtimeEvent(type=event_type, correlation_id=corr,
                                    meeting_id=MEETING, speaker_id=SPEAKER,
                                    segment_id=segment, payload=payload))


async def _healthy_chain(bus: AgentBus, sup: Supervisor) -> None:
    """One complete turn: audio in, transcript, translation, chunks, delivery."""
    await _publish(bus, Stage.AUDIO_CAPTURED)
    await _publish(bus, Stage.TRANSCRIPT_FINAL, source_language="hi")
    sup.note_active_segment(SPEAKER, correlation_id="utt-1", sequence_number=1,
                            target_languages=["en"])
    await _publish(bus, Stage.TRANSLATION_READY, target_language="en")
    await _publish(bus, Stage.TTS_CHUNK_READY, target_language="en", chunk_index=0)
    await _publish(bus, Stage.AUDIO_DELIVERED, target_language="en")


# --------------------------------------------------------------------------- #
# the empty meeting
# --------------------------------------------------------------------------- #

def test_no_events_means_no_stage_claims_to_have_run():
    _bus, sup, _clock = _room()
    status = sup.stage_status()

    assert list(status) == ["listening", "translation", "voice", "delivery"]
    assert {s["status"] for s in status.values()} == {"not_yet_ran"}
    # The word this whole task exists to remove must not come back through the
    # side door as a synonym.
    assert "active" not in json.dumps(status)


# --------------------------------------------------------------------------- #
# "waiting": work arrived, nothing came out
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_audio_that_produced_no_transcript_is_stalled_not_healthy():
    bus, sup, _clock = _room()
    await _publish(bus, Stage.AUDIO_CAPTURED)

    listening = sup.stage_status()["listening"]
    assert listening["expected"] == 1
    assert listening["events"] == 0
    assert listening["status"] == "waiting"


@pytest.mark.asyncio
async def test_a_requested_translation_that_never_arrived_is_visible():
    """The provider call hanging is indistinguishable from it succeeding, unless
    the request itself is counted. This is the shape of "captions worked but
    nobody ever heard anything"."""
    bus, sup, _clock = _room()
    await _publish(bus, Stage.AUDIO_CAPTURED)
    await _publish(bus, Stage.TRANSCRIPT_FINAL, source_language="hi")
    sup.note_active_segment(SPEAKER, correlation_id="utt-1", sequence_number=1,
                            target_languages=["en", "ta"])

    status = sup.stage_status()
    assert status["listening"]["status"] == "ok"
    assert status["translation"]["expected"] == 2
    assert status["translation"]["status"] == "waiting"
    # Nothing was handed to the stages downstream of the stall, so they are not
    # blamed for it.
    assert status["voice"]["status"] == "not_yet_ran"


@pytest.mark.asyncio
async def test_a_barge_in_stops_owing_the_cancelled_turn():
    """Cancellation must release the stage's promise, not keep it outstanding.

    A speaker who talks over themselves is not a stalled provider: after the
    interrupt, nobody is waiting for that translation, so reporting `waiting`
    would be a false alarm — and a health report that cries wolf is not read.
    The cumulative `expected` count still says the work was asked for.
    """
    bus, sup, _clock = _room()
    await _publish(bus, Stage.AUDIO_CAPTURED)
    await _publish(bus, Stage.TRANSCRIPT_FINAL, source_language="hi")
    sup.note_active_segment(SPEAKER, correlation_id="utt-1", sequence_number=1,
                            target_languages=["en"])
    assert sup.stage_status()["translation"]["status"] == "waiting"

    assert await sup.interrupt(SPEAKER, reason="barge_in") == ["utt-1"]

    translation = sup.stage_status()["translation"]
    assert translation["pending"] == 0
    assert translation["expected"] == 1
    assert translation["status"] == "not_yet_ran"


# --------------------------------------------------------------------------- #
# failures
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_stage_that_only_fails_is_failing_and_does_not_drag_the_others_down():
    bus, sup, _clock = _room()
    await _publish(bus, Stage.AUDIO_CAPTURED)
    await _publish(bus, Stage.TRANSCRIPT_FINAL, source_language="hi")
    sup.note_active_segment(SPEAKER, correlation_id="utt-1", sequence_number=1,
                            target_languages=["en"])
    await _publish(bus, Stage.STAGE_FAILED, stage="translation",
                   reason="provider_unavailable", error_code="LookupError")

    status = sup.stage_status()
    assert status["translation"]["status"] == "failing"
    assert status["translation"]["failures"] == 1
    assert status["listening"]["status"] == "ok"
    assert status["voice"]["status"] == "not_yet_ran"


@pytest.mark.asyncio
async def test_one_language_healthy_and_one_broken_is_degraded_not_ok():
    bus, sup, _clock = _room()
    await _healthy_chain(bus, sup)
    await _publish(bus, Stage.STAGE_FAILED, corr="utt-2", segment="seg-2",
                   stage="translation", reason="provider_unavailable",
                   error_code="LookupError")

    translation = sup.stage_status()["translation"]
    assert translation["events"] == 1
    assert translation["failures"] == 1
    assert translation["status"] == "degraded"


@pytest.mark.asyncio
async def test_stages_name_themselves_as_the_provider_does_not_the_pipeline():
    """Agent 1 reports "stt", Agent 3 reports "tts". Both belong to listening and
    voice here, or their failures land in a bucket nobody reads."""
    bus, sup, _clock = _room()
    await _publish(bus, Stage.STAGE_FAILED, stage="stt", reason="provider_unavailable")
    await _publish(bus, Stage.STAGE_FAILED, stage="tts", reason="provider_unavailable")

    status = sup.stage_status()
    assert status["listening"]["status"] == "failing"
    assert status["voice"]["status"] == "failing"
    assert status["translation"]["status"] == "not_yet_ran"


# --------------------------------------------------------------------------- #
# evidence, not assertion
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_complete_turn_reads_ok_on_every_stage_with_the_events_to_prove_it():
    bus, sup, clock = _room()
    await _healthy_chain(bus, sup)

    status = sup.stage_status()
    assert [s["status"] for s in status.values()] == ["ok", "ok", "ok", "ok"]
    assert status["listening"]["events"] == 1
    assert status["translation"]["events"] == 1
    assert status["voice"]["events"] == 1
    assert status["delivery"]["events"] == 1
    assert status["delivery"]["last_event_ms"] == clock.now_ms


@pytest.mark.asyncio
async def test_the_last_time_a_stage_proved_itself_is_part_of_the_answer():
    bus, sup, clock = _room()
    clock.advance(400)
    await _publish(bus, Stage.TRANSLATION_READY, target_language="en")

    assert sup.stage_status()["translation"]["last_event_ms"] == clock.now_ms
    # A stage that never ran has no "last" — and says so with 0 rather than a
    # timestamp that would look like recent activity.
    assert sup.stage_status()["voice"]["last_event_ms"] == 0


@pytest.mark.asyncio
async def test_the_age_of_outstanding_work_is_part_of_the_answer():
    bus, sup, clock = _room()
    await _publish(bus, Stage.AUDIO_CAPTURED)
    clock.advance(2_500)

    listening = sup.stage_status()["listening"]
    assert listening["status"] == "waiting"
    assert listening["pending_ms"] == 2_500


@pytest.mark.asyncio
async def test_a_stage_that_worked_once_and_then_went_quiet_still_shows_the_debt():
    """A provider that recovers and then stops is the common failure, and "ok"
    based on its history would bury it. The supervisor reports the status and the
    outstanding age side by side; deciding when old means broken is the room
    owner's job, because only it knows what the window is."""
    bus, sup, clock = _room()
    await _healthy_chain(bus, sup)

    await _publish(bus, Stage.AUDIO_CAPTURED, corr="utt-2", segment="seg-2")
    await _publish(bus, Stage.TRANSCRIPT_FINAL, corr="utt-2", segment="seg-2",
                   source_language="hi")
    sup.note_active_segment(SPEAKER, correlation_id="utt-2", sequence_number=2,
                            target_languages=["en"])
    clock.advance(9_000)

    translation = sup.stage_status()["translation"]
    assert translation["status"] == "ok"
    assert translation["pending"] == 1
    assert translation["pending_ms"] >= 9_000


def test_the_status_is_a_small_finite_vocabulary():
    """An operator reading this over HTTP must not have to guess which of nine
    adjectives mean "broken"."""
    _bus, sup, _clock = _room()
    assert sup.STATUSES == {"not_yet_ran", "waiting", "ok", "degraded", "failing"}
    assert set(s["status"] for s in sup.stage_status().values()) <= sup.STATUSES


# --------------------------------------------------------------------------- #
# the composed pipeline: what this room should have produced
# --------------------------------------------------------------------------- #

import app.realtime.pipeline as P                                    # noqa: E402
from app.realtime.session_manager import RtParticipant, RtSession, manager  # noqa: E402


@pytest.fixture
def session():
    return RtSession(session_id="sess-health", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    """Stage health must be answerable without touching a database."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        yield SimpleNamespace(add=lambda *_: None, commit=lambda: None,
                              execute=lambda *_: None)
    monkeypatch.setattr(P, "db_session", _fake_session)


@pytest.fixture
def real_providers(monkeypatch):
    """Pin the dev-stand-in flags to "these are real engines". The tests below
    this one are about stage bookkeeping; the flag itself gets its own test."""
    monkeypatch.setattr(P, "dev_flags", lambda: {"stt_dev_mode": False,
                                                  "mt_dev_mode": False,
                                                  "tts_dev_mode": False})


def _listener(mode: str) -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name="listener", speak_lang="hi", hear_lang="en",
                         audio_mode=mode, captions_enabled=True, ws=None,
                         connected=True)


@pytest.mark.asyncio
async def test_a_captions_only_room_is_not_reported_as_a_broken_delivery_stage(
        session, no_db, real_providers):
    """The supervisor is room-blind: chunks with no delivery look identical to a
    lost socket. The session owner knows nobody asked for audio, so it says so
    here instead of leaving a warning nobody can act on."""
    manager.add_participant(session, _listener("captions_only"))
    pipe = P.MeetingPipeline(session)
    await _publish(pipe.bus, Stage.TTS_CHUNK_READY, target_language="en",
                   chunk_index=0)

    health = pipe.stage_health()
    assert health["stages"]["delivery"]["status"] == "not_expected"
    assert health["healthy"] is True


@pytest.mark.asyncio
async def test_a_room_that_asked_for_audio_and_received_none_is_not_healthy(
        session, no_db, real_providers):
    manager.add_participant(session, _listener("translated"))
    pipe = P.MeetingPipeline(session)
    await _publish(pipe.bus, Stage.TTS_CHUNK_READY, target_language="en",
                   chunk_index=0)

    health = pipe.stage_health()
    assert health["stages"]["delivery"]["status"] == "waiting"
    assert health["healthy"] is False


@pytest.mark.asyncio
async def test_a_fresh_meeting_joins_with_nothing_claimed(session, no_db,
                                                           real_providers):
    """This is the payload that replaced ``"translation": "active"``. A joining
    participant is told the truth: no stage has produced anything yet."""
    manager.add_participant(session, _listener("translated"))
    pipe = P.MeetingPipeline(session)

    health = pipe.stage_health()
    assert {s["status"] for s in health["stages"].values()} == {"not_yet_ran"}
    assert health["healthy"] is True
    assert health["bus"]["published"] == 0


@pytest.mark.asyncio
async def test_a_stage_that_ran_on_a_dev_stand_in_is_not_reported_as_working(
        session, no_db, monkeypatch):
    """An empty transcript from a stub provider once presented as "translation
    active" with nothing to listen to. Running is not the same as working, and
    the flag has to survive the composition rather than be re-derived."""
    monkeypatch.setattr(P, "dev_flags", lambda: {"stt_dev_mode": False,
                                                 "mt_dev_mode": True,
                                                 "tts_dev_mode": False})
    manager.add_participant(session, _listener("translated"))
    pipe = P.MeetingPipeline(session)
    await _publish(pipe.bus, Stage.TRANSLATION_READY, target_language="en")

    health = pipe.stage_health()
    translation = health["stages"]["translation"]
    assert translation["events"] == 1          # it did run
    assert translation["status"] == "dev_stand_in"
    assert health["healthy"] is False          # ...and that is not green
    # A translation arriving is synthesis being owed, so the next stage is
    # honestly reported as outstanding rather than innocent.
    assert health["stages"]["voice"]["status"] == "waiting"


@pytest.mark.asyncio
async def test_outstanding_work_past_the_window_is_a_stall_whatever_the_history(
        session, no_db, real_providers, monkeypatch):
    """The supervisor has no opinion about how long is too long. The session
    owner does — it is the same staleness window that already decides whether
    late audio is still worth playing — so the upgrade from "ok" to "waiting"
    happens here."""
    from app.config import settings
    monkeypatch.setattr(settings, "rt_stale_after_ms", 0)
    manager.add_participant(session, _listener("translated"))
    pipe = P.MeetingPipeline(session)
    await _publish(pipe.bus, Stage.TRANSLATION_READY, corr="utt-1",
                   target_language="en")
    await _publish(pipe.bus, Stage.TTS_CHUNK_READY, corr="utt-1",
                   target_language="en", chunk_index=0)
    # A second turn's translation lands and nothing synthesizes it.
    await _publish(pipe.bus, Stage.TRANSLATION_READY, corr="utt-2",
                   target_language="en")

    health = pipe.stage_health()
    assert health["stages"]["voice"]["status"] == "waiting"
    assert health["stages"]["voice"]["events"] == 1
    assert health["healthy"] is False


@pytest.mark.asyncio
async def test_health_carries_the_bus_counters_that_used_to_be_unreachable(
        session, no_db, real_providers):
    """``bus.health()`` has always computed real drop counters and nothing
    outside the process could read them. The stage report is where they surface."""
    manager.add_participant(session, _listener("translated"))
    pipe = P.MeetingPipeline(session)
    await _publish(pipe.bus, Stage.TRANSLATION_READY, target_language="en")

    health = pipe.stage_health()
    assert health["bus"]["published"] == 1
    assert health["bus"]["dropped_events"] == 0
    assert health["supervisor"]["stage_failures"] == 0
