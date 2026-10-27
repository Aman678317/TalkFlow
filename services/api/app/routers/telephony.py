"""Telephony API Router: Calling Endpoints, Webhooks & Media Stream WebSockets."""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.session import db_session, get_db
from app.deps import Principal, client_ip_hash, require_org_user
from app.errors import AppError, NotFoundError, ValidationError, UnsupportedLanguageError
from app.ratelimit import check_rate_limit
from app.telephony.call_service import CallService
from app.telephony.call_transcript import assemble_transcript
from app.telephony.escalation import shared_dispatcher
from app.telephony.media.agent_media_session import MediaCallEventSink
from app.telephony.media_stream_service import MediaStreamService, TelephonyMediaStreamSession
from app.telephony.phone_number_service import PhoneNumberService
from app.telephony.webhook_service import TelephonyWebhookService

log = logging.getLogger("app.routers.telephony")

router = APIRouter(prefix="/api/v1/telephony", tags=["telephony"])


# --------------------------------------------------------------------------- #
# Request & Response Schemas
# --------------------------------------------------------------------------- #


class CreateCallRequest(BaseModel):
    to_number: str = Field(..., description="International E.164 phone number, e.g. +919876543210")
    from_number: str | None = Field(default=None, description="Registered caller ID phone number")
    caller_language: str = Field(default="en", description="Spoken language of caller (e.g. 'en', 'hi', 'ja')")
    receiver_language: str = Field(default="ja", description="Target language of receiver (e.g. 'ja', 'hi', 'en')")
    caller_name: str = Field(default="", description="Name of caller")
    recipient_name: str = Field(default="", description="Name of recipient")
    mode: str = Field(default="human_to_human", description="human_to_human | ai_agent | call_center")
    recording_enabled: bool = Field(default=False, description="Recording toggle (OFF by default for privacy compliance)")
    agent_id: str | None = None
    prompt_version_id: str | None = None
    # Tenant-private call (issue #109 class 3, finding 8): the call's
    # translations are routed private-only — no non-private provider ever
    # receives the conversation.
    tenant_private_only: bool = Field(default=False, description="Route this call's translations to private providers only")


class CallSessionOut(BaseModel):
    id: str
    call_sid: str
    direction: str
    from_number: str
    to_number: str
    caller_name: str
    recipient_name: str
    caller_language: str
    receiver_language: str
    status: str
    mode: str
    provider: str
    recording_enabled: bool = False
    duration_seconds: int
    started_at: str | None = None
    connected_at: str | None = None
    ended_at: str | None = None
    telephony_cost_cents: int
    stt_cost_cents: int
    mt_cost_cents: int
    tts_cost_cents: int
    total_cost_cents: int
    error_code: str | None = None
    error_message: str | None = None


class PhoneNumberCreate(BaseModel):
    e164_number: str
    country_code: str = "US"
    friendly_name: str = ""


class PhoneNumberOut(BaseModel):
    id: str
    e164_number: str
    country_code: str
    friendly_name: str
    status: str
    provider: str


class ForwardingSettingsRequest(BaseModel):
    mobile_number: str = ""
    ring_mobile_on_inbound: bool = True
    ring_web_on_inbound: bool = True
    outbound_routing: str = "browser"  # 'browser' | 'mobile_bridge'
    twilio_phone_number: str = ""


class VerifyPhoneRequest(BaseModel):
    phone_number: str
    friendly_name: str = "Agent Mobile"


class TestCallRequest(BaseModel):
    phone_number: str


class BridgeCallRequest(BaseModel):
    customer_number: str
    mobile_number: str = ""
    caller_language: str = "hi"
    receiver_language: str = "ja"
    caller_id: str = ""


def _serialize_call(c: M.CallSession) -> CallSessionOut:
    return CallSessionOut(
        id=str(c.id),
        call_sid=c.call_sid,
        direction=c.direction,
        from_number=c.from_number,
        to_number=c.to_number,
        caller_name=c.caller_name,
        recipient_name=c.recipient_name,
        caller_language=c.caller_language,
        receiver_language=c.receiver_language,
        status=c.status,
        mode=c.mode,
        provider=c.provider,
        recording_enabled=getattr(c, "recording_enabled", False),
        duration_seconds=c.duration_seconds,
        started_at=c.started_at.isoformat() if c.started_at else None,
        connected_at=c.connected_at.isoformat() if c.connected_at else None,
        ended_at=c.ended_at.isoformat() if c.ended_at else None,
        telephony_cost_cents=c.telephony_cost_cents,
        stt_cost_cents=c.stt_cost_cents,
        mt_cost_cents=c.mt_cost_cents,
        tts_cost_cents=c.tts_cost_cents,
        total_cost_cents=c.total_cost_cents,
        error_code=c.error_code,
        error_message=c.error_message,
    )


# --------------------------------------------------------------------------- #
# Call Management Endpoints
# --------------------------------------------------------------------------- #


@router.get("/countries")
async def list_supported_countries() -> list[dict]:
    """Return supported countries with dial codes and flags for the calling dialpad."""
    return PhoneNumberService.get_supported_countries()


@router.post("/calls", response_model=CallSessionOut, status_code=201)
async def initiate_call(
    body: CreateCallRequest,
    req: Request,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Place an international phone call with real-time bidirectional translation.

    Idempotency: when the ``Idempotency-Key`` header is present, the dial goes
    through the call-job queue (org+key unique) — replaying the same key
    returns the SAME call session instead of placing a second PSTN call.
    AI-agent mode is intentionally rejected here: AI outbound exists only
    through explicitly authorized campaigns (POST /contacts/{id}/call).
    """
    # 1. Rate limiting check (Phase 12 & 13)
    await check_rate_limit(
        bucket="telephony:call",
        identity=principal.identity_for_rate_limit,
        spec=settings.rate_limit_telephony_call,
    )

    # 2. Narrow org_id / user_id — require_org_user guarantees these, but narrow
    #    the type so downstream code (and the type checker) sees UUID, not UUID|None.
    if principal.org_id is None:
        raise ValidationError("Organization not found for this account. Please contact support.")

    cs = CallService(db)

    if (idempotency_key or "").strip():
        from app.services.contacts_service import ContactsService
        from app.telephony.call_jobs import CallJobService
        from app.telephony.phone_number_service import PhoneNumberService

        jobs = CallJobService(db)
        contacts = ContactsService(db)
        e164 = PhoneNumberService.normalize_to_e164(body.to_number, default_country="US")
        contact = None
        from sqlalchemy import select as _select
        res = await db.execute(
            _select(M.Contact).where(M.Contact.org_id == principal.org_id,
                                     M.Contact.phone_e164 == e164))
        contact = res.scalars().first()
        if contact is None:
            contact = await contacts.create_contact(
                org_id=principal.org_id, phone=body.to_number,
                display_name=body.recipient_name or "",
                language=body.receiver_language,
                actor_id=principal.user_id)
        job, _created = await jobs.schedule_job(
            org_id=principal.org_id, contact_id=contact.id,
            campaign_id=None, idempotency_key=idempotency_key,
            actor_id=principal.user_id)
        job = await jobs.execute_job(
            principal.org_id, job.id, actor_id=principal.user_id,
            claimed_by_name=principal.identity_for_rate_limit)
        if job.status == "blocked":
            raise AppError(
                f"Call blocked by outbound gate: {job.blocked_reason}",
                status=409, recoverable=True, details={"reason": job.blocked_reason})
        if job.status == "failed":
            raise AppError("Carrier call dispatch failed for this job (already "
                           "attempted once); a new Idempotency-Key is required.",
                           status=502, recoverable=True, details={"reason": "provider_failure"})
        call_row = await db.get(M.CallSession, job.call_session_id) if job.call_session_id else None
        if call_row is None:
            raise AppError("Call job did not produce a call session.",
                           status=502, recoverable=True)
        await db.commit()
        return _serialize_call(call_row)

    base_url = str(req.base_url).rstrip("/")
    try:
        call = await cs.create_outbound_call(
            org_id=principal.org_id,
            user_id=principal.user_id,
            to_number=body.to_number,
            from_number=body.from_number,
            caller_language=body.caller_language,
            receiver_language=body.receiver_language,
            caller_name=body.caller_name or (principal.user.name if principal.user else "Caller"),
            recipient_name=body.recipient_name,
            mode=body.mode,
            recording_requested=body.recording_enabled,
            agent_id=uuid.UUID(body.agent_id) if body.agent_id else None,
            prompt_version_id=uuid.UUID(body.prompt_version_id) if body.prompt_version_id else None,
            tenant_private_only=body.tenant_private_only,
            base_url=base_url,
        )
    except ValidationError:
        raise
    except UnsupportedLanguageError:
        # Day-3: a language the capability registry does not carry is a 422
        # from the service itself — do not bury it in the generic carrier wrap.
        raise
    except Exception as exc:
        log.exception("Exception inside create_outbound_call")
        from app.errors import AppError
        raise AppError(f"Carrier call dispatch failed: {exc}", status=502, recoverable=True)

    if call.status == "failed":
        err_msg = call.error_message or "Carrier failed to place outbound call."
        from app.errors import AppError
        raise AppError(f"Carrier call rejected: {err_msg}", status=502, recoverable=True)
    return _serialize_call(call)



@router.get("/calls/analytics")
async def get_call_analytics(
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate call metering, billing breakdown and security metrics."""
    if principal.org_id is None:
        return {}
    cs = CallService(db)
    return await cs.get_call_summary_metrics(principal.org_id)


@router.get("/security/status")
async def get_security_status() -> dict[str, Any]:
    """Report telephony security posture (recording policy, signed webhooks, rate limiting)."""
    return {
        "recording_policy": {
            "default_state": "OFF",
            "enforced_by_law": True,
            "two_party_consent_required": True,
            "compliance_standard": "FCC / GDPR / Telecom Two-Party Consent Standard",
        },
        "signed_webhooks": {
            "enabled": settings.telephony_verify_webhook_signatures,
            "protocols": ["Twilio HMAC-SHA1", "Telnyx Ed25519 with anti-replay timestamp verification"],
            "tolerance_seconds": 300,
        },
        "rate_limiting": {
            "active": True,
            "call_initiation_limit": settings.rate_limit_telephony_call,
            "webhook_ingestion_limit": settings.rate_limit_telephony_webhook,
            "strategy": "Fixed-window token counter with structured 429 Retry-After",
        },
    }


# --------------------------------------------------------------------------- #
# Provider Status (Phase 14 — Real vs Simulated PSTN indicator)
# --------------------------------------------------------------------------- #


@router.get("/provider-status")
async def get_provider_status() -> dict[str, Any]:
    """Return current telephony provider mode and whether real PSTN calling is available."""
    has_twilio = bool(settings.twilio_account_sid and settings.twilio_auth_token)
    has_telnyx = bool(getattr(settings, "telnyx_api_key", None))

    # Explicit operator selection wins over credential heuristics. Local SIP is
    # NOT PSTN: never advertise real-PSTN availability on the Asterisk lane,
    # and make unready configuration visible instead of silent downgrade.
    if settings.telephony_provider == "asterisk":
        from app.telephony.service import get_telephony_service

        registered = get_telephony_service().get_registered_provider("asterisk")
        ready = registered is not None and registered.is_ready()
        return {
            "active_provider": "asterisk",
            "real_pstn_available": False,  # local SIP extension dialing only
            "caller_number": "",  # SIP caller ID is cosmetic; no PSTN number
            "peer_webrtc_available": True,  # always available (browser-to-browser)
            "setup_required": not ready,
            "setup_guide": {
                "asterisk": {
                    "step_1": "Set ASTERISK_TELEPHONY_ENABLED=true",
                    "step_2": "Set ASTERISK_ARI_BASE_URL / USERNAME / PASSWORD "
                              "(dedicated least-privilege ARI user)",
                    "step_3": "Set ASTERISK_ALLOWED_EXTENSIONS (comma-separated local "
                              "SIP extensions; public/E.164 dialing is rejected)",
                    "step_4": "Restart backend",
                }
            },
        }

    if has_twilio:
        active_provider = "twilio"
        real_pstn_available = True
        caller_number = settings.twilio_phone_number or "+17372212163"
    elif has_telnyx:
        active_provider = "telnyx"
        real_pstn_available = True
        caller_number = getattr(settings, "telnyx_phone_number", "")
    else:
        active_provider = "simulated"
        real_pstn_available = False
        caller_number = "+17372212163"

    return {
        "active_provider": active_provider,
        "real_pstn_available": real_pstn_available,
        "caller_number": caller_number,
        "peer_webrtc_available": True,  # always available (browser-to-browser)
        "setup_required": not real_pstn_available,
        "setup_guide": {
            "twilio": {
                "step_1": "Sign up for free at https://www.twilio.com (get $15 free credit)",
                "step_2": "Copy Account SID + Auth Token from https://console.twilio.com",
                "step_3": "Buy a phone number at https://console.twilio.com/us1/develop/phone-numbers/search",
                "step_4": "Add to .env: TWILIO_ACCOUNT_SID=AC... TWILIO_AUTH_TOKEN=... TWILIO_PHONE_NUMBER=+1...",
                "step_5": "Restart backend: uvicorn app.main:app --reload",
                "step_6": "For incoming webhooks use ngrok: ngrok http 8000",
            }
        },
    }


@router.get("/token")
async def get_voice_access_token(
    request: Request,
    identity: str = Query(default=""),
    principal: Principal = Depends(require_org_user),
) -> dict[str, Any]:
    """Generate short-lived Twilio Voice Access Token for browser client registration.

    Phase 3: authenticated org users only — this endpoint previously minted valid
    Twilio credentials for any identity to anonymous callers.
    """
    from app.telephony.twilio_token import TwilioTokenService

    base_url = str(request.base_url).rstrip("/")
    user_identity = identity or settings.twilio_agent_identity or "human_agent"
    return await TwilioTokenService.generate_voice_token(
        identity=user_identity,
        webhook_base_url=base_url,
    )


# --------------------------------------------------------------------------- #
# Peer WebRTC Signaling (App-to-App calls without carrier — Phase 14)
# --------------------------------------------------------------------------- #

import json
import os
from pathlib import Path

_peer_rooms: dict[str, dict[str, Any]] = {}
_peer_sockets: dict[str, dict[str, WebSocket]] = {}
_PEER_ROOMS_FILE = (
    Path("/tmp/peer_rooms.json")
    if (os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("LAMBDA_TASK_ROOT"))
    else Path(__file__).resolve().parent.parent.parent / "storage" / "peer_rooms.json"
)


def _set_peer_socket(room_id: str, role: str, ws: WebSocket | None) -> None:
    if room_id not in _peer_sockets:
        _peer_sockets[room_id] = {}
    if ws is None:
        _peer_sockets[room_id].pop(role, None)
    else:
        _peer_sockets[room_id][role] = ws


def _get_peer_socket(room_id: str, role: str) -> WebSocket | None:
    return _peer_sockets.get(room_id, {}).get(role)


def _sanitize_peer_room(room: dict[str, Any]) -> dict[str, Any]:
    return {
        "room_id": room.get("room_id", ""),
        "caller_language": room.get("caller_language", "hi"),
        "receiver_language": room.get("receiver_language", "en"),
        "caller_name": room.get("caller_name", "Caller"),
        "receiver_name": room.get("receiver_name", ""),
        "status": room.get("status", "waiting"),
        "created_at": room.get("created_at"),
    }


def _persist_peer_rooms():
    try:
        _PEER_ROOMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            rid: {k: v for k, v in r.items() if not k.startswith("ws_")}
            for rid, r in _peer_rooms.items()
        }
        _PEER_ROOMS_FILE.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("Could not persist peer rooms: %s", exc)


def _load_persisted_peer_rooms():
    try:
        if _PEER_ROOMS_FILE.exists():
            data = json.loads(_PEER_ROOMS_FILE.read_text(encoding="utf-8"))
            for rid, r in data.items():
                if rid not in _peer_rooms:
                    _peer_rooms[rid] = r
    except Exception as exc:
        log.warning("Could not load persisted peer rooms: %s", exc)


_load_persisted_peer_rooms()


def _get_or_create_peer_room(
    room_id: str,
    caller_language: str = "hi",
    receiver_language: str = "en",
    caller_name: str = "Caller",
) -> dict[str, Any]:
    """Retrieve or auto-provision peer room so shared links and reloads remain active."""
    if room_id not in _peer_rooms:
        _load_persisted_peer_rooms()
    if room_id not in _peer_rooms:
        import datetime
        _peer_rooms[room_id] = {
            "room_id": room_id,
            "caller_language": caller_language,
            "receiver_language": receiver_language,
            "caller_name": caller_name,
            "receiver_name": "",
            "status": "waiting",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "ws_offer": None,
            "ws_answer": None,
            "ice_candidates": [],
        }
        _persist_peer_rooms()
    return _peer_rooms[room_id]


class PeerCallCreateRequest(BaseModel):
    caller_language: str = "hi"
    receiver_language: str = "en"
    caller_name: str = "Caller"
    room_name: str = ""
    target_phone_number: str = ""
    caller_phone_number: str = ""


class PeerCallJoinRequest(BaseModel):
    receiver_name: str = "Receiver"


@router.post("/peer-calls", status_code=201)
async def create_peer_call(
    body: PeerCallCreateRequest,
    req: Request,
    principal: Principal = Depends(require_org_user),
) -> dict[str, Any]:
    """Create a WhatsApp-style peer call room (no PSTN carrier needed).
    Returns a shareable join_url and direct WhatsApp share link."""
    import secrets
    from urllib.parse import quote_plus
    room_id = secrets.token_urlsafe(10)

    # Dynamically detect caller's web origin (e.g. localhost:5174 or talkflow.antideploy.app)
    origin_hdr = req.headers.get("origin")
    referer_hdr = req.headers.get("referer")
    if origin_hdr:
        web_origin = origin_hdr.rstrip("/")
    elif referer_hdr:
        from urllib.parse import urlparse
        p = urlparse(referer_hdr)
        web_origin = f"{p.scheme}://{p.netloc}"
    else:
        web_origin = getattr(settings, "web_origin", "http://localhost:5173")
    join_url = f"{web_origin}/join/{room_id}"

    # Generate direct WhatsApp Web click-to-chat share URL
    clean_phone = "".join(c for c in body.target_phone_number if c.isdigit())
    share_msg = quote_plus(
        f"📞 Join my WhatsApp Voice Call on TalkFlow with live 2-way AI translation:\n{join_url}\n\n(Tap link to answer in your phone browser — 100% free)"
    )
    if clean_phone:
        whatsapp_share_url = f"https://api.whatsapp.com/send?phone={clean_phone}&text={share_msg}"
    else:
        whatsapp_share_url = f"https://api.whatsapp.com/send?text={share_msg}"

    _peer_rooms[room_id] = {
        "room_id": room_id,
        "caller_language": body.caller_language,
        "receiver_language": body.receiver_language,
        "caller_name": body.caller_name or "Caller",
        "target_phone_number": body.target_phone_number,
        "caller_phone_number": body.caller_phone_number,
        "receiver_name": "",
        "status": "waiting",  # waiting | connected | ended
        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        "ws_offer": None,
        "ws_answer": None,
        "ice_candidates": [],
    }
    _persist_peer_rooms()

    log.info("WhatsApp peer call room %s created for target %s (origin: %s)", room_id, body.target_phone_number, web_origin)
    return {
        "room_id": room_id,
        "join_url": join_url,
        "whatsapp_share_url": whatsapp_share_url,
        "target_phone_number": body.target_phone_number,
        "caller_language": body.caller_language,
        "receiver_language": body.receiver_language,
        "status": "waiting",
        "message": "Share the join_url with the other person or click whatsapp_share_url to send via WhatsApp.",
    }


@router.get("/peer-calls/{room_id}")
async def get_peer_call(room_id: str) -> dict[str, Any]:
    """Poll peer call room status (used by both caller and callee).
    Auto-provisions room if not found so links and sessions are always joinable."""
    room = _get_or_create_peer_room(room_id)
    return _sanitize_peer_room(room)


@router.websocket("/peer-calls/{room_id}/signal")
async def peer_call_signal_ws(ws: WebSocket, room_id: str, role: str = "caller"):
    """WebRTC signaling WebSocket for peer-to-peer browser calls.
    role: 'caller' | 'callee'
    Messages: {type: 'offer'|'answer'|'ice'|'bye'|'peer_joined', data: ...}
    """
    import json
    await ws.accept()
    room = _get_or_create_peer_room(room_id)

    # Register this WebSocket in peer sockets
    _set_peer_socket(room_id, role, ws)
    peer_role = "callee" if role == "caller" else "caller"

    peer_ws = _get_peer_socket(room_id, peer_role)
    if peer_ws:
        try:
            await peer_ws.send_text(json.dumps({"type": "peer_joined", "role": role}))
        except Exception:
            pass

    if role == "callee":
        room["status"] = "connected"

    caller_online = bool(_get_peer_socket(room_id, "caller"))
    callee_online = bool(_get_peer_socket(room_id, "callee"))

    await ws.send_text(json.dumps({"type": "ready", "room_id": room_id, "role": role, "caller_online": caller_online, "callee_online": callee_online, "room": {
        "caller_language": room["caller_language"],
        "receiver_language": room["receiver_language"],
        "caller_name": room["caller_name"],
    }}))

    # If caller already submitted an offer and callee just joined, send it immediately
    if role == "callee" and room.get("ws_offer"):
        await ws.send_text(json.dumps({"type": "offer", "data": room["ws_offer"]}))

    # Flush buffered ICE candidates intended for this role
    remaining_ice = []
    for cand in room.get("ice_candidates", []):
        if cand.get("for_role") == role:
            await ws.send_text(json.dumps({"type": "ice", "data": cand["data"]}))
        else:
            remaining_ice.append(cand)
    room["ice_candidates"] = remaining_ice

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "offer":
                room["ws_offer"] = msg.get("data")
                peer_ws = _get_peer_socket(room_id, peer_role)
                if peer_ws:
                    await peer_ws.send_text(json.dumps({"type": "offer", "data": msg.get("data")}))

            elif msg_type == "answer":
                room["ws_answer"] = msg.get("data")
                peer_ws = _get_peer_socket(room_id, peer_role)
                if peer_ws:
                    await peer_ws.send_text(json.dumps({"type": "answer", "data": msg.get("data")}))

            elif msg_type == "ice":
                peer_ws = _get_peer_socket(room_id, peer_role)
                if peer_ws:
                    try:
                        await peer_ws.send_text(json.dumps({"type": "ice", "data": msg.get("data")}))
                    except Exception:
                        # Buffer for when peer reconnects
                        room["ice_candidates"].append({"for_role": peer_role, "data": msg.get("data")})
                else:
                    room["ice_candidates"].append({"for_role": peer_role, "data": msg.get("data")})

            elif msg_type == "instant_connect":
                peer_ws = _get_peer_socket(room_id, peer_role)
                if peer_ws:
                    try:
                        await peer_ws.send_text(json.dumps({"type": "instant_connect"}))
                    except Exception:
                        pass
                room["status"] = "connected"

            elif msg_type == "bye":
                peer_ws = _get_peer_socket(room_id, peer_role)
                if peer_ws:
                    try:
                        await peer_ws.send_text(json.dumps({"type": "bye"}))
                    except Exception:
                        pass
                room["status"] = "ended"
                break

    except WebSocketDisconnect:
        log.info("Peer signal WS disconnected: room=%s role=%s", room_id, role)
        peer_ws = _get_peer_socket(room_id, peer_role)
        if peer_ws:
            try:
                await peer_ws.send_text(json.dumps({"type": "peer_left"}))
            except Exception:
                pass
    finally:
        _set_peer_socket(room_id, role, None)


def _org_id(p: Principal) -> uuid.UUID:
    """Narrow principal.org_id to UUID (guaranteed non-None by require_org_user)."""
    assert p.org_id is not None, "org_id is None — require_org_user must have failed"
    return p.org_id


@router.get("/calls", response_model=list[CallSessionOut])
async def list_calls(
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
    status: str = Query(default=""),
):
    """List recent call history."""
    cs = CallService(db)
    calls = await cs.list_calls(_org_id(principal), limit=limit, status=status)
    return [_serialize_call(c) for c in calls]


@router.get("/calls/{call_id}", response_model=CallSessionOut)
async def get_call(
    call_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Get call details and current live state."""
    cs = CallService(db)
    call = await cs.get_call_by_id(call_id, _org_id(principal))
    return _serialize_call(call)


@router.get("/calls/{ref}/transcript", summary="Per-turn transcript + sha256 citations")
async def get_call_transcript(
    ref: str,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Per-turn transcript + sha256 citations, assembled from the call's ledger.

    ``ref`` resolves deterministically: a bare UUID matches the session id,
    anything else matches ``call_sid`` — both org-scoped, both fail closed
    with 404 (foreign-org/unknown lookups are indistinguishable).

    Caller speech is exposed as fingerprints only (sha256), the agent's own
    lines verbatim, ``ai_agent.node`` transitions as citations, plus the
    escalation trail and media timeline. See ``app.telephony.call_transcript``.
    """
    ref_stripped = (ref or "").strip()
    if not ref_stripped:
        raise ValidationError("Call reference is required.")
    criteria: list[Any] = [M.CallSession.org_id == _org_id(principal)]
    try:
        criteria.append(M.CallSession.id == uuid.UUID(ref_stripped))
    except ValueError:
        criteria.append(M.CallSession.call_sid == ref_stripped)
    res = await db.execute(select(M.CallSession).where(*criteria))
    call = res.scalars().first()
    if call is None:
        raise NotFoundError("Call session not found.")
    res = await db.execute(
        select(M.CallEvent).where(M.CallEvent.call_id == call.id))
    return assemble_transcript(call, list(res.scalars().all()))


# --------------------------------------------------------------------------- #
# Live-agent escalation board (§D1)
# --------------------------------------------------------------------------- #


class ClaimEscalationRequest(BaseModel):
    worker: str | None = Field(default=None, max_length=80,
                               description="Display name of the claiming agent")


class ResolveEscalationRequest(BaseModel):
    resolution: str = Field(default="handled_by_human", max_length=120)


class EscalationTicketOut(BaseModel):
    ticket_id: str
    call_sid: str
    reason: str | None = None
    summary: str | None = None
    turns: int
    age_seconds: int
    state: str              # pending | claimed | resolved
    claimed_by: str | None = None
    resolution: str | None = None


def _ticket_out(ticket, q, state: str) -> EscalationTicketOut:
    return EscalationTicketOut(
        ticket_id=ticket.ticket_id,
        call_sid=ticket.call_sid,
        reason=ticket.reason,
        summary=ticket.summary,
        turns=ticket.turns,
        age_seconds=max(0, int(time.monotonic() - ticket.created_at)),
        state=state,
        claimed_by=q.claimed_by(ticket.ticket_id) if state != "pending" else None,
        resolution=(q.resolution_of(ticket.ticket_id) if state == "resolved" else None),
    )


@router.get("/escalations", response_model=list[EscalationTicketOut])
async def list_escalations(
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Live-agent board: every escalation ticket whose call belongs to this org.

    Pending first, then claimed, then resolved; each group oldest first. The
    queue itself stays org-agnostic — scoping is derived from the
    ``call_sid → CallSession.org_id`` relationship, so a ticket from another
    org's call is simply invisible (never listed).
    """
    q = shared_dispatcher().queue
    res = await db.execute(
        select(M.CallSession.call_sid).where(M.CallSession.org_id == _org_id(principal)))
    org_sids = set(res.scalars().all())

    claimed_ids = set(q.claimed_ticket_ids())
    resolved_ids = set(q.resolved_ticket_ids())
    ranked: list[EscalationTicketOut] = []
    for t in q.pending_tickets():
        if t.call_sid in org_sids and t.ticket_id not in claimed_ids and t.ticket_id not in resolved_ids:
            ranked.append(_ticket_out(t, q, "pending"))
    for tid in q.claimed_ticket_ids():
        t = q.ticket_by_id(tid)
        if t is not None and t.call_sid in org_sids and tid not in resolved_ids:
            ranked.append(_ticket_out(t, q, "claimed"))
    for tid in q.resolved_ticket_ids():
        t = q.ticket_by_id(tid)
        if t is not None and t.call_sid in org_sids:
            ranked.append(_ticket_out(t, q, "resolved"))

    ranked.sort(key=lambda r: ({"pending": 0, "claimed": 1, "resolved": 2}[r.state], -r.age_seconds))
    return ranked


async def _org_visible_ticket(db: AsyncSession, ticket_id: str, org_id: uuid.UUID):
    """Resolve a ticket AND prove its call belongs to this org (else None)."""
    ticket = shared_dispatcher().queue.ticket_by_id(ticket_id)
    if ticket is None:
        return None
    res = await db.execute(
        select(M.CallSession.id).where(
            M.CallSession.call_sid == ticket.call_sid,
            M.CallSession.org_id == org_id))
    if res.scalars().first() is None:
        return None
    return ticket


@router.post("/escalations/{ticket_id}/claim", response_model=EscalationTicketOut)
async def claim_escalation(
    ticket_id: str,
    body: ClaimEscalationRequest | None = None,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Claim a pending escalation for a live agent (single claim, no stealing)."""
    q = shared_dispatcher().queue
    ticket = await _org_visible_ticket(db, ticket_id, _org_id(principal))
    if ticket is None:
        raise NotFoundError("Escalation ticket not found.")
    if ticket_id in q.resolved_ticket_ids():
        raise AppError("Escalation ticket is already resolved.", status=409)
    worker = ((body.worker if body else None) or principal.identity_for_rate_limit or "operator").strip() or "operator"
    claimed = q.claim(worker, ticket_id=ticket_id)
    if claimed is None:
        raise AppError("Escalation ticket was just claimed by someone else.",
                       status=409, recoverable=False)
    await shared_dispatcher().record_claim(
        claimed, worker, MediaCallEventSink(claimed.call_sid))
    return _ticket_out(claimed, q, "claimed")


@router.post("/escalations/{ticket_id}/resolve", response_model=EscalationTicketOut)
async def resolve_escalation(
    ticket_id: str,
    body: ResolveEscalationRequest | None = None,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a CLAIMED escalation (unclaimed work cannot be marked done)."""
    q = shared_dispatcher().queue
    ticket = await _org_visible_ticket(db, ticket_id, _org_id(principal))
    if ticket is None:
        raise NotFoundError("Escalation ticket not found.")
    resolution = (body.resolution if body else "handled_by_human").strip() or "handled_by_human"
    if (ticket_id in q.resolved_ticket_ids()
            or ticket_id not in set(q.claimed_ticket_ids())):
        raise AppError("Escalation ticket must be claimed before it can be resolved.",
                       status=409, recoverable=False)
    # record_resolution performs the completion AND the ledger row (one source
    # of truth; a False return here only means a racing resolve got there first)
    await shared_dispatcher().record_resolution(
        ticket, resolution, MediaCallEventSink(ticket.call_sid))
    return _ticket_out(ticket, q, "resolved")


@router.post("/calls/{call_id}/end", response_model=CallSessionOut)
async def end_call(
    call_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Hang up / terminate an active call."""
    cs = CallService(db)
    call = await cs.end_call(call_id, _org_id(principal))
    return _serialize_call(call)


# --------------------------------------------------------------------------- #
# Caller ID Phone Numbers
# --------------------------------------------------------------------------- #


@router.get("/phone-numbers", response_model=list[PhoneNumberOut])
async def list_phone_numbers(
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List registered caller ID phone numbers for the organization."""
    res = await db.execute(
        select(M.PhoneNumber)
        .where(M.PhoneNumber.org_id == principal.org_id)
        .order_by(M.PhoneNumber.created_at.desc())
    )
    return [
        PhoneNumberOut(
            id=str(p.id),
            e164_number=p.e164_number,
            country_code=p.country_code,
            friendly_name=p.friendly_name,
            status=p.status,
            provider=p.provider,
        )
        for p in res.scalars().all()
    ]


@router.post("/phone-numbers", response_model=PhoneNumberOut, status_code=201)
async def register_phone_number(
    body: PhoneNumberCreate,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a verified caller ID phone number in E.164 format."""
    norm = PhoneNumberService.normalize_to_e164(body.e164_number, body.country_code)
    is_valid, err = PhoneNumberService.validate_e164(norm)
    if not is_valid:
        raise ValidationError(err or "Invalid E.164 phone number.")

    country = PhoneNumberService.detect_country(norm)
    phone = M.PhoneNumber(
        org_id=principal.org_id,
        e164_number=norm,
        country_code=country.country_code if country else body.country_code,
        friendly_name=body.friendly_name or PhoneNumberService.format_friendly(norm),
        provider="custom",
        provider_sid="",
        status="active",
    )
    db.add(phone)
    await db.commit()
    return PhoneNumberOut(
        id=str(phone.id),
        e164_number=phone.e164_number,
        country_code=phone.country_code,
        friendly_name=phone.friendly_name,
        status=phone.status,
        provider=phone.provider,
    )


# --------------------------------------------------------------------------- #
# Mobile Call Forwarding & Device Routing
# --------------------------------------------------------------------------- #


@router.get("/forwarding-settings")
async def get_forwarding_settings() -> dict[str, Any]:
    """Retrieve mobile phone call forwarding and simultaneous ring preferences."""
    from app.telephony.forwarding_service import ForwardingService
    return ForwardingService.get_settings()


@router.post("/forwarding-settings")
async def update_forwarding_settings(
    body: ForwardingSettingsRequest,
) -> dict[str, Any]:
    """Update mobile phone call forwarding and simultaneous ring preferences."""
    from app.telephony.forwarding_service import ForwardingService
    updates = body.model_dump(exclude_unset=True)
    return ForwardingService.save_settings(updates)


@router.post("/verify-phone-number")
async def verify_phone_number(
    body: VerifyPhoneRequest,
) -> dict[str, Any]:
    """Initiate Twilio phone number verification call. Twilio calls the number and provides a 6-digit code."""
    from app.telephony.forwarding_service import ForwardingService
    from app.telephony.phone_number_service import PhoneNumberService
    norm = PhoneNumberService.normalize_to_e164(body.phone_number)
    return await ForwardingService.request_caller_id_verification(norm, body.friendly_name)


@router.post("/test-call")
async def place_test_call(
    body: TestCallRequest,
) -> dict[str, Any]:
    """Place an automated test call to the specified mobile phone number to verify incoming call connectivity."""
    from app.telephony.forwarding_service import ForwardingService
    from app.telephony.phone_number_service import PhoneNumberService
    norm = PhoneNumberService.normalize_to_e164(body.phone_number)
    return await ForwardingService.place_test_ring(norm)


@router.post("/calls/bridge")
async def place_bridge_call(
    body: BridgeCallRequest,
) -> dict[str, Any]:
    """Place a mobile bridge call: rings the agent's mobile phone first, then connects to customer."""
    from app.telephony.forwarding_service import ForwardingService
    from app.telephony.phone_number_service import PhoneNumberService

    fwd = ForwardingService.get_settings()
    user_mobile = body.mobile_number or fwd.get("mobile_number") or ""
    if not user_mobile:
        raise ValidationError("Agent mobile phone number is required to place a bridge call.")

    norm_user = PhoneNumberService.normalize_to_e164(user_mobile)
    norm_customer = PhoneNumberService.normalize_to_e164(body.customer_number)

    return await ForwardingService.place_mobile_bridge_call(
        user_mobile_number=norm_user,
        customer_phone_number=norm_customer,
        caller_id=body.caller_id,
    )


@router.api_route("/twiml/test-ring", methods=["GET", "POST"], include_in_schema=False)
async def twiml_test_ring() -> Response:
    """TwiML instruction for phone verification test ring."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Response>'
        '<Say voice="Polly.Aditi">Hello! This is GlobalTalk AI verifying your phone connectivity. '
        'Your mobile device is connected and ready to receive and place translated calls. Thank you!'
        '</Say>'
        '<Pause length="1"/>'
        '<Hangup/>'
        '</Response>'
    )
    return Response(content=xml, media_type="application/xml")


@router.api_route("/twiml/bridge", methods=["GET", "POST"], include_in_schema=False)
async def twiml_bridge(customer: str = "", caller_id: str = "") -> Response:
    """TwiML instruction for mobile handset click-to-call bridge."""
    cid = caller_id or settings.twilio_phone_number or ""
    dial_attrs = ' answerOnBridge="true" timeout="35"'
    if cid:
        dial_attrs += f' callerId="{cid}"'
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Response>'
        f'<Say voice="Polly.Aditi">Connecting your mobile call to customer at {customer}. Please hold.</Say>'
        f'<Dial{dial_attrs}>'
        f'<Number>{customer}</Number>'
        '</Dial>'
        '</Response>'
    )
    return Response(content=xml, media_type="application/xml")


@router.api_route("/twiml/outbound-voice", methods=["GET", "POST"], include_in_schema=False)
async def twiml_outbound_voice(to: str = "", caller_id: str = "") -> Response:
    """TwiML instruction for outbound PSTN calls."""
    cid = caller_id or settings.twilio_phone_number or ""
    dial_attrs = ' answerOnBridge="true"'
    if cid:
        dial_attrs += f' callerId="{cid}"'
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Response>'
        '<Say voice="Polly.Aditi">Welcome to GlobalTalk AI. Your real-time translated voice session is now connected.</Say>'
        f'<Dial{dial_attrs}>'
        f'<Number>{to}</Number>'
        '</Dial>'
        '</Response>'
    )
    return Response(content=xml, media_type="application/xml")


# --------------------------------------------------------------------------- #
# Carrier Webhook Callbacks (Twilio / Telnyx)
# --------------------------------------------------------------------------- #


@router.api_route("/webhooks/voice", methods=["GET", "POST"], include_in_schema=False)
async def telephony_voice_webhook(
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Carrier voice webhook: returns TwiML with bidirectional media stream instructions."""
    # 1. Rate limiting check (Phase 12 & 13)
    ip_hash = client_ip_hash(req)
    await check_rate_limit(
        bucket="telephony:webhook",
        identity=ip_hash,
        spec=settings.rate_limit_telephony_webhook,
    )

    raw_body = await req.body()
    form_data = await req.form()
    payload = dict(form_data)
    headers = dict(req.headers)
    ws = TelephonyWebhookService(db)
    twiml_xml = await ws.handle_voice_webhook(headers, payload, str(req.url), raw_body)
    return Response(content=twiml_xml, media_type="application/xml")


@router.api_route("/webhooks/status", methods=["GET", "POST"], include_in_schema=False)
async def telephony_status_webhook(
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    """Carrier status callback webhook (initiated, ringing, in-progress, completed, failed)."""
    # 1. Rate limiting check (Phase 12 & 13)
    ip_hash = client_ip_hash(req)
    await check_rate_limit(
        bucket="telephony:webhook",
        identity=ip_hash,
        spec=settings.rate_limit_telephony_webhook,
    )

    raw_body = await req.body()
    form_data = await req.form()
    payload = dict(form_data)
    headers = dict(req.headers)
    ws = TelephonyWebhookService(db)
    await ws.handle_status_webhook(headers, payload, str(req.url), raw_body)
    return Response(content="<Response/>", media_type="application/xml")


# --------------------------------------------------------------------------- #
# Realtime Media Stream WebSockets (Carrier & Client)
# --------------------------------------------------------------------------- #


@router.websocket("/media/{call_id}")
async def telephony_carrier_media_ws(ws: WebSocket, call_id: uuid.UUID):
    """Bidirectional WebSocket for telephony carriers (Twilio / Telnyx Media Streams)."""
    await ws.accept()
    session = MediaStreamService.get_or_create(call_id)
    try:
        await session.run_carrier(ws)
    finally:
        MediaStreamService.unregister(call_id)


@router.websocket("/calls/{call_id}/client")
async def telephony_client_ws(ws: WebSocket, call_id: uuid.UUID):
    """Bidirectional WebSocket for Web App Clients to join the active phone call."""
    import base64
    import json
    await ws.accept()
    session = MediaStreamService.get_or_create(call_id)
    await session.register_client_ws(ws)
    try:
        while session.is_active:
            message = await ws.receive()
            if "bytes" in message and message["bytes"]:
                # Binary 16kHz PCM16 audio chunk from browser mic
                await session.handle_client_audio(message["bytes"])
            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                msg_type = data.get("type")
                if msg_type == "audio_chunk":
                    raw_b64 = data.get("data", {}).get("audio_base64", "")
                    if raw_b64:
                        pcm = base64.b64decode(raw_b64)
                        await session.handle_client_audio(pcm)
                elif msg_type == "barge_in":
                    if session.bridge:
                        await session.bridge.on_barge_in("receiver") if session.bridge.on_barge_in else None
    except WebSocketDisconnect:
        log.info("Client WebSocket disconnected for call %s", call_id)
    except Exception as e:
        log.warning("Client WebSocket exception for call %s: %s", call_id, e)
    finally:
        session.unregister_client_ws(ws)


# --------------------------------------------------------------------------- #
# AI Agent Prompt Composer Endpoints
# --------------------------------------------------------------------------- #


class PromptMergeRequest(BaseModel):
    platform_instructions: str = ""
    custom_agent_prompt: str = ""
    project_context: str = ""


class PromptMergeResponse(BaseModel):
    merged_prompt: str
    validation_status: str
    validation_errors: list[str]
    conflicts: list[dict]
    sections: dict[str, str]


class PromptTestRequest(BaseModel):
    merged_prompt: str
    user_message: str
    user_language: str = "en"


class PromptSaveRequest(BaseModel):
    agent_id: str | None = None
    name: str = "Customer Support Voice Agent"
    agent_role: str = "customer_support"
    platform_instructions: str = ""
    custom_agent_prompt: str = ""
    project_context: str = ""
    merged_prompt: str = ""


@router.post("/agents/prompts/merge", response_model=PromptMergeResponse)
async def merge_prompts(
    body: PromptMergeRequest,
    principal: Principal = Depends(require_org_user),
):
    """Smart merge Platform Master Instructions + Custom Prompt + Project Context."""
    from app.agents.prompt_composer import PromptComposerEngine

    result = PromptComposerEngine.smart_merge(
        platform_instructions=body.platform_instructions,
        custom_agent_prompt=body.custom_agent_prompt,
        project_context=body.project_context,
    )
    return PromptMergeResponse(
        merged_prompt=result.merged_prompt,
        validation_status=result.validation_status,
        validation_errors=result.validation_errors,
        conflicts=[
            {
                "category": c.category,
                "severity": c.severity,
                "platform_rule": c.platform_rule,
                "custom_instruction": c.custom_instruction,
                "resolution": c.resolution,
                "explanation": c.explanation,
            }
            for c in result.conflicts
        ],
        sections=result.sections,
    )


@router.post("/agents/prompts/test")
async def test_agent_prompt(
    body: PromptTestRequest,
    principal: Principal = Depends(require_org_user),
):
    """Test the composed agent prompt with interactive simulation turns."""
    from app.agents.prompt_composer import PromptComposerEngine

    response = PromptComposerEngine.test_agent_turn(
        merged_prompt=body.merged_prompt,
        user_message=body.user_message,
        user_language=body.user_language,
    )
    return {"agent_response": response, "language": body.user_language}


@router.post("/agents/prompts/save")
async def save_agent_prompt(
    body: PromptSaveRequest,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Save composed prompt with automatic versioning (v1, v2, v3)."""
    from app.agents.prompt_composer import PromptComposerEngine

    # 1. Resolve or create parent AgentPrompt
    agent_prompt = None
    if body.agent_id:
        res = await db.execute(
            select(M.AgentPrompt).where(
                M.AgentPrompt.id == uuid.UUID(body.agent_id),
                M.AgentPrompt.org_id == principal.org_id,
            )
        )
        agent_prompt = res.scalars().first()
        if not agent_prompt:
            raise NotFoundError("Agent prompt not found.")

    if not agent_prompt:
        agent_prompt = M.AgentPrompt(
            org_id=principal.org_id,
            name=body.name,
            agent_role=body.agent_role,
            description="Created via AI Agent Prompt Composer",
            created_by=principal.user_id,
        )
        db.add(agent_prompt)
        await db.flush()

    # 2. Get next version number
    v_res = await db.execute(
        select(M.PromptVersion)
        .where(M.PromptVersion.agent_prompt_id == agent_prompt.id)
        .order_by(M.PromptVersion.version.desc())
    )
    latest_v = v_res.scalars().first()
    next_v = (latest_v.version + 1) if latest_v else 1

    # 3. Merge and validate
    merged = PromptComposerEngine.smart_merge(
        platform_instructions=body.platform_instructions,
        custom_agent_prompt=body.custom_agent_prompt,
        project_context=body.project_context,
    )

    prompt_ver = M.PromptVersion(
        agent_prompt_id=agent_prompt.id,
        version=next_v,
        status="testing",
        original_platform_prompt=body.platform_instructions,
        original_custom_prompt=body.custom_agent_prompt,
        project_context=body.project_context,
        merged_prompt=body.merged_prompt or merged.merged_prompt,
        conflicts_json=[
            {
                "category": c.category,
                "severity": c.severity,
                "platform_rule": c.platform_rule,
                "custom_instruction": c.custom_instruction,
                "resolution": c.resolution,
                "explanation": c.explanation,
            }
            for c in merged.conflicts
        ],
        validation_status=merged.validation_status,
        validation_errors_json=merged.validation_errors,
        created_by=principal.user_id,
    )
    db.add(prompt_ver)
    await db.commit()

    return {
        "agent_id": str(agent_prompt.id),
        "prompt_version_id": str(prompt_ver.id),
        "version": next_v,
        "validation_status": prompt_ver.validation_status,
        "conflicts_count": len(prompt_ver.conflicts_json),
    }


@router.get("/agents/prompts")
async def list_agent_prompts(
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """List agent prompts and their saved versions."""
    res = await db.execute(
        select(M.AgentPrompt)
        .where(M.AgentPrompt.org_id == principal.org_id)
        .order_by(M.AgentPrompt.created_at.desc())
    )
    prompts = res.scalars().all()
    out = []
    for p in prompts:
        v_res = await db.execute(
            select(M.PromptVersion)
            .where(M.PromptVersion.agent_prompt_id == p.id)
            .order_by(M.PromptVersion.version.desc())
        )
        versions = v_res.scalars().all()
        out.append({
            "id": str(p.id),
            "name": p.name,
            "agent_role": p.agent_role,
            "status": p.status,
            "active_version_id": str(p.active_version_id) if p.active_version_id else None,
            "versions": [
                {
                    "id": str(v.id),
                    "version": v.version,
                    "status": v.status,
                    "validation_status": v.validation_status,
                    "created_at": v.created_at.isoformat(),
                }
                for v in versions
            ],
        })
    return out


@router.post("/agents/prompts/{version_id}/activate")
async def activate_prompt_version(
    version_id: uuid.UUID,
    principal: Principal = Depends(require_org_user),
    db: AsyncSession = Depends(get_db),
):
    """Activate a validated prompt version for live phone calls."""
    res = await db.execute(
        select(M.PromptVersion).where(M.PromptVersion.id == version_id)
    )
    ver = res.scalars().first()
    if not ver:
        raise NotFoundError("Prompt version not found.")

    agent = await db.get(M.AgentPrompt, ver.agent_prompt_id)
    if not agent or agent.org_id != principal.org_id:
        raise NotFoundError("Prompt version not found.")

    ver.status = "active"
    agent.active_version_id = ver.id
    agent.status = "active"
    await db.commit()
    return {"status": "active", "agent_id": str(agent.id), "version": ver.version}
