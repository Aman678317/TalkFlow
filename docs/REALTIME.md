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

### Measured baseline (first one, 2026-10-13)

`speech end → first translated audio`, per language pair, over the
`transcript.inject` path (`python tests/realtime/bench_latency.py`). Conditions,
because a percentile without them is not a baseline:

- Host `Windows-10-10.0.19045-SP0`, Intel64 Family 6 Model 158, Python 3.14.2.
  Client and server on one machine over loopback, so no access-network term is
  in the number — but the providers are reached over the public internet (below).
- Backend `services/api` on `127.0.0.1:8126`, dev stand-in providers — the run
  reports `stt_dev_mode/mt_dev_mode/tts_dev_mode: True` rather than asserting
  which model answered.
- Text injected, so there is no capture and no recogniser in these rows:
  `audio_capture_ms` and `stt_final_ms` are absent, not zero.

| pair | turns | p50 | p95 | of which translation p50 | TTS first frame p50 |
| --- | --- | --- | --- | --- | --- |
| `hi→en` | 20 | 1429 ms | 2217 ms | 1385 ms | 11 ms |
| `mr→en` | 2 | 1339 ms | 1653 ms | — | — |
| `bn→en` | 2 | 1507 ms | 1677 ms | — | — |
| `ja→en` | 2 | 1870 ms | 2250 ms | — | — |
| `ta→en` | 2 | 1958 ms | 2292 ms | — | — |

Two runs, not one: the `hi→en` row is `--source hi --hear en` over 20 turns, the
others are the two samples each that a mixed-source 10-turn run produced. A p95
over two samples is a max wearing a percentile's name — it is here because the
rollup reports it, not because it says anything. Translation and TTS columns are
only broken out for the run that used one pair throughout.

Every turn was anchored and delivered audio; none was dropped as stale. The
server-side rollup for the 20-turn run reads `hi→en n=20 p50 1407 p95 2137`,
which is the same distribution the harness measured, a few ms lower because it
stops at the supervisor's own clock instead of the delivery.

"Dev stand-in" does not mean nothing left the machine, and the rows say so: the
`/metrics` for this server are `provider="neural_online"` for translation (a
public HTTP translator, because no MT key is configured) and `provider="dev_tone"`
for speech. Its `hi→en` translation counter stands at 48 calls over 70.6 s — a
1470 ms mean, which is the whole of the headline number: the wait is that round
trip. Voice synthesis itself was ~11 ms, and each turn first discovered twice
over that `piper` and `kokoro` are not installed on this host.

So this is a *pipeline* baseline measured over a live internet path, not a
provider baseline: no microphone and no recogniser are in it (`audio_capture_ms`
and `stt_final_ms` are absent, not zero), and no credentialed MT or neural voice
answered. Both directions of a real two-browser call with real credentials are
what Phase 6 gates on, and they need the items in
`docs/REALTIME_DEPLOY_REQUIREMENTS.md` that are still unset on this machine.

### Provider failure policy

Three bounded layers, all settings (`services/api/app/config.py`), none of them
a promise that a provider is fast:

1. **Deadline per call.** `ai_timeout_s` (8 s) caps one provider attempt,
   `ai_retry_budget_s` (20 s) caps the whole failover walk for a turn, and the
   realtime path tightens the first to `rt_translate_timeout_s` (5 s) — a
   translation that misses that window is worth less to the room than the
   original caption it is holding. A provider that accepts a request and then
   stalls is now indistinguishable from a slow one for at most one deadline, and
   the walk moves to the candidate behind it.
2. **Finite retries.** The walk tries each candidate once, in router order,
   ending in the local dev stand-in. It never loops: a provider that fails twice
   is not asked twice in the same turn.
3. **Circuit breaker.** Four failures in a rolling window (or one refusal the
   facade can see directly — a healthcheck that says no, a voice that cannot
   stream) opens that provider's circuit for `provider_cooldown_s` (30 s),
   doubling per failed recovery probe up to `provider_max_cooldown_s` (600 s).
   After a cooldown the provider is offered once, and that single outcome either
   closes the circuit for the next turn or re-opens it for longer. Breakers
   survive a model-registry reload; an operator's `mark_available` outranks
   them.

The measured reason for layer 3: the run above logged 35 refused `piper` probes
and 35 refused `kokoro` probes for 20 turns — two internet-free healthchecks
thrown away before every caption, and the same for every later turn a room is
open. `tests/unit/test_provider_circuit_breaker.py` pins the cooldown, the
backoff, the re-open, and that a turn still gets audio from the fallback while a
dead voice is left alone.

Failure is never silent and never fatal: when every translation candidate fails,
the room keeps the speaker's original text as the caption and the event names
which layer gave up. When every voice fails, synthesis raises a stated
`ProviderError` rather than handing out a stream that dies on the first frame.

### Naming a failure

An outage and a refused language pair are different answers, and before this the
room could not tell them apart: the stage event said `provider_unavailable` for
*every* exception while the wire event said the exception's own class name, so
one caption carried two contradictory reasons and a listener who had simply
picked a language this deployment has not enabled was told to wait.

`app.realtime.agents.contracts.failure_reason()` is now the only classifier. It
takes the code an `AppError` subclass already names itself with
(`unsupported_language`, `provider_error`, `rate_limited`, `validation_error`),
falls back to `timeout` for anything that is a `TimeoutError` — which is what
`asyncio.wait_for`, `httpx` and the socket layer all raise — and only then
reaches `provider_unavailable`, so the outage label is earned rather than
assumed. The internal `stage.failed` event, the client-facing
`translation.failed` code and the Prometheus `reason` label all call it, which is
the only reason the three can be trusted to agree.

`translation.failed` carries that code plus one sentence per reason
(`_FAILED_MESSAGES` in `services/api/app/realtime/pipeline.py`), and every
sentence names what still works — the original audio and captions — because that
is the part a listener can act on. Two things deliberately do not go on *this*
event:

- the provider's own sentence. An unset `MT_HTTP_URL` is an operator's finding,
  not something to show a browser, so it goes to the log; the `diagnostic` event
  still carries a truncated copy, which is a leak with its own name. The removed
  `detail` field was the old copy of it on `translation.failed` — clients that
  read it must read `code` and `message` instead.
- a traceback, unless nothing in the failure named itself. `log.exception` is
  reserved for `provider_unavailable`, because a stack trace for a known refusal
  every few seconds is how a real crash gets lost in the noise.

`tests/unit/test_realtime_failure_reasons.py` drives the real stage body with a
refusing engine and asserts the reason, the code and the sentence all match the
failure — including that an unsupported pair still leaves the speaker's original
caption on screen and never claims the pair is merely slow.
Reconnection, participant identity and resume replay are covered by
`tests/integration/test_realtime_reconnect.py`.

### Delivery backpressure

Every frame the room sends to a participant — JSON event, base64 chunk, binary
audio — goes into that connection's bounded queue (`rt_send_queue_size`, default
128) and is written by one writer task per socket. It is not awaited by the
caller any more.

This matters because the caller used to be the meeting's fan-out task, and
`broadcast` wrote to each listener in turn from it: one backgrounded browser tab
stops reading its socket, the TCP window closes, and that single listener holds
up every other listener behind it and the pipeline behind them. A room of eight
was as fast as its worst connection.

The policy when a queue is full is to drop the **oldest** queued frame, because a
live meeting has only one useful direction: the frame a listener would receive
four seconds late describes a turn they have already moved past. Media outruns
captions, so what actually gets dropped is stale audio; the caption that just
arrived is queued behind nothing. Drops are counted per connection
(`gt_ws_send_dropped_total{kind,reason}`), reported in
`GET /meetings/{id}/realtime/health` under `send` (`dropped_audio`, `dropped_events`,
`queued`, `slow`), and set the meeting's `quality_degraded`. A socket that has
not accepted a single frame in `rt_send_timeout_s` (10 s) is treated as dead
rather than slow: the writer stops, and the listener's own reconnect resumes from
the replay buffer.

`tests/unit/test_realtime_send_backpressure.py` pins all of it — that a listener
which never reads cannot delay one that does, that the backlog stays at the
configured bound and keeps the newest frames, that a caption is not dropped to
save a stale audio frame, that events and their binary frames still arrive as an
ordered pair, and that a reconnect does not inherit the dead socket's backlog.

### What leaving a meeting releases

`participant_id` is issued per join and never reused, so everything the meeting
keys by it accumulates once per reconnect unless leaving means something.
Hanging up used to stop the task that read the microphone and nothing else, which
left four things behind for the life of the session: the speaker's translation
context window (their recognised words, in memory, in a room they had left),
their per-speaker sequence ledger, their stale-language marks, and the fan-out of
the turn they abandoned mid-sentence — which went on producing audio for listeners
that nobody had introduced.

`MeetingPipeline.release_participant()` is now called from the socket handler's
`finally` and from the REST leave route, and is idempotent because those two race.
It is synchronous and announces nothing on purpose: it runs inside a task that is
being cancelled, where an `await` can raise before it reaches the room, and
`participant.left` already says who went away. Audio for the departed speaker's
last turn is cancelled rather than flushed — the chunks already handed to a
browser play out, and a flush the client cannot attribute to a live speaker would
cut audio that was legitimately owed.

Two per-turn tables are now bounded rather than merely drained, because a release
path that races a cancellation cannot be counted on to be the thing that empties
them: the supervisor's cancelled-correlation marker is capped at the observation
window (`record_limit`, oldest first) like its segment records, and the detection
record for a turn is taken before the transcript stage decides its outcome, so a
turn whose language could not be resolved no longer keeps the only record of the
detection that failed.

`tests/unit/test_realtime_participant_release.py` and the departure case in
`tests/integration/test_realtime_disconnect.py` pin this: no transcript text, no
ledger entry, no agent dedup state and no abandoned run left alive for a departed
participant, while the speaker who stayed in the room still receives every chunk
of their own turn.

## Pipeline stages (server)

1. **Ingest** 50 ms PCM chunks (16 kHz mono) → EnergyVAD (or Silero) on 30 ms frames.
2. **Segmentation** all four thresholds are settings, not literals (see `.env.example`):
   turn ends after `vad_min_silence_ms` (default 500 ms) of silence, which is also the
   end-of-speech latency; a burst shorter than `vad_min_speech_ms` (250 ms) is a cough,
   not a turn; a speaker who never pauses is force-committed at `vad_max_speech_ms`
   (15 s). `tests/unit/test_vad_cadence.py` measures the latency each setting costs.
   A fifth trigger commits a turn *mid-speech* once it has run
   `vad_phrase_commit_ms` (4 s, `0` disables) and the live caption ends on a clause
   boundary (`. ! ? । ॥ 。` — never a comma): a presenter no longer waits for a
   breath before the first sentence is translated. The committed audio becomes one
   segment and the continuation the next, so `seq` stays monotonic per speaker; the
   trade is one occasional short early segment (an abbreviation ending in a period)
   against fifteen seconds of nothing.
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
  replay of buffered events `> N` (ring buffer `rt_resume_buffer_size`, default 500
  sequenced events per session; finals additionally persisted in DB, so nothing is
  lost beyond the buffer — refetch transcript via REST). `N` must be greater than 0:
  a client that has played nothing has no watermark, and the server treats `0` as
  "there is nothing to catch you up on" rather than replaying the whole session.
- A reconnect over `?token=` resolves back to the **same** `participant_id` the first
  join issued, so the browser's caption attribution and its resume position stay
  meaningful. The superseded socket's cleanup checks that the participant it is
  closing is still the one it opened before releasing anything, which is what keeps
  the departure release from deleting the new socket's speaker loop.
- Preferences persist server-side (DB) and survive reconnects.
- Exponential backoff + jitter client-side (`MeetingSocket`); 4401/4403 are permanent
  (no retry storm).
- Idempotency: events carry `sequence`; clients dedupe by sequence. Replayed history
  arrives after the `session.resumed` marker; live events continue after it.
- `tests/integration/test_realtime_reconnect.py` pins all three: identity across the
  gap, a takeover that leaves the survivor's pipeline running, and a resume whose
  `replayed` count is backed by the actual caption spoken during the disconnect.

## Multi-node note

With Redis configured, the cache adapter's pub/sub carries fan-out across API nodes
(hub interface is backend-agnostic). Session state authoritative in DB; ring buffer per node.
