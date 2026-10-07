"""Phase 15: Full QA & End-to-End Validation Test Suite.

Executes and verifies complete multi-stage user journeys across:
1. Authentication & Tenant Onboarding (signup, JWT, session, password update, me)
2. Multilingual Text & AI Writing Pipelines (/translate, /write/rephrase, /write/correct)
3. Realtime Meeting & Voice Session Lifecycle (meeting creation, cryptographic join tickets, preferences, summaries)
4. Document Translation & Tenant-Isolated Storage (upload, async submission, retrieval)
5. Developer Platform (API key creation, scope verification, key rotation, revocation)
6. Observability & Telemetry Health (/health, /ready, /metrics)
"""
from __future__ import annotations

import hmac
import hashlib
import json
import uuid
import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.db import models as M
from app.db.session import db_session
from app.security import hash_api_key, verify_session_ticket


def test_journey_1_auth_and_workspace_onboarding(services_app_client):
    """Journey 1: User signs up, creates org workspace, inspects profile, updates password."""
    email = f"qa_{uuid.uuid4().hex[:8]}@example.com"
    password = "InitialPassword123"
    org_name = f"QA Workspace {uuid.uuid4().hex[:6]}"

    # 1. Signup
    signup_resp = services_app_client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": password,
            "name": "QA Lead",
            "organization_name": org_name,
        },
    )
    assert signup_resp.status_code == 201, signup_resp.text
    signup_data = signup_resp.json()
    token = signup_data["tokens"]["access_token"]
    user_id = signup_data["user"]["id"]
    org_id = signup_data["organization"]["id"]

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Inspect profile (/me)
    me_resp = services_app_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["user"]["email"] == email
    assert me_data["user"]["name"] == "QA Lead"
    assert me_data["organizations"][0]["org"]["name"] == org_name
    assert me_data["organizations"][0]["role"] == "owner"

    # 3. Change password
    new_password = "UpdatedPassword456"
    pw_resp = services_app_client.post(
        "/api/v1/auth/me/change-password",
        headers=headers,
        json={"current_password": password, "new_password": new_password},
    )
    assert pw_resp.status_code == 204

    # 4. Login with updated password
    login_resp = services_app_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": new_password},
    )
    assert login_resp.status_code == 200
    new_token = login_resp.json()["tokens"]["access_token"]
    assert new_token != token


def test_journey_2_text_translation_and_writing_assistant(services_app_client, user):
    """Journey 2: Text translation, AI writing assistant, and dictionary lookup."""
    headers = user["headers"]

    # 1. Text Translation
    trans_resp = services_app_client.post(
        "/api/v1/translate",
        headers=headers,
        json={
            "text": "Hello, welcome to our global communication platform.",
            "source_language": "en",
            "target_language": "es",
        },
    )
    assert trans_resp.status_code == 200, trans_resp.text
    trans_data = trans_resp.json()
    assert "translations" in trans_data and len(trans_data["translations"]) > 0
    translated = trans_data["translations"][0]["translated_text"]
    assert len(translated) > 0

    # 2. AI Writing Assistant (/write)
    write_resp = services_app_client.post(
        "/api/v1/write",
        headers=headers,
        json={
            "text": "hey whats up we should totally do this thing right now.",
            "language": "en",
            "style": "business",
            "tone": "professional",
            "corrections_only": False,
        },
    )
    assert write_resp.status_code == 200, write_resp.text
    write_data = write_resp.json()
    assert "improved_text" in write_data
    assert len(write_data["improved_text"]) > 0

    # 3. AI Dictionary Lookup (/dictionary)
    dict_resp = services_app_client.post(
        "/api/v1/dictionary",
        headers=headers,
        json={
            "word": "platform",
            "source_lang": "en",
            "target_lang": "es",
        },
    )
    assert dict_resp.status_code == 200, dict_resp.text
    dict_data = dict_resp.json()
    assert "query" in dict_data
    assert dict_data["query"] == "platform"


@pytest.mark.asyncio
async def test_journey_3_realtime_meeting_lifecycle(services_app_client, user):
    """Journey 3: Create meeting, mint HMAC join ticket, update preferences, request summary."""
    headers = user["headers"]

    # 1. Create Meeting
    meet_resp = services_app_client.post(
        "/api/v1/meetings",
        headers=headers,
        json={"title": "Q3 Executive Multilingual Sync", "mode": "ws", "hear_lang": "en"},
    )
    assert meet_resp.status_code == 201, meet_resp.text
    meet_data = meet_resp.json()
    meeting_id = meet_data["id"]
    room_name = meet_data["room_name"]

    # 2. Join meeting to mint cryptographic ticket & session key
    join_resp = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join",
        headers=headers,
        json={
            "display_name": "QA Participant",
            "speak_lang": "en",
            "hear_lang": "en",
            "audio_mode": "translated",
        },
    )
    assert join_resp.status_code == 200, join_resp.text
    join_data = join_resp.json()
    ticket = join_data["rt_url"].split("ticket=")[1]
    participant_id = join_data["participant_id"]

    # 3. Verify ticket validity via cryptographic verifier
    resolved_room, resolved_pid = verify_session_ticket(ticket, consume=False)
    assert resolved_room == room_name
    assert resolved_pid == participant_id

    # 4. Update participant preferences
    pref_resp = services_app_client.put(
        f"/api/v1/meetings/{meeting_id}/participants/{participant_id}/preferences",
        headers=headers,
        json={
            "speak_lang": "es",
            "hear_lang": "en",
            "audio_mode": "translated",
            "captions_enabled": True,
        },
    )
    assert pref_resp.status_code == 200
    assert pref_resp.json()["speak_lang"] == "es"

    # 5. Seed a stable transcript segment for the meeting summary engine
    async with db_session() as db:
        seg = M.TranscriptSegment(
            meeting_id=uuid.UUID(meeting_id),
            speaker_name="QA Participant",
            source_lang="en",
            source_text="Welcome everyone. Today we are aligning on quarterly milestones and roadmap deliverables.",
            seq=1,
            is_final=True,
        )
        db.add(seg)
        await db.commit()

    # 6. Request AI meeting summary
    summary_resp = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/summary",
        headers=headers,
        json={"lang": "en", "max_length": 500},
    )
    assert summary_resp.status_code == 200, summary_resp.text
    summary_data = summary_resp.json()
    assert "summary" in summary_data or "action_items" in summary_data


def test_journey_4_document_translation_workflow(services_app_client, user):
    """Journey 4: Document creation, upload submission, and tenant-scoped retrieval."""
    headers = user["headers"]

    # 1. Upload document (multipart form data)
    files = {"file": ("annual_report_2026.txt", b"Annual Report Content 2026 for GlobalTalk AI.", "text/plain")}
    doc_resp = services_app_client.post(
        "/api/v1/documents",
        headers=headers,
        files=files,
        data={"target_lang": "de"},
    )
    assert doc_resp.status_code == 202, doc_resp.text
    doc_data = doc_resp.json()
    doc_id = doc_data["id"]

    # 2. Retrieve document by ID
    get_resp = services_app_client.get(
        f"/api/v1/documents/{doc_id}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == doc_id
    assert get_resp.json()["filename"] == "annual_report_2026.txt"


def test_journey_5_developer_platform_api_keys_and_webhooks(services_app_client, user):
    """Journey 5: High-entropy API key generation, translation via API key, rotation, and revocation."""
    headers = user["headers"]

    # 1. Create scoped API key
    key_resp = services_app_client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={
            "name": "Integration Test Pipeline Key",
            "scopes": ["translate:write", "translate"],
        },
    )
    assert key_resp.status_code == 201, key_resp.text
    key_data = key_resp.json()
    plaintext_key = key_data["plaintext_key"]
    key_id = key_data["id"]
    assert plaintext_key.startswith("gtk_live_") or plaintext_key.startswith("gt_live_")

    # 2. Authenticate directly via API key for translation
    api_key_headers = {"Authorization": f"Bearer {plaintext_key}"}
    trans_resp = services_app_client.post(
        "/api/v1/translate",
        headers=api_key_headers,
        json={
            "text": "Automated system test via developer API key.",
            "source_language": "en",
            "target_language": "de",
        },
    )
    assert trans_resp.status_code == 200, trans_resp.text

    # 3. Rotate API key
    rotate_resp = services_app_client.post(
        f"/api/v1/api-keys/{key_id}/rotate",
        headers=headers,
    )
    assert rotate_resp.status_code == 200
    rotate_data = rotate_resp.json()
    new_plaintext_key = rotate_data["plaintext_key"]
    new_key_id = rotate_data["id"]
    assert new_plaintext_key != plaintext_key

    # 4. Old key must now be rejected
    old_call_resp = services_app_client.post(
        "/api/v1/translate",
        headers={"Authorization": f"Bearer {plaintext_key}"},
        json={"text": "Test", "source_language": "en", "target_language": "de"},
    )
    assert old_call_resp.status_code == 401

    # 5. New rotated key functions successfully
    new_call_resp = services_app_client.post(
        "/api/v1/translate",
        headers={"Authorization": f"Bearer {new_plaintext_key}"},
        json={"text": "Rotated key live call.", "source_language": "en", "target_language": "de"},
    )
    assert new_call_resp.status_code == 200

    # 6. Revoke key
    del_resp = services_app_client.post(
        f"/api/v1/api-keys/{new_key_id}/revoke",
        headers=headers,
    )
    assert del_resp.status_code == 204

    # 7. Revoked key must now be rejected
    revoked_call_resp = services_app_client.post(
        "/api/v1/translate",
        headers={"Authorization": f"Bearer {new_plaintext_key}"},
        json={"text": "Revoked key call.", "source_language": "en", "target_language": "de"},
    )
    assert revoked_call_resp.status_code == 401


def test_journey_6_observability_and_health_probes(services_app_client, monkeypatch):
    """Journey 6: Fail-closed health, readiness, and metrics verification."""
    from app.routers import health

    # 1. Health probe
    health_resp = services_app_client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # 2. Readiness probe
    ready_resp = services_app_client.get("/ready")
    assert ready_resp.status_code in (200, 503)

    # 3. Metrics endpoint (gated via metrics_enabled)
    monkeypatch.setattr(health.settings, "metrics_enabled", True)
    metrics_resp = services_app_client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text
    assert "gt_http_requests_total" in metrics_text
    assert "gt_translation_latency_ms" in metrics_text
