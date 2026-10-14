"""Phase 3 — committing a long speaker's turn at a clause boundary.

The implementation guide asks for "phrase segmentation stable enough for
translation without waiting for a whole monologue". Before this, the only way a
turn ended was silence (`vad_min_silence_ms`) or the 15 s force-split, so a
presenter talking for forty seconds produced *nothing* a listener could read or
hear until the first pause. The partial captions proved the words were already
known — the pipeline just waited for a breath before using them.

These tests are at the unit level on the speaker loop: a fake VAD that opens
speech and never closes it, and a fake partial transcript. What is asserted is
when the loop decides to commit, and that the continuation is a separate, later
segment rather than a rewrite of the one already translating.
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.vad import SpeechEvent, VadState

import app.realtime.pipeline as P
from app.config import settings
from app.realtime.pipeline import MeetingPipeline, _ends_at_clause
from app.realtime.session_manager import RtParticipant, RtSession, manager

CHUNK_BYTES = 1600  # 50 ms of 16 kHz mono PCM16, the AudioWorklet frame


class OnsetVad:
    """Speech on the first frame, then never again: a speaker who does not stop."""

    def __init__(self) -> None:
        self.clock_ms = 0
        self._fired = False

    def process(self, _pcm16: bytes) -> list[SpeechEvent]:
        if self._fired:
            return []
        self._fired = True
        return [SpeechEvent(state=VadState.SPEECH, timestamp_ms=0, energy=0.05)]


@pytest.fixture
def room(monkeypatch):
    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        yield SimpleNamespace(add=lambda *_: None, commit=lambda: None,
                              execute=lambda *_: None)

    monkeypatch.setattr(P, "db_session", _fake_session)
    monkeypatch.setattr(P, "create_vad", lambda *_a, **_k: OnsetVad())
    # Keep the force-split out of the picture: these tests are about the clause
    # boundary, and a 15 s cap would otherwise fire first in the slow cases.
    monkeypatch.setattr(settings, "vad_max_speech_ms", 60000, raising=False)
    monkeypatch.setattr(settings, "vad_partial_interval_ms", 100, raising=False)
    monkeypatch.setattr(settings, "vad_phrase_commit_ms", 200, raising=False)

    session = RtSession(session_id="sess-phrase", meeting_id=uuid.uuid4(),
                        org_id=uuid.uuid4(), room_name="room", mode="ws")
    speaker = RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                            display_name="Aman", speak_lang="hi", hear_lang="en",
                            audio_mode="translated", captions_enabled=True,
                            ws=SimpleNamespace(events=[], send_text=lambda *_: None,
                                               send_bytes=lambda *_: None,
                                               connected=True),
                            connected=True)
    manager.add_participant(session, speaker)
    return session, speaker


class Recorder:
    """Stand in for finalization: records what got committed, in order.

    The loop fires finalization as a task, so a test needs to know the task ran,
    not merely that it was created — `first` is set on the first commit.
    """

    def __init__(self) -> None:
        self.commits: list[tuple[str, int, bytes]] = []
        self.first = asyncio.Event()

    async def __call__(self, _p, _u, *, forced=False, audio_bytes=b"",
                       start_ms=0, capture_started=None,
                       utterance_id=None, seq=0) -> None:
        self.commits.append((str(utterance_id), seq, bytes(audio_bytes)))
        self.first.set()

    async def wait(self, timeout: float = 2.0) -> None:
        try:
            await asyncio.wait_for(self.first.wait(), timeout)
        except asyncio.TimeoutError:
            pass


async def _speak(pipe: MeetingPipeline, speaker: RtParticipant,
                 frames: int, gap: float = 0.01) -> None:
    """Feed 50 ms AudioWorklet frames.

    `gap` is the only clock that matters here: the loop's thresholds are
    wall-clock, so feeding faster than realtime makes a turn look short even
    when it carries seconds of audio.
    """
    for _ in range(frames):
        await pipe.feed_audio(speaker.participant_id, b"\x01\x02" * (CHUNK_BYTES // 2))
        await asyncio.sleep(gap)


@pytest.mark.parametrize("text,expected", [
    ("आज हम योजना पर चर्चा करेंगे।", True),        # Hindi danda
    ("Hello everyone.", True),
    ("Are you coming?", True),
    ("それでは、始めましょう。", True),                # Japanese full stop
    ('They said "no".', True),                 # terminator behind a quote
    ("आज हम योजना पर चर्चा", False),             # mid-clause
    ("Let us review the plan,", False),        # a comma is not a clause end
    ("आज हम योजना पर ,", False),                  # ...not even a Devanagari one
    ("", False),
])
def test_clause_boundary_recognizes_each_shipped_script(text: str,
                                                        expected: bool) -> None:
    assert _ends_at_clause(text) is expected


@pytest.mark.asyncio
async def test_a_long_speaker_is_committed_at_the_clause_boundary(room, monkeypatch):
    """The gate claim: translation starts before the monologue ends."""
    session, speaker = room
    pipe = MeetingPipeline(session)
    rec = Recorder()
    monkeypatch.setattr(pipe, "_finalize_utterance", rec)

    async def partial(**_kw):
        # The live caption already contains a finished sentence — which is the
        # whole point: the words were known, the loop just waited for a breath.
        return SimpleNamespace(recognized_text="नमस्ते दोस्तों, आज हम नई योजना पर चर्चा करेंगे।",
                               source_language="hi", confidence=0.9)

    monkeypatch.setattr(pipe.listening, "transcribe_partial", partial)

    pipe.start_speaker(speaker)
    try:
        await _speak(pipe, speaker, 60)
        await rec.wait()
    finally:
        pipe.stop_speaker(speaker.participant_id)

    assert len(rec.commits) >= 2, (
        f"a continuous speaker with finished clauses produced {len(rec.commits)} "
        "segment(s) — the break never fired")
    seqs = [c[1] for c in rec.commits]
    ids = {c[0] for c in rec.commits}
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), (
        f"segments were not ordered: {seqs}")
    assert len(ids) == len(rec.commits), "one segment id was committed twice"
    assert all(len(c[2]) > CHUNK_BYTES for c in rec.commits), "committed a stub"
    # The first commit carried a real clause, not a scrap of the turn.
    assert len(rec.commits[0][2]) / 32.0 >= settings.vad_phrase_commit_ms


@pytest.mark.asyncio
async def test_a_speaker_below_the_threshold_is_left_alone(room, monkeypatch):
    """Short turns must not be cut into pieces — that is the regression risk."""
    session, speaker = room
    monkeypatch.setattr(settings, "vad_phrase_commit_ms", 5000, raising=False)
    pipe = MeetingPipeline(session)
    rec = Recorder()
    monkeypatch.setattr(pipe, "_finalize_utterance", rec)

    async def partial(**_kw):
        return SimpleNamespace(recognized_text="नमस्ते दोस्तों।",
                               source_language="hi", confidence=0.9)

    monkeypatch.setattr(pipe.listening, "transcribe_partial", partial)

    pipe.start_speaker(speaker)
    try:
        await _speak(pipe, speaker, 60)
        await asyncio.sleep(0.1)
    finally:
        pipe.stop_speaker(speaker.participant_id)

    assert rec.commits == [], "a turn shorter than the threshold was cut up"


@pytest.mark.asyncio
async def test_an_unfinished_clause_never_splits(room, monkeypatch):
    session, speaker = room
    pipe = MeetingPipeline(session)
    rec = Recorder()
    monkeypatch.setattr(pipe, "_finalize_utterance", rec)

    async def partial(**_kw):
        return SimpleNamespace(recognized_text="आज हम योजना पर चर्चा",
                               source_language="hi", confidence=0.9)

    monkeypatch.setattr(pipe.listening, "transcribe_partial", partial)

    pipe.start_speaker(speaker)
    try:
        await _speak(pipe, speaker, 60)
        await asyncio.sleep(0.1)
    finally:
        pipe.stop_speaker(speaker.participant_id)

    assert rec.commits == [], "an in-flight clause was committed as a finished one"


@pytest.mark.asyncio
async def test_the_break_can_be_switched_off(room, monkeypatch):
    """A deployment that dislikes early commits turns one setting off."""
    session, speaker = room
    monkeypatch.setattr(settings, "vad_phrase_commit_ms", 0, raising=False)
    pipe = MeetingPipeline(session)
    rec = Recorder()
    monkeypatch.setattr(pipe, "_finalize_utterance", rec)

    async def partial(**_kw):
        return SimpleNamespace(recognized_text="नमस्ते दोस्तों।",
                               source_language="hi", confidence=0.9)

    monkeypatch.setattr(pipe.listening, "transcribe_partial", partial)

    pipe.start_speaker(speaker)
    try:
        await _speak(pipe, speaker, 60)
        await asyncio.sleep(0.1)
    finally:
        pipe.stop_speaker(speaker.participant_id)

    assert rec.commits == []
