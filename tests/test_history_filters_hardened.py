"""
History filters and single-row deletion.

The History page sent `source_language`/`target_language` (the endpoint takes
`source_lang`/`target_lang`) and a `q` the endpoint ignored, so the search box
and both language dropdowns silently did nothing while the page still
reported a result count. Its per-row Delete button called
`DELETE /api/v1/history/{id}`, which did not exist (only a clear-all route).

(2026-10-21 same-class sweep.)
"""
from __future__ import annotations

import uuid


def _create_segment(services_app_client, headers, source: str, target: str, product: str = "text"):
    """Write a history row through the translate endpoint (the real path)."""
    r = services_app_client.post("/api/v1/translate", json={
        "text": source, "source_language": "en", "target_language": "es",
    }, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_history_search_filters_by_text(services_app_client, user):
    _create_segment(services_app_client, user["headers"], "pineapple telemetry", "pina telemetry")
    _create_segment(services_app_client, user["headers"], "unrelated sentence", "sinçš„å…³ç³»")

    r = services_app_client.get("/api/v1/history?q=pineapple", headers=user["headers"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "the search term should match the row we just created"
    assert all("pineapple" in (i["source_text"] + i["target_text"]).lower() for i in items)


def test_history_language_filters_are_applied(services_app_client, user):
    _create_segment(services_app_client, user["headers"], "filter probe", "sonda")
    r = services_app_client.get("/api/v1/history?source_lang=en&target_lang=es", headers=user["headers"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert all(i["source_lang"] == "en" for i in items)
    assert all(i["target_lang"] == "es" for i in items)


def test_a_history_row_can_be_deleted_on_its_own(services_app_client, user):
    _create_segment(services_app_client, user["headers"], "delete me please", "borreme por favor")
    before = services_app_client.get("/api/v1/history?limit=200", headers=user["headers"]).json()["items"]
    assert before, "expected at least one history row"
    target = before[0]["id"]

    r = services_app_client.delete(f"/api/v1/history/{target}", headers=user["headers"])
    assert r.status_code == 204, r.text

    after = services_app_client.get("/api/v1/history?limit=200", headers=user["headers"]).json()["items"]
    assert target not in [i["id"] for i in after]


def test_deleting_an_unknown_history_row_is_not_found(services_app_client, user):
    r = services_app_client.delete(f"/api/v1/history/{uuid.uuid4()}", headers=user["headers"])
    assert r.status_code == 404, r.text


def test_history_rows_of_another_organization_are_not_deletable(services_app_client, user, second_user):
    _create_segment(services_app_client, user["headers"], "private row", "fila privada")
    row = services_app_client.get("/api/v1/history?limit=200", headers=user["headers"]).json()["items"][0]
    r = services_app_client.delete(f"/api/v1/history/{row['id']}", headers=second_user["headers"])
    assert r.status_code == 404, r.text
