"""Phase 4: a failure has to say why it failed.

The guide's Phase 4 list names four things that can go wrong on a live call —
provider outage, missing credentials, unsupported language, a dropped socket —
and asks for a test of each. Four tests exist for ways the path *succeeds*;
nothing pinned what the room is *told* when it does not.

That gap is not only missing coverage, it is a wrong report. Both failure paths
in the translation stage assumed the same cause: Agent 2 published
``reason="provider_unavailable"`` for every exception the provider raised, and
the pipeline broadcast one canned sentence — "Translation is taking longer than
expected" — whatever had happened. So a language pair this deployment is not
licensed for, which will never succeed on any turn, was reported to the room as
a slow provider and to the trace as an outage. An operator reading the failure
counter would add capacity to a system whose problem was a capability row.

The rule these tests enforce is one sentence: **the reason the stage event
carries, the code the wire event carries, and the words the listener reads all
come from what the failure actually said.** `app.errors.AppError` subclasses
already name themselves with a `code`; `asyncio.TimeoutError` is the meeting's
own deadline; only everything else gets the outage label.

Evidence level: the real ``MeetingPipeline`` stage bodies, the real
``TranslationAgent`` and ``RealtimeTranslatorProvider``, the real bus; fake
providers and a fake database session.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.types import (
    AudioChunk, DetectionResult, ProviderUnavailable, RouteDecision,
    TranscriptChunk, TranslationResult,
)

import app.realtime.agents.translation as T
import app.realtime.pipeline as P
from app.errors import ProviderError, UnsupportedLanguageError
from app.realtime.agents.contracts import Stage
from app.realtime.session_manager import RtParticipant, RtSession, manager

# 1000 ms of 16 kHz mono PCM16: exactly 32 000 bytes.
AUDIO_1S = b"\x01\x02" * 16_000

#: What a misconfigured provider says about itself. `gt_ai.translation.http`
#: raises exactly this when MT_HTTP_URL is unset, so the room must not repeat it.
CONFIG_ERROR = "MT_HTTP_URL not configured"


class FakeWs:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.frames: list[bytes] = []

    async def send_text(self, payload: str) -> None:
        self.events.append(json.loads(payload))

    async def send_bytes(self, payload: bytes) -> None:
        self.frames.append(payload)


def _decision(provider: str, task: str) -> RouteDecision:
    return RouteDecision(provider=provider, model=f"{provider}-m", task=task,
                         reason="test-fake")


class FakeAI:
    def __init__(self, *, language: str = "hi") -> None:
        self.language = language

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        return (TranscriptChunk(text="नमस्ते", language=self.language, is_final=True,
                                confidence=0.9, model="fake-stt", provider="fake"),
                _decision("fake-stt", "stt"))

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language=self.language, confidence=0.88,
                               provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        async def stream():
            yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                             encoding="pcm_s16le", format="wav",
                             provider="fake-tts", model="fake-tts-m",
                             duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


def _participant(*, hear: str, speak: str = "hi", mode: str = "translated",
                 name: str = "p") -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name=name, speak_lang=speak, hear_lang=hear,
                         audio_mode=mode, captions_enabled=True,
                         ws=FakeWs(), connected=True)


@pytest.fixture
def session():
    return RtSession(session_id="sess-reason", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    class _Result:
        def scalar(self):
            return 0

    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        def _add(obj):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

        async def _execute(*_a, **_kw):
            return _Result()

        async def _commit():
            return None

        yield SimpleNamespace(add=_add, commit=_commit, execute=_execute)
    monkeypatch.setattr(P, "db_session", _fake_session)
    monkeypatch.setattr(P.settings, "retention_audio_days", 0, raising=False)


@pytest.fixture
def speaker():
    """The person talking, hearing their own language in the original."""
    return _participant(hear="hi", mode="original", name="Aman")


def _join(session: RtSession, *participants: RtParticipant) -> None:
    for p in participants:
        manager.add_participant(session, p)


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e["data"] for e in ws.events if e.get("type") == event_type]


def _stage_failures(pipe: P.MeetingPipeline) -> list[dict]:
    return [e.payload for e in pipe.bus.trace if e.type is Stage.STAGE_FAILED]


def _refusing(error: Exception):
    """A translation service that always answers with this exception."""
    async def refuse(db, text, src, tgt, ctx):
        raise error
    return refuse


# --------------------------------------------------------------------------- #
# one classifier, three consumers
# --------------------------------------------------------------------------- #

_CASES = [
    pytest.param(lambda: UnsupportedLanguageError(
        "Translation into 'ta' is experimental and not enabled."),
        "unsupported_language", id="pair-not-enabled"),
    pytest.param(lambda: ProviderError(
        "AI capability temporarily unavailable. Original content is unaffected."),
        "provider_error", id="outage"),
    pytest.param(lambda: asyncio.TimeoutError(), "timeout", id="deadline"),
    pytest.param(lambda: RuntimeError("connection reset by peer"),
                 "provider_unavailable", id="anything-else"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("make_error,expected_reason", _CASES)
async def test_the_room_is_told_the_reason_the_engine_gave(
        session, speaker, no_db, monkeypatch, make_error, expected_reason):
    """The stage event, the wire code and the metric all read one classifier.

    Asserting they agree is the point: two names for the same failure means
    whichever dashboard you look at decides whether you have an outage.
    """
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    monkeypatch.setattr(P, "translate_text", _refusing(make_error()))
    pipe = P.MeetingPipeline(session)

    await pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=1, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0)

    assert _stage_failures(pipe)[-1]["reason"] == expected_reason
    failed = _events(en.ws, "translation.failed")[-1]
    assert failed["code"] == expected_reason
    assert failed["recoverable"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("make_error,expected_reason", _CASES)
async def test_the_listener_reads_a_sentence_that_matches_the_failure(
        session, speaker, no_db, monkeypatch, make_error, expected_reason):
    """A message about duration is a lie when the answer will never come.

    The words are chosen from the reason, so each case is checked against the
    claim it is making: only a deadline may mention time, and an unlicensed
    pair may not promise that waiting helps.
    """
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    monkeypatch.setattr(P, "translate_text", _refusing(make_error()))
    pipe = P.MeetingPipeline(session)

    await pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=1, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0)

    message = _events(en.ws, "translation.failed")[-1]["message"].lower()
    if expected_reason == "timeout":
        assert "longer" in message
    else:
        assert "longer" not in message
    if expected_reason == "unsupported_language":
        assert "language" in message
    # Every one of them says the conversation continues, which is the promise
    # the guide makes about failure.
    assert "original" in message


# --------------------------------------------------------------------------- #
# the deadline is real, not a synthetic exception
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_the_meetings_own_deadline_reaches_the_room_as_a_timeout(
        monkeypatch, no_db):
    """`timeout` is only an honest reason if the code path that produces it runs.

    ``RealtimeTranslatorProvider`` cuts a translation that outlives the turn. The
    test lets a real translation run past a real deadline rather than raising a
    ``TimeoutError`` by hand, so the label is attached to the thing it names.
    """
    from app.realtime.agents.bus import AgentBus
    from app.realtime.agents.contracts import TranscriptSegment
    from app.realtime.agents.translation import RealtimeTranslatorProvider

    monkeypatch.setattr(T.settings, "rt_translate_timeout_s", 0.05, raising=False)

    async def slow(db, text, src, tgt, ctx):
        await asyncio.sleep(30)

    bus = AgentBus()
    meeting_id = str(uuid.uuid4())
    agent = T.TranslationAgent(
        bus, RealtimeTranslatorProvider(P.db_session, lambda *a: None,
                                        translate_fn=slow),
        meeting_id=meeting_id)
    segment = TranscriptSegment(
        correlation_id="utt-1", meeting_id=meeting_id, speaker_id="s-1",
        segment_id="seg-1", sequence_number=1, source_language="hi",
        recognized_text="नमस्ते", is_final=True)

    with pytest.raises(asyncio.TimeoutError):
        await agent.translate_one(segment, "en", ["r-1"])

    failed = [e.payload for e in bus.trace if e.type is Stage.STAGE_FAILED]
    assert failed[-1]["reason"] == "timeout"


# --------------------------------------------------------------------------- #
# missing credentials: the setting is named, but only to the operator
# --------------------------------------------------------------------------- #

def test_a_provider_without_its_endpoint_says_which_setting_is_missing():
    """The error an operator needs exists, and it is not swallowed.

    ``MT_HTTP_URL not configured`` is what ``gt_ai.translation.http`` raises when
    it is selected with no endpoint. Nothing downstream may lose that sentence,
    because it is the only thing that says what to do about it.
    """
    from gt_ai.translation.http import HttpMtProvider
    from gt_ai.types import TranslationRequest

    provider = HttpMtProvider(url="", api_key="")
    request = TranslationRequest(text="नमस्ते", source_lang="hi", target_lang="en")

    with pytest.raises(ProviderUnavailable) as raised:
        asyncio.run(provider.translate(request))
    assert CONFIG_ERROR in str(raised.value)


@pytest.mark.asyncio
async def test_a_missing_credential_is_reported_to_the_log_not_to_the_room(
        session, speaker, no_db, monkeypatch, caplog):
    """The room gets a reason; the operator gets the sentence.

    A wire event is copied into every participant's browser, and into the
    meeting's replay buffer. An internal setting name does not belong there —
    while dropping it must not drop the diagnosis, which is why the same string
    is asserted in the log record.
    """
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    monkeypatch.setattr(P, "translate_text",
                        _refusing(ProviderUnavailable(CONFIG_ERROR)))
    pipe = P.MeetingPipeline(session)

    with caplog.at_level(logging.WARNING, logger="app.realtime.agents.translation"):
        await pipe._translate_and_synthesize(
            segment_id=uuid.uuid4(), seq=1, speaker=speaker, text="नमस्ते",
            source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0)

    assert CONFIG_ERROR in caplog.text
    failed = _events(en.ws, "translation.failed")[-1]
    assert CONFIG_ERROR not in json.dumps(failed)
    assert failed["code"] == "provider_unavailable"
    assert _stage_failures(pipe)[-1]["reason"] == "provider_unavailable"


# --------------------------------------------------------------------------- #
# the conversation outlives the failure
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_an_unsupported_pair_still_leaves_the_original_caption(
        session, no_db, monkeypatch):
    """Phase 4's standing promise: translation fails, the meeting does not.

    One whole turn — real speaker loop body, real routing — with a provider that
    refuses the pair. The listener must still receive the words the speaker said
    in the language they said them, and must not be handed machine audio that
    was never made.
    """
    speaker = _participant(hear="hi", mode="original", name="Aman")
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    monkeypatch.setattr(P, "translate_text", _refusing(UnsupportedLanguageError(
        "Realtime translation into 'en' is not enabled.")))
    pipe = P.MeetingPipeline(session)

    u = P.UtteranceState(participant_id=speaker.participant_id,
                         capture_started=time.perf_counter(), started_at_ms=0, seq=1,
                         in_speech=False)
    await pipe._finalize_utterance(speaker, u, audio_bytes=AUDIO_1S,
                                   utterance_id=u.utterance_id, seq=1)
    await asyncio.gather(*list(pipe.translation_tasks.values()),
                         return_exceptions=True)

    final = _events(en.ws, "transcript.final")[-1]
    assert final["text"] == "नमस्ते"
    assert final["language"] == "hi"
    assert _events(en.ws, "translation.failed")[-1]["code"] == "unsupported_language"
    assert _events(en.ws, "tts.chunk") == []
    assert en.ws.frames == []


@pytest.mark.asyncio
async def test_a_refused_pair_is_not_logged_as_a_crash(session, speaker, no_db,
                                                       monkeypatch, caplog):
    """Turn after turn, a rejected pair produced a traceback per turn.

    ``log.exception`` is for the failures nobody predicted. A provider that said
    "this language is not enabled" answered a known question, and an ERROR
    traceback every few seconds is how a real outage gets missed in the noise.
    """
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    monkeypatch.setattr(P, "translate_text", _refusing(UnsupportedLanguageError(
        "Translation into 'en' is experimental and not enabled.")))
    pipe = P.MeetingPipeline(session)

    with caplog.at_level(logging.INFO):
        await pipe._translate_and_synthesize(
            segment_id=uuid.uuid4(), seq=1, speaker=speaker, text="नमस्ते",
            source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0)

    crash = [r for r in caplog.records
             if r.levelno >= logging.ERROR and "translation crashed" in r.getMessage()]
    assert crash == [], "a named failure was reported as an unhandled crash"
    # ...and it is still reported, because silence is the other way to hide it.
    assert _stage_failures(pipe), "the failure was swallowed along with the log line"
