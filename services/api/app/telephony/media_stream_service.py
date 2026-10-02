"""Telephony Media Stream Service: Bidirectional Audio Bridge & Carrier Gateway.

Bridges PSTN Media Stream WebSockets (8kHz G.711 μ-law, 20ms frames) and
Web Client WebSockets (16kHz PCM16) with the BidirectionalTranslationBridge.
Includes low-latency audio pacer, barge-in clear events, playback marks,
and real-time event broadcasting to web clients.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any

from fastapi import WebSocket

from app.db import models as M
from app.db.session import db_session
from app.telephony.audio_codec import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    resample_8k_to_16k,
    resample_to_8k,
)
from app.telephony.bidirectional_bridge import BidirectionalTranslationBridge
from app.telephony.call_service import CallService

log = logging.getLogger("app.telephony.media_stream")

PACER_CHUNK_BYTES = 160     # 20ms of 8000Hz 8-bit mono μ-law
PACER_INTERVAL_S = 0.020    # 20 milliseconds pacing cadence


class TelephonyMediaStreamSession:
    """Manages active media streaming for a call session (Carrier PSTN + Web Client)."""

    def __init__(self, call_id: uuid.UUID, ws: WebSocket | None = None) -> None:
        self.call_id = call_id
        self.carrier_ws: WebSocket | None = ws
        self.client_ws_list: list[WebSocket] = []
        self.stream_sid: str = ""
        self.call_sid: str = ""
        self.is_active: bool = True
        self.pacer_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=500)
        self.pacer_task: asyncio.Task | None = None

        # Call configuration
        self.caller_language: str = "hi"
        self.receiver_language: str = "ja"
        self.call_mode: str = "human_to_human"
        self.unified_prompt: str = ""

        # Bidirectional Translation Bridge
        self.bridge: BidirectionalTranslationBridge | None = None

    async def initialize(self) -> None:
        """Fetch call parameters from database and spin up the translation bridge."""
        async with db_session() as db:
            cs = CallService(db)
            # Find call by ID
            from sqlalchemy import select
            res = await db.execute(select(M.CallSession).where(M.CallSession.id == self.call_id))
            call_row = res.scalars().first()
            if call_row:
                self.call_sid = call_row.call_sid
                self.caller_language = call_row.caller_language or "hi"
                self.receiver_language = call_row.receiver_language or "ja"
                self.call_mode = call_row.mode or "human_to_human"

                # If prompt version ID is attached, load prompt
                if call_row.prompt_version_id:
                    v_res = await db.execute(
                        select(M.PromptVersion).where(M.PromptVersion.id == call_row.prompt_version_id)
                    )
                    v_row = v_res.scalars().first()
                    if v_row:
                        self.unified_prompt = v_row.merged_prompt

        # Create the Bidirectional Bridge
        self.bridge = BidirectionalTranslationBridge(
            call_id=self.call_id,
            caller_language=self.caller_language,
            receiver_language=self.receiver_language,
            mode=self.call_mode,
            unified_prompt=self.unified_prompt,
            on_event=self._broadcast_event,
            on_audio_out=self._handle_bridge_audio_out,
            on_barge_in=self._handle_bridge_barge_in,
        )
        await self.bridge.start()

    async def run_carrier(self, ws: WebSocket) -> None:
        """Main lifecycle loop for the telephony carrier media stream (Twilio/Telnyx)."""
        self.carrier_ws = ws
        self.pacer_task = asyncio.create_task(self._pacer_loop(), name=f"pacer-{self.call_id}")

        if not self.bridge:
            await self.initialize()

        try:
            while self.is_active:
                raw_msg = await ws.receive_text()
                data = json.loads(raw_msg)
                event = data.get("event")

                if event == "connected":
                    log.info("Carrier media stream connected for call %s", self.call_id)

                elif event == "start":
                    await self._handle_carrier_start(data)

                elif event == "media":
                    await self._handle_carrier_media(data)

                elif event == "mark":
                    mark_name = data.get("mark", {}).get("name")
                    log.debug("Received playback mark ack: %s", mark_name)

                elif event == "stop":
                    log.info("Carrier media stream stop event for call %s", self.call_id)
                    break

        except Exception as e:
            log.warning("Carrier stream loop ended for call %s: %s", self.call_id, e)
        finally:
            self.carrier_ws = None
            if self.pacer_task:
                self.pacer_task.cancel()
            await self._handle_termination()

    async def register_client_ws(self, ws: WebSocket) -> None:
        """Register a web browser client on the active call session."""
        self.client_ws_list.append(ws)
        if not self.bridge:
            await self.initialize()

        # Send initial call status and configuration
        await ws.send_text(json.dumps({
            "type": "call.status",
            "data": {
                "call_id": str(self.call_id),
                "caller_language": self.caller_language,
                "receiver_language": self.receiver_language,
                "mode": self.call_mode,
                "is_active": self.is_active,
            }
        }))

    def unregister_client_ws(self, ws: WebSocket) -> None:
        if ws in self.client_ws_list:
            self.client_ws_list.remove(ws)

    async def handle_client_audio(self, pcm16_audio: bytes) -> None:
        """Inbound 16kHz audio from web browser user's microphone (Leg A)."""
        if self.bridge and self.is_active:
            await self.bridge.feed_caller_pcm16(pcm16_audio)

    async def _handle_carrier_start(self, data: dict[str, Any]) -> None:
        start_data = data.get("start", {})
        self.stream_sid = data.get("streamSid") or start_data.get("streamSid", "")
        self.call_sid = start_data.get("callSid") or self.call_sid

        log.info(
            "Telephony stream started: stream_sid=%s, call_sid=%s (Call %s)",
            self.stream_sid, self.call_sid, self.call_id
        )

        async with db_session() as db:
            cs = CallService(db)
            if self.call_sid:
                await cs.transition_status(self.call_sid, "translating", extra_data={"stream_sid": self.stream_sid})

        await self._broadcast_event("call.connected", {
            "stream_sid": self.stream_sid,
            "call_sid": self.call_sid,
        })

    async def _handle_carrier_media(self, data: dict[str, Any]) -> None:
        """Inbound 8kHz μ-law audio from PSTN phone handset (Leg B)."""
        media_data = data.get("media", {})
        payload_b64 = media_data.get("payload")
        if not payload_b64:
            return

        try:
            # 1. Decode base64 8kHz μ-law
            mulaw_bytes = base64.b64decode(payload_b64)
            if not mulaw_bytes:
                return

            # 2. Transcode 8kHz μ-law -> 8kHz PCM16 linear
            pcm16_8k = mulaw_to_pcm16(mulaw_bytes)

            # 3. Resample 8kHz PCM16 -> 16kHz PCM16 for speech pipeline
            pcm16_16k = resample_8k_to_16k(pcm16_8k)

            # 4. Feed into Receiver Leg of Bidirectional Bridge
            if self.bridge:
                await self.bridge.feed_receiver_pcm16(pcm16_16k)

        except Exception as e:
            log.debug("Error processing carrier media chunk: %s", e)

    async def _handle_bridge_audio_out(self, target_leg: str, pcm16_16k: bytes) -> None:
        """Audio synthesized by the bridge to be delivered to a participant."""
        if target_leg == "receiver":
            # Receiver is PSTN callee -> convert to 8kHz μ-law and pace into carrier WebSocket
            await self.queue_outbound_tts_audio(pcm16_16k, src_sample_rate=16000)
        elif target_leg == "caller":
            # Caller is Web Client -> broadcast PCM16 audio chunks to web clients
            payload_b64 = base64.b64encode(pcm16_16k).decode("ascii")
            msg = json.dumps({
                "type": "call.audio_chunk",
                "data": {
                    "target": "caller",
                    "audio_base64": payload_b64,
                    "sample_rate": 16000,
                    "format": "pcm16",
                }
            })
            for ws in list(self.client_ws_list):
                try:
                    await ws.send_text(msg)
                except Exception:
                    pass

    async def _handle_bridge_barge_in(self, target_leg: str) -> None:
        """Barge-in: participant interrupted playback -> flush buffers."""
        if target_leg == "receiver":
            await self.handle_barge_in()
        elif target_leg == "caller":
            # Notify web client to abort playing any buffered TTS audio
            await self._broadcast_event("call.barge_in", {"target": "caller"})

    async def queue_outbound_tts_audio(self, pcm16_audio: bytes, src_sample_rate: int = 16000) -> None:
        """Enqueue synthesized translated audio from TTS to be streamed out to phone handset."""
        if not self.is_active or not self.carrier_ws:
            return

        # 1. Downsample to 8,000 Hz with anti-aliasing
        pcm16_8k = resample_to_8k(pcm16_audio, src_sample_rate)

        # 2. Compand to 8-bit ITU-T G.711 μ-law
        mulaw_bytes = pcm16_to_mulaw(pcm16_8k)

        # 3. Slice into exact 160-byte (20ms) frames and enqueue
        for i in range(0, len(mulaw_bytes), PACER_CHUNK_BYTES):
            chunk = mulaw_bytes[i:i + PACER_CHUNK_BYTES]
            if len(chunk) < PACER_CHUNK_BYTES:
                chunk = chunk.ljust(PACER_CHUNK_BYTES, b"\xFF")
            try:
                self.pacer_queue.put_nowait(chunk)
            except asyncio.QueueFull:
                break

    async def handle_barge_in(self) -> None:
        """PSTN caller started speaking — purge queued playback buffer instantly."""
        while not self.pacer_queue.empty():
            try:
                self.pacer_queue.get_nowait()
            except Exception:
                break

        if self.carrier_ws and self.stream_sid:
            try:
                await self.carrier_ws.send_text(json.dumps({
                    "event": "clear",
                    "streamSid": self.stream_sid,
                }))
                log.debug("Barge-in: sent clear event to carrier stream %s", self.stream_sid)
            except Exception:
                pass

    async def _pacer_loop(self) -> None:
        """Paces out 160 bytes of μ-law audio every 20ms to prevent carrier buffer-bloat."""
        while self.is_active:
            try:
                chunk = await self.pacer_queue.get()
                if not self.carrier_ws or not self.stream_sid:
                    await asyncio.sleep(PACER_INTERVAL_S)
                    continue

                payload_b64 = base64.b64encode(chunk).decode("ascii")
                msg = json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": payload_b64},
                })
                await self.carrier_ws.send_text(msg)
                await asyncio.sleep(PACER_INTERVAL_S)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug("Pacer exception: %s", e)
                await asyncio.sleep(PACER_INTERVAL_S)

    async def _broadcast_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast live event (transcripts, latency, state) to all connected web clients."""
        msg = json.dumps({"type": event_type, "data": data})
        for ws in list(self.client_ws_list):
            try:
                await ws.send_text(msg)
            except Exception:
                pass

    async def _handle_termination(self) -> None:
        self.is_active = False
        if self.bridge:
            await self.bridge.stop()
        async with db_session() as db:
            cs = CallService(db)
            if self.call_sid:
                await cs.transition_status(self.call_sid, "ended")
        await self._broadcast_event("call.ended", {"call_id": str(self.call_id)})


class MediaStreamService:
    _active_streams: dict[uuid.UUID, TelephonyMediaStreamSession] = {}

    @classmethod
    def get_or_create(cls, call_id: uuid.UUID) -> TelephonyMediaStreamSession:
        if call_id not in cls._active_streams:
            cls._active_streams[call_id] = TelephonyMediaStreamSession(call_id)
        return cls._active_streams[call_id]

    @classmethod
    def register(cls, call_id: uuid.UUID, session: TelephonyMediaStreamSession) -> None:
        cls._active_streams[call_id] = session

    @classmethod
    def unregister(cls, call_id: uuid.UUID) -> None:
        cls._active_streams.pop(call_id, None)

    @classmethod
    def get_stream(cls, call_id: uuid.UUID) -> TelephonyMediaStreamSession | None:
        return cls._active_streams.get(call_id)
