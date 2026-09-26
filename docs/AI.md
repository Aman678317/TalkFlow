# AI Architecture

## Provider abstraction (section 78)

```
Application (routes/services/realtime)
   → AI abstraction (ai/interfaces.py: STTProvider, StreamingSTTProvider,
      TranslationProvider, TTSProvider, LanguageDetectionProvider, VADProvider,
      LLMProvider, EmbeddingProvider, DocumentParserProvider)
      → provider adapters (ai/providers/**)
         → actual models (faster-whisper, Argos, Piper/Kokoro, langid, Silero, vLLM…)
```

No route, ORM model, service or frontend file imports a concrete model. Adapters report
identity (provider/model/version) so every stored artifact records its provenance.

## Model Router (ai/model_router)

Input: task, source/target language, domain, intent (`quality_optimized`,
`latency_optimized`, `cost_optimized`, `private_only`, `offline_only`, `experimental`),
latency target, hardware, tenant policy (`allow_pivot_translation`), feature flags,
model health. Output: ordered `Route` (primary + fallbacks + reason). `execute()` walks
the chain on `ProviderUnavailable`, logs `route_fallback`, and raises only when every
candidate failed — callers then apply domain-specific final fallbacks (captions-only,
passthrough). Request-level failures never blacklist a provider globally.

## Chains (section 89/109)

- **STT:** (IndicConformer → FunASR →) faster-whisper → whisper.cpp/sherpa (edge) →
  caption/original-audio fallback.
- **MT:** quality model → Argos (offline NMT) → Marian/opus-mt (pair filler, e.g. mr) →
  **passthrough** (returns source flagged `untranslated_fallback` — never invents text).
- **TTS:** Kokoro/Piper → Indic-Parler (Phase 5) → captions-only fallback.
- **LLM:** vLLM (local server) → extractive assistant (deterministic, labeled).

## Capability registry (section 8)

DB-backed `language_capabilities` + `language_pair_validations`, reconciled at startup and
via `POST /languages/refresh` using **lightweight probes** (`available()` — no weight
loading). A language is SUPPORTED only when the provider is healthy *in this deployment*;
PRODUCTION requires a passed evaluation gate + human review. The registry drives UI
selectors, routing filters, and docs — one source of truth.

## Evaluation & quality gates (ai/evaluation, scripts/run_evaluation.py)

Metrics: WER/CER (Levenshtein), corpus BLEU, number/URL preservation, latency p50/p95,
failure rate; COMET as optional adapter. Datasets: greetings, time, finance, legal,
technical, names, Indian locations, currency, dates, URLs, Hinglish code-switching;
audio manifest for clean/noise/accent/code-switch/overlap/fast/slow sets (recordings
supplied by ops into `EVAL_AUDIO_PATH`, never committed). Gate: automatic thresholds →
SUPPORTED; human review → PRODUCTION. Results persisted to `quality_evaluations` and
(optionally) promote `language_pair_validations`. Example sandbox run: en→hi BLEU 82.9
SUPPORTED; Hinglish→en BLEU 0.0 → stays EXPERIMENTAL (honest).

## Memory system (section 23)

Seven classes in `memory_items`: working (current meeting window), semantic (topics/facts),
episodic (meeting summaries), procedural (how-to patterns), retrieval (embedded transcript
lines for grounded Q&A), parametric (model registry metadata), prospective (action items
with expiry). Retrieval is scoped (org/meeting/user) and bounded — the assistant receives
only relevant context (≤24 KB window, top-k retrieval), never the full history.
Feedback-loop prevention: derivatives are never re-ingested as sources.

## Agent bridge (section 22)

`POST /bridge/turn` demonstrates the contract: canonical human text → independent
per-agent-language projections; agent replies become canonical for *their own turn*
(tagged), translated from that turn's source — never from another agent's translation.
LiveKit Agents runtime (services/agents) hosts Speech/Translation/Voice/Timing/
LanguageRouter agents in production; the hub (deterministic infrastructure) owns
sequences, timing, routing and identity. Agents cannot mutate canonical sources.

## Low-memory operation (sandbox profile)

`ai/memory_guard.py`: MemAvailable watchdog + `ensure_headroom(task)` staged eviction
(TTS → MT → STT) + subprocess isolation for MT/TTS on <2 GB machines (`GT_LOW_MEMORY`,
`ARGOS_MAX_CACHED_PAIRS`, `PIPER_MAX_CACHED_VOICES`, `MARIAN_FREE_AFTER_USE`). Warm pools
on production GPU workers make the guard inert. Measured sandbox envelope: whisper-tiny
(144 MB) + one Argos pair (446 MB) + Piper subprocess (peak ~230 MB) rotate within 1 GiB.

## Voice safety (section 41)

Synthetic output always flagged (`synthetic: true` in TTS events + `TTSResult.synthetic`);
voice preservation requires explicit consent rows (`voice_consents`) with grant/revoke
timestamps and audit trail; revoked samples destroyed by the cleanup worker. No anonymous
voice impersonation features exist.
