# Realtime Protocol & Pipeline (WebSocket + LiveKit)

## Transport

- **Production:** LiveKit rooms (WebRTC SFU). Human media + AI-published translated audio
  tracks; captions/events via data channels. `LiveKitAdapter` (services/realtime) creates
  rooms/tokens; `/api/v1/voice/session?meeting_id=...` returns `{transport:"livekit", token}`.
- **Dev / edge / sandbox:** WebSocket at `/ws/meetings/{meeting_id}?token=<JWT>` or
  `?join_token=<meeting-token>` (guests). Identical hub, pipeline and event protocol.
  `voice/session` then returns `{transport:"websocket", ws_url}`.

## Wire format

- **JSON text frames** — control + captions/translations (schema below).
- **Binary frames** — audio. Layout:

```
byte 0        'O' original relay │ 'T' translated TTS PCM
bytes 1..16   utterance/segment short-id (ASCII)
byte 17       (T only) language-code length N
bytes 18..    (T only) language code
rest          PCM16 mono 16 kHz little-endian
```

Clients send microphone audio as raw PCM16 mono 16 kHz binary frames (the AudioWorklet
in `apps/web/src/lib/audio.ts` downsamples and forwards ~100 ms blocks).

## Event envelope (version 1)

```json
{
  "version": 1,
  "type": "transcript.final",
  "session_id": "…", "conversation_id": "<meeting_id>",
  "speaker_id": "<participant_id>",
  "sequence": 1042,
  "timestamp": "2026-09-26T12:00:00Z",
  "…payload fields…": ""
}
```

`sequence` is per-conversation, assigned by the hub (deterministic infrastructure —
never by agents), monotonic across all participants.

## Client → server events

| type | payload | notes |
|---|---|---|
| `session.join` | `display_name, speaking_language, listening_language, audio_mode, caption_mode, latency_mode, last_sequence, resume, participant_id?` | first frame after connect; 15 s join timeout |
| `preferences.update` | any of the preference fields | live re-routing; persisted to DB |
| `chat.send` | `text` | original stored immutably; per-listener translations fan out |
| `audio.stopped` | — | mic released |
| `ping` | `ts` | heartbeat; server replies `pong` |

## Server → client events

`session.created/updated/resumed`, `participant.joined/left`, `audio.started/stopped`,
`speech.started/ended`, `transcript.partial/final`, `translation.started/partial/final`,
`tts.started/completed` (base64 WAV in `audio`, `synthetic:true`), `audio.published`,
`caption.updated`, `language.changed`, `chat.message`, `chat.translation`,
`quality.latency` (per-stage breakdown), `quality.degraded` (recoverable, with
`user_message`), `translation.failed`, `reconnect.required`, `error`, `pong`.

## Latency contract

`quality.latency` reports per-utterance, per-target-language:

```
audio_capture_ms · stt_first_partial_ms · stt_final_ms · translation_ms ·
tts_first_audio_ms · delivery_ms · total_e2e_latency_ms
```

Product benchmark 1.5–2.5 s (warm GPU/CPU pools, good network). Measured p50/p95/p99
per language pair at `/metrics` (`realtime_e2e_latency_ms`). The 1 GB-CPU sandbox profile
runs ~8–12 s per utterance due to subprocess model isolation — documented, measured,
never faked.

## Pipeline stages (server)

1. **Ingest** 100 ms PCM chunks → EnergyVAD (or Silero) probability.
2. **Segmentation** start ≥0.18 prob, end after 700 ms hangover; min 350 ms, max 30 s.
3. **Partials** every `partial_interval_ms` (800/1500/2500 by `latency_mode`); stale
   partials dropped via utterance generation counters (cancellation).
4. **Final STT** → canonical `TranscriptSegment` persisted **before** broadcast.
5. **Fan-out** one translation per `(segment, target_language)` — cached, deduplicated;
   5 listeners wanting English = 1 translation job.
6. **TTS** once per language, fanned out as base64 WAV (+ stored object, `audio.published`).
7. **Listener router** delivers per `audio_mode`/`caption_mode`; original relay always
   available so the human conversation continues even with AI fully down.
8. **Backpressure** bounded concurrent fan-out per speaker (semaphore), overflow →
   `quality.degraded` (captions-only), never queue explosion.

## Reconnect & resume

- Client reconnects with `resume:true, last_sequence:N` → `session.resumed` marker then
  replay of buffered events `> N` (ring buffer 2000 events; finals additionally persisted
  in DB, so nothing is lost beyond the buffer — refetch transcript via REST).
- Preferences persist server-side (DB) and survive reconnects.
- Exponential backoff + jitter client-side (`MeetingSocket`); 4401/4403 are permanent
  (no retry storm).
- Idempotency: events carry `sequence`; clients dedupe by sequence. Replayed history
  arrives after the `session.resumed` marker; live events continue after it.

## Multi-node note

With Redis configured, the cache adapter's pub/sub carries fan-out across API nodes
(hub interface is backend-agnostic). Session state authoritative in DB; ring buffer per node.
