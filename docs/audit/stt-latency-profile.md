# STT Finalization Latency Profile (G-002 re-measurement)

**Date:** 2026-10-29 · method: `scripts/load_drill_realtime.py` (real weights, real WS audio path —
the ONLY latency-carrying lane in the envelope docs per its own honesty rules)
**Closes the profiling gap the initial report registered as G-002** ("no new profiling artifact
exists"; `docs/LOAD_CAPACITY_ENVELOPE.md` p50 12.2/35.4/51.2 s at C=1/2/4).

## 1. Which lane was actually measured — an ownership note

`scripts/load_drill_realtime.py` boots `globaltalk.main:app` with
`PYTHONPATH=apps/api:.` — i.e. the **legacy lane** (`apps/api/globaltalk/realtime/`), the only
lane carrying the offline full-weight realtime stack (faster-whisper small → Argos → Piper,
cache 1357 MB). The canonical `services/api` realtime pipeline shares the STT/MT/TTS
provider seams (`ai/providers/*`) but with dev providers in compose (dev_text/dev_echo/dev_tone)
and provider-keyed stacks in production. The envelope numbers therefore characterize the
legacy lane's realtime audio pipeline; they are relevant for day-6 pilot recipes and the
golden-call transport, and are the current basis for G-002 until an on-target pilot
re-measurement is produced.

## 2. Controls performed (2026-10-29, this box, 2-utterance C=1 probes)

Two conditions: same box, same day, back-to-back, only the STT thread environment differs.
Raw artifacts (exact drill output) committed under `docs/audit/artifacts/2026-10-29-c1-drill/`.

| Trace (per event) | OMP=1 (`drill-C1-T1.json`) | `GT_STT_CPU_THREADS=8` (`drill-C1-T8.json`) |
| :--- | :--- | :--- |
| **U1 warm** `stt_final_ms` | **17 087** | **9 688** |
| U1 warm `translation_ms` | 945 | 646 |
| U1 warm `tts_first_audio_ms` | 751.9 | 461 |
| U1 warm `total_e2e_latency_ms` | 18 715 | 10 812 |
| **U0 cold** `stt_final_ms` | 15 811 | 13 479 |
| U0 cold `translation_ms` (Argos cold load) | 10 112 | 9 780 |
| U0 cold `tts_first_audio_ms` (Piper cold load) | 4 691 | 9 594 |
| U0 cold `total_e2e_latency_ms` | 34 118 | 32 879 |
| deliverability | 4/4, 0 failures, 0 timeouts | 4/4, 0 failures, 0 timeouts |

(U0 in the earlier capture `drill-baseline-C1.json` additionally failed its two legs into honest
`translation.failed` deliveries — the same cold-utterance anomaly the envelope doc's §4 already
audited on day-6; nothing regressed in handling: failures are recorded, never faked.)

A third probe (`drill-C1-T8-warm.json`, 8 events over 4 utterances) was STARTED CONCURRENTLY with
the Docker Desktop daemon booting, so its medians are contended (stt p95 46.5 s on utterance-1)
and are recorded here ONLY as evidence that the run methodology is load-sensitive — not as
comparable numbers. Its warm tail (utterances 2-3) still independently shows the same shape:
translation 0.65-1.8 s, tts first audio 0.7 s, total 13.0-14.2 s with warmstt 10.8-12.7 s.

### What the controls establish

1. **The single-thread default was the dominant, silent cause of the STT p50.** With
   `cpu_threads=8` the WARM utterance's STT finalization drops 17.09 s → 9.69 s (**1.76×**).
   The load drill's recipe booted with `OMP_NUM_THREADS=1` (deliberately, to avoid
   oversubscription at C>1) — which silently limited the engine to one inference thread.
   `ai/providers/stt/faster_whisper.py::load_model` now accepts `GT_STT_CPU_THREADS` so an
   operator can spend threads per transcription while the pipeline's own serialization still
   bounds simultaneous meetings from multiplying it.
2. **STT remains the convex bottleneck at warm; MT/TTS are NOT the problem block** — warm MT
   (0.65 s) and TTS first-audio (0.46 s) are two orders under STT, matching the envelope doc's
   shape. Any further C=1 latency reduction requires STT-side work (smaller/faster model,
   concurrency-2 worker pool, or GPU), not MT/TTS work.
3. **The first utterance of a fresh server pays ~20+ s of cold weight-loads** (Argos ~10 s +
   Piper ~5-10 s land inside `translation_ms`/`tts_first_audio_ms` of utterance-0). Day-6's
   "12.2 s C=1 e2e p50" mixed these cold events; today's warm-UTTERANCE e2e p50 at
   `GT_STT_CPU_THREADS=8` is **10.8 s** — but only after warm-up. **Recommended next lever
   (owner decision): boot-time model preload** so a pilot's first turn doesn't absorb the
   cold band; trivially reversible with a config flag and boot diagnostics.
## 3. Honest boundaries

- These are THIS dev box numbers under a busy session (Chrome + Docker Desktop showed in
  system pressure), NOT a pilot-hardware benchmark. The absolute stall numbers must be
  re-measured on pilot hardware; the A/B ratio (threads=1 vs 8) is internally controlled.
- The DEADLINE regression risk of raising the STT default is NONE: the default in-config
  `rt_stt_deadline_ms` is unchanged, and this knob changes throughput per utterance, not
  contract deadlines.
- The warm-vs-cold split was extracted from per-event `trace_store` records, not averaged
  away — the medians in §2.2 of the envelope doc mix these populations and can flatter or
  shame depending on mix; per-table breakdown is the honest presentation going forward.
