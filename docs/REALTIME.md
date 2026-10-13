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
`quality.degraded` (recoverable, with `user_message`), `translation.failed`,
`playback.flush`, `latency.report`, `reconnect.required`, `error`, `pong`.

### Caption identity and timeline

Three events build one caption and they do not arrive together: `transcript.partial`
while the speaker is still talking, `transcript.final` when they stop, then
`translation.final` several hundred ms later — by which time another speaker may
already have a line on screen. So arrival order is not turn order, and a client that
joins them by display name can put a translation on the wrong person's caption.

Every caption event therefore names the turn it describes (`utterance_id`, or
`segment_id` — `ServerEvent.to_json` fills in the former from the latter), and
`transcript.final`, `translation.final` and `latency.report` carry the turn's
measured timeline:

| field | meaning |
| --- | --- |
| `start_wall_ms` | epoch ms at which the turn began, computed as now minus how long the turn had been open when final STT landed |
| `duration_ms` | how long that turn's audio ran (`16 kHz mono PCM16` byte count) |
| `seq` | the speaker's own turn counter, for ordering within one speaker |

`start_wall_ms` is not `start_ms` in the database row: the stored value is the VAD's
per-speaker frame clock, which restarts with each connection and so cannot place two
speakers on one timeline.

Playback state is deliberately **not** on the wire. Only the browser's audio queue
knows what a listener actually heard, so `AudioPlayer` reports `playing` / `played` /
`dropped` per turn and `lib/captions.ts` attaches it to the line — which is also how a
barge-in shows as "not heard" instead of silently deleting the caption.

## Latency contract

`latency.report` reports per-utterance, per-target-language, and carries the same
turn identity and timeline as the captions it delayed (`utterance_id`,
`start_wall_ms`, `duration_ms`):

```
audio_capture_ms · stt_first_partial_ms · stt_final_ms · translation_ms ·
tts_first_audio_ms · delivery_ms · total_e2e_latency_ms
```

Product benchmark 1.5–2.5 s (warm GPU/CPU pools, good network). Measured p50/p95/p99
per language pair at `/metrics` (`realtime_e2e_latency_ms`). The 1 GB-CPU sandbox profile
runs ~8–12 s per utterance due to subprocess model isolation — documented, measured,
never faked.

## Pipeline stages (server)

1. **Ingest** 50 ms PCM chunks (16 kHz mono) → EnergyVAD (or Silero) on 30 ms frames.
2. **Segmentation** all four thresholds are settings, not literals (see `.env.example`):
   turn ends after `vad_min_silence_ms` (default 500 ms) of silence, which is also the
   end-of-speech latency; a burst shorter than `vad_min_speech_ms` (250 ms) is a cough,
   not a turn; a speaker who never pauses is force-committed at `vad_max_speech_ms`
   (15 s). `tests/unit/test_vad_cadence.py` measures the latency each setting costs.
3. **Partials** every `vad_partial_interval_ms` (default 1200 ms) for live captions;
   stale partials dropped via utterance generation counters (cancellation).
4. **Final STT** → canonical `TranscriptSegment` persisted **before** broadcast.
5. **Fan-out** one translation per `(segment, target_language)` — cached, deduplicated;
   5 listeners wanting English = 1 translation job.
6. **TTS** once per language, fanned out as base64 WAV (+ stored object, `audio.published`).
7. **Listener router** delivers per `audio_mode`/`caption_mode`; original relay always
   available so the human conversation continues even with AI fully down.
8. **Backpressure** bounded concurrent fan-out per speaker (semaphore), overflow →
   `quality.degraded` (captions-only), never queue explosion.

## Listener modes (tested matrix)

`tests/unit/test_realtime_listener_modes.py` locks the routing table. A translated
language group is delivered per chunk, to `hear_lang == target` participants in
`translated` or `mixed` mode — never to the speaker of that turn, and never to a
participant the supervisor has marked stale for that language.

| Listener | translated audio | original relay | source caption | translated caption |
| --- | --- | --- | --- | --- |
| speaker | no | no (never echoed to sender) | yes | yes |
| `original` | no | yes | yes | only if `caption_mode` allows it |
| `mixed` | yes | yes | yes | as above |
| `translated` | yes | no | yes | as above |

Two people wanting English get one translation job and one chunk each — the group
is per `(segment, language)`, not per listener, so there is no duplicate voice.

### Changing your mind mid-utterance

Two scopes, deliberately different:

- `playback.flush` with `scope:"speaker"` — a barge-in. Broadcast to the session
  and sequenced (a resume must not lose it); the browser cancels that speaker's
  queue tags and everybody else keeps playing.
- `playback.flush` with `scope:"recipient"` — one listener changed `hear_lang`.
  Sent to that socket only and **not** sequenced, because a replayed recipient
  flush would tell a *different* reconnecting participant to stop live audio.
  The supervisor marks `(recipient, previous_language)` stale, and clears the
  mark for `(recipient, new_language)` so en→ur→en does not leave English dead
  for the rest of the meeting.

Both scopes report the cut turn as `dropped` to the caption layer, so the line
says "not heard" instead of implying the listener heard a sentence they did not.

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
