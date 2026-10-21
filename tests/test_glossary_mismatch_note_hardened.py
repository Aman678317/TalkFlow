"""Glossary mismatch honesty (2026-10-20 local audit).

A requested glossary whose declared language pair does not match the translation
pair was silently dropped before this audit: the translation simply used the
requested pair with zero glossary signal. The response now carries an honest
`glossary_note` saying the glossary was NOT applied (and why). Matching pairs
carry no note and keep the term enforcement; the refusal-to-guess behavior is
unchanged — only the silence is.
"""
from __future__ import annotations

import uuid


def _make_glossary(client, user, source_lang: str, target_lang: str) -> str:
    r = client.post("/api/v1/glossaries", headers=user["headers"], json={
        "name": f"Audit {source_lang}-{target_lang} {uuid.uuid4().hex[:6]}",
        "source_lang": source_lang,
        "target_lang": target_lang,
        "description": "local-audit glossary",
        "terms": [{"source_text": "AuditBrand", "target_text": "ऑडिटब्रांड"}],
    })
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    r2 = client.post(f"/api/v1/glossaries/{gid}/activate", headers=user["headers"])
    assert r2.status_code in (200, 204), r2.text
    return gid


def test_translate_reports_mismatched_glossary_pair(services_app_client, user):
    header = user["headers"]
    gid = _make_glossary(services_app_client, user, "en", "hi")
    r = services_app_client.post("/api/v1/translate", headers=header, json={
        "text": f"AuditBrand reported strong growth this quarter. {uuid.uuid4().hex[:8]}",
        "source_language": "en",
        "target_language": "de",
        "glossary_id": gid,
    })
    assert r.status_code == 200, r.text
    out = r.json()["translations"][0]
    note = out["glossary_note"]
    assert note is not None
    assert "not applied" in note
    assert "mismatch" in note
    assert "en→hi" in note and "de" in note


def test_translate_matching_glossary_carries_no_note(services_app_client, user):
    header = user["headers"]
    gid = _make_glossary(services_app_client, user, "en", "hi")
    r = services_app_client.post("/api/v1/translate", headers=header, json={
        "text": f"AuditBrand reported strong growth this quarter. {uuid.uuid4().hex[:8]}",
        "source_language": "en",
        "target_language": "hi",
        "glossary_id": gid,
    })
    assert r.status_code == 200, r.text
    out = r.json()["translations"][0]
    assert out["glossary_note"] is None
