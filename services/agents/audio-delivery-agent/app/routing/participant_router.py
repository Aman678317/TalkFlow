"""In-memory room registry and participant routing engine."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from app.core.exceptions import RoomIsolatedError
from app.core.logging import get_logger
from app.models.delivery_models import AudioTrackInfo, ParticipantRoute, RoomSession

logger = get_logger("routing.router")


class ParticipantRouter:
    """Manages active rooms, participants, and per-target-language fan-out routing."""

    def __init__(self):
        # room_id -> RoomSession
        self._rooms: Dict[str, RoomSession] = {}

    def get_or_create_room(self, room_id: str, tenant_id: str = "org_default") -> RoomSession:
        """Retrieve existing room session or initialize a new isolated room."""
        if room_id not in self._rooms:
            self._rooms[room_id] = RoomSession(room_id=room_id, tenant_id=tenant_id)
            logger.info("Created isolated room session", extra={"room_id": room_id, "tenant_id": tenant_id})
        return self._rooms[room_id]

    def get_room(self, room_id: str) -> Optional[RoomSession]:
        return self._rooms.get(room_id)

    def register_participant(self, route: ParticipantRoute) -> RoomSession:
        """Register or update a participant within an isolated room."""
        room = self.get_or_create_room(route.room_id, route.tenant_id)

        # Multi-tenant safety check: cross-tenant access prohibited
        if room.tenant_id != route.tenant_id:
            raise RoomIsolatedError(
                f"Tenant mismatch for room {route.room_id}: expected {room.tenant_id}, got {route.tenant_id}"
            )

        room.participants[route.participant_id] = route
        logger.info(
            "Registered participant route",
            extra={
                "room_id": route.room_id,
                "participant_id": route.participant_id,
                "hear_lang": route.hear_lang,
                "playback_mode": route.playback_mode,
            }
        )
        return room

    def unregister_participant(self, room_id: str, participant_id: str) -> None:
        """Remove a participant from a room."""
        room = self._rooms.get(room_id)
        if room and participant_id in room.participants:
            del room.participants[participant_id]
            logger.info(
                "Unregistered participant",
                extra={"room_id": room_id, "participant_id": participant_id}
            )

    def update_preferences(
        self,
        room_id: str,
        participant_id: str,
        hear_lang: Optional[str] = None,
        playback_mode: Optional[str] = None,
        translation_audio_enabled: Optional[bool] = None,
        original_audio_enabled: Optional[bool] = None,
        captions_enabled: Optional[bool] = None,
    ) -> Optional[ParticipantRoute]:
        """Update audio delivery settings for a participant."""
        room = self._rooms.get(room_id)
        if not room or participant_id not in room.participants:
            return None

        p = room.participants[participant_id]
        if hear_lang is not None:
            p.hear_lang = hear_lang
        if playback_mode is not None:
            p.playback_mode = playback_mode
        if translation_audio_enabled is not None:
            p.translation_audio_enabled = translation_audio_enabled
        if original_audio_enabled is not None:
            p.original_audio_enabled = original_audio_enabled
        if captions_enabled is not None:
            p.captions_enabled = captions_enabled
        p.last_seen_at = time.time()
        return p

    def get_recipients(
        self, room_id: str, target_lang: str, speaker_id: Optional[str] = None
    ) -> List[ParticipantRoute]:
        """Resolve eligible recipients for translated audio in target_lang at this instant.
        
        CRITICAL RULES:
        1. Only listeners wanting translated audio (hear_lang == target_lang and playback_mode in ('translated', 'both')).
        2. In multi-participant rooms, EXCLUDE the human speaker to prevent audio feedback loops.
        3. Only active, connected participants with translation audio enabled.
        """
        room = self._rooms.get(room_id)
        if not room:
            return []

        eligible: List[ParticipantRoute] = []
        is_multi_participant = len(room.participants) > 1

        for p in room.participants.values():
            if not p.is_connected or not p.translation_audio_enabled:
                continue

            # Check language match and playback mode
            if p.hear_lang.lower() == target_lang.lower() and p.playback_mode in ("translated", "both"):
                # Feedback loop prevention: exclude speaker's own microphone origin
                if is_multi_participant and speaker_id and p.participant_id == speaker_id:
                    continue
                eligible.append(p)

        return eligible

    def list_all_rooms(self) -> List[RoomSession]:
        return list(self._rooms.values())

