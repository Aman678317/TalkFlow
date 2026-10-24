"""Behavioral coverage for the saved-translation Notes search surface.

The search contract mirrors the observable DeepL saved-translation behavior:
saved entries are reusable, newest-first records and a query can find the
entry through its user-visible metadata, not only the two translation panes.
"""
from __future__ import annotations


def _create_note(client, headers, **overrides):
    payload = {
        "title": "Language study",
        "source_text": "A useful phrase",
        "translated_text": "Una frase útil",
        "source_lang": "en",
        "target_lang": "es",
        "note": "Review this phrase before the next lesson.",
        "tags": ["review"],
        "annotations": [],
        "is_favorite": True,
    }
    payload.update(overrides)
    response = client.post("/api/v1/notes", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_notes_search_normalizes_accents_and_searches_all_metadata(
    services_app_client, user
):
    _create_note(
        services_app_client,
        user["headers"],
        title="Crème brûlée terminology",
        source_text="Crème brûlée is on the menu.",
        translated_text="La crème brûlée está en el menú.",
        note="Restaurant vocabulary to review.",
        tags=["culinary", "review"],
        annotations=[
            {
                "text": "menu",
                "start": 26,
                "end": 30,
                "tag": "vocabulary",
                "comment": "restaurant context",
            }
        ],
    )

    accent_query = services_app_client.get(
        "/api/v1/notes?q=creme%20brulee", headers=user["headers"]
    )
    assert accent_query.status_code == 200, accent_query.text
    accent_item = accent_query.json()["items"][0]
    assert accent_query.json()["total"] == 1
    assert "<mark>Crème</mark>" in accent_item["highlight_source"]
    assert "<mark>brûlée</mark>" in accent_item["highlight_source"]

    metadata_query = services_app_client.get(
        "/api/v1/notes?q=culinary%20context", headers=user["headers"]
    )
    assert metadata_query.status_code == 200, metadata_query.text
    assert metadata_query.json()["total"] == 1


def test_notes_search_requires_every_query_term_but_allows_different_fields(
    services_app_client, user
):
    _create_note(
        services_app_client,
        user["headers"],
        title="Roadmap",
        source_text="The sprint starts Monday.",
        translated_text="El sprint comienza el lunes.",
        note="Keep this for the planning review.",
        tags=["planning"],
    )

    match = services_app_client.get(
        "/api/v1/notes?q=roadmap%20planning", headers=user["headers"]
    )
    assert match.status_code == 200, match.text
    assert match.json()["total"] == 1

    no_match = services_app_client.get(
        "/api/v1/notes?q=roadmap%20nonexistent", headers=user["headers"]
    )
    assert no_match.status_code == 200, no_match.text
    assert no_match.json()["total"] == 0


def test_notes_search_highlights_are_html_escaped(
    services_app_client, user
):
    _create_note(
        services_app_client,
        user["headers"],
        source_text="<script>alert(1)</script>",
        translated_text="Safe text",
    )

    response = services_app_client.get(
        "/api/v1/notes?q=script", headers=user["headers"]
    )
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert "<script" not in item["highlight_source"]
    assert "&lt;<mark>script</mark>&gt;" in item["highlight_source"]
