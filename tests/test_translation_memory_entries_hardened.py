"""Translation-memory entries: list, search, edit, delete, export.

The editor page used to read the *memory list* where it expected entries, so
every row rendered an empty language pair, "confidence NaN%" and a Delete
button that removed a whole memory (2026-10-21 audit). These tests pin the
entry-level API that replaced it, including the org isolation.
"""
from __future__ import annotations

import pytest


def _memory(client, headers, name="Support en->hi", source="en", target="hi"):
    r = client.post("/api/v1/translation-memories", json={
        "name": name, "source_lang": source, "target_lang": target, "domain": "general",
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _entry(client, headers, tm_id, source="cloud console", target="क्लाउड कंसोल", approved=True):
    r = client.post("/api/v1/translation-memories/entries", json={
        "tm_id": tm_id, "source_text": source, "target_text": target, "approved": approved,
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #

def test_entries_are_listed_with_the_fields_the_editor_needs(services_app_client, user):
    tm = _memory(services_app_client, user["headers"])
    entry = _entry(services_app_client, user["headers"], tm["id"])

    r = services_app_client.get("/api/v1/translation-memories/entries", headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    row = body[0]
    assert row["id"] == entry["id"]
    assert row["source_text"] == "cloud console"
    assert row["target_text"] == "क्लाउड कंसोल"
    assert row["source_language"] == "en"
    assert row["target_language"] == "hi"
    assert row["approved"] is True
    assert row["tm_name"] == tm["name"]
    assert row["tm_id"] == tm["id"]
    assert isinstance(row["confidence"], (int, float))
    assert isinstance(row["usage_count"], int)
    assert row["version"] >= 1


def test_entries_can_be_searched_by_source_text(services_app_client, user):
    tm = _memory(services_app_client, user["headers"])
    _entry(services_app_client, user["headers"], tm["id"], source="cloud console")
    _entry(services_app_client, user["headers"], tm["id"], source="data pipeline")

    r = services_app_client.get("/api/v1/translation-memories/entries?q=cloud",
                                 headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["source_text"] == "cloud console"


def test_the_memory_list_endpoint_still_returns_memories(services_app_client, user):
    """The two shapes must not be confused again."""
    tm = _memory(services_app_client, user["headers"])
    _entry(services_app_client, user["headers"], tm["id"])

    memories = services_app_client.get("/api/v1/translation-memories", headers=user["headers"]).json()
    assert memories[0]["name"] == tm["name"]
    assert "source_text" not in memories[0]

    entries = services_app_client.get("/api/v1/translation-memories/entries", headers=user["headers"]).json()
    assert "source_text" in entries[0]
    assert "name" not in entries[0]


def test_entries_are_isolated_per_organization(services_app_client, user, second_user):
    tm = _memory(services_app_client, user["headers"])
    _entry(services_app_client, user["headers"], tm["id"])

    r = services_app_client.get("/api/v1/translation-memories/entries", headers=second_user["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == []


# --------------------------------------------------------------------------- #
# Editing / deleting
# --------------------------------------------------------------------------- #

def test_editing_an_entry_updates_it_and_bumps_the_version(services_app_client, user):
    tm = _memory(services_app_client, user["headers"])
    entry = _entry(services_app_client, user["headers"], tm["id"])

    r = services_app_client.put(f"/api/v1/translation-memories/entries/{entry['id']}",
                                 json={"target_text": "क्लाउड कंसोल (संशोधित)", "approved": False},
                                 headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_text"] == "क्लाउड कंसोल (संशोधित)"
    assert body["approved"] is False
    assert body["version"] == entry["version"] + 1


def test_deleting_an_entry_leaves_the_memory_intact(services_app_client, user):
    tm = _memory(services_app_client, user["headers"])
    entry = _entry(services_app_client, user["headers"], tm["id"])

    r = services_app_client.delete(f"/api/v1/translation-memories/entries/{entry['id']}",
                                   headers=user["headers"])
    assert r.status_code == 204, r.text

    entries = services_app_client.get("/api/v1/translation-memories/entries", headers=user["headers"]).json()
    assert entries == []
    memories = services_app_client.get("/api/v1/translation-memories", headers=user["headers"]).json()
    assert len(memories) == 1, "the memory itself must survive deleting one pair"


def test_editing_an_unknown_entry_is_not_found(services_app_client, user):
    import uuid
    r = services_app_client.put(f"/api/v1/translation-memories/entries/{uuid.uuid4()}",
                                 json={"target_text": "x"}, headers=user["headers"])
    assert r.status_code == 404, r.text


def test_another_organization_cannot_edit_an_entry(services_app_client, user, second_user):
    tm = _memory(services_app_client, user["headers"])
    entry = _entry(services_app_client, user["headers"], tm["id"])

    r = services_app_client.put(f"/api/v1/translation-memories/entries/{entry['id']}",
                                 json={"target_text": "hijacked"}, headers=second_user["headers"])
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def test_entries_can_be_exported_as_csv(services_app_client, user):
    tm = _memory(services_app_client, user["headers"])
    _entry(services_app_client, user["headers"], tm["id"], source="cloud console", target="क्लाउड कंसोल")

    r = services_app_client.get("/api/v1/translation-memories/entries/export", headers=user["headers"])
    assert r.status_code == 200, r.text
    text = r.text
    assert "source_text" in text.splitlines()[0]
    assert "cloud console" in text
    assert "क्लाउड कंसोल" in text
