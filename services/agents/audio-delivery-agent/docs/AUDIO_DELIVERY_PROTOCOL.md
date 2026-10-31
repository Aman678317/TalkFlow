# TalkFlow Audio Delivery Protocol Specification

## 1. Binary Wire Framing (Tag: 0x54)

TalkFlow delivers lowest-latency audio using binary frames over WebSockets.

### Byte Layout

| Offset | Length | Type | Description |
|---|---|---|---|
| 0 | 1 | uint8 | Magic Tag: `0x54` (`ASCII 'T'`) |
| 1 | 16 | bytes | Short Segment UUID (16 characters UTF-8, padded with `\x00`) |
| 17 | 1 | uint8 | Language Code Byte Length ($L$) |
| 18 | $L$ | string | UTF-8 Target Language Code (e.g. `mr`, `hi`, `en`) |
| $18+L$ | 1 | uint8 | Chunk Index Extension Marker: `0x01` |
| $19+L$ | 4 | uint32 | Chunk Sequence Index (Big-Endian) |
| $23+L$ | Remainder | bytes | Audio Payload (PCM 16-bit 24kHz / WAV bytes) |

Clients that do not support chunk indexing (legacy clients) omit the extension marker and receive audio directly at offset $18+L$.

---

## 2. Inbound REST / Event Contract

Agent 07 accepts chunks from Agent 06 at:
`POST /api/v1/delivery/chunks` or `POST /api/v1/audio/sync/chunk`

```json
{
  "version": 1,
  "type": "tts.chunk",
  "session_id": "room_conf_01",
  "conversation_id": "room_conf_01",
  "speaker_id": "speaker_human",
  "segment_id": "seg_001",
  "utterance_id": "seg_001",
  "seq": 1,
  "target_lang": "mr",
  "chunk_index": 0,
  "is_final_chunk": false,
  "duration_ms": 250.0,
  "audio_base64": "UklGRi...",
  "synthetic": true,
  "audio_origin": "synthetic_tts",
  "start_wall_ms": 1729837192000
}
```

---

## 3. Barge-In Interruption & Flush

`POST /api/v1/delivery/cancel` or `POST /api/v1/audio/sync/cancel`

```json
{
  "room_id": "room_conf_01",
  "speaker_id": "speaker_human",
  "reason": "speaker_barge_in"
}
```

Dispatches `playback.flush` to all connected client WebSockets:
```json
{
  "type": "playback.flush",
  "room_id": "room_conf_01",
  "segment_id": "seg_001",
  "reason": "speaker_barge_in",
  "timestamp": 1729837193.12
}
```
Client audio engines instantly clear their queued audio buffers upon receipt.

