"""The usage and billing accounting must be true (issue #109, class 4).

Evidence behind this suite (2026-10-21, sweep #109 cluster 4):

* The plan LIMITS and the usage LEDGER used different unit names — the
  limits said "documents" / "meeting_minutes" / "audio_minutes" while the
  ledger recorded "document_pages" / "telephony_minutes" / audio seconds.
  A limit compared against a unit nothing ever records is a limit that can
  never trip: ``documents.py`` checked "documents" while the ledger records
  "document_pages", and the audio/telephony limits were never checked at
  all. The canonical realtime path recorded no audio seconds either, so the
  audio limit had nothing to accrue.
* The usage page asked for "document_pages" / "audio_seconds" /
  "translation_requests" limits while the server published "documents" /
  "audio_minutes" / "meeting_minutes": three quota cards could never show a
  percentage and three limits were never displayed.
* The invoice priced characters / audio_minutes / document_pages and never
  the translation volume, while the page claimed the invoice came "from real
  metering … never estimated".
* The billing page hard-coded the plan prices and quotas, and they
  contradicted the server ("$29 / 100 voice minutes / 500 pages" vs the
  server's "$24 / 1000 minutes / 200 documents").
* The calling tab rendered a hard-coded latency waterfall (280/130/145 ms,
  555 ms total) before any call and fell back to a FABRICATED call history
  ("Tokyo Client (Tanaka)", 763 s) when the calls endpoint failed.

Pinned here: one canonical dimension vocabulary shared by the ledger, the
limits, the pricing and the client; limits that actually trip; an invoice
that prices the translation volume and discloses what it does not price; a
server-published plan table; and no fabricated numbers anywhere in the UI.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from app.errors import QuotaExceededError
from app.services import billing_service, usage_service

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "apps" / "web" / "src"


# --------------------------------------------------------------------------- #
# 1. one vocabulary
# --------------------------------------------------------------------------- #
def test_the_plan_limits_use_the_canonical_dimensions():
    """The limits are expressed in the units the ledger records."""
    for plan, quotas in usage_service.DEFAULT_PLAN_QUOTAS.items():
        assert set(quotas) == set(usage_service.METERED_DIMENSIONS), (
            f"plan {plan} limits {sorted(quotas)} do not match the metered "
            f"dimensions {sorted(usage_service.METERED_DIMENSIONS)}")


def test_the_priced_dimensions_are_metered_dimensions():
    for plan, pricing in billing_service.PLAN_PRICING.items():
        priced = {k for k in pricing if k not in ("base_cents", "included")}
        assert priced <= set(usage_service.METERED_DIMENSIONS), (
            f"plan {plan} prices units nothing meters: {sorted(priced)}")
        included = set(pricing.get("included", {}))
        assert included <= set(usage_service.METERED_DIMENSIONS)


def test_the_old_limit_names_are_normalized():
    """Existing subscriptions carry the old names; the limits migrate on read."""
    out = usage_service.normalize_quotas({
        "characters": 100, "audio_minutes": 60, "documents": 20,
        "api_requests": 5, "meeting_minutes": 300,
    })
    assert out["document_pages"] == 20
    assert out["telephony_minutes"] == 300
    # the audio limit changes VALUE: the ledger counts seconds
    assert out["audio_seconds"] == 3600
    assert out["characters"] == 100
    assert "documents" not in out and "audio_minutes" not in out
    assert "meeting_minutes" not in out


def test_normalizing_the_current_quotas_is_a_no_op():
    out = usage_service.normalize_quotas(usage_service.DEFAULT_PLAN_QUOTAS["pro"])
    assert out == {k: float(v) for k, v in usage_service.DEFAULT_PLAN_QUOTAS["pro"].items()}


# --------------------------------------------------------------------------- #
# 2. the limits must actually be able to trip
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_document_page_limit_trips_against_the_recorded_unit():
    """Before the fix the check compared "documents" against a ledger that
    records "document_pages", so the limit could never trip."""
    from app.db import models as M
    from app.db.session import db_session
    org_id = uuid.uuid4()
    async with db_session() as db:
        db.add(M.Subscription(org_id=org_id, plan_code="free", status="active",
                              quota_json={"document_pages": 2}))
        await db.commit()
        await usage_service.record_usage(
            db, org_id=org_id, product="document", unit_type="document_pages",
            units=5)
        await db.commit()
        with pytest.raises(QuotaExceededError):
            await usage_service.check_quota(db, org_id, "document_pages", 1)
        # the old unit name is not a dimension any more
        with pytest.raises(QuotaExceededError):
            await usage_service.check_quota(db, org_id, "document_pages", 1)


@pytest.mark.asyncio
async def test_the_translation_request_limit_trips():
    from app.db import models as M
    from app.db.session import db_session
    org_id = uuid.uuid4()
    async with db_session() as db:
        db.add(M.Subscription(org_id=org_id, plan_code="free", status="active",
                              quota_json={"translation_requests": 2}))
        await db.commit()
        await usage_service.record_usage(
            db, org_id=org_id, product="text", unit_type="translation_requests",
            units=3)
        await db.commit()
        with pytest.raises(QuotaExceededError):
            await usage_service.check_quota(db, org_id, "translation_requests", 1)


@pytest.mark.asyncio
async def test_the_audio_limit_is_compared_in_seconds():
    from app.db import models as M
    from app.db.session import db_session
    org_id = uuid.uuid4()
    async with db_session() as db:
        db.add(M.Subscription(org_id=org_id, plan_code="free", status="active",
                              quota_json={"audio_seconds": 10}))
        await db.commit()
        await usage_service.record_usage(
            db, org_id=org_id, product="realtime", unit_type="audio_seconds",
            units=12.0)
        await db.commit()
        with pytest.raises(QuotaExceededError):
            await usage_service.check_quota(db, org_id, "audio_seconds", 1)


# --------------------------------------------------------------------------- #
# 3. every check must use the unit the ledger records
# --------------------------------------------------------------------------- #
def _service_source(rel: str) -> str:
    return (REPO / "services" / "api" / "app" / rel).read_text(encoding="utf-8")


def test_the_document_route_checks_the_recorded_unit():
    """The bug: the route checked "documents" while the ledger records
    "document_pages", so the limit could never trip."""
    src = _service_source("routers/documents.py")
    assert 'check_quota(db, principal.org_id, "document_pages"' in src, (
        "the document limit must be checked in the unit the ledger records")
    assert 'check_quota(db, principal.org_id, "documents"' not in src


def test_the_translation_routes_check_the_translation_volume():
    src = _service_source("routers/translate.py")
    assert '"translation_requests"' in src, (
        "the translation volume limit must be checked where translations run")
    assert '"api_requests"' in src, (
        "the api-request limit must be checked where api requests are metered")


def test_the_call_path_checks_the_call_minutes():
    src = _service_source("telephony/call_service.py")
    assert '"telephony_minutes"' in src, (
        "the call-minute limit must be checked before a call is placed")


def test_the_realtime_path_meters_and_checks_the_audio():
    src = _service_source("realtime/pipeline.py")
    assert '"audio_seconds"' in src, (
        "the realtime path must meter the audio it consumes — the audio limit "
        "had nothing to accrue")
    assert 'check_quota(' in src, "the audio limit must be checked before the STT"


# --------------------------------------------------------------------------- #
# 4. the invoice
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_the_invoice_prices_the_translation_volume():
    from app.db import models as M
    from app.db.session import db_session
    from datetime import datetime, timedelta, timezone
    org_id = uuid.uuid4()
    async with db_session() as db:
        db.add(M.Organization(id=org_id, name="Usage Billing Test Org", slug=f"ubt-{org_id.hex[:8]}", plan="pro"))
        db.add(M.Subscription(org_id=org_id, plan_code="pro", status="active",
                              quota_json=dict(usage_service.DEFAULT_PLAN_QUOTAS["pro"])))
        await db.commit()
        # more than the pro plan's included translations
        await usage_service.record_usage(
            db, org_id=org_id, product="text", unit_type="translation_requests",
            units=120_000)
        await db.commit()
        start = datetime.now(timezone.utc) - timedelta(days=1)
        inv = await billing_service.compute_invoice(
            db, org_id, start, datetime.now(timezone.utc) + timedelta(days=1))
    priced = [ln for ln in inv["lines"] if "translation_requests" in ln["description"]]
    assert priced, f"the translation volume is not billed: {inv['lines']}"
    assert priced[0]["amount_cents"] > 0


@pytest.mark.asyncio
async def test_the_invoice_discloses_the_unpriced_dimensions():
    from app.db import models as M
    from app.db.session import db_session
    from datetime import datetime, timedelta, timezone
    org_id = uuid.uuid4()
    async with db_session() as db:
        db.add(M.Organization(id=org_id, name="Usage Billing Test Org", slug=f"ubt-{org_id.hex[:8]}", plan="pro"))
        db.add(M.Subscription(org_id=org_id, plan_code="pro", status="active",
                              quota_json=dict(usage_service.DEFAULT_PLAN_QUOTAS["pro"])))
        await db.commit()
        await usage_service.record_usage(
            db, org_id=org_id, product="telephony", unit_type="telephony_minutes",
            units=12.0)
        await db.commit()
        start = datetime.now(timezone.utc) - timedelta(days=1)
        inv = await billing_service.compute_invoice(
            db, org_id, start, datetime.now(timezone.utc) + timedelta(days=1))
    disclosed = [ln for ln in inv["lines"]
                 if ln.get("unpriced") and "telephony_minutes" in ln["description"]]
    assert disclosed, f"the tracked call minutes are not disclosed: {inv['lines']}"
    assert disclosed[0]["amount_cents"] == 0
    assert "not priced" in disclosed[0]["description"]


# --------------------------------------------------------------------------- #
# 4. the server publishes the plan table
# --------------------------------------------------------------------------- #
def test_the_plan_catalog_carries_the_server_prices():
    cat = billing_service.plan_catalog()
    codes = [p["code"] for p in cat["plans"]]
    assert codes == ["free", "pro", "business", "enterprise"]
    pro = next(p for p in cat["plans"] if p["code"] == "pro")
    assert pro["base_cents"] == 2400
    assert pro["per_unit_cents"]["translation_requests"] > 0
    assert "translation_requests" in pro["included"]
    assert cat["unpriced_dimensions"] == ["telephony_minutes"]
    assert set(cat["metered_dimensions"]) == set(usage_service.METERED_DIMENSIONS)


def test_the_plans_route_is_published():
    from app.main import create_app
    paths = set(create_app().openapi()["paths"])
    assert "/api/v1/billing/plans" in paths, (
        "the plan table has to come from the server, not from the client")


# --------------------------------------------------------------------------- #
# 5. the client must not invent numbers
# --------------------------------------------------------------------------- #
def test_the_usage_page_asks_for_the_canonical_dimensions():
    src = (WEB / "pages" / "Usage.tsx").read_text(encoding="utf-8")
    asked = set(re.findall(r'\["([a-z_]+)",\s*"', src))
    assert asked == set(usage_service.METERED_DIMENSIONS), (
        f"the usage page asks for {sorted(asked)}")


def test_the_billing_page_has_no_hard_coded_prices():
    src = (WEB / "pages" / "Billing.tsx").read_text(encoding="utf-8")
    assert "/api/v1/billing/plans" in src, "the plan table must be fetched"
    for literal in ("$29", "$129", "voice minutes · 500 pages"):
        assert literal not in src, f"a hard-coded plan price survived: {literal}"


def test_the_calling_tab_has_no_fabricated_numbers():
    src = (WEB / "components" / "voice" / "PhoneCallingTab.tsx").read_text(encoding="utf-8")
    for literal in ("recipient_name: 'Tokyo Client (Tanaka)'",
                    "recipient_name: 'Moscow Partner (Dmitry)'",
                    "total_e2e_latency_ms: 555",
                    "speech_to_stt_ms: 280",
                    "stt_to_mt_ms: 130",
                    "mt_to_tts_ms: 145"):
        assert literal not in src, f"fabricated data must not come back: {literal}"


def test_the_write_diff_matches_words_not_substrings():
    src = (WEB / "pages" / "Write.tsx").read_text(encoding="utf-8")
    assert "includes(cleanWord)" not in src, (
        "the substring diff test must not come back")
    helper = (WEB / "lib" / "writeDiff.ts").read_text(encoding="utf-8")
    assert "matchChangedWord" in helper
