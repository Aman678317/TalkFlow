"""Backend media plane for the Asterisk chan_websocket transport.

Pure protocol codec, externalMedia request assembly, and the WS media server
Asterisk dials into (``connection_type=client``). See
``docs/ASTERISK_LOCAL_SIP_LAB.md`` §P3 for the recorded decision and the
spike acceptance criteria this package is written to satisfy.
"""
from app.telephony.media.external_media import (
    ExternalMediaError,
    ExternalMediaSession,
    ExternalMediaWebSocketOptions,
    MediaChannelInfo,
    MediaDirection,
)
from app.telephony.media.ws_media_protocol import (
    CadenceTracker,
    ControlMessage,
    FrameChunker,
    FrameSlicer,
    MediaStart,
    WSMediaProtocolError,
    build_command,
    build_json_command,
    parse_media_start,
    rms_linear16,
)

__all__ = [
    "CadenceTracker",
    "ControlMessage",
    "ExternalMediaError",
    "ExternalMediaSession",
    "ExternalMediaWebSocketOptions",
    "FrameChunker",
    "FrameSlicer",
    "MediaChannelInfo",
    "MediaDirection",
    "MediaStart",
    "WSMediaProtocolError",
    "build_command",
    "build_json_command",
    "parse_media_start",
    "rms_linear16",
]
