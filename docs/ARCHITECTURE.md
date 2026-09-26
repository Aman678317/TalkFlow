# GlobalTalk AI — Architecture

## 1. The Canonical Source Rule

The **human voice or human text is the only semantic source of truth**. Everything else —
transcripts of that audio, translations, TTS audio, summaries, agent outputs — is a
*derivative artifact* carrying `source_segment_id`. Two hard invariants:

1. **No translation chains.** Hindi → {English, Japanese, Marathi} independently.
   A translation never becomes the input of another translation. (Engine-internal pivots,
   e.g. Argos hi→en→mr, are flagged `pivoted_via_intermediate` and policy-gated —
   the *canonical source* remains the human segment.)
2. **No feedback loops.** TTS audio is never re-transcribed as a new source; AI summaries
   never become canonical; translated agent output never becomes a human source.

Enforcement points: `TranscriptSegment` is immutable once `is_final` (no UPDATE path to
text/language exists in the codebase); `TranslationSegment.source_kind ∈
{transcript, chat, document}` always references the human original; the assistant reads
only `stable_transcript_text()`.

## 2. Planes

```
┌────────────────────────── CONTROL PLANE ──────────────────────────┐
│ auth · orgs/tenancy · RBAC · billing/metering · language capability│
│ registry · model registry · glossaries · TM · style · API keys ·   │
│ feature flags · audit · admin · webhooks                           │
└────────────────────────────────────────────────────────────────────┘
┌─────────────────────────── DATA PLANE ────────────────────────────┐
│ LiveKit/WebRTC or WS audio · VAD · streaming STT · canonical       │
│ segments · translation fan-out (dedup) · TTS · listener router ·   │
│ captions · chat · transcript store · document pipeline             │
└────────────────────────────────────────────────────────────────────┘
┌────────────────────── AI INFERENCE PLANE ─────────────────────────┐
│ Model Router → provider adapters (STT/MT/TTS/LID/VAD/LLM/Embed)    │
│ warm pools · GPU workers · queues · fallback chains · eval gates   │
└────────────────────────────────────────────────────────────────────┘
```

The API server never runs heavy inference inline in production: jobs flow through
Redis queues to workers; on small deployments an in-process queue + MemoryGuard
(subprocess isolation, staged eviction) keeps everything within RAM.

## 3. Realtime conversation flow (section 9 of the spec)

```
Human microphone
      │  PCM16 mono 16 kHz (AudioWorklet)
      ▼
WebRTC/LiveKit (prod)  │  WebSocket binary (dev/edge)
      ▼
AudioPipeline (per speaker)
  noise gate → VAD (energy│silero) → speech segmentation (hangover 700 ms)
      │                     └─ original-audio relay → listeners (client mixes per audio_mode)
      ▼
Streaming STT (faster-whisper; partials every 0.8–2.5 s per latency_mode)
      ▼
Language ID (whisper LID on audio; langid+script fusion on text)
      ▼
CANONICAL SOURCE SEGMENT  ── persist (immutable) ──► transcript_segments
      │
      ▼
Translation Router ── same-target dedup: (segment_id, target_lang) generated once
      ├──► en ─► TTS ─►┐
      ├──► hi ─► TTS ─►├──► Listener Router ── per participant:
      ├──► ja ─► TTS ─►┘      audio_mode (original│translated│mixed)
      └──► mr ─► (no MT?) ─► translation.failed + original captions (honest degrade)
```

## 4. Repository layout

```
globaltalk-ai/
  apps/api          FastAPI control+data plane (globaltalk.*)
  apps/web          React+Vite+TS SPA
  ai/               provider interfaces, adapters, model router, evaluation, memory guard
  services/         realtime (livekit adapter), agents runtime, domain service shells
  workers/          standalone queue workers (python -m globaltalk.workers.run)
  infrastructure/   docker (compose topology, nginx, prometheus), kubernetes
  scripts/          bootstrap, model downloads (sh+ps1), verify-ai-stack, evaluation
  tests/            unit · integration · realtime (golden call) · e2e
  docs/             architecture, api, database, ai, realtime, documents, security,
                    deployment, local development, testing, troubleshooting
```

## 5. Multi-tenancy & isolation

Shared schema with `org_id` on every business table; UUID PKs. Enforcement layers:
(1) `Principal` resolved from JWT/API key at the edge; (2) `ensure_org_member` /
`require_permission` at service boundaries; (3) every query filters by `org_id`
(tenant isolation test proves cross-org reads 404); (4) audit trail on mutating actions.
Vector stores are tenant-scoped by construction (`MemoryItem.org_id`, TM lookups filter org).

## 6. Failure & degradation philosophy

Every AI stage has a fallback chain ending in **honest degradation** — never fabrication:

- STT down → no transcript, meeting audio continues (original relay).
- MT down → `translation.failed` event + user message; original captions remain.
- TTS down → translated captions only (`quality.degraded`, recoverable=true).
- Redis down → in-process cache/queue (single-node semantics).
- LiveKit unset → WebSocket PCM transport (same protocol events).
- Memory pressure → MemoryGuard evicts TTS→MT→STT weights; subprocess isolation
  returns memory to the OS; the control plane never dies.

## 7. Scaling

- API pods: HPA on CPU; stateless except WS sessions (pin via ingress; Redis pub/sub for
  multi-node fan-out — hub interface already routes through the cache adapter).
- Workers: document/webhook/cleanup/metering scale on queue depth.
- Inference: GPU node pool (`globaltalk.ai/gpu=true`), warm model pools, batching,
  autoscale on GPU utilization; STT/MT/TTS are separate task queues with priorities
  (realtime > documents > batch).
- Media: LiveKit SFU cluster; TURN for restrictive networks.

## 8. Key design decisions (trade-offs)

| Decision | Why |
|---|---|
| SQLite dev / Postgres prod, same models | Zero-dependency local dev; GUID(36)+JSON types behave identically; Alembic migration is the source of truth in prod |
| WS PCM transport alongside LiveKit | LiveKit needs a server binary (Docker); the WS path exercises the *same* hub/pipeline/routing code so realtime logic is testable anywhere |
| Provider adapters + Model Router | No model name leaks into business logic; swap faster-whisper→IndicConformer by registry/config |
| Passthrough as final MT fallback | Returns SOURCE text flagged `untranslated_fallback`; UI shows original + explicit notice — fake translations are forbidden |
| Extractive assistant fallback | Deterministic summarization/action-item extraction when no LLM configured; outputs labeled `method: extractive` |
| MemoryGuard + subprocess inference | Makes a 1 GB-RAM machine run the full realtime pipeline; on big machines it never triggers (warm pools) |
