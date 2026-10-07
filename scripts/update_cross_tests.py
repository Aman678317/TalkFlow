import sys

tests_append = '''

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
            "entries": "revenue\\tUmsatz\\nprofit\\tGewinn",
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
'''

with open("tests/test_cross_tenant_security.py", "r", encoding="utf-8") as f:
    orig = f.read()

if "test_cross_tenant_style_profile_isolation" not in orig:
    with open("tests/test_cross_tenant_security.py", "a", encoding="utf-8") as f:
        f.write(tests_append)
    print("Appended tests successfully.")
else:
    print("Tests already present.")

