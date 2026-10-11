"""Regression tests for the web client's video-call contract.

The deployed API (services/api) and the SPA were out of sync: the media layer
keyed LiveKit off `transport`/`livekit_url`, which the API never returned, and
polished a `POST /meetings/{id}/media-token` route that did not exist.
"""
from __future__ import annotations

import uuid

import pytest


INTERNAL_URL = "ws://livekit:7880"
PUBLIC_URL = "wss://meet.example.com"


@pytest.fixture()
def livekit_on(monkeypatch):
    """Point every module that reads LiveKit config at one patched settings view.

    The settings singleton can be reloaded by other suites in the same session,
    so patch the attribute each consumer module actually references.
    """
    from types import SimpleNamespace
    from app.config import settings as real
    patched = SimpleNamespace(
        livekit_enabled=True, livekit_url=INTERNAL_URL,
        livekit_public_url=PUBLIC_URL, livekit_api_key="devkey",
        livekit_api_secret="devsecretdevsecretdevsecret1234",
        web_origin=real.web_origin)
    from app.realtime import livekit_bridge
    from app.routers import meetings
    monkeypatch.setattr(livekit_bridge, "settings", patched)
    monkeypatch.setattr(meetings, "settings", patched)
    return patched


def _create(client, headers, mode):
    res = client.post("/api/v1/meetings", headers=headers,
                      json={"title": f"{mode} call", "mode": mode, "hear_lang": "en"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _join(client, headers, meeting_id, display_name="Host"):
    res = client.post(f"/api/v1/meetings/{meeting_id}/join", headers=headers,
                      json={"display_name": display_name, "speak_lang": "en",
                            "hear_lang": "en", "audio_mode": "translated"})
    assert res.status_code == 200, res.text
    return res.json()["participant_id"]


def test_meeting_detail_exposes_transport_and_summary(services_app_client, user):
    """`transport` and `has_summary` drive the SPA's transport selection."""
    client = services_app_client
    meeting_id = _create(client, user["headers"], "ws")
    detail = client.get(f"/api/v1/meetings/{meeting_id}", headers=user["headers"])
    assert detail.status_code == 200
    body = detail.json()
    assert body["transport"] == "ws"
    assert body["has_summary"] is False
    assert body["livekit_url"] is None


def test_meeting_detail_advertises_reachable_livekit_url(services_app_client, user, livekit_on):
    meeting_id = _create(services_app_client, user["headers"], "livekit")
    body = services_app_client.get(f"/api/v1/meetings/{meeting_id}",
                                  headers=user["headers"]).json()
    assert body["transport"] == "livekit"
    # Browsers must never be handed the docker-internal address.
    assert body["livekit_url"] == PUBLIC_URL


def test_media_token_hands_the_browser_livekit_credentials(services_app_client, user, livekit_on):
    meeting_id = _create(services_app_client, user["headers"], "livekit")
    participant_id = _join(services_app_client, user["headers"], meeting_id)

    res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/media-token?participant_id={participant_id}",
        headers=user["headers"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["url"] == PUBLIC_URL
    # identity is the LiveKit participant identity, distinct from the DB uuid.
    assert body["identity"]
    assert body["token"]

    import jwt
    claims = jwt.decode(body["token"], livekit_on.livekit_api_secret,
                        algorithms=["HS256"], options={"require": ["exp"]})
    assert claims["video"]["room"] == body["room"]
    assert claims["sub"] == body["identity"]


def test_media_token_is_explicit_when_livekit_unconfigured(services_app_client, user):
    """A missing transport must be a 422 the UI can show, not a 404 route miss."""
    meeting_id = _create(services_app_client, user["headers"], "ws")
    res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/media-token?participant_id={uuid.uuid4()}",
        headers=user["headers"])
    assert res.status_code == 422
    assert res.json()["error"]["details"]["code"] == "media_transport_unavailable"


def test_media_token_rejects_unknown_participant(services_app_client, user, livekit_on):
    meeting_id = _create(services_app_client, user["headers"], "livekit")
    res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/media-token?participant_id={uuid.uuid4()}",
        headers=user["headers"])
    assert res.status_code == 404


def test_media_token_denies_foreign_participant(services_app_client, user, second_user, livekit_on):
    """Another org's user must not be able to mint a join token for our meeting."""
    meeting_id = _create(services_app_client, user["headers"], "livekit")
    participant_id = _join(services_app_client, user["headers"], meeting_id)
    res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/media-token?participant_id={participant_id}",
        headers=second_user["headers"])
    assert res.status_code in (403, 404)
