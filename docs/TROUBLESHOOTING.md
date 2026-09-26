# Troubleshooting

**Server won't start: `unable to open database file`**
SQLite path resolves against the repo root — ensure `data/` is writable and you deleted
stale `data/*.db-wal/-shm` files together with the `.db` when resetting.

**Everything translates to the same text (`untranslated_fallback` flag)**
No MT provider is healthy: run `make verify-ai-stack`. Fix: `bash scripts/download_models.sh`
(Argos packages download into `MODEL_CACHE_PATH/argos`). Check `/internal/components`.

**A language is missing from UI selectors**
The registry only lists what THIS deployment validated. Install models, then
`POST /api/v1/languages/refresh` (or restart — startup probe reconciles). Marathi MT is
NOT_CONFIGURED in the CPU sandbox (no Argos package; enable Marian with ≥2 GB RAM:
`GT_ENABLE_MARIAN=true` + torch/transformers installed).

**Process killed / OOM (exit 137)**
1 GiB machines must stay in low-memory mode (`GT_LOW_MEMORY=auto` default): MT/TTS run in
subprocesses, MemoryGuard evicts staged. If you disabled it, re-enable, reduce
`ARGOS_MAX_CACHED_PAIRS=1`, use `faster-whisper-tiny`.

**Realtime latency is ~8–12 s per utterance in sandbox**
Expected on 1 GiB/2-core CPU (subprocess model reloads dominate). Check the
`quality.latency` event breakdown. Production profile (GPU + warm pools) targets 1.5–2.5 s.

**No translated audio but captions work**
TTS for that language isn't installed (see `speech_output_supported` in `/api/v1/languages`).
Japanese TTS needs `pyopenjtalk` (source build); Marathi has no open voice yet — the UI
shows "captions" next to those languages and emits `quality.degraded` (recoverable).

**WebSocket closes immediately (4401/4404/4408)**
4401: bad/expired JWT or join_token. 4404: meeting id wrong. 4408: client didn't send
`session.join` within 15 s. Guest links use `?join=<token>` from Meetings → Copy invite.

**Reconnect duplicates messages?**
It shouldn't: events carry monotonic `sequence`; resume replays only `> last_sequence`.
If you see duplicates, verify the client tracks `max(sequence)` (see `MeetingSocket`).

**Document stuck in `translating`**
Worker died or queue backed up: check worker logs (`queue_job_failed`), then
`POST /documents/{id}/retry`. Large PDFs segment thousands of blocks — progress is in
`GET /documents/{id}/status`.

**`disk I/O error` on SQLite**
WAL files from a killed process — stop the server, delete `data/*.db*`, restart (dev only).

**Argos warns `expects mwt, which has been added`**
Benign: sentence-boundary metadata note.

**Kokoro download 401**
The HF repo is gated from some networks — Kokoro stays OPTIONAL; Piper is the primary TTS.

**LiveKit NOT_CONFIGURED**
Expected without LIVEKIT_* env; the platform runs the WebSocket transport. For prod,
set LIVEKIT_URL/API_KEY/API_SECRET and start the livekit service (compose file included).
