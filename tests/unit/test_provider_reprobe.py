"""A provider excluded for errors has to be re-probed, not buried.

`record_outcome` drops a provider once its error rate crosses 0.5, and the
error rate only decays on requests that are routed to it. Before the cooldown
existed, that made the exclusion self-locking: a concurrent benchmark pushed
the local CPU model past its attempt deadline, `mt/nllb_ct2` was marked
unhealthy, and every later request — including single-shot REST a few seconds
afterwards — landed on `dev_echo`. A load spike was being remembered as an
outage forever.
"""
from __future__ import annotations

import time

from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.types import Task

KEY = (Task.MT.value, "nllb_ct2")


def _router(**kw) -> ModelRouter:
    specs = {Task.MT: [
        ProviderSpec(name="nllb_ct2", task=Task.MT, quality_tier=78,
                     cost_tier=40, latency_class="fast", private=True),
        ProviderSpec(name="dev_echo", task=Task.MT, quality_tier=1,
                     cost_tier=0, latency_class="realtime"),
    ]}
    return ModelRouter(specs, gpu_available=False, **kw)


def _fail_until_excluded(r: ModelRouter) -> None:
    for _ in range(6):
        r.record_outcome(Task.MT, "nllb_ct2", 60_000.0, ok=False)
    assert r.health[KEY].available is False


def route_provider(r: ModelRouter) -> str:
    return r.route(Task.MT, source_lang="en", target_lang="de").provider


def test_excluded_provider_is_skipped_during_the_cooldown() -> None:
    r = _router(reprobe_after_s=30.0)
    _fail_until_excluded(r)
    assert route_provider(r) == "dev_echo"


def test_exclusion_expires_and_the_provider_is_probed_again() -> None:
    r = _router(reprobe_after_s=30.0)
    _fail_until_excluded(r)
    r.health[KEY].unavailable_since -= 31.0      # the cooldown elapses
    assert route_provider(r) == "nllb_ct2"
    # re-admission clears the stale counters, or the next single failure would
    # re-open the breaker instantly (1 error of 6 requests was already > 0.5).
    assert r.health[KEY].request_count <= 1


def test_a_probe_gets_a_fair_trial_before_reopening() -> None:
    """Re-admission clears the counters, so the exclusion needs 4 fresh
    failures again rather than tipping over on the first timeout."""
    r = _router(reprobe_after_s=30.0)
    _fail_until_excluded(r)
    r.health[KEY].unavailable_since -= 31.0
    route_provider(r)
    r.record_outcome(Task.MT, "nllb_ct2", 60_000.0, ok=False)
    assert r.health[KEY].available is True
    for _ in range(3):
        r.record_outcome(Task.MT, "nllb_ct2", 60_000.0, ok=False)
    assert route_provider(r) == "dev_echo"


def test_success_clears_the_exclusion_stamp() -> None:
    r = _router(reprobe_after_s=30.0)
    _fail_until_excluded(r)
    r.health[KEY].unavailable_since -= 31.0
    route_provider(r)
    r.record_outcome(Task.MT, "nllb_ct2", 900.0, ok=True)
    h = r.health[KEY]
    assert h.available and h.unavailable_since == 0.0


def test_cooldown_of_zero_keeps_the_sticky_behaviour() -> None:
    """Operator escape hatch: a provider that is genuinely down should stay
    down until something re-enables it explicitly."""
    r = _router(reprobe_after_s=0.0)
    _fail_until_excluded(r)
    r.health[KEY].unavailable_since = time.time() - 3600
    assert route_provider(r) == "dev_echo"


def test_reaffirming_an_exclusion_does_not_restart_the_cooldown() -> None:
    """AIFacade excludes each candidate while it assembles a failover chain and
    restores the previous state right after. Restoring must not be read as a
    fresh outage, or the reprobe clock is reset on every request and the
    exclusion is permanent again — which is exactly how the local model stayed
    dead for the REST pass that followed a concurrent storm."""
    r = _router(reprobe_after_s=30.0)
    _fail_until_excluded(r)
    stamp = r.health[KEY].unavailable_since
    for _ in range(5):
        r.mark_available(Task.MT, "nllb_ct2", False)
        r.mark_available(Task.MT, "nllb_ct2", False)
    assert r.health[KEY].unavailable_since == stamp
    r.health[KEY].unavailable_since -= 31.0
    assert route_provider(r) == "nllb_ct2"
