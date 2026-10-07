"""LiveKit bridge (PDD §12, §13).

Responsibilities:
- room creation & join tokens (secrets stay server-side)
- participant metadata (language preferences) sync
- publishing AI-generated translated audio as synthetic tracks into the room
  (per target language: one track per (room, target_lang), listeners subscribe
  to the track matching their hear_lang — dedup fan-out at the media layer)

When LIVEKIT_ENABLED=false the bridge is a documented no-op: meetings run in
WS transport mode (audio chunks over WebSocket), which is fully functional
for the conversation pipeline; LiveKit adds multi-party SFU video/audio.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid

import httpx

from app.config import settings
from app.realtime.session_manager import RtSession, manager

log = logging.getLogger("app.realtime.livekit")

# track name convention: synthetic translated audio tracks
def translated_track_name(target_lang: str) -> str:
    return f"gt-translated-{target_lang}"


def enabled() -> bool:
    return bool(settings.livekit_enabled and settings.livekit_url
                and settings.livekit_api_key and settings.livekit_api_secret)


async def ensure_room(room_name: str) -> bool:
    """Create room via LiveKit server API (idempotent)."""
    if not enabled():
        return False
    token = _service_token(room_name)
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{settings.livekit_url.replace('wss://', 'https://').replace('ws://', 'http://')}/rtc",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json={"room": {"name": room_name, "empty_timeout": 300}})
            return r.status_code < 300
    except Exception as e:
        log.warning("livekit room ensure failed: %s (WS transport continues)", e)
        return False


def _service_token(room_name: str) -> str:
    import time as _t
    import secrets
    import jwt as pyjwt
    now = int(_t.time())
    payload = {
        "iss": settings.livekit_api_key, "sub": "globaltalk-api",
        "nbf": now - 10, "exp": now + 300, "jti": secrets.token_hex(8),
        "video": {"roomCreate": True, "roomJoin": True, "room": room_name,
                  "canPublish": True},
    }
    return pyjwt.encode(payload, settings.livekit_api_secret, algorithm="HS256")


def join_token(room_name: str, identity: str, name: str, metadata: dict, ttl_seconds: int = 1800) -> dict | None:
    if not enabled():
        return None
    import time as _t
    import secrets
    import jwt as pyjwt
    now = int(_t.time())
    payload = {
        "iss": settings.livekit_api_key, "sub": identity, "name": name,
        "metadata": json.dumps(metadata),
        "nbf": now - 10, "exp": now + ttl_seconds, "jti": secrets.token_hex(8),
        "video": {"roomJoin": True, "room": room_name, "canPublish": True,
                  "canSubscribe": True},
    }
    token = pyjwt.encode(payload, settings.livekit_api_secret, algorithm="HS256")
    return {"url": settings.livekit_url, "token": token}


async def publish_translated_audio(session: RtSession, target_lang: str,
                                   text: str, segment_id: str, seq: int) -> bool:
    """Publish synthetic audio for a target language into the room.

    Implementation path when the livekit server SDK (livekit-rtc) is
    installed: a persistent RoomConnection per session publishes one audio
    track per target language; listeners subscribe by track name.

    Without the SDK we return False and the WS transport (tts.chunk events)
    remains the delivery path — the meeting still works end-to-end.
    """
    if not enabled() or session.mode != "livekit":
        return False
    try:
        from livekit import rtc  # type: ignore
    except ImportError:
        log.debug("livekit-rtc SDK not installed; translated audio delivered via WS")
        return False
    try:
        conn = await _room_connection(session, rtc)
        source = _track_source(conn, rtc, target_lang)
        # synthesize and push frames
        from app.ai import ai
        stream, _decision = await ai.synthesize_stream(text, target_lang)
        async for audio in stream:
            frames = _wav_to_frames(rtc, audio.data, audio.sample_rate)
            for f in frames:
                await source.capture_frame(f)
        await manager.broadcast(session, "audio.published", {
            "track": translated_track_name(target_lang),
            "segment_id": segment_id, "seq": seq, "target_lang": target_lang})
        return True
    except Exception:
        log.exception("livekit publish failed; WS fallback active")
        return False


_conns: dict[str, object] = {}
_sources: dict[tuple[str, str], object] = {}


async def _room_connection(session: RtSession, rtc):
    key = session.session_id
    if key in _conns:
        return _conns[key]
    token = join_token(session.room_name, f"gt-ai-{session.session_id[:8]}",
                       "GlobalTalk AI", {"role": "ai_publisher"})
    room = rtc.Room()
    await room.connect(token["url"], token["token"])
    _conns[key] = room
    return room


def _track_source(room, rtc, target_lang: str):
    key = (id(room), target_lang)
    if key in _sources:
        return _sources[key]
    source = rtc.AudioSource(24000, 1)
    track = rtc.LocalAudioTrack.create_audio_track(
        translated_track_name(target_lang), source)
    pub_opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    asyncio.ensure_future(room.local_participant.publish_track(track, pub_opts))
    _sources[key] = source
    return source


def _wav_to_frames(rtc, wav_bytes: bytes, sample_rate: int):
    import numpy as np
    from gt_ai.audio_utils import wav_to_pcm16, resample_pcm16
    pcm, rate = wav_to_pcm16(wav_bytes)
    if rate != sample_rate:
        pcm = resample_pcm16(pcm, rate, sample_rate)
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    frames = []
    step = sample_rate // 100  # 10ms frames
    for i in range(0, len(arr), step):
        chunk = arr[i:i + step]
        frame = rtc.AudioFrame(chunk.tobytes(), sample_rate, 1, len(chunk))
        frames.append(frame)
    return frames


async def close_room(session: RtSession) -> None:
    import contextlib
    key = session.session_id
    room = _conns.pop(key, None)
    for k in [k for k in _sources if k[0] == id(room)]:
        _sources.pop(k, None)
    if room is not None:
        with contextlib.suppress(Exception):
            await room.disconnect()
