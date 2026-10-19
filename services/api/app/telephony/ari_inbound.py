"""Inbound Stasis leg intake (P3 lab decision — docs/ASTERISK_LOCAL_SIP_LAB.md).

An inbound leg has NO originate, NO client-chosen ``talkflow-<uuid>`` channel
id, and no operator-initiated CallSession. This module turns a ``StasisStart``
that arrives through the lab's private ``talkflow-inbound`` dialplan context
into product state under the same contracts as the rest of the adapter:

- **Route-arg policy** (documented; the dialplan must match): the ONLY accepted
  shape is ``Stasis(talkflow,inbound)`` — exactly one arg, exactly
  :data:`INBOUND_ROUTE_ARG`. Anything else is not an inbound leg and stays
  ignored (never guessed into state).
- **Identity**: caller number AND dialed exten must BOTH be operator-allowlisted
  local extensions (``asterisk_allowed_extensions`` — the same allowlist the
  adapter enforces before originate). Unauthenticated inbound from unknown
  AORs/trunks is rejected BEFORE any session is created: best-effort hangup,
  logged, no state invented. Outbound-meta reconciled legs (operator transfer
  into Stasis) are future work; the allowlisted-AOR path ships here.
- **Tenancy**: inbound sessions attach to the operator-configured org
  (``asterisk_inbound_org_id``). Unset (default) ⇒ every inbound leg is
  rejected — multi-tenant ownership is never guessed.
- **Lifecycle**: accepted legs join the outbound correlation machinery
  immediately — the shared channel map is seeded so the existing normalizer +
  dispatch + single terminal-claim own the rest (ringing → connected → ended,
  one terminal claim, reconnect-safe). ``call_sid`` is derived deterministically
  from the channel id, so a restart's re-delivered ``StasisStart`` re-seeds the
  map and is absorbed by the ``call_sid`` unique constraint instead of
  duplicating the session.
- **Ring/answer**: an accepted ``StasisStart`` maps to RINGING (the call is
  arriving on the TalkFlow side — honest, unlike the outbound pre-dial case)
  and the leg is answered best-effort so the CONNECTED transition (and the
  agent-media attach) can follow. A failed answer never invents state: the
  caller simply clears and the leg ends through normal hangup processing.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Awaitable, Callable, Iterable

from app.telephony.ari_events import ARIEventFrame, DispatchFn
from app.telephony.base import CallStatus

log = logging.getLogger("app.telephony.ari_inbound")

#: The one accepted dialplan shape: ``Stasis(<app>,inbound)``. Kept a constant
#: (not a flag) so the dialplan contract and the product policy cannot drift.
INBOUND_ROUTE_ARG = "inbound"

AnswerFn = Callable[[str], Awaitable[None]]   # channel_id → answered
HangupFn = Callable[[str], Awaitable[None]]   # channel_id → terminated


def inbound_call_sid(channel_id: str) -> str:
    """Deterministic ``call_sid`` for an inbound leg (restart-safe correlation)."""
    digest = hashlib.sha256(channel_id.encode("utf-8")).hexdigest()[:32]
    return f"talkflow-inbound-{digest}"


class InboundIntake:
    """Consume ``StasisStart`` frames for inbound legs (or reject them)."""

    def __init__(
        self,
        *,
        dispatch: DispatchFn,
        channel_map: dict[str, str],
        org_id: uuid.UUID | None,
        allowed_extensions: Iterable[str],
        answer: AnswerFn | None = None,
        hangup: HangupFn | None = None,
    ) -> None:
        self._dispatch = dispatch
        self._channel_map = channel_map
        self._org_id = org_id
        self._allowed = frozenset(ext.strip() for ext in allowed_extensions if ext.strip())
        self._answer = answer
        self._hangup = hangup
        self._handled: set[str] = set()

    @staticmethod
    def is_inbound_shape(payload: dict[str, Any]) -> bool:
        """True only for the documented ``Stasis(talkflow,inbound)`` shape."""
        return payload.get("args") == [INBOUND_ROUTE_ARG]

    async def __call__(self, payload: dict[str, Any], frame: ARIEventFrame) -> bool:
        """Intake one raw event. Return ``True`` when the event is consumed."""
        if frame.event_type != "StasisStart" or not self.is_inbound_shape(payload):
            return False
        channel_id = frame.channel_id
        if channel_id in self._handled:
            log.debug(
                "absorbing re-delivered StasisStart for inbound channel %s", channel_id)
            return True

        channel = payload.get("channel") or {}
        caller = str((channel.get("caller") or {}).get("number") or "").strip()
        exten = str((channel.get("dialplan") or {}).get("exten") or "").strip()
        reason = self._reject_reason(caller, exten)
        if reason is not None:
            log.warning(
                "inbound Stasis leg %s rejected (%s); caller=%r exten=%r",
                channel_id, reason, caller, exten,
            )
            self._handled.add(channel_id)
            await self._best_effort(self._hangup, channel_id, "hangup")
            return True

        call_sid = inbound_call_sid(channel_id)
        caller_name = str((channel.get("caller") or {}).get("name") or "")[:120]
        created = await self._create_session(
            call_sid, caller, exten, channel_id, caller_name)
        self._handled.add(channel_id)
        # Seed BEFORE anything else: the rest of the leg's life (state changes,
        # hangup) must flow through the shared correlation map either way.
        self._channel_map[channel_id] = call_sid
        if not created:
            log.info(
                "inbound leg %s already tracked as %s; absorbing re-delivery",
                channel_id, call_sid,
            )
            return True

        log.info(
            "inbound call accepted: channel=%s caller=%s exten=%s sid=%s",
            channel_id, caller, exten, call_sid,
        )
        await self._dispatch(call_sid, CallStatus.RINGING, channel_id)
        await self._best_effort(self._answer, channel_id, "answer")
        return True

    # ------------------------------------------------------------------ #

    def _reject_reason(self, caller: str, exten: str) -> str | None:
        if self._org_id is None:
            return "inbound org not configured (fail closed)"
        if caller not in self._allowed:
            return "caller extension not allowlisted"
        if exten not in self._allowed:
            return "dialed extension not allowlisted"
        return None

    async def _create_session(
        self, call_sid: str, caller: str, exten: str, channel_id: str,
        caller_name: str,
    ) -> bool:
        """Insert the inbound CallSession. ``False`` ⇒ it already existed."""
        from sqlalchemy.exc import IntegrityError

        from app.db import models as M
        from app.db.session import db_session

        async with db_session() as db:
            db.add(M.CallSession(
                org_id=self._org_id,
                created_by=None,
                call_sid=call_sid,
                direction="inbound",
                from_number=caller,
                to_number=exten,
                caller_name=caller_name,
                status="initiating",
                mode="ai_agent",
                provider="asterisk",
                metadata_json={
                    "ari_channel": channel_id,
                    "source": "asterisk_ari_inbound",
                    "route_arg": INBOUND_ROUTE_ARG,
                },
            ))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                return False
        return True

    async def _best_effort(
        self, fn: Callable[[str], Awaitable[None]] | None, channel_id: str, what: str
    ) -> None:
        if fn is None:
            return
        try:
            await fn(channel_id)
        except Exception:  # noqa: BLE001 — answer/hangup failures never break intake
            log.exception("best-effort %s failed for channel %s", what, channel_id)


def build_inbound_intake(
    *,
    dispatch: DispatchFn,
    channel_map: dict[str, str],
    answer: AnswerFn | None,
    hangup: HangupFn | None,
) -> InboundIntake:
    """Build the production intake from pydantic-settings (fail-closed org)."""
    from app.config import settings

    org_raw = (settings.asterisk_inbound_org_id or "").strip()
    try:
        org_id = uuid.UUID(org_raw) if org_raw else None
    except ValueError:
        log.error(
            "ASTERISK_INBOUND_ORG_ID=%r is not a UUID; inbound legs are rejected",
            org_raw,
        )
        org_id = None
    return InboundIntake(
        dispatch=dispatch,
        channel_map=channel_map,
        org_id=org_id,
        allowed_extensions=tuple(
            ext.strip() for ext in settings.asterisk_allowed_extensions.split(",") if ext.strip()
        ),
        answer=answer,
        hangup=hangup,
    )
