"""Telephony API Router: Calling Endpoints, Webhooks & Media Stream WebSockets."""
from __future__ import annotations

import logging
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
from app.errors import NotFoundError, ValidationError
from app.ratelimit import check_rate_limit
from app.telephony.call_service import CallService
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
):
    """Place an international phone call with real-time bidirectional translation."""
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
            base_url=base_url,
        )
    except ValidationError:
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
    has_twilio = bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_phone_number)
    has_telnyx = bool(getattr(settings, "telnyx_api_key", None))

    if has_twilio:
        active_provider = "twilio"
        real_pstn_available = True
        caller_number = settings.twilio_phone_number
    elif has_telnyx:
        active_provider = "telnyx"
        real_pstn_available = True
        caller_number = getattr(settings, "telnyx_phone_number", "")
    else:
        active_provider = "simulated"
        real_pstn_available = False
        caller_number = "+12025550199"

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
) -> dict[str, Any]:
    """Generate short-lived Twilio Voice Access Token for browser client registration."""
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


class PeerCallJoinRequest(BaseModel):
    receiver_name: str = "Receiver"


@router.post("/peer-calls", status_code=201)
async def create_peer_call(
    body: PeerCallCreateRequest,
    req: Request,
    principal: Principal = Depends(require_org_user),
) -> dict[str, Any]:
    """Create an App-to-App peer call room (no PSTN carrier needed).
    Returns a shareable join_url the other person opens in their browser."""
    import secrets
    room_id = secrets.token_urlsafe(10)

    # Dynamically detect caller's web origin (e.g. localhost:5174 or localhost:5173)
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

    _peer_rooms[room_id] = {
        "room_id": room_id,
        "caller_language": body.caller_language,
        "receiver_language": body.receiver_language,
        "caller_name": body.caller_name or "Caller",
        "receiver_name": "",
        "status": "waiting",  # waiting | connected | ended
        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        "ws_offer": None,
        "ws_answer": None,
        "ice_candidates": [],
    }
    _persist_peer_rooms()

    log.info("Peer call room %s created by org %s (origin: %s)", room_id, principal.org_id, web_origin)
    return {
        "room_id": room_id,
        "join_url": join_url,
        "caller_language": body.caller_language,
        "receiver_language": body.receiver_language,
        "status": "waiting",
        "message": "Share the join_url with the other person. They open it in their browser.",
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
# Carrier Webhook Callbacks (Twilio / Telnyx)
# --------------------------------------------------------------------------- #


@router.post("/webhooks/voice", include_in_schema=False)
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


@router.post("/webhooks/status", include_in_schema=False)
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
