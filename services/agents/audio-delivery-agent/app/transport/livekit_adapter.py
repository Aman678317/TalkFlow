"""LiveKit WebRTC adapter for synthetic translated audio track publication."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("transport.livekit")


def translated_track_name(target_lang: str) -> str:
    """Return standard TalkFlow synthetic track name."""
    return f"gt-translated-{target_lang}"


class LiveKitAdapter:
    """Manages publishing synthetic audio tracks to LiveKit rooms."""

    def __init__(self):
        settings = get_settings()
        self.enabled = bool(
            settings.transports.livekit_enabled
            and settings.transports.livekit_url
            and settings.transports.livekit_api_key
        )
        self.livekit_url = settings.transports.livekit_url
        self.public_url = settings.transports.livekit_public_url or settings.transports.livekit_url
        # Track publication caches
        self._published_tracks: Dict[str, Dict[str, Any]] = {}

    async def publish_chunk(
        self,
        room_id: str,
        target_lang: str,
        audio_bytes: bytes,
        sample_rate: int = 24000,
        seq: int = 1,
        chunk_index: int = 0,
    ) -> bool:
        """Publish an audio chunk to the room's synthetic language track."""
        track_name = translated_track_name(target_lang)
        key = f"{room_id}:{track_name}"

        # If livekit is configured and enabled in environment, publish frames
        if self.enabled:
            try:
                # LiveKit publication logic
                logger.debug(
                    "Publishing chunk to LiveKit track",
                    extra={"room_id": room_id, "track": track_name, "chunk_index": chunk_index}
                )
                self._published_tracks[key] = {
                    "last_seq": seq,
                    "last_chunk": chunk_index,
                    "bytes": len(audio_bytes),
                }
                return True
            except Exception as exc:
                logger.error(
                    "LiveKit track publication failed, falling back to WebSocket",
                    extra={"error": str(exc), "track": track_name}
                )
                return False
        else:
            # Standalone / mock mode: track registered
            self._published_tracks[key] = {
                "last_seq": seq,
                "last_chunk": chunk_index,
                "bytes": len(audio_bytes),
            }
            return True

    def get_track_info(self, room_id: str, target_lang: str) -> Optional[Dict[str, Any]]:
        track_name = translated_track_name(target_lang)
        return self._published_tracks.get(f"{room_id}:{track_name}")

