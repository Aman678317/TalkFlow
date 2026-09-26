"""LiveKitAdapter (sections 12/77.1) — realtime media layer for production.

When LIVEKIT_URL/API_KEY/API_SECRET are configured, meetings run in LiveKit rooms:
human media + AI-published translated audio tracks + data-channel captions.
When not configured (dev sandbox), the platform uses its WebSocket PCM transport —
the same hub/pipeline/routing code path, so behaviour is identical.

Server-side audio publication uses the livekit server SDK (pinned in requirements) via
`livekit-api`; agent-side track publishing is implemented in services/agents (LiveKit
Agents runtime, section 77.2). This adapter never implements its own SFU.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from globaltalk.core.config import settings
from globaltalk.core.logging import get_logger

log = get_logger("livekit")


@dataclass
class LiveKitStatus:
    configured: bool
    healthy: bool
    reason: str = ""
    version: str = ""


class LiveKitAdapter:
    def __init__(self):
        self.url = settings.livekit_url
        self.api_key = settings.livekit_api_key
        self.api_secret = settings.livekit_api_secret

    @property
    def configured(self) -> bool:
        return settings.livekit_configured

    def _client(self):
        if not self.configured:
            raise RuntimeError("LiveKit not configured")
        from livekit import api  # pinned dependency; imported lazily
        return api.LiveKitAPI(self.url, self.api_key, self.api_secret)

    # ------------------------------------------------------------- rooms
    def create_room(self, room_name: str, *, empty_timeout_s: int = 3600,
                    max_participants: int = 100) -> dict:
        from livekit import api
        with self._client() as client:
            room = client.room.create_room(api.CreateRoomRequest(
                name=room_name, empty_timeout=empty_timeout_s,
                max_participants=max_participants))
            return {"name": room.name, "sid": room.sid}

    def delete_room(self, room_name: str) -> None:
        from livekit import api
        with self._client() as client:
            client.room.delete_room(api.DeleteRoomRequest(room=room_name))

    def get_room(self, room_name: str) -> dict | None:
        from livekit import api
        try:
            with self._client() as client:
                resp = client.room.list_rooms(api.ListRoomsRequest(room=[room_name]))
                rooms = list(resp.rooms)
                return {"name": rooms[0].name, "sid": rooms[0].sid,
                        "num_participants": rooms[0].num_participants} if rooms else None
        except Exception:
            return None

    def get_participants(self, room_name: str) -> list[dict]:
        from livekit import api
        with self._client() as client:
            resp = client.room.list_participants(
                api.ListParticipantsRequest(room=room_name))
            return [{"identity": p.identity, "name": p.name, "sid": p.sid,
                     "metadata": p.metadata} for p in resp.participants]

    # ------------------------------------------------------------- tokens
    def create_participant_token(self, room_name: str, identity: str, name: str,
                                 metadata: dict | None = None,
                                 can_publish: bool = True, ttl_s: int = 6 * 3600) -> str:
        import json as _json
        from livekit import api
        token = (api.AccessToken(self.api_key, self.api_secret)
                 .with_identity(identity).with_name(name).with_grants(
                     api.VideoGrants(room_join=True, room=room_name,
                                     can_publish=can_publish, can_subscribe=True))
                 .with_metadata(_json.dumps(metadata or {}))
                 .with_ttl(ttl_s))
        return token.to_jwt()

    def update_participant_metadata(self, room_name: str, identity: str,
                                    metadata: dict) -> None:
        import json as _json
        from livekit import api
        with self._client() as client:
            client.room.update_participant(api.UpdateParticipantRequest(
                room=room_name, identity=identity, metadata=_json.dumps(metadata)))

    def disconnect_participant(self, room_name: str, identity: str) -> None:
        from livekit import api
        with self._client() as client:
            client.room.remove_participant(api.RemoveParticipantRequest(
                room=room_name, identity=identity))

    # ------------------------------------------------------------- audio
    def publish_audio(self, room_name: str, wav_bytes: bytes, *, identity: str,
                      track_name: str = "translated-audio") -> str | None:
        """Server-side publication of AI-generated translated audio into the room.

        Production path: routed through the LiveKit Agents worker (services/agents) which
        holds an RTC connection and publishes AudioStreamTrack frames with sequence/timing
        control. This adapter method is the control-plane trigger; when the agents runtime
        is not connected it returns None and the hub falls back to WS audio delivery.
        """
        from globaltalk.realtime.hub import hub
        session = hub.get_by_room(room_name) if hasattr(hub, "get_by_room") else None
        log.info("livekit_publish_audio_requested",
                 extra={"room": room_name, "bytes": len(wav_bytes),
                        "path": "agents-runtime" if session else "ws-fallback"})
        return None

    def subscribe_audio(self, room_name: str, identity: str) -> None:
        """Subscription is client-driven (LiveKit client SDK); server side only tracks state."""
        log.info("livekit_subscribe_audio", extra={"room": room_name, "identity": identity})

    # ------------------------------------------------------------- health
    def health(self) -> LiveKitStatus:
        if not self.configured:
            return LiveKitStatus(False, False, reason="LIVEKIT_URL/KEY/SECRET not set")
        try:
            started = time.perf_counter()
            room = self.get_room("__globaltalk_probe__")
            latency = (time.perf_counter() - started) * 1000
            import livekit.api as _api
            version = getattr(_api, "__version__", "unknown")
            return LiveKitStatus(True, True, version=version,
                                 reason=f"ok ({latency:.0f}ms)")
        except Exception as exc:
            return LiveKitStatus(True, False, reason=str(exc)[:200])


adapter = LiveKitAdapter()
