"""Outbound Calling Gate (P0/P1 acceptance §4).

Pure decision function: every queued or direct outbound dial must pass
BEFORE any telephony provider is invoked. No DB access here — the caller
aggregates inputs; this module owns the POLICY so it can be unit-tested
independently of infrastructure.

Policy summary (never bypassed in service code):
- AI-agent calls exist ONLY through an explicitly authorized campaign
  (ai_agent_authorized + authorized_by finalized at activation).
- AI disclosure is mandatory for AI-agent campaigns.
- DNC (contact.do_not_call) blocks every mode.
- AI-agent dials require the newest consent decision to be a grant.
- Calls only inside the campaign window (UTC hours, [start, end)).
- Per-contact attempt caps + retry backoff + concurrency caps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

BLOCK_REASONS = frozenset({
    "contact_not_found",       # job pointed at a missing contact
    "campaign_not_active",     # draft/paused/completed/stopped campaign
    "ai_not_authorized",       # ai_agent mode without finished authorization
    "ai_disclosure_missing",   # ai_agent mode without mandatory disclosure flag
    "agent_prompt_missing",    # ai_agent mode with no prompt configured
    "dnc",                     # contact opted out of calling (do_not_call)
    "no_consent",              # ai_agent without a standing consent grant
    "outside_window",          # outside the campaign calling window
    "backoff_window",          # inside the per-contact retry-backoff silence
    "max_attempts_reached",    # contact already called max_attempts times
    "max_concurrent_reached",  # campaign concurrency cap
})


@dataclass(frozen=True)
class GateInput:
    mode: str = "human_dial"                     # human_dial | ai_agent
    campaign_active: bool = True
    campaign_ai_authorized: bool = False
    campaign_ai_disclosure_required: bool = True
    campaign_agent_prompt_id: str | None = None
    campaign_window_start_hour_utc: int = 8
    campaign_window_end_hour_utc: int = 20
    campaign_max_attempts: int = 2
    campaign_max_concurrent: int = 1
    contact_do_not_call: bool = False
    consent_granted: bool | None = None          # None = no ledger rows yet
    contact_attempts: int = 0                    # calls already attempted for this contact (campaign scope)
    active_concurrent_calls: int = 0             # claimed/placing jobs in campaign scope
    next_attempt_eligible_at: datetime | None = None  # backoff floor
    now: datetime | None = None                  # evaluated clock (UTC-aware)


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str | None = None
    detail: dict = field(default_factory=dict)


def evaluate(input_: GateInput) -> GateDecision:
    """Return allow/block. The FIRST failing policy wins; order is stable."""
    detail: dict = {}

    if not input_.campaign_active:
        return GateDecision(False, "campaign_not_active", detail)

    if input_.contact_do_not_call:
        return GateDecision(False, "dnc", detail)

    if input_.mode == "ai_agent":
        if not input_.campaign_ai_authorized:
            return GateDecision(False, "ai_not_authorized", detail)
        if not input_.campaign_ai_disclosure_required:
            return GateDecision(False, "ai_disclosure_missing", detail)
        if not input_.campaign_agent_prompt_id:
            return GateDecision(False, "agent_prompt_missing", detail)

    # (DNC check moved earlier — it outranks campaign configuration errors.)

    if input_.mode == "ai_agent" and input_.consent_granted is not True:
        return GateDecision(False, "no_consent", detail)

    now = input_.now or datetime.now(timezone.utc)

    if input_.next_attempt_eligible_at is not None and now < input_.next_attempt_eligible_at:
        detail["retry_after"] = input_.next_attempt_eligible_at.isoformat()
        return GateDecision(False, "backoff_window", detail)

    if input_.campaign_window_end_hour_utc > input_.campaign_window_start_hour_utc:
        hour = now.astimezone(timezone.utc).hour if now.tzinfo is not None else now.hour
        # the window is UTC-based; a caller may pass tz-aware local time — convert
        if not (input_.campaign_window_start_hour_utc <= hour < input_.campaign_window_end_hour_utc):
            detail["window"] = f"{input_.campaign_window_start_hour_utc}:00-{input_.campaign_window_end_hour_utc}:00 UTC"
            return GateDecision(False, "outside_window", detail)

    if input_.contact_attempts >= input_.campaign_max_attempts:
        detail["attempts"] = input_.contact_attempts
        detail["max_attempts"] = input_.campaign_max_attempts
        return GateDecision(False, "max_attempts_reached", detail)

    if input_.active_concurrent_calls >= input_.campaign_max_concurrent:
        detail["active_calls"] = input_.active_concurrent_calls
        detail["max_concurrent"] = input_.campaign_max_concurrent
        return GateDecision(False, "max_concurrent_reached", detail)

    return GateDecision(True, None, detail)
