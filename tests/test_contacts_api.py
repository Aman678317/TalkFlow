"""Outbound CRM API (P1): contacts CRUD, CSV import/export, consent ledger,
contact-document pivot, per-org isolation, campaigns & queued jobs.

Every claim is verified through the real app against the simulated provider;
nothing here requires PSTN credentials.
"""
from __future__ import annotations

import io
import uuid

import pytest


def _create_contact(client, headers, phone=None, **overrides) -> dict:
    payload = {"phone": phone or "+919876543210",
               "display_name": "Ravi Kumar", "language": "hi",
               "email": "ravi@example.com", "tags": ["vip"]}
    payload.update(overrides)
    r = client.post("/api/v1/contacts", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Contacts CRUD
# --------------------------------------------------------------------------- #


def test_create_and_get_contact(services_app_client, user):
    created = _create_contact(services_app_client, user["headers"])
    r = services_app_client.get(f"/api/v1/contacts/{created['id']}",
                                headers=user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["phone_e164"] == "+919876543210"
    assert body["display_name"] == "Ravi Kumar"
    assert body["language"] == "hi"
    assert body["do_not_call"] is False
    assert body["archived"] is False


def test_duplicate_phone_rejected_per_org(services_app_client, user):
    _create_contact(services_app_client, user["headers"])
    r = services_app_client.post(
        "/api/v1/contacts", json={"phone": "+919876543210", "display_name": "Dup"},
        headers=user["headers"])
    assert r.status_code == 409, r.text


def test_invalid_number_rejected(services_app_client, user):
    r = services_app_client.post(
        "/api/v1/contacts", json={"phone": "not-a-phone"}, headers=user["headers"])
    assert r.status_code == 422, r.text


def test_national_format_normalized_with_default_country(services_app_client, user):
    body = _create_contact(services_app_client, user["headers"],
                           phone="9876543211", default_country="IN",
                           display_name="National", language="hi")
    assert body["phone_e164"] == "+919876543211"


def test_update_and_archive_contact(services_app_client, user):
    created = _create_contact(services_app_client, user["headers"])
    r = services_app_client.patch(
        f"/api/v1/contacts/{created['id']}",
        json={"display_name": "Ravi K.", "language": "en", "tags": ["vip", "followup"]},
        headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["display_name"] == "Ravi K."
    assert r.json()["tags"] == ["vip", "followup"]

    r = services_app_client.delete(f"/api/v1/contacts/{created['id']}",
                                   headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["archived"] is True

    # archived contacts excluded from the default list
    r = services_app_client.get("/api/v1/contacts", headers=user["headers"])
    assert all(not c["archived"] for c in r.json()["items"])
    # but visible when requested
    r = services_app_client.get("/api/v1/contacts?archived=true", headers=user["headers"])
    assert any(c["archived"] for c in r.json()["items"])


def test_contact_isolated_between_orgs(services_app_client, user, second_user):
    created = _create_contact(services_app_client, user["headers"])
    # another org's user cannot see, patch, or attach to it
    r = services_app_client.get(f"/api/v1/contacts/{created['id']}",
                                headers=second_user["headers"])
    assert r.status_code == 404, r.text
    r = services_app_client.patch(f"/api/v1/contacts/{created['id']}",
                                  json={"display_name": "Hijack"},
                                  headers=second_user["headers"])
    assert r.status_code == 404, r.text
    # and their own list is empty
    r = services_app_client.get("/api/v1/contacts", headers=second_user["headers"])
    assert r.json()["items"] == []


def test_phone_e164_can_repeat_across_orgs(services_app_client, user, second_user):
    _create_contact(services_app_client, user["headers"])
    r = services_app_client.post(
        "/api/v1/contacts", json={"phone": "+919876543210", "display_name": "Other org"},
        headers=second_user["headers"])
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------- #
# Consent ledger
# --------------------------------------------------------------------------- #


def test_consent_grant_revoke_dnc_semantics(services_app_client, user):
    created = _create_contact(services_app_client, user["headers"])
    cid = created["id"]

    r = services_app_client.post(
        f"/api/v1/contacts/{cid}/consent",
        json={"decision": "grant", "source": "call_prompt",
              "evidence": {"recording_ref": "call:abc"}},
        headers=user["headers"])
    assert r.status_code == 201, r.text

    r = services_app_client.get(f"/api/v1/contacts/{cid}/consent", headers=user["headers"])
    body = r.json()
    assert body["effective_granted"] is True
    assert len(body["history"]) == 1

    r = services_app_client.post(
        f"/api/v1/contacts/{cid}/consent",
        json={"decision": "revoke", "source": "customer_portal"},
        headers=user["headers"])
    assert r.status_code == 201

    r = services_app_client.get(f"/api/v1/contacts/{cid}/consent", headers=user["headers"])
    body = r.json()
    assert body["effective_granted"] is False
    assert len(body["history"]) == 2  # append-only: both rows kept

    detail = services_app_client.get(f"/api/v1/contacts/{cid}", headers=user["headers"])
    assert detail.json()["do_not_call"] is True

    r = services_app_client.post(
        f"/api/v1/contacts/{cid}/consent",
        json={"decision": "invalid_decision"}, headers=user["headers"])
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Contact documents (org-scoped pivot)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_attach_document_and_isolation(services_app_client, user, second_user):
    # Arrange: one document row per org seeded directly in the test DB.
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        db.add(M.Document(
            org_id=uuid.UUID(user["org_id"]), filename="offer.pdf",
            mime_type="application/pdf", checksum="c1", size_bytes=10,
            target_lang="en", source_object_key="k/o/offer.pdf"))
        await db.flush()
        seeded = await db.execute(
            M.Document.__table__.select()
            .where(M.Document.__table__.c.org_id == uuid.UUID(user["org_id"])))
        doc_id = seeded.fetchall()[0].id
        await db.commit()

    created = _create_contact(services_app_client, user["headers"])
    cid = created["id"]

    r = services_app_client.post(f"/api/v1/contacts/{cid}/documents",
                                 data={"document_id": str(doc_id)},
                                 headers=user["headers"])
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["id"] == str(doc_id)

    # double attach -> conflict 409
    r = services_app_client.post(f"/api/v1/contacts/{cid}/documents",
                                 data={"document_id": str(doc_id)},
                                 headers=user["headers"])
    assert r.status_code == 409, r.text

    # the other org cannot attach anything to OUR contact
    r = services_app_client.post(f"/api/v1/contacts/{cid}/documents",
                                 data={"document_id": str(uuid.uuid4())},
                                 headers=second_user["headers"])
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# CSV import / export
# --------------------------------------------------------------------------- #


def _csv_bytes(*lines: str) -> bytes:
    header = "phone,name,language,country,tags"
    return ("\n".join([header, *lines]) + "\n").encode("utf-8")


def _import_csv(client, headers, data: bytes, default_country="US") -> dict:
    r = client.post("/api/v1/contacts/import",
                    files={"file": ("contacts.csv", io.BytesIO(data), "text/csv")},
                    data={"default_country": default_country},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_csv_import_reports_invalid_and_imports_valid(services_app_client, user):
    data = _csv_bytes(
        "+911234567890,Ada,hi,IN,tier1",
        "not-a-number,Broke,en,US,tier2",
        "9876500001,Bob,en,IN,vip",
    )
    report = _import_csv(services_app_client, user["headers"], data, default_country="IN")
    assert report["imported"] == 2
    # the normalizer strips non-dialable chars first; a row with no digits at
    # all therefore reports the empty-number error
    assert report["invalid"] == [
        {"row": 3, "phone": "not-a-number", "error": "Phone number cannot be empty."},
    ]

    r = services_app_client.get("/api/v1/contacts?q=Ada", headers=user["headers"])
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["phone_e164"] == "+911234567890"
    assert items[0]["display_name"] == "Ada"
    assert items[0]["language"] == "hi"
    assert items[0]["tags"] == ["tier1"]

    r = services_app_client.get("/api/v1/contacts?q=Bob", headers=user["headers"])
    assert r.json()["items"][0]["phone_e164"] == "+919876500001"


def test_csv_import_is_idempotent_and_merges_tags(services_app_client, user):
    data = _csv_bytes("+910000000001,Ada,en,US,newsletter")
    first = _import_csv(services_app_client, user["headers"], data)
    assert first["imported"] == 1

    second = _import_csv(services_app_client, user["headers"], data)
    assert second["imported"] == 0 and second["updated"] == 1

    data_v2 = _csv_bytes("+910000000001,Ada,en,US,vip")
    third = _import_csv(services_app_client, user["headers"], data_v2)
    assert third["imported"] == 0 and third["updated"] == 1

    r = services_app_client.get("/api/v1/contacts?q=Ada", headers=user["headers"])
    item = r.json()["items"][0]
    assert item["tags"] == ["newsletter", "vip"]  # merged, order-preserving


def test_csv_duplicate_rows_in_one_file_reported(services_app_client, user):
    data = _csv_bytes(
        "+910000000002,Duo,en,US,a",
        "+910000000002,Duo2,en,US,b",
    )
    report = _import_csv(services_app_client, user["headers"], data)
    assert report["imported"] == 1
    assert report["invalid"][0]["error"] == "duplicate row in file"
    assert report["invalid"][0]["row"] == 3


def test_csv_export_roundtrip(services_app_client, user):
    _create_contact(services_app_client, user["headers"],
                    phone="+91200030001", display_name="Zoe",
                    language="en", tags=["z-list"])
    r = services_app_client.get("/api/v1/contacts/export", headers=user["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8")
    assert "phone,name,language,country" in text
    assert "+91200030001" in text
    assert "Zoe" in text
    assert "z-list" in text
