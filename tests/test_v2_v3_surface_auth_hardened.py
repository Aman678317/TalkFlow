"""The v2/v3 compatibility surface must hold the same auth line as the API.

Evidence behind this suite (2026-10-22, the day-2 ownership map, finding B-4
and the coverage gap in §7.3):

The legacy-compat routes are mounted at the root (``/v2/*``, ``/v3/*``) and
most of them take ``get_principal_optional``. Reading the handlers shows the
tenant routes DO reject an anonymous caller (through ``_org_of``), so the
surface was not an open door — but two real problems remained:

* ``GET /v2/usage`` had no auth at all **and** answered with HARDCODED
  numbers (1250 characters, 5.4 speech minutes) — a fabricated usage report
  to anyone, authenticated or not;
* the suite that covers this surface's isolation
  (``tests/test_tenant_security_extended.py``) ran in no CI job, so a
  regression here would have been invisible.

Pinned here: the tenant routes refuse an anonymous caller, the usage route
requires a member and reports the ledger, and the capability routes that are
public by design stay public.
"""
from __future__ import annotations

import pytest

# the tenant-scoped routes of the compatibility surface
TENANT_ROUTES = [
    ("get", "/v2/glossaries", None),
    ("get", "/v2/glossaries/some-id", None),
    ("get", "/v3/style_rules", None),
    ("get", "/v3/translation_memories", None),
    ("get", "/v3/spoken-terms", None),
]

# the capability/utility routes that are public by design (the canonical API
# publishes the same information without a principal)
PUBLIC_ROUTES = [
    ("get", "/v2/languages", None),
    ("get", "/v3/languages/resources", None),
    ("get", "/v2/desi/languages", None),
]


@pytest.mark.parametrize("method,path,payload", TENANT_ROUTES)
def test_a_tenant_route_refuses_an_anonymous_caller(services_app_client, method, path, payload):
    res = services_app_client.request(method, path, json=payload)
    assert res.status_code in (401, 403), (
        f"{path} served an anonymous caller: HTTP {res.status_code} {res.text[:160]}")


@pytest.mark.parametrize("method,path,payload", PUBLIC_ROUTES)
def test_a_capability_route_stays_public(services_app_client, method, path, payload):
    res = services_app_client.request(method, path, json=payload)
    assert res.status_code == 200, (
        f"{path} is a public capability route and must stay reachable: {res.text[:160]}")


def test_the_write_routes_refuse_an_anonymous_caller(services_app_client):
    for path in ("/v2/write/rephrase", "/v2/write/correct"):
        res = services_app_client.post(path, json={"text": "hello"})
        assert res.status_code in (401, 403), (
            f"{path} served an anonymous caller: HTTP {res.status_code}")


def test_the_usage_route_refuses_an_anonymous_caller(services_app_client):
    res = services_app_client.get("/v2/usage")
    assert res.status_code in (401, 403), (
        f"the usage report served an anonymous caller: HTTP {res.status_code}")


def test_the_usage_route_reports_the_ledger_not_placeholders(services_app_client, user):
    """The old answer was hardcoded (1250 characters, 5.4 speech minutes)."""
    res = services_app_client.get("/v2/usage", headers=user["headers"])
    assert res.status_code == 200, res.text
    data = res.json()
    for field in ("character_count", "character_limit", "document_count",
                  "document_limit", "team_document_count", "team_document_limit",
                  "speech_to_text_minutes", "speech_to_speech_minutes"):
        assert field in data, f"the desi.Usage shape must keep {field}"
    # a fresh organization has used nothing
    assert data["character_count"] == 0, (
        "the usage report must come from the ledger, not from hardcoded numbers")
    assert data["speech_to_text_minutes"] == 0
    assert data["character_limit"], "the plan limit must be reported"


def test_the_usage_route_counts_what_the_org_actually_used(services_app_client, user):
    """After a translation the character count must move."""
    res = services_app_client.post("/api/v1/translate", headers=user["headers"],
                                   json={"text": "the quick brown fox jumps over the lazy dog",
                                         "source_language": "en", "target_language": "hi"})
    assert res.status_code in (200, 400, 503, 502), res.text
    usage = services_app_client.get("/v2/usage", headers=user["headers"])
    assert usage.status_code == 200
    if res.status_code == 200:
        assert usage.json()["character_count"] > 0, (
            "the usage report must reflect what the organization consumed")


# --------------------------------------------------------------------------- #
# Day-3 (2026-10-23): content honesty on the same surface. The capability
# routes were already public by design; what they SAY must now be true, and
# the v2 translate fallback must never fabricate a "translation".
# --------------------------------------------------------------------------- #

def _registry_serving_codes():
    from gt_ai.capabilities import DEFAULT_LANGUAGES
    return {lc.code.upper() for lc in DEFAULT_LANGUAGES if lc.translation_supported}


def test_the_v2_language_list_serves_only_registry_languages(services_app_client):
    """GET /v2/languages advertised ~95 codes — Latin, Esperanto, unrelated
    scripts no adapter, no registry row and no provider serves. The default
    language list is an advertisement: it may only contain languages the
    capability registry carries."""
    res = services_app_client.get("/v2/languages?type=target")
    assert res.status_code == 200
    entries = res.json()
    serving = _registry_serving_codes()
    advertised = {str(e["language"]).split("-")[0].upper() for e in entries}
    over_advertised = advertised - serving
    assert not over_advertised, (
        "/v2/languages advertised languages nothing serves: "
        + ", ".join(sorted(over_advertised)))
    formality = {e["language"] for e in entries if e.get("supports_formality")}
    assert {c.lower() for c in formality} <= {"de", "es", "fr"}, (
        "formality advertised for languages with no formality rules: "
        + ", ".join(sorted(formality)))


def test_a_real_provider_result_is_never_replaced_by_the_canned_dictionary(
        services_app_client, monkeypatch):
    """The dictionary override ran POST-provider: a configured provider's real
    translation was silently swapped for the canned phrase whenever the source
    happened to match a dictionary key."""
    from types import SimpleNamespace
    import app.routers.v2_v3 as v2

    async def real_provider(db, text, src, tgt, ctx):
        return SimpleNamespace(
            source_lang="en",
            result=SimpleNamespace(
                text="A genuinely translated greeting.",
                quality_flags=[],
                is_dev=False),
        )

    monkeypatch.setattr(v2, "translate_text", real_provider)
    res = services_app_client.post(
        "/v2/translate",
        json={"text": ["hello world"], "source_lang": "EN", "target_lang": "DE"})
    assert res.status_code == 200, res.text
    item = res.json()["translations"][0]
    assert item["text"] == "A genuinely translated greeting.", (
        "the canned dictionary replaced the provider's real translation: "
        + item["text"])
    assert "untranslated_fallback" not in item


def test_a_failed_provider_yields_no_fabricated_translation(
        services_app_client, monkeypatch):
    """The fallback answered with ``"[DE] <source text>"`` (or a dictionary
    phrase) on ANY exception — a fabricated text indistinguishable from a real
    translation. Honest shape: empty text + ``untranslated_fallback`` flag."""
    import app.routers.v2_v3 as v2

    async def down(db, text, src, tgt, ctx):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(v2, "translate_text", down)
    text = "The quarterly expedition reached the plateau before dawn."
    res = services_app_client.post(
        "/v2/translate",
        json={"text": [text], "source_lang": "EN", "target_lang": "DE"})
    assert res.status_code == 200, res.text
    item = res.json()["translations"][0]
    assert item["text"] != f"[DE] {text}"
    assert text not in item["text"], "the source was shipped as the translation"
    assert item["text"] == "", "empty means nothing was translated"
    assert item.get("untranslated_fallback") is True, (
        "a machine-checkable failure flag is required")


def test_the_desi_translate_dictionary_hit_carries_provenance(services_app_client):
    """/v2/desi/translate answers from its phrase dictionary before any
    provider runs; the caller must be able to tell (DeepL-compatible clients
    treat dictionary output differently from MT output)."""
    res = services_app_client.post(
        "/v2/desi/translate",
        json={"text": ["hello world"], "source_lang": "en", "target_lang": "hi"})
    assert res.status_code == 200, res.text
    item = res.json()["translations"][0]
    assert item["text"] == "नमस्ते दुनिया"
    assert item.get("translated_by") == "dictionary", (
        f"a canned dictionary answer shipped without provenance: {item!r}")


def test_the_desi_translate_path_never_fabricates_either(
        services_app_client, monkeypatch):
    import app.routers.v2_v3 as v2

    async def down(db, text, src, tgt, ctx):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(v2, "translate_text", down)
    text = "The quarterly expedition reached the plateau before dawn."
    res = services_app_client.post(
        "/v2/desi/translate",
        json={"text": [text], "source_lang": "en", "target_lang": "hi"})
    assert res.status_code == 200, res.text
    item = res.json()["translations"][0]
    assert text not in item["text"], "the source was shipped as the translation"
    assert f"[HI]" not in item["text"] and f"[HI]".lower() not in item["text"].lower()
    assert item["text"] == ""
    assert item.get("untranslated_fallback") is True
