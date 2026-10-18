"""Outbound calling gate policy (app.telephony.gate) — pure unit lane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.telephony.gate import GateInput, evaluate


def _allow(**overrides) -> GateInput:
    base = dict(
        mode="human_dial",
        campaign_active=True,
        campaign_window_start_hour_utc=0,
        campaign_window_end_hour_utc=24,
        campaign_max_attempts=2,
        campaign_max_concurrent=1,
        contact_do_not_call=False,
        consent_granted=None,
        contact_attempts=0,
        active_concurrent_calls=0,
        now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return GateInput(**base)


def test_human_dial_with_no_campaign_constraints_allowed():
    decision = evaluate(_allow())
    assert decision.allowed is True
    assert decision.reason is None


def test_dnc_blocks_every_mode():
    for mode in ("human_dial", "ai_agent"):
        decision = evaluate(_allow(mode=mode, contact_do_not_call=True,
                                   campaign_ai_authorized=True,
                                   consent_granted=True))
        assert decision.allowed is False
        assert decision.reason == "dnc"


def test_ai_calls_require_authorized_campaign():
    decision = evaluate(_allow(mode="ai_agent", campaign_ai_authorized=False,
                               consent_granted=True))
    assert decision.allowed is False
    assert decision.reason == "ai_not_authorized"


def test_ai_calls_require_disclosure_flag():
    decision = evaluate(_allow(mode="ai_agent", campaign_ai_authorized=True,
                               campaign_ai_disclosure_required=False,
                               consent_granted=True))
    assert decision.allowed is False
    assert decision.reason == "ai_disclosure_missing"


def test_ai_calls_require_agent_prompt():
    decision = evaluate(_allow(mode="ai_agent", campaign_ai_authorized=True,
                               campaign_agent_prompt_id=None,
                               consent_granted=True))
    assert decision.allowed is False
    assert decision.reason == "agent_prompt_missing"


def test_ai_calls_require_standing_consent():
    for consent in (None, False):
        decision = evaluate(_allow(mode="ai_agent", campaign_ai_authorized=True,
                                   campaign_agent_prompt_id="prompt",
                                   consent_granted=consent))
        assert decision.allowed is False
        assert decision.reason == "no_consent"


def test_ai_call_with_consent_and_authorization_allowed():
    decision = evaluate(_allow(mode="ai_agent", campaign_ai_authorized=True,
                               campaign_agent_prompt_id="prompt",
                               consent_granted=True))
    assert decision.allowed is True


def test_inactive_campaign_blocks_human_dial_too():
    decision = evaluate(_allow(campaign_active=False))
    assert decision.allowed is False
    assert decision.reason == "campaign_not_active"


def test_calling_window_utc_hours():
    # window 13:00-20:00 UTC, now 12:00 UTC -> outside
    decision = evaluate(_allow(campaign_window_start_hour_utc=13,
                               campaign_window_end_hour_utc=20))
    assert decision.allowed is False
    assert decision.reason == "outside_window"
    assert "13:00" in decision.detail["window"]

    # same window, now 14:30 UTC -> inside
    decision = evaluate(_allow(
        campaign_window_start_hour_utc=13, campaign_window_end_hour_utc=20,
        now=datetime(2026, 6, 1, 14, 30, tzinfo=timezone.utc)))
    assert decision.allowed is True


def test_calling_window_converts_tz_aware_clock_to_utc():
    # 16:00 in UTC+4 == 12:00 UTC -> outside a 13-20 window
    decision = evaluate(_allow(
        campaign_window_start_hour_utc=13, campaign_window_end_hour_utc=20,
        now=datetime(2026, 6, 1, 16, 0, tzinfo=timezone(timedelta(hours=4)))))
    assert decision.allowed is False
    assert decision.reason == "outside_window"


def test_retry_backoff_window_blocks_until_eligible():
    eligible = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    decision = evaluate(_allow(
        campaign_window_start_hour_utc=0, campaign_window_end_hour_utc=0,  # skip window check
        next_attempt_eligible_at=eligible,
        now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)))
    assert decision.allowed is False
    assert decision.reason == "backoff_window"
    assert decision.detail["retry_after"] == eligible.isoformat()


def test_max_attempts_reached():
    decision = evaluate(_allow(contact_attempts=2, campaign_max_attempts=2))
    assert decision.allowed is False
    assert decision.reason == "max_attempts_reached"


def test_max_concurrent_reached():
    decision = evaluate(_allow(active_concurrent_calls=1, campaign_max_concurrent=1))
    assert decision.allowed is False
    assert decision.reason == "max_concurrent_reached"
