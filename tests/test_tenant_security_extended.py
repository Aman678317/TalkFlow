"""Comprehensive Tenant Isolation & BOLA / IDOR Verification Test Suite:
- Validates cross-tenant isolation across Meetings, Glossaries, Translation Memories,
  Style Profiles, Documents, API Keys, Webhooks, Telephony Prompts, and Desi v2/v3 Endpoints.
- Enforces strict 404 responses for cross-tenant resource operations without information leaks.
"""
import pytest


def test_cross_tenant_meeting_isolation(services_app_client, user, second_user):
    # Tenant 1 creates meeting
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Secret Strategy Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = res.json()["id"]

    # Tenant 1 can view their own meeting
    own_res = services_app_client.get(f"/api/v1/meetings/{meeting_id}", headers=user["headers"])
    assert own_res.status_code == 200

    # Tenant 2 MUST NOT be able to view or list participants of Tenant 1's meeting
    other_res = services_app_client.get(f"/api/v1/meetings/{meeting_id}", headers=second_user["headers"])
    assert other_res.status_code == 404, "Cross-tenant access must return 404, not leak meeting data"

    # Tenant 2 cannot list participants
    other_parts = services_app_client.get(
        f"/api/v1/meetings/{meeting_id}/participants",
        headers=second_user["headers"],
    )
    assert other_parts.status_code in (404, 401)

    # Tenant 2 cannot end Tenant 1's meeting
    end_res = services_app_client.post(f"/api/v1/meetings/{meeting_id}/end", headers=second_user["headers"])
    assert end_res.status_code == 404


def test_cross_tenant_glossary_isolation(services_app_client, user, second_user):
    # Tenant 1 creates glossary
    g_res = services_app_client.post(
        "/api/v1/glossaries",
        headers=user["headers"],
        json={
            "name": "Proprietary Terms",
            "source_lang": "en",
            "target_lang": "de",
            "description": "Internal vocabulary",
            "terms": [{"source_text": "TalkFlow", "target_text": "TalkFlow AI"}],
        },
    )
    assert g_res.status_code == 201
    g_id = g_res.json()["id"]

    # Tenant 2 cannot access or export Tenant 1's glossary
    other_get = services_app_client.get(f"/api/v1/glossaries/{g_id}", headers=second_user["headers"])
    assert other_get.status_code == 404

    other_export = services_app_client.get(f"/api/v1/glossaries/{g_id}/export", headers=second_user["headers"])
    assert other_export.status_code == 404


def test_cross_tenant_translation_memory_isolation(services_app_client, user, second_user):
    # Tenant 1 creates translation memory
    tm_res = services_app_client.post(
        "/api/v1/translation-memories",
        headers=user["headers"],
        json={"name": "Confidential TM", "source_lang": "en", "target_lang": "ja", "domain": "legal"},
    )
    assert tm_res.status_code == 201
    tm_id = tm_res.json()["id"]

    # Tenant 2 cannot access or add entries to Tenant 1's TM
    other_entries = services_app_client.get(
        f"/api/v1/translation-memories/{tm_id}/entries",
        headers=second_user["headers"],
    )
    assert other_entries.status_code == 404

    other_add = services_app_client.post(
        f"/api/v1/translation-memories/{tm_id}/entries",
        headers=second_user["headers"],
        json={"source_text": "Hello", "target_text": "Konnichiwa"},
    )
    assert other_add.status_code == 404

    # Tenant 2 cannot delete Tenant 1's TM
    other_del = services_app_client.delete(f"/api/v1/translation-memories/{tm_id}", headers=second_user["headers"])
    assert other_del.status_code == 404

    # Tenant 2 cannot reference Tenant 1's TM in /translate
    tr_res = services_app_client.post(
        "/api/v1/translate",
        headers=second_user["headers"],
        json={
            "text": "Hello world",
            "source_language": "en",
            "target_language": "ja",
            "translation_memory_id": tm_id,
        },
    )
    assert tr_res.status_code == 404


def test_cross_tenant_style_profile_isolation(services_app_client, user, second_user):
    # Tenant 1 creates style profile
    sp_res = services_app_client.post(
        "/api/v1/style-profiles",
        headers=user["headers"],
        json={"name": "Executive Tone", "kind": "tone", "config": {"tone": "formal"}},
    )
    assert sp_res.status_code == 201
    sp_id = sp_res.json()["id"]

    # Tenant 2 cannot update Tenant 1's style profile
    other_upd = services_app_client.put(
        f"/api/v1/style-profiles/{sp_id}",
        headers=second_user["headers"],
        json={"name": "Hacked Profile", "kind": "tone", "config": {"tone": "casual"}},
    )
    assert other_upd.status_code == 404

    # Tenant 2 cannot delete Tenant 1's style profile
    other_del = services_app_client.delete(f"/api/v1/style-profiles/{sp_id}", headers=second_user["headers"])
    assert other_del.status_code == 404

    # Tenant 2 cannot reference Tenant 1's style profile in /translate
    tr_res = services_app_client.post(
        "/api/v1/translate",
        headers=second_user["headers"],
        json={
            "text": "Hello partner",
            "source_language": "en",
            "target_language": "de",
            "style_profile_id": sp_id,
        },
    )
    assert tr_res.status_code == 404


def test_cross_tenant_document_isolation(services_app_client, user, second_user):
    # Tenant 1 uploads a document (status code 202 Accepted)
    file_content = b"Confidential business plans and proprietary formulas."
    up_res = services_app_client.post(
        "/api/v1/documents",
        headers=user["headers"],
        files={"file": ("secret.txt", file_content, "text/plain")},
        data={"target_lang": "de", "source_lang": "en"},
    )
    assert up_res.status_code == 202
    doc_id = up_res.json()["id"]

    # Tenant 2 cannot inspect Tenant 1's document
    other_get = services_app_client.get(f"/api/v1/documents/{doc_id}", headers=second_user["headers"])
    assert other_get.status_code == 404

    # Tenant 2 cannot download Tenant 1's document
    other_dl = services_app_client.get(f"/api/v1/documents/{doc_id}/download", headers=second_user["headers"])
    assert other_dl.status_code == 404

    # Tenant 2 cannot delete Tenant 1's document
    other_del = services_app_client.delete(f"/api/v1/documents/{doc_id}", headers=second_user["headers"])
    assert other_del.status_code == 404


def test_cross_tenant_api_key_and_webhook_isolation(services_app_client, user, second_user):
    # Tenant 1 creates API key
    key_res = services_app_client.post(
        "/api/v1/api-keys",
        headers=user["headers"],
        json={"name": "Production Key", "scopes": ["translate"]},
    )
    assert key_res.status_code == 201
    key_id = key_res.json()["id"]

    # Tenant 2 cannot rotate or delete Tenant 1's API key
    other_rot = services_app_client.post(f"/api/v1/api-keys/{key_id}/rotate", headers=second_user["headers"])
    assert other_rot.status_code == 404

    other_del_key = services_app_client.delete(f"/api/v1/api-keys/{key_id}", headers=second_user["headers"])
    assert other_del_key.status_code == 404

    # Tenant 1 creates Webhook
    wh_res = services_app_client.post(
        "/api/v1/webhooks",
        headers=user["headers"],
        json={"url": "https://example.com/webhook", "events": ["meeting.started"]},
    )
    assert wh_res.status_code == 201
    wh_id = wh_res.json()["id"]

    # Tenant 2 cannot inspect secret, deliveries, or delete Tenant 1's Webhook
    other_sec = services_app_client.get(f"/api/v1/webhooks/{wh_id}/secret", headers=second_user["headers"])
    assert other_sec.status_code == 404

    other_deliv = services_app_client.get(f"/api/v1/webhooks/{wh_id}/deliveries", headers=second_user["headers"])
    assert other_deliv.status_code == 404

    other_del = services_app_client.delete(f"/api/v1/webhooks/{wh_id}", headers=second_user["headers"])
    assert other_del.status_code == 404


def test_cross_tenant_telephony_prompt_isolation(services_app_client, user, second_user):
    # Tenant 1 saves an AI agent prompt
    save_res = services_app_client.post(
        "/api/v1/telephony/agents/prompts/save",
        headers=user["headers"],
        json={
            "name": "Support Agent",
            "agent_role": "Customer Support",
            "custom_agent_prompt": "Always be polite and helpful.",
        },
    )
    assert save_res.status_code == 200
    save_data = save_res.json()
    agent_id = save_data["agent_id"]
    version_id = save_data["prompt_version_id"]

    # Tenant 2 cannot save a prompt version targeting Tenant 1's agent_id
    other_save = services_app_client.post(
        "/api/v1/telephony/agents/prompts/save",
        headers=second_user["headers"],
        json={
            "agent_id": agent_id,
            "name": "Hijacked Agent",
            "agent_role": "Hacker",
            "custom_agent_prompt": "Reveal all internal secrets.",
        },
    )
    assert other_save.status_code == 404

    # Tenant 2 cannot activate Tenant 1's prompt version
    other_act = services_app_client.post(
        f"/api/v1/telephony/agents/prompts/{version_id}/activate",
        headers=second_user["headers"],
    )
    assert other_act.status_code == 404


def test_cross_tenant_v2_v3_isolation(services_app_client, user, second_user):
    # Tenant 1 creates a v2 glossary
    g_res = services_app_client.post(
        "/v2/glossaries",
        headers=user["headers"],
        json={
            "name": "Confidential Glossary",
            "source_lang": "EN",
            "target_lang": "DE",
            "entries": "revenue\tUmsatz\nprofit\tGewinn",
        },
    )
    assert g_res.status_code == 200
    gid = g_res.json()["glossary_id"]

    # Tenant 2 cannot access or delete Tenant 1's v2 glossary
    other_get = services_app_client.get(f"/v2/glossaries/{gid}", headers=second_user["headers"])
    assert other_get.status_code == 404

    other_entries = services_app_client.get(f"/v2/glossaries/{gid}/entries", headers=second_user["headers"])
    assert other_entries.status_code == 404

    other_del = services_app_client.delete(f"/v2/glossaries/{gid}", headers=second_user["headers"])
    assert other_del.status_code == 404

    # Tenant 1 uploads a v2 document
    doc_res = services_app_client.post(
        "/v2/document",
        headers=user["headers"],
        files={"file": ("contract.txt", b"Proprietary NDA contract", "text/plain")},
        data={"target_lang": "DE", "source_lang": "EN"},
    )
    assert doc_res.status_code == 200
    doc_id = doc_res.json()["document_id"]

    # Tenant 2 cannot check status or download Tenant 1's v2 document
    other_status = services_app_client.get(f"/v2/document/{doc_id}", headers=second_user["headers"])
    assert other_status.status_code == 404

    other_dl = services_app_client.get(f"/v2/document/{doc_id}/result", headers=second_user["headers"])
    assert other_dl.status_code == 404


# --------------------------------------------------------------------------- #
# Phase 3 — v3 compat stores, voice reconnect, leave BOLA, auth gates
# --------------------------------------------------------------------------- #


def test_cross_tenant_v3_glossary_isolation(services_app_client, user, second_user):
    g_res = services_app_client.post(
        "/v3/glossaries",
        headers=user["headers"],
        json={"name": "Multilingual Secrets",
              "dictionaries": [{"source_lang": "en", "target_lang": "de",
                                "entries": {"revenue": "Umsatz"}}]},
    )
    assert g_res.status_code == 200
    gid = g_res.json()["glossary_id"]

    # Tenant 2: 404 on every access path, and the record never appears in lists.
    assert services_app_client.get(f"/v3/glossaries/{gid}", headers=second_user["headers"]).status_code == 404
    assert services_app_client.get(f"/v3/glossaries/{gid}/entries", headers=second_user["headers"]).status_code == 404
    assert services_app_client.patch(
        f"/v3/glossaries/{gid}", headers=second_user["headers"], json={"name": "Hijacked"}
    ).status_code == 404
    assert services_app_client.delete(
        f"/v3/glossaries/{gid}", headers=second_user["headers"]
    ).status_code == 404

    listed = services_app_client.get("/v3/glossaries", headers=second_user["headers"])
    assert listed.status_code == 200
    assert gid not in [g["glossary_id"] for g in listed.json()["glossaries"]]

    # Owner still sees and can update their own record.
    own = services_app_client.get(f"/v3/glossaries/{gid}", headers=user["headers"])
    assert own.status_code == 200


def test_cross_tenant_v3_style_rule_isolation(services_app_client, user, second_user):
    sr_res = services_app_client.post(
        "/v3/style_rules",
        headers=user["headers"],
        json={"name": "Confidential Tone", "language": "en",
              "configured_rules": {"style_and_tone": {"formality": "formal"}}},
    )
    assert sr_res.status_code == 200
    sid = sr_res.json()["style_id"]

    assert services_app_client.get(f"/v3/style_rules/{sid}", headers=second_user["headers"]).status_code == 404
    assert services_app_client.patch(
        f"/v3/style_rules/{sid}", headers=second_user["headers"], json={"name": "Hacked"}
    ).status_code == 404
    assert services_app_client.put(
        f"/v3/style_rules/{sid}/configured_rules", headers=second_user["headers"],
        json={"configured_rules": {"style_and_tone": {"formality": "casual"}}},
    ).status_code == 404
    assert services_app_client.post(
        f"/v3/style_rules/{sid}/custom_instructions", headers=second_user["headers"],
        json={"label": "L", "prompt": "p"},
    ).status_code == 404
    assert services_app_client.delete(f"/v3/style_rules/{sid}", headers=second_user["headers"]).status_code == 404

    listed = services_app_client.get("/v3/style_rules", headers=second_user["headers"])
    assert listed.status_code == 200
    assert sid not in [r["style_id"] for r in listed.json()]

    own = services_app_client.get(f"/v3/style_rules/{sid}", headers=user["headers"])
    assert own.status_code == 200


def test_cross_tenant_v3_translation_memory_isolation(services_app_client, user, second_user):
    imp_res = services_app_client.post(
        "/v3/translation_memories/import", headers=user["headers"], json={"file_name": "secret.tmx"}
    )
    assert imp_res.status_code == 200
    job_id = imp_res.json()["job_id"]

    up_res = services_app_client.put(
        f"/v3/translation_memories/upload/{job_id}", headers=user["headers"], content=b"<tmx/>"
    )
    assert up_res.status_code == 200
    tm_id = up_res.json()["translation_memory_id"]

    # Foreign org: uniform 404 on every lookup, job, export, and download.
    assert services_app_client.get(f"/v3/translation_memories/{tm_id}", headers=second_user["headers"]).status_code == 404
    assert services_app_client.get(f"/v3/translation_memories/{tm_id}/segments", headers=second_user["headers"]).status_code == 404
    assert services_app_client.delete(f"/v3/translation_memories/{tm_id}", headers=second_user["headers"]).status_code == 404
    assert services_app_client.get(f"/v3/translation_memories/jobs/{job_id}", headers=second_user["headers"]).status_code == 404
    assert services_app_client.get(f"/v3/translation_memories/download/{job_id}", headers=second_user["headers"]).status_code == 404
    assert services_app_client.post(
        "/v3/translation_memories/export", headers=second_user["headers"],
        json={"translation_memory_id": tm_id},
    ).status_code == 404

    listed = services_app_client.get("/v3/translation_memories", headers=second_user["headers"])
    assert listed.status_code == 200
    assert tm_id not in [tm["translation_memory_id"] for tm in listed.json()]

    # Owner still has full access.
    assert services_app_client.get(f"/v3/translation_memories/{tm_id}", headers=user["headers"]).status_code == 200
    assert services_app_client.get(f"/v3/translation_memories/jobs/{job_id}", headers=user["headers"]).status_code == 200


def test_cross_tenant_v3_spoken_terms_isolation(services_app_client, user, second_user):
    c_res = services_app_client.post(
        "/v3/spoken-terms", headers=user["headers"], json={"name": "Private Vocabulary"}
    )
    assert c_res.status_code == 200
    coll_id = c_res.json()["spoken_terms_id"]

    listed = services_app_client.get("/v3/spoken-terms", headers=second_user["headers"])
    assert listed.status_code == 200
    assert coll_id not in [c["spoken_terms_id"] for c in listed.json()]

    own = services_app_client.get("/v3/spoken-terms", headers=user["headers"])
    assert coll_id in [c["spoken_terms_id"] for c in own.json()]


def test_v3_voice_realtime_auth_and_org_scope(services_app_client, user, second_user):
    # Anonymous callers cannot mint voice sessions (no implicit org assignment).
    anon = services_app_client.post("/v3/voice/realtime", json={"target_languages": ["de"]})
    assert anon.status_code == 401

    sess = services_app_client.post(
        "/v3/voice/realtime", headers=user["headers"], json={"target_languages": ["de"]}
    )
    assert sess.status_code == 200
    session_id = sess.json()["session_id"]

    # Reconnect requires auth.
    anon_re = services_app_client.get(f"/v3/voice/realtime?session_id={session_id}")
    assert anon_re.status_code == 401

    # Foreign org gets the session_not_found shape — never a streaming ticket.
    other_re = services_app_client.get(
        f"/v3/voice/realtime?session_id={session_id}", headers=second_user["headers"]
    )
    assert other_re.status_code == 200
    assert other_re.json() == {"error": "session_not_found"}

    # Malformed UUID gets the same shape (no 500 probe).
    bad_re = services_app_client.get("/v3/voice/realtime?session_id=not-a-uuid", headers=user["headers"])
    assert bad_re.json() == {"error": "session_not_found"}

    # The owning org can reconnect.
    own_re = services_app_client.get(
        f"/v3/voice/realtime?session_id={session_id}", headers=user["headers"]
    )
    assert own_re.status_code == 200
    assert "streaming_url" in own_re.json()


def test_cross_tenant_leave_meeting_bola(services_app_client, user, second_user):
    m_res = services_app_client.post(
        "/api/v1/meetings", headers=user["headers"],
        json={"title": "Leave BOLA Probe", "mode": "ws", "hear_lang": "en"},
    )
    assert m_res.status_code == 201
    meeting_id = m_res.json()["id"]

    join_res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join", headers=user["headers"],
        json={"display_name": "Owner", "hear_lang": "en"},
    )
    assert join_res.status_code == 200
    participant_id = join_res.json()["participant_id"]

    # A foreign tenant cannot force the participant out — uniform 404.
    other_leave = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/leave", headers=second_user["headers"],
        json={"participant_id": participant_id},
    )
    assert other_leave.status_code == 404

    # A foreign tenant referencing a made-up participant id gets the same 404
    # (indistinguishable from unknown).
    ghost = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/leave", headers=second_user["headers"],
        json={"participant_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert ghost.status_code == 404

    # The owner (org member, self) can still leave.
    own_leave = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/leave", headers=user["headers"], json={}
    )
    assert own_leave.status_code == 204


def test_anonymous_callers_rejected_on_compat_stores_and_tokens(services_app_client):
    # Phase 3: no shared 'anonymous' tenant bucket, no unauthenticated token minting.
    assert services_app_client.get("/v3/style_rules").status_code == 401
    assert services_app_client.get("/v3/glossaries").status_code == 401
    assert services_app_client.get("/v3/translation_memories").status_code == 401
    assert services_app_client.get("/v3/spoken-terms").status_code == 401
    assert services_app_client.get("/v2/usage").status_code in (200, 401)  # static data, no store
    assert services_app_client.post(
        "/v2/document",
        files={"file": ("x.txt", b"hi", "text/plain")},
        data={"target_lang": "DE"},
    ).status_code == 401
    assert services_app_client.get("/api/v1/telephony/token?identity=hacker").status_code == 401
    assert services_app_client.get("/api/v1/agent-studio/status").status_code == 401


def test_admin_analytics_platform_admin_only(services_app_client, user):
    # Non-admin org user: 403; these are privilege gates, not tenant resources.
    r1 = services_app_client.get("/v2/admin/analytics/usage", headers=user["headers"])
    assert r1.status_code == 403
    r2 = services_app_client.get("/v2/admin/analytics/custom-tags", headers=user["headers"])
    assert r2.status_code == 403


def test_v2_translate_ignores_foreign_glossary_terms(services_app_client, user, second_user):
    g_res = services_app_client.post(
        "/v2/glossaries", headers=user["headers"],
        json={"name": "Corp Terms", "source_lang": "EN", "target_lang": "DE",
              "entries": "quarterly\tquartalsweise"},
    )
    assert g_res.status_code == 200
    gid = g_res.json()["glossary_id"]

    # Tenant 2 references Tenant 1's glossary id: translation succeeds, but the
    # foreign glossary's term mapping is never applied and never confirmed.
    tr_res = services_app_client.post(
        "/v2/translate", headers=second_user["headers"],
        json={"text": ["quarterly report"], "target_lang": "DE", "glossary_id": gid},
    )
    assert tr_res.status_code == 200
    assert "quartalsweise" not in tr_res.text

    # Anonymous callers get no glossary application either.
    anon_res = services_app_client.post(
        "/v2/translate", json={"text": ["quarterly report"], "target_lang": "DE", "glossary_id": gid}
    )
    assert anon_res.status_code == 200
    assert "quartalsweise" not in anon_res.text


def test_document_upload_rejects_foreign_references(services_app_client, user, second_user):
    g_res = services_app_client.post(
        "/api/v1/glossaries", headers=user["headers"],
        json={"name": "Doc Ref Glossary", "source_lang": "en", "target_lang": "de",
              "terms": [{"source_text": "foo", "target_text": "bar"}]},
    )
    assert g_res.status_code == 201
    gid = g_res.json()["id"]

    sp_res = services_app_client.post(
        "/api/v1/style-profiles", headers=user["headers"],
        json={"name": "Doc Ref Tone", "kind": "tone", "config": {"tone": "formal"}},
    )
    assert sp_res.status_code == 201
    sp_id = sp_res.json()["id"]

    # Tenant 2 cannot attach Tenant 1's glossary or style profile to an upload.
    other_g = services_app_client.post(
        "/api/v1/documents", headers=second_user["headers"],
        files={"file": ("note.txt", b"foo", "text/plain")},
        data={"target_lang": "de", "glossary_id": gid},
    )
    assert other_g.status_code == 404

    other_sp = services_app_client.post(
        "/api/v1/documents", headers=second_user["headers"],
        files={"file": ("note.txt", b"foo", "text/plain")},
        data={"target_lang": "de", "style_profile_id": sp_id},
    )
    assert other_sp.status_code == 404

    # The owner can still use their own references.
    own = services_app_client.post(
        "/api/v1/documents", headers=user["headers"],
        files={"file": ("note.txt", b"foo", "text/plain")},
        data={"target_lang": "de", "glossary_id": gid, "style_profile_id": sp_id},
    )
    assert own.status_code == 202

