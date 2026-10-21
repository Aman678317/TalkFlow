"""The metering worker must keep billing (issue #109 follow-up, day-2 finding B-1).

The worker stored its usage-threshold markers INSIDE ``quota_json`` and then
iterated that same dict as if every entry were a limit — so the next pass
divided the usage by a marker map, raised ``TypeError``, and the blanket
``except`` turned it into "metering pass failed". After the first 80 %/100 %
crossing the worker stopped finalizing invoices and stopped dispatching
threshold webhooks, for every organization.

Pinned here: the reserved marker key is never treated as a limit, only
numeric limits are compared, the markers survive the pass, and one
subscription's bad data cannot stop the others.
"""
from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WORKER = REPO / "workers" / "metering-worker" / "main.py"


def _worker():
    spec = importlib.util.spec_from_file_location("metering_worker_main", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# 1. the marker key is not a limit
# --------------------------------------------------------------------------- #
def test_the_threshold_markers_are_not_mistaken_for_limits():
    module = _worker()
    limits, state = module._limits_and_state({
        "characters": 5_000,
        module.THRESHOLD_KEY: {"threshold_characters_0.8": "2026-10-01T00:00:00Z"},
    })
    assert limits == {"characters": 5_000.0}
    assert state == {"threshold_characters_0.8": "2026-10-01T00:00:00Z"}


def test_a_non_numeric_limit_is_skipped_not_divided_by():
    module = _worker()
    limits, _state = module._limits_and_state({
        "characters": 5_000,
        "weird": {"not": "a limit"},
    })
    assert limits == {"characters": 5_000.0}, "a non-numeric limit is skipped"


def test_reserved_keys_never_reach_the_limits():
    module = _worker()
    limits, _state = module._limits_and_state({"_internal": 1, "characters": 2})
    assert limits == {"characters": 2.0}


# --------------------------------------------------------------------------- #
# 2. a pass over a subscription that already has markers must not raise
# --------------------------------------------------------------------------- #
class _FakeSub:
    def __init__(self, quota_json: dict) -> None:
        self.org_id = uuid.uuid4()
        self.quota_json = quota_json
        self.current_period_start = None
        self.current_period_end = None


class _FakeDB:
    def __init__(self) -> None:
        self.dispatched: list = []
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_a_subscription_with_markers_still_dispatches_thresholds(monkeypatch):
    module = _worker()
    from app.services import usage_service, webhook_service

    async def _usage(_db, _org_id):
        return {"characters": 5_000.0}   # 100% of the 5,000 limit

    dispatched: list = []

    async def _dispatch(_db, org_id, kind, payload):
        dispatched.append((kind, payload))

    monkeypatch.setattr(usage_service, "current_period_usage", _usage)
    monkeypatch.setattr(webhook_service, "dispatch", _dispatch)

    sub = _FakeSub({
        "characters": 5_000,
        module.THRESHOLD_KEY: {"threshold_characters_0.8": "2026-10-01T00:00:00Z"},
    })
    db = _FakeDB()
    await module._process_subscription(db, sub, now=_now())

    kinds = [(kind, payload["threshold"]) for kind, payload in dispatched]
    assert kinds == [("usage.threshold", 1.0)], (
        "the 80% marker is already set, so only the 100% threshold is new")
    # the markers survive the pass
    assert module.THRESHOLD_KEY in sub.quota_json
    assert "threshold_characters_1.0" in sub.quota_json[module.THRESHOLD_KEY]


@pytest.mark.asyncio
async def test_the_markers_do_not_turn_the_next_pass_into_a_type_error(monkeypatch):
    """The exact pre-fix failure: the stored markers are iterated as limits."""
    module = _worker()
    from app.services import usage_service, webhook_service

    async def _usage(_db, _org_id):
        return {"characters": 10.0}

    async def _dispatch(*_a, **_k):
        return None

    monkeypatch.setattr(usage_service, "current_period_usage", _usage)
    monkeypatch.setattr(webhook_service, "dispatch", _dispatch)

    sub = _FakeSub({
        "characters": 5_000,
        module.THRESHOLD_KEY: {"threshold_characters_0.8": "2026-10-01T00:00:00Z"},
    })
    db = _FakeDB()
    await module._process_subscription(db, sub, now=_now())  # must not raise


@pytest.mark.asyncio
async def test_one_bad_subscription_does_not_stop_the_others(monkeypatch):
    """The pass isolates a failure to the subscription that caused it.

    The real failure mode: one organization's invoice finalization raises
    (bad period data, a provider error) — pre-fix the blanket ``except``
    ended the whole pass, so every other organization stopped being billed.
    """
    module = _worker()
    from app.services import billing_service, usage_service, webhook_service

    async def _usage(_db, _org_id):
        return {"characters": 1.0}

    async def _dispatch(*_a, **_k):
        return None

    finalized: list = []

    async def _finalize(_db, org_id, start, end):
        finalized.append(org_id)
        if org_id == broken.org_id:
            raise RuntimeError("invoice finalization failed for this org")
        return {"total_cents": 0}

    monkeypatch.setattr(usage_service, "current_period_usage", _usage)
    monkeypatch.setattr(webhook_service, "dispatch", _dispatch)
    monkeypatch.setattr(billing_service, "finalize_invoice", _finalize)

    good = _FakeSub({"characters": 5_000})
    broken = _FakeSub({"characters": 5_000})
    for sub in (good, broken):
        # a period that has ended → the invoice is finalized in this pass
        sub.current_period_end = _now() - timedelta(days=1)
        sub.current_period_start = _now() - timedelta(days=31)
    db = _FakeDB()

    await module._process_all(db, [broken, good], _now())

    assert finalized == [broken.org_id, good.org_id], (
        "the broken subscription's failure must not stop the good one's billing")
    assert db.rollbacks == 1, "the failing subscription is rolled back on its own"


def _now():
    from app.db.base import utcnow
    return utcnow()
