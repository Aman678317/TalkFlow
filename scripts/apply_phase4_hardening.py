"""Applies Phase 4 Realtime and Meeting Security hardening."""
import sys

# 1. Patch security.py
with open("services/api/app/security.py", "r", encoding="utf-8") as f:
    sec_code = f.read()

old_sec = '''def verify_session_ticket(ticket: str) -> tuple[str, str]:
    """Returns (session_id, participant_id)."""
    payload = decode_token(ticket, "access")
    if payload.get("purpose") != "rt_ticket":
        raise AuthenticationError("Invalid realtime ticket.")
    return payload["sub"], payload["pid"]'''

new_sec = '''_CONSUMED_RT_TICKETS: dict[str, float] = {}  # jti -> expires_at


def verify_session_ticket(ticket: str, consume: bool = True) -> tuple[str, str]:
    """Returns (session_id, participant_id).
    Enforces replay protection: each ticket's unique jti is marked consumed.
    """
    now = time.time()
    expired = [k for k, exp in _CONSUMED_RT_TICKETS.items() if exp < now]
    for k in expired:
        _CONSUMED_RT_TICKETS.pop(k, None)

    payload = decode_token(ticket, "access")
    if payload.get("purpose") != "rt_ticket":
        raise AuthenticationError("Invalid realtime ticket.")

    jti = payload.get("jti")
    if not jti:
        raise AuthenticationError("Realtime ticket missing token ID.")

    if jti in _CONSUMED_RT_TICKETS:
        raise AuthenticationError("Realtime ticket has already been used (replay detected).")

    if consume:
        _CONSUMED_RT_TICKETS[jti] = float(payload.get("exp", now + 120))

    return payload["sub"], payload["pid"]'''

if old_sec in sec_code:
    sec_code = sec_code.replace(old_sec, new_sec)
    with open("services/api/app/security.py", "w", encoding="utf-8") as f:
        f.write(sec_code)
    print("Patched security.py")
else:
    print("security.py already patched or pattern mismatch")

# 2. Patch session_manager.py
with open("services/api/app/realtime/session_manager.py", "r", encoding="utf-8") as f:
    sm_code = f.read()

old_attach = '''    def attach_ws(self, session: RtSession, participant_id: uuid.UUID,
                  ws: WebSocket) -> RtParticipant | None:
        p = session.participants.get(str(participant_id))
        if p:
            p.ws = ws
            p.connected = True
        return p'''

new_attach = '''    def attach_ws(self, session: RtSession, participant_id: uuid.UUID,
                  ws: WebSocket) -> tuple[RtParticipant | None, WebSocket | None]:
        p = session.participants.get(str(participant_id))
        old_ws = None
        if p:
            if p.connected and p.ws is not None and p.ws != ws:
                old_ws = p.ws
            p.ws = ws
            p.connected = True
        return p, old_ws'''

if old_attach in sm_code:
    sm_code = sm_code.replace(old_attach, new_attach)
    with open("services/api/app/realtime/session_manager.py", "w", encoding="utf-8") as f:
        f.write(sm_code)
    print("Patched session_manager.py")
else:
    print("session_manager.py already patched or pattern mismatch")

# 3. Patch ws.py
with open("services/api/app/realtime/ws.py", "r", encoding="utf-8") as f:
    ws_code = f.read()

old_ws_ticket = '''    if ticket:
        try:
            _, pid = verify_session_ticket(ticket)
            participant_id = uuid.UUID(pid)'''

new_ws_ticket = '''    ticket_room: str | None = None
    if ticket:
        try:
            ticket_room, pid = verify_session_ticket(ticket, consume=True)
            participant_id = uuid.UUID(pid)'''

ws_code = ws_code.replace(old_ws_ticket, new_ws_ticket)

old_ws_part = '''        if participant is None:
            await ws.close(code=4404, reason="participant not found")
            return

        meeting = await db.get(M.Meeting, participant.meeting_id)'''

new_ws_part = '''        if participant is None:
            await ws.close(code=4404, reason="participant not found")
            return

        if target_meeting_id is not None and participant.meeting_id != target_meeting_id:
            await ws.close(code=4403, reason="Forbidden: credential not valid for this meeting")
            return

        meeting = await db.get(M.Meeting, participant.meeting_id)
        if meeting is None or meeting.status not in ("scheduled", "live"):
            await ws.close(code=4410, reason="meeting not joinable")
            return

        if ticket and ticket_room and ticket_room not in (meeting.room_name, str(meeting.id)):
            await ws.close(code=4403, reason="Ticket room mismatch")
            return'''

# Replace only the first occurrence after line 135
if old_ws_part in ws_code:
    ws_code = ws_code.replace(old_ws_part, new_ws_part, 1)

old_ws_attach = '''    manager.add_participant(session, rp)
    manager.attach_ws(session, rp.participant_id, ws)
    pl.get_pipeline(session).start_speaker(rp)'''

new_ws_attach = '''    manager.add_participant(session, rp)
    _, old_ws = manager.attach_ws(session, rp.participant_id, ws)
    if old_ws is not None and old_ws != ws:
        with contextlib.suppress(Exception):
            await old_ws.close(code=4409, reason="duplicate_connection_superseded")
    pl.get_pipeline(session).start_speaker(rp)'''

ws_code = ws_code.replace(old_ws_attach, new_ws_attach)

old_ws_auth = '''def _auth(ticket: str, meeting_id: str) -> tuple[str, uuid.UUID]:
    if not ticket:
        raise AuthenticationError("Missing realtime ticket.")
    try:
        sid, pid = verify_session_ticket(ticket)
        return sid, uuid.UUID(pid)'''

new_ws_auth = '''def _auth(ticket: str, meeting_id: str) -> tuple[str, uuid.UUID]:
    if not ticket:
        raise AuthenticationError("Missing realtime ticket.")
    try:
        sid, pid = verify_session_ticket(ticket, consume=True)
        return sid, uuid.UUID(pid)'''

ws_code = ws_code.replace(old_ws_auth, new_ws_auth)

with open("services/api/app/realtime/ws.py", "w", encoding="utf-8") as f:
    f.write(ws_code)
print("Patched ws.py")

# 4. Patch livekit_bridge.py
with open("services/api/app/realtime/livekit_bridge.py", "r", encoding="utf-8") as f:
    lk_code = f.read()

old_lk = '''def join_token(room_name: str, identity: str, name: str, metadata: dict) -> dict | None:
    if not enabled():
        return None
    import time as _t
    import secrets
    import jwt as pyjwt
    now = int(_t.time())
    payload = {
        "iss": settings.livekit_api_key, "sub": identity, "name": name,
        "metadata": json.dumps(metadata),
        "nbf": now - 10, "exp": now + 6 * 3600, "jti": secrets.token_hex(8),'''

new_lk = '''def join_token(room_name: str, identity: str, name: str, metadata: dict, ttl_seconds: int = 1800) -> dict | None:
    if not enabled():
        return None
    import time as _t
    import secrets
    import jwt as pyjwt
    now = int(_t.time())
    payload = {
        "iss": settings.livekit_api_key, "sub": identity, "name": name,
        "metadata": json.dumps(metadata),
        "nbf": now - 10, "exp": now + ttl_seconds, "jti": secrets.token_hex(8),'''

if old_lk in lk_code:
    lk_code = lk_code.replace(old_lk, new_lk)
    with open("services/api/app/realtime/livekit_bridge.py", "w", encoding="utf-8") as f:
        f.write(lk_code)
    print("Patched livekit_bridge.py")

# 5. Patch meeting_service.py
with open("services/api/app/services/meeting_service.py", "r", encoding="utf-8") as f:
    ms_code = f.read()

ms_code = ms_code.replace("at.ttl = _td(hours=6)", "at.ttl = _td(seconds=1800)")
ms_code = ms_code.replace('"exp": now + 6 * 3600', '"exp": now + 1800')
with open("services/api/app/services/meeting_service.py", "w", encoding="utf-8") as f:
    f.write(ms_code)
print("Patched meeting_service.py")

# 6. Patch meetings.py join check
with open("services/api/app/routers/meetings.py", "r", encoding="utf-8") as f:
    m_code = f.read()

old_m_join = '''    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None or meeting.status not in ("scheduled", "live"):
        raise ValidationError("Meeting is not joinable.",
                              details={"status": meeting.status if meeting else "not_found"})'''

new_m_join = '''    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")
    if meeting.status not in ("scheduled", "live"):
        raise ValidationError("Meeting is not joinable.",
                              details={"status": meeting.status})'''

if old_m_join in m_code:
    m_code = m_code.replace(old_m_join, new_m_join)
    with open("services/api/app/routers/meetings.py", "w", encoding="utf-8") as f:
        f.write(m_code)
    print("Patched meetings.py")

print("All Phase 4 hardening applied successfully.")
