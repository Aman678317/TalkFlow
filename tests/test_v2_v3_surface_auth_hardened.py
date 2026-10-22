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
