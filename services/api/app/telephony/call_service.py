"""Call Service: International calling lifecycle, state machine & DB management."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.errors import AppError, NotFoundError, ValidationError
from app.services import audit_service, meeting_service, usage_service
from app.telephony.base import CallDirection, CallStatus, TelephonyCallResult
from app.telephony.phone_number_service import PhoneNumberService
from app.telephony.service import get_telephony_service

log = logging.getLogger("app.telephony.call_service")


class CallService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.telephony = get_telephony_service()

    async def create_outbound_call(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        to_number: str,
        from_number: str | None = None,
        caller_language: str = "en",
        receiver_language: str = "ja",
        caller_name: str = "Caller",
        recipient_name: str = "",
        mode: str = "human_to_human",
        recording_requested: bool = False,
        agent_id: uuid.UUID | None = None,
        prompt_version_id: uuid.UUID | None = None,
        base_url: str = "",
    ) -> M.CallSession:
        from app.telephony.security import TelephonySecurity

        # Enforce Recording OFF by default (Phase 12 & 13 Privacy Policy)
        recording_enabled = TelephonySecurity.enforce_recording_policy(
            requested_recording=recording_requested,
            caller_consented=False,
            recipient_consented=False,
        )

        # 1. Normalize and validate E.164 destination
        norm_to = PhoneNumberService.normalize_to_e164(to_number)
        is_valid, err = PhoneNumberService.validate_e164(norm_to)
        if not is_valid:
            raise ValidationError(err or "Invalid destination phone number.")

        # 2. Determine caller ID
        caller_id = from_number
        if not caller_id:
            res = await self.db.execute(
                select(M.PhoneNumber)
                .where(M.PhoneNumber.org_id == org_id, M.PhoneNumber.status == "active")
                .limit(1)
            )
            phone_row = res.scalars().first()
            caller_id = phone_row.e164_number if phone_row else (settings.twilio_phone_number or "+12025550199")

        caller_id = PhoneNumberService.normalize_to_e164(caller_id)

        # 3. Create underlying meeting for real-time translation pipeline reuse
        meeting_title = f"Phone Call: {caller_id} -> {norm_to}"
        meeting, participant = await meeting_service.create_meeting(
            self.db,
            org_id=org_id,
            created_by=user_id,
            title=meeting_title,
            mode="ws",
            speak_lang=caller_language,
            hear_lang=receiver_language,
        )

        call_id = uuid.uuid4()
        temp_sid = f"CA_{call_id.hex[:24]}"

        # 4. Construct webhook & media stream URLs
        host_base = base_url or settings.telephony_webhook_base_url or f"http://127.0.0.1:{settings.api_port}"
        webhook_url = f"{host_base}/api/v1/telephony/webhooks/voice"
        ws_scheme = "wss" if host_base.startswith("https") else "ws"
        host_netloc = host_base.split("://")[-1]
        stream_url = f"{ws_scheme}://{host_netloc}/ws/telephony/media/{call_id}"

        # 5. Place call via provider
        provider = self.telephony.get_provider()
        call_res: TelephonyCallResult = await provider.create_call(
            to=norm_to,
            from_=caller_id,
            webhook_url=webhook_url,
            stream_url=stream_url,
            custom_params={
                "call_id": str(call_id),
                "caller_lang": caller_language,
                "receiver_lang": receiver_language,
                "mode": mode,
            },
        )

        actual_sid = call_res.call_sid or temp_sid

        # 6. Create CallSession in database
        call_session = M.CallSession(
            id=call_id,
            org_id=org_id,
            created_by=user_id,
            call_sid=actual_sid,
            direction="outbound",
            from_number=caller_id,
            to_number=norm_to,
            caller_name=caller_name,
            recipient_name=recipient_name or PhoneNumberService.format_friendly(norm_to),
            caller_language=caller_language,
            receiver_language=receiver_language,
            status=call_res.status.value,
            mode=mode,
            provider=provider.provider_name,
            agent_id=agent_id,
            prompt_version_id=prompt_version_id,
            meeting_id=meeting.id,
            recording_enabled=recording_enabled,
            started_at=utcnow(),
            error_code=call_res.error_code,
            error_message=call_res.error_message,
            metadata_json={"raw": call_res.raw_response, "stream_url": stream_url},
        )
        self.db.add(call_session)

        # 7. Record immutable event
        event = M.CallEvent(
            call_id=call_id,
            event_type="call_initiated",
            payload_json={
                "status": call_res.status.value,
                "provider": provider.provider_name,
                "sid": actual_sid,
            },
            created_at=utcnow(),
        )
        self.db.add(event)
        await self.db.commit()

        await audit_service.record(
            self.db,
            action="telephony.call_created",
            org_id=org_id,
            actor_id=user_id,
            resource_type="call_session",
            resource_id=str(call_id),
        )

        log.info(
            "Outbound call session created: %s -> %s (sid: %s, status: %s)",
            caller_id, norm_to, actual_sid, call_res.status.value
        )
        return call_session

    async def get_call_by_id(self, call_id: uuid.UUID, org_id: uuid.UUID) -> M.CallSession:
        res = await self.db.execute(
            select(M.CallSession).where(
                M.CallSession.id == call_id,
                M.CallSession.org_id == org_id,
            )
        )
        call = res.scalars().first()
        if not call:
            raise NotFoundError("Call session not found.")
        return call

    async def get_call_by_sid(self, call_sid: str) -> M.CallSession | None:
        res = await self.db.execute(
            select(M.CallSession).where(M.CallSession.call_sid == call_sid)
        )
        return res.scalars().first()

    async def list_calls(
        self,
        org_id: uuid.UUID,
        limit: int = 50,
        status: str = "",
    ) -> list[M.CallSession]:
        q = select(M.CallSession).where(M.CallSession.org_id == org_id)
        if status:
            q = q.where(M.CallSession.status == status)
        q = q.order_by(M.CallSession.created_at.desc()).limit(limit)
        res = await self.db.execute(q)
        return list(res.scalars().all())

    async def transition_status(
        self,
        call_sid: str,
        new_status: CallStatus | str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_seconds: int = 0,
        extra_data: dict | None = None,
    ) -> M.CallSession | None:
        call = await self.get_call_by_sid(call_sid)
        if not call:
            return None

        status_val = new_status.value if isinstance(new_status, CallStatus) else new_status
        call.status = status_val

        if status_val in ("connected", "translating") and not call.connected_at:
            call.connected_at = utcnow()

        if status_val in ("ended", "failed", "busy", "no_answer", "declined"):
            if not call.ended_at:
                call.ended_at = utcnow()
            if duration_seconds > 0:
                call.duration_seconds = duration_seconds
            elif call.connected_at and call.ended_at:
                delta = int((call.ended_at - call.connected_at).total_seconds())
                call.duration_seconds = max(0, delta)

            # Calculate itemized metering cost breakdown (Phase 12 & 13)
            # 1. Telephony: standard PSTN outbound at $0.02 / min
            minutes = max(1, (call.duration_seconds + 59) // 60)
            call.telephony_cost_cents = minutes * 2

            # 2. STT Speech-to-Text (~$0.006 / min)
            if not call.stt_cost_cents:
                call.stt_cost_cents = max(1, (call.duration_seconds * 1 + 59) // 100)

            # 3. MT Machine Translation (~$0.005 / min)
            if not call.mt_cost_cents:
                call.mt_cost_cents = max(1, (call.duration_seconds * 1 + 59) // 120)

            # 4. TTS Text-to-Speech (~$0.009 / min)
            if not call.tts_cost_cents:
                call.tts_cost_cents = max(1, (call.duration_seconds * 1 + 59) // 80)

            # 5. Total Cost (Sum of all 4 independent line items)
            call.total_cost_cents = (
                call.telephony_cost_cents + call.stt_cost_cents + call.mt_cost_cents + call.tts_cost_cents
            )

            # Record in immutable billing usage ledger
            try:
                await usage_service.record_usage(
                    self.db,
                    org_id=call.org_id,
                    user_id=call.created_by,
                    product="telephony",
                    unit_type="telephony_minutes",
                    units=float(minutes),
                    source_lang=call.caller_language,
                    target_lang=call.receiver_language,
                    metadata={
                        "call_id": str(call.id),
                        "duration_seconds": call.duration_seconds,
                        "cost_cents": call.total_cost_cents,
                    },
                )
            except Exception as e:
                log.warning("Failed to record telephony usage: %s", e)

        if error_code:
            call.error_code = error_code
        if error_message:
            call.error_message = error_message

        # Log event
        ev = M.CallEvent(
            call_id=call.id,
            event_type="status_change",
            payload_json={"status": status_val, "error": error_message, **(extra_data or {})},
            created_at=utcnow(),
        )
        self.db.add(ev)
        await self.db.commit()
        return call

    async def end_call(self, call_id: uuid.UUID, org_id: uuid.UUID) -> M.CallSession:
        call = await self.get_call_by_id(call_id, org_id)
        provider = self.telephony.get_provider(call.provider)
        await provider.end_call(call.call_sid)
        updated = await self.transition_status(call.call_sid, CallStatus.ENDED)
        return updated or call

    async def get_call_summary_metrics(self, org_id: uuid.UUID) -> dict[str, Any]:
        """Aggregate metering breakdown across calls for the organization (Phase 12 & 13)."""
        calls = await self.list_calls(org_id, limit=200)
        total_calls = len(calls)
        total_duration = sum(c.duration_seconds for c in calls)
        telephony_cost = sum(c.telephony_cost_cents for c in calls)
        stt_cost = sum(c.stt_cost_cents for c in calls)
        mt_cost = sum(c.mt_cost_cents for c in calls)
        tts_cost = sum(c.tts_cost_cents for c in calls)
        total_cost = sum(c.total_cost_cents for c in calls)
        avg_duration = int(total_duration / total_calls) if total_calls > 0 else 0

        return {
            "total_calls": total_calls,
            "total_duration_seconds": total_duration,
            "avg_duration_seconds": avg_duration,
            "telephony_cost_cents": telephony_cost,
            "stt_cost_cents": stt_cost,
            "mt_cost_cents": mt_cost,
            "tts_cost_cents": tts_cost,
            "total_cost_cents": total_cost,
            "recording_default": "OFF",
            "security_status": "enforced",
        }

    async def get_call_events(self, call_id: uuid.UUID, org_id: uuid.UUID) -> list[M.CallEvent]:
        """Fetch immutable audit ledger events for a call."""
        # Verify ownership
        await self.get_call_by_id(call_id, org_id)
        res = await self.db.execute(
            select(M.CallEvent).where(M.CallEvent.call_id == call_id).order_by(M.CallEvent.created_at.asc())
        )
        return list(res.scalars().all())
