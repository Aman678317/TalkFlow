"""Unit tests for ParticipantRouter and FanoutEngine."""
from __future__ import annotations

import pytest
from app.core.exceptions import RoomIsolatedError
from app.models.delivery_models import ParticipantRoute
from app.routing.participant_router import ParticipantRouter


def test_participant_routing_and_language_filter():
    router = ParticipantRouter()
    room_id = "meeting_101"

    # Register participants
    p_mr = ParticipantRoute(
        participant_id="user_aarav",
        room_id=room_id,
        hear_lang="mr",
        playback_mode="translated",
    )
    p_hi = ParticipantRoute(
        participant_id="user_pooja",
        room_id=room_id,
        hear_lang="hi",
        playback_mode="translated",
    )
    p_en = ParticipantRoute(
        participant_id="user_john",
        room_id=room_id,
        hear_lang="en",
        playback_mode="both",
    )

    router.register_participant(p_mr)
    router.register_participant(p_hi)
    router.register_participant(p_en)

    # Resolve Marathi recipients
    mr_listeners = router.get_recipients(room_id=room_id, target_lang="mr")
    assert len(mr_listeners) == 1
    assert mr_listeners[0].participant_id == "user_aarav"

    # Resolve Hindi recipients
    hi_listeners = router.get_recipients(room_id=room_id, target_lang="hi")
    assert len(hi_listeners) == 1
    assert hi_listeners[0].participant_id == "user_pooja"


def test_speaker_feedback_loop_prevention():
    """Verify that the speaker's own seat is excluded from receiving their translated audio."""
    router = ParticipantRouter()
    room_id = "meeting_conf"

    speaker = ParticipantRoute(
        participant_id="speaker_aman",
        room_id=room_id,
        hear_lang="hi",
        playback_mode="translated",
    )
    listener = ParticipantRoute(
        participant_id="listener_rohit",
        room_id=room_id,
        hear_lang="hi",
        playback_mode="translated",
    )

    router.register_participant(speaker)
    router.register_participant(listener)

    # Speaker is speaker_aman: they must NOT receive Hindi translated audio in multi-user room
    recipients = router.get_recipients(room_id=room_id, target_lang="hi", speaker_id="speaker_aman")
    assert len(recipients) == 1
    assert recipients[0].participant_id == "listener_rohit"


def test_multi_tenant_isolation():
    """Verify cross-tenant operations are strictly prohibited."""
    router = ParticipantRouter()
    room_id = "tenant_room"

    p1 = ParticipantRoute(
        participant_id="user_org1",
        room_id=room_id,
        tenant_id="org_alpha",
    )
    router.register_participant(p1)

    p2 = ParticipantRoute(
        participant_id="user_org2",
        room_id=room_id,
        tenant_id="org_beta",  # Different tenant!
    )
    with pytest.raises(RoomIsolatedError):
        router.register_participant(p2)

