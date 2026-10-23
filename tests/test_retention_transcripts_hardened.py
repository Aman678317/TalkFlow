"""Roadmap day 4 — retention TRUTH: the advertised schedules are enforced.

`app.config` advertises `retention_transcript_days` (365 default; 0 =
forever, the buckets' own contract) and the retention module docstring
promises "audio (largest, least durable value) goes first" — but the
day-4 audit found the sweep never touched transcripts at all: meeting
transcript TEXT and each segment's per-segment audio object lived
forever while the policy pretended otherwise. The audio bucket also
ignored the config's own "0 = forever" comment (a `0` window swept
everything instead of nothing).

This suite locks the transcript buckets added to `retention_service`:

- realtime transcript segments older than `retention_transcript_days`
  are deleted — stale non-final fragments age with the same window —
  anchored on row creation time;
- their translation fan-outs go WITH the source segment (a translated
  output cannot outlive the text it claims to translate);
- newer segments are untouched; a `0` text window keeps the text
  forever;
- transcript-segment audio keys age on the SAME audio schedule as
  session audio (`retention_audio_days`; 0 = forever), and any key that
  would be orphaned by a text-row deletion is purged with the row;
- standalone translation rows (product=text/document/chat, segment_id
  NULL) are NOT governed by the transcript window — one-off translate
  history is a product decision, not retention fallout;
- the meeting rows themselves survive a transcript sweep — metadata is
  not the transcript;
- the counts dictionary exposes the new buckets (observability).

Isolation convention (shared-DB lane): every seeded row is tracked by
id and purged in a `finally`, and sweeps are judged via those ids —
never global table state, never other suites' leftovers.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

OLD_AUDIO_TEXT = "पुराना ऑडियो सहित"
OLD_TEXT_ONLY = "पुराना केवल टेक्स्ट"
MID_TEXT = "बीच में का सेगमेंट"
NEW_TEXT = "ताज़ा सेगमेंट"
STANDALONE_TEXT = "standalone one-off"


@pytest.fixture()
def _storage_spy(monkeypatch):
    """Replace the module-owned `storage` binding in retention_service
    with a spy that records deleted keys (no real object store)."""
    import app.services.retention_service as ret_svc

    deleted: list[str] = []

    class _Spy:
        async def delete(self, key: str) -> None:
            deleted.append(key)

    monkeypatch.setattr(ret_svc, "storage", lambda: _Spy(), raising=True)
    return deleted


@pytest.fixture()
def _force_windows(monkeypatch):
    """`retention_transcript_days=30`, `retention_audio_days=7` on every
    module-owned settings binding (app.config + retention_service)."""
    import app.config as cfg_mod
    import app.services.retention_service as ret_svc

    for holder in (ret_svc.settings, cfg_mod.settings):
        monkeypatch.setattr(holder, "retention_transcript_days", 30,
                            raising=True)
        monkeypatch.setattr(holder, "retention_audio_days", 7, raising=True)


async def _seed(user_id: str, org_id: str) -> tuple[str, dict[str, list[str]]]:
    """Meetings/segments with controlled creation ages:

    - 40d meeting: segment WITH an audio key, segment without one, one
      realtime translation fan-out on the first — the whole meeting text
      is past the 30d transcript window;
    - 20d meeting: segment WITH an audio key + fan-out — text inside the
      30d window, audio already past the 7d audio window;
    - 2d meeting: segment + fan-out — untouchable by either window;
    - one standalone 40d translation (product=text, segment_id NULL,
      created_by = this test's user) — not the transcript window's
      business.

    Returns (room-name stem, tracked ids: meetings / segments per text /
    fan rows alive at seed time by text / standalone fan rows).
    """
    from app.db import models as M
    from app.db.session import db_session

    now = datetime.now(UTC)
    stem = uuid.uuid4().hex[:10]
    async with db_session() as db:
        m_old = M.Meeting(org_id=uuid.UUID(org_id), room_name=f"rt-{stem}-old",
                          status="ended", mode="ws")
        m_mid = M.Meeting(org_id=uuid.UUID(org_id), room_name=f"rt-{stem}-mid",
                          status="ended", mode="ws")
        m_new = M.Meeting(org_id=uuid.UUID(org_id), room_name=f"rt-{stem}-new",
                          status="live", mode="ws")
        db.add_all([m_old, m_mid, m_new])
        await db.flush()

        s_old_audio = M.TranscriptSegment(
            meeting_id=m_old.id, seq=1, source_lang="hi",
            source_text=OLD_AUDIO_TEXT, is_final=True,
            audio_object_key=f"audio/{stem}-a1.wav",
            created_at=now - timedelta(days=40), speaker_name="")
        s_old_text = M.TranscriptSegment(
            meeting_id=m_old.id, seq=2, source_lang="hi",
            source_text=OLD_TEXT_ONLY, is_final=True,
            created_at=now - timedelta(days=40), speaker_name="")
        s_mid = M.TranscriptSegment(
            meeting_id=m_mid.id, seq=1, source_lang="hi",
            source_text=MID_TEXT, is_final=True,
            audio_object_key=f"audio/{stem}-m1.wav",
            created_at=now - timedelta(days=20), speaker_name="")
        s_new = M.TranscriptSegment(
            meeting_id=m_new.id, seq=1, source_lang="hi",
            source_text=NEW_TEXT, is_final=True,
            created_at=now - timedelta(days=2), speaker_name="")
        db.add_all([s_old_audio, s_old_text, s_mid, s_new])
        await db.flush()

        c_old = M.TranslationSegment(
            segment_id=s_old_audio.id, meeting_id=m_old.id,
            org_id=uuid.UUID(org_id), product="realtime",
            source_lang="hi", target_lang="en",
            source_text=OLD_AUDIO_TEXT, target_text="old with audio",
            created_at=now - timedelta(days=40))
        c_mid = M.TranslationSegment(
            segment_id=s_mid.id, meeting_id=m_mid.id,
            org_id=uuid.UUID(org_id), product="realtime",
            source_lang="hi", target_lang="en",
            source_text=MID_TEXT, target_text="mid segment",
            created_at=now - timedelta(days=20))
        c_new = M.TranslationSegment(
            segment_id=s_new.id, meeting_id=m_new.id,
            org_id=uuid.UUID(org_id), product="realtime",
            source_lang="hi", target_lang="en",
            source_text=NEW_TEXT, target_text="fresh segment",
            created_at=now - timedelta(days=2))
        c_standalone = M.TranslationSegment(
            product="text", source_lang="en", target_lang="hi",
            source_text=STANDALONE_TEXT, target_text="एक बार का अनुवाद",
            created_by=uuid.UUID(user_id),
            created_at=now - timedelta(days=40))
        db.add_all([c_old, c_mid, c_new, c_standalone])
        await db.commit()

        ids = {
            "meetings": [str(m_old.id), str(m_mid.id), str(m_new.id)],
            "segments": [str(s_old_audio.id), str(s_old_text.id),
                         str(s_mid.id), str(s_new.id)],
            "segment_by_text": {
                OLD_AUDIO_TEXT: str(s_old_audio.id),
                OLD_TEXT_ONLY: str(s_old_text.id),
                MID_TEXT: str(s_mid.id),
                NEW_TEXT: str(s_new.id),
            },
            "fan_by_text": {
                OLD_AUDIO_TEXT: str(c_old.id),
                MID_TEXT: str(c_mid.id),
                NEW_TEXT: str(c_new.id),
            },
            "standalone_fans": [str(c_standalone.id)],
            "audio_keys": {
                OLD_AUDIO_TEXT: f"audio/{stem}-a1.wav",
                MID_TEXT: f"audio/{stem}-m1.wav",
            },
        }
    return stem, ids


async def _purge(ids: dict[str, list[str]]) -> None:
    """Remove exactly the rows this seed created (no cascade reliance)."""
    from sqlalchemy import delete

    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        fan_ids = [uuid.UUID(x) for x in
                   list(ids["fan_by_text"].values()) + ids["standalone_fans"]]
        await db.execute(delete(M.TranslationSegment).where(
            M.TranslationSegment.id.in_(fan_ids)))
        await db.execute(delete(M.TranscriptSegment).where(
            M.TranscriptSegment.id.in_(
                [uuid.UUID(x) for x in ids["segments"]])))
        await db.execute(delete(M.Meeting).where(
            M.Meeting.id.in_([uuid.UUID(x) for x in ids["meetings"]])))
        await db.commit()


async def _state(ids: dict[str, list[str]]) -> dict:
    """Survival state of the seeded rows, judged by exact id."""
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        segs = (await db.execute(
            select(M.TranscriptSegment).where(
                M.TranscriptSegment.id.in_(
                    [uuid.UUID(x) for x in ids["segments"]])))
        ).scalars().all()
        alive_fans = set((await db.execute(
            select(M.TranslationSegment.id).where(
                M.TranslationSegment.id.in_([uuid.UUID(x) for x in
                                             ids["fan_by_text"].values()])
            ))).scalars())
        alive_standalone = set((await db.execute(
            select(M.TranslationSegment.id).where(
                M.TranslationSegment.id.in_(
                    [uuid.UUID(x) for x in ids["standalone_fans"]])))
        ).scalars())
        alive_meetings = set((await db.execute(
            select(M.Meeting.id).where(
                M.Meeting.id.in_([uuid.UUID(x) for x in ids["meetings"]])))
        ).scalars())
    seg_alive = {str(s.id): s for s in segs}
    return {
        "segment_alive": {text: sid in seg_alive
                          for text, sid in ids["segment_by_text"].items()},
        "segment_rows": seg_alive,
        "fan_alive": {text: fid in {str(x) for x in alive_fans}
                      for text, fid in ids["fan_by_text"].items()},
        "standalone_alive": [str(x) for x in alive_standalone],
        "meeting_alive": len(alive_meetings),
    }


async def test_transcript_window_enforcement(services_app_client, user,
                                             _force_windows, _storage_spy):
    from app.db.session import db_session
    from app.services import retention_service

    stem, ids = await _seed(user["user_id"], user["org_id"])
    try:
        async with db_session() as db:
            counts = await retention_service.sweep(db)

        state = await _state(ids)

        # the two 40d segments are gone; 20d/2d never touched
        assert state["segment_alive"] == {OLD_AUDIO_TEXT: False,
                                          OLD_TEXT_ONLY: False,
                                          MID_TEXT: True, NEW_TEXT: True}

        # the meeting rows themselves survive (metadata is not transcript)
        assert state["meeting_alive"] == 3

        # the doomed segment's fan-out goes with its source; kept
        # segments keep their fan-outs
        assert state["fan_alive"] == {OLD_AUDIO_TEXT: False,
                                      MID_TEXT: True, NEW_TEXT: True}

        # standalone one-off (product=text, segment_id NULL) is not the
        # transcript window's business
        assert len(state["standalone_alive"]) == 1

        # audio schedule (7d): the 40d key (purged with its doomed row)
        # and the 20d key (cleared on the audio window) both hit storage;
        # the kept row survives with its audio key nulled
        mine = [k for k in _storage_spy if stem in k]
        assert set(mine) == {ids["audio_keys"][OLD_AUDIO_TEXT],
                             ids["audio_keys"][MID_TEXT]}
        assert state["segment_rows"][ids["segment_by_text"][MID_TEXT]] \
            .audio_object_key is None

        # the sweep's buckets exist and cleared exactly our hardware
        assert {"transcripts", "translations",
                "audio_objects"}.issubset(set(counts))
        assert set(_storage_spy) <= {
            f"audio/{stem}-a1.wav", f"audio/{stem}-m1.wav"}
    finally:
        await _purge(ids)


async def test_zero_transcript_window_keeps_text_forever(
        services_app_client, user, monkeypatch, _storage_spy):
    """0 = forever is per-bucket: the text rows stay, the AUDIO schedule
    still runs underneath."""
    import app.config as cfg_mod
    import app.services.retention_service as ret_svc

    for holder in (ret_svc.settings, cfg_mod.settings):
        monkeypatch.setattr(holder, "retention_transcript_days", 0,
                            raising=True)
        monkeypatch.setattr(holder, "retention_audio_days", 7, raising=True)

    from app.db.session import db_session
    from app.services import retention_service

    stem, ids = await _seed(user["user_id"], user["org_id"])
    try:
        async with db_session() as db:
            await retention_service.sweep(db)

        state = await _state(ids)
        assert state["segment_alive"] == {OLD_AUDIO_TEXT: True,
                                          OLD_TEXT_ONLY: True,
                                          MID_TEXT: True, NEW_TEXT: True}
        assert state["fan_alive"] == {OLD_AUDIO_TEXT: True,
                                      MID_TEXT: True, NEW_TEXT: True}
        assert len(state["standalone_alive"]) == 1
        # the audio schedule still applies: both keys older than 7d are
        # cleared from storage and from their rows
        mine = {k for k in _storage_spy if stem in k}
        assert mine == {ids["audio_keys"][OLD_AUDIO_TEXT],
                        ids["audio_keys"][MID_TEXT]}
        assert all(row.audio_object_key is None
                   for row in state["segment_rows"].values())
    finally:
        await _purge(ids)


async def test_zero_audio_window_keeps_segment_audio(services_app_client,
                                                     user, monkeypatch,
                                                     _storage_spy):
    """0 = forever on audio: only keys orphaned by a text-row deletion
    are purged; survivors keep their audio key."""
    import app.config as cfg_mod
    import app.services.retention_service as ret_svc

    for holder in (ret_svc.settings, cfg_mod.settings):
        monkeypatch.setattr(holder, "retention_transcript_days", 30,
                            raising=True)
        monkeypatch.setattr(holder, "retention_audio_days", 0, raising=True)

    from app.db.session import db_session
    from app.services import retention_service

    stem, ids = await _seed(user["user_id"], user["org_id"])
    try:
        async with db_session() as db:
            await retention_service.sweep(db)

        state = await _state(ids)
        # 30d text window still applies
        assert state["segment_alive"] == {OLD_AUDIO_TEXT: False,
                                          OLD_TEXT_ONLY: False,
                                          MID_TEXT: True, NEW_TEXT: True}
        assert state["fan_alive"] == {OLD_AUDIO_TEXT: False,
                                      MID_TEXT: True, NEW_TEXT: True}
        # only the orphaned key of the doomed segment is purged...
        mine = [k for k in _storage_spy if stem in k]
        assert mine == [ids["audio_keys"][OLD_AUDIO_TEXT]]
        # ...and the kept row's audio key survives the 0-forever contract
        assert state["segment_rows"][ids["segment_by_text"][MID_TEXT]] \
            .audio_object_key == ids["audio_keys"][MID_TEXT]
    finally:
        await _purge(ids)


async def test_counts_buckets_include_transcript_and_translations(
        services_app_client, user, _force_windows):
    from app.db.session import db_session
    from app.services import retention_service

    async with db_session() as db:
        counts = await retention_service.sweep(db)

    assert {"transcripts", "translations"}.issubset(set(counts))
