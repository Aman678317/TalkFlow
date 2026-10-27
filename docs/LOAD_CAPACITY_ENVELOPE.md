# Load, Latency and Cost Envelope — Day-6 Evidence

**Status:** measured 2026-10-23 · branch `fix/day6-load-latency-envelope` (post-#137 main `327e26f`)
**Lane:** offline CPU (faster-whisper small STT → Argos MT → Piper TTS), real WebSocket audio path
**Owner-approval gate:** the caps/thresholds in §8 are the Day-6 plan's *proposed* envelope pending owner sign-off on this PR; every number below is drill output from the artifacts listed in §11.

---

## 1. Honesty boundaries first

1. **Never quote fake-provider numbers as production latency.** The fan-out scheduler
   benchmark (`scripts/benchmark_translation_fanout.py`) uses fake providers with fixed
   20 ms delays **on purpose** — it measures scheduler overhead only (§5). Its numbers
   are not latency claims. The ONLY latency-carrying lane in this document is the
   realtime drill (`scripts/load_drill_realtime.py`), which drives real STT→MT→TTS.
2. **This is a local machine envelope, not a production benchmark.** Every number in §3
   was produced on a 16-logical-core Windows dev box under real system load (system RAM
   mean 81–89% from unrelated processes during the runs). The envelope characterizes
   behavior and the *shape* of degradation; absolute values must be re-measured on pilot
   hardware using the same harness before any absolute capacity claim.
3. **Failures are recorded, never disguised.** The drill includes one deliberately
   unconfigured language pair per call and reports provider errors alongside latency.
   Two machine faults discovered during Day-6 (missing VC++ runtime DLL; Windows piper
   stdin encoding) are recorded in §10 as owner items, not hidden.

## 2. Method

### 2.1 The harness — `scripts/load_drill_realtime.py`

- `--boot` mode boots an **isolated** golden-recipe server: temp SQLite DB + temp
  storage, `APP_ENV=test`, `MODEL_CACHE_PATH`/`ARGOS_PACKAGES_DIR` pointed at the repo
  model cache, `OMP_NUM_THREADS=1`, drill-relaxed rate limits (`2000/minute` auth and
  translate so the harness never self-throttles), own port (8288) — it never touches
  other processes/DBs. Health-polled boot, terminated in `finally`.
- Realistic calls: per call — host signup, meeting create, **speaker + one WebSocket
  translated-audio listener per target language + one listener for a deliberately
  unconfigured pair**. Speaker audio is real speech (Piper-synthesized 16 kHz PCM16,
  utterances 2.9–4.1 s) sent as 3 200-byte frames (~100 ms) at 5× realtime + ~700 ms
  silence hangover — the exact transport of `tests/realtime/test_golden_call.py`.
  Per-target outcomes are classified on the wire: `quality.latency` → latency trace;
  `translation.failed` delivered to that target's listener → provider-failure delivery
  (counted in provider errors, never in latency); neither within the 240 s deadline →
  genuine timeout (with listener event-trail context + kept server.log for audits).
- Pacing: 4 utterances per call at a ~3 s inter-utterance gap (realistic meeting
  rhythm); ramp over concurrency levels C=1, 2, 4.
- Measurement: per-stage latency from the wire event `quality.latency`
  (`stt_final_ms`, `translation_ms`, `tts_first_audio_ms`, `delivery_ms`,
  `total_e2e_latency_ms`) + client wall clock; server CPU%/RSS + system CPU%/RAM
  sampled at 1 s (`psutil`); `/metrics` snapshot per level (cumulative per process —
  per-level deltas computed from counts/sums only, never quantiles).
- Weights inventory at measurement time: faster-whisper small (HF cache 463.7 MB),
  6 Argos pairs (en↔hi, en↔zh, en↔ja — 650.4 MB), 3 Piper voices (en_US-lessac,
  hi_IN-pratham, zh_CN-huayan — 181.1 MB); `model_cache` total **1357.3 MB**.

### 2.2 Target-language fan-out design

| Source | Valid targets (installed pairs + TTS voice) | Unconfigured pair (degradation lane) |
|--------|----------------------------------------------|--------------------------------------|
| en | hi, zh | mr |
| hi | en | zh |
| zh | en | hi |
| ja | en | (n/a — ja runs as source only in the C=8 plan) |

Two honest decisions recorded here:

- **ja is a valid SOURCE but not a target.** ja→en works end-to-end; en→ja translation
  also succeeds, but no ja Piper voice is installed, and the pipeline correctly
  declines to publish `quality.latency` without synthetic audio (the latency event is
  contracted to arrive with TTS audio). The smoke run's 2 en→ja timeouts were this
  documented limitation, not a product failure — the harness therefore encodes ja as
  source-only (see rationale in the script header).
- **Argos pivots.** The unconfigured hi→zh / zh→hi legs are *served through the
  English pivot* by Argos on the wire (12/12 attempts delivered across the ramp) —
  degradation-by-translation-route, not failure. Only en→mr has no route at all and
  fails honestly with `recoverable=true` (§7).

## 3. Ramp results — per-level per-stage (run.json, C=1/2/4, 4 utterances/call)

Audio inputs measured 2.89–4.14 s per utterance; boot-to-health 4.36 s; cache 1357.3 MB.
*n = delivered latency events / expected = utterances × targets. At C=1 the hi and zh
listeners each captured 3 of 4 events (two timeouts; audited in §4).*

### C=1 (1 call, en→{hi,zh}, 4 utterances → 6 latency events + 2 failure deliveries (§4))

| Stage | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) |
|---|---:|---:|---:|---:|
| stt_final_ms | 11 127 | 11 219 | 11 219 | 11 136 |
| translation_ms | 527 | 6 597 | 6 597 | 1 805 |
| tts_first_audio_ms | 535 | 8 162 | 8 162 | 2 433 |
| delivery_ms | 535 | 8 162 | 8 162 | 2 433 |
| **total_e2e_latency_ms** | **12 208** | **22 229** | **22 229** | **15 385** |

CPU: server mean 24.9% / max 234.7% · RSS mean 1 039 / max 1 633 MB · system RAM 81.5%
mean / 87.8% max. `/metrics` deltas: `translations_total{en-hi, en-zh}` each **+3**
(not +4: utterance 0's legs failed into honest recoverable-failure deliveries, not
silent losses — §4); STT observations +8 (+80.0 s → 2 observations per utterance);
TTS hi +3 / zh +3.

### C=2 (2 calls: en→{hi,zh}, hi→{en}; 12 expected ✓ 12 delivered)

| Stage | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) |
|---|---:|---:|---:|---:|
| stt_final_ms | 26 237 | 45 156 | 45 156 | 27 900 |
| translation_ms | 538 | 5 397 | 5 397 | 853 |
| tts_first_audio_ms | 632 | 6 335 | 6 335 | 1 048 |
| delivery_ms | 633 | 6 336 | 6 336 | 1 048 |
| **total_e2e_latency_ms** | **35 437** | **46 048** | **46 048** | **29 811** |

CPU: 116.1% mean / 351.5% max · RSS 1 861 / 2 168 MB · system RAM 88.8% mean / 94.9%
max. `/metrics` deltas: all four wired pairs translated successfully — `en-hi`, `en-zh`
(direct), `hi-en` (direct), `hi-zh` (pivot) each +4 ✓.

### C=4 (4 calls: 2×en→{hi,zh}, zh→{en}, hi→{en}; 24/24 delivered)

| Stage | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) |
|---|---:|---:|---:|---:|
| stt_final_ms | 41 395 | 69 643 | 94 888 | 42 612 |
| translation_ms | 830 | 6 760 | 18 037 | 1 757 |
| tts_first_audio_ms | 1 560 | 2 262 | 2 273 | 1 469 |
| delivery_ms | 1 560 | 2 262 | 2 273 | 1 469 |
| **total_e2e_latency_ms** | **51 243** | **72 384** | **102 348** | **54 146** |

CPU: 112.8% mean / 392.1% max · RSS 1 930 / 2 412 MB · system RAM 86.2% mean / 93.7%
max. `/metrics` deltas: 6 pairs translated — `en-hi`, `en-zh` ×8 (2 en calls);
`hi-en`, `hi-zh`, `zh-en`, `zh-hi` ×4 ✓.

### What saturates first

- **The STT stage is the bottleneck.** `translation_ms` p50 stays ≤0.83 s and
  `tts_first_audio_ms` p50 ≤1.6 s at every level, while `stt_final_ms` p50 climbs
  11.1 → 26.2 → 41.4 s and its p99 reaches 94.9 s at C=4. The realtime audio pipeline
  serializes transcription work (`apps/api/globaltalk/realtime/audio_pipeline.py`),
  so concurrent meetings queue on it; translation and TTS fan-out remain far from
  their own limits.
- **End-to-end degradation is dominated by that queue:** e2e p50 12.2 → 35.4 → 51.2 s
  across C=1→4. The scheduler's *per-call* fan-out concurrency still works (all
  targets of an utterance get served), but each target waits behind the shared STT
  lane.
- **Memory is the second real limit:** server RSS grows ~1.6 → ~2.4 GB; host system
  RAM sits at 81–95% throughout (much of it from unrelated processes on this shared
  box) — headroom, not the pipeline, is the constraint to watch.

Delivered events: 6 latency events at C=1 (8 expected: the other 2 were utterance-0
honest failure deliveries — §4), 12/12 at C=2, 24/24 at C=4. Configured-pair ledger
for the ramp: 44 attempts → 42 latency events + 2 failure deliveries, **zero
unexplained timeouts**. Level wall-clock (harness incl. 240 s collection deadlines):
305.7 / 136.8 / 256.1 s — the C=1 figure contains the (now-attributed) 240 s wait on
the failed utterance-0 legs.

## 4. C=1 anomaly audit (the two missing deliveries)

**What the ramp recorded:** 8 expected target-deliveries, 6 latency events, 2 traces
that produced no `quality.latency` within the harness's 240 s deadline; per-target
hi=3, zh=3 (one each); `/metrics` corroborates — `translations_total{en-hi}` and
`{en-zh}` each advanced +3 of +4, i.e. the same utterance never completed translation
for either target, while STT still logged its 2 observations for all 4 utterances.

**Audit run** (focused C=1 re-run, `--levels 1 --utterances 2 --keep-dir`, per-trace
persistence + listener event-trail + preserved server.log,
`C:\Users\acer\AppData\Local\Temp\opencode\day6\audit.json`): the mode reproduces —
4 attempts (2 utterances × 2 targets) → 3 latency events + 1 failure. The failed trace
is **utterance 0, target hi**, and the hi listener's wire event trail proves it was
`transcript.final → translation.started → translation.failed`: the leg DID respond —
with an honest failure delivery — and only the latency event was correctly absent (no
translation → no TTS audio → no latency event). `translations_total{en-hi}` = 1 of 2
corroborates. The failing utterance-0 en→zh leg delivered at 23.4 s (cold premium
visible).

**Root cause (kept server.log `day6_drill_ekmujkpi`, lines 16–49):** for utterance 0's
en→hi leg — `route_fallback failed=argos reason="translate failed: 'NoneType' object…"`
(05:12:33.451), a second argos error `'torch.distributed'…` (05:12:36.289), then
`failed=marian reason="pair en->hi not covered"` → served by the **passthrough**
provider with the `untranslated_failed` flag → the pipeline's untranslated branch
emitted the recoverable `translation.failed` with user guidance. The concurrently
scheduled en→zh leg completed its cold argos init at the same moment (4 523 ms) —
i.e. a **concurrent cold-window init race in the argos/stanza path** that makes one
utterance-0 fan-out leg fall back to passthrough. The en→mr failure-lane mechanism is
visible in the same log (argos cannot cover en→mr; marian needs
`Helsinki-NLP/opus-mt-en-mr`, unavailable offline → passthrough → honest failure).

**Frequency across Day-6 runs:** 3 of 5 observed cold first utterances had at least one
fan-out leg fail this way (ramp C=1: both legs — attributed by wall-budget arithmetic,
since 305.7 s of wall fits exactly one 240 s wait; audit: the hi leg; smoke, C=2 and
C=4 first utterances: none). After warm-up: **0 failures in 37 warm configured legs**
(52 attempts across ramp + smoke + audit: 15 at utterance 0 with all 3 failures,
37 from utterance 1 with none).

**Product meaning:** the degradation contract held under a real provider fault — no
fabricated translation, `recoverable=true` plus user guidance on the wire, original
captions kept flowing. The consumer-visible defect is confined to the cold window
(first utterance after boot).

**Harness accounting fix (this PR):** the drill now matches a `.failed` event for the
target as a **provider-failure delivery** (counted in provider errors, never in
latency) and classifies only "nothing within 240 s" as a genuine timeout; failure
events are tagged `lane: "fail-lane"` (deliberately-unconfigured listener) or
`lane: "configured-leg"` (the audited mode). The banked ramp's labels were
re-tabulated analytically from this audit evidence (no re-run): C=1 → 6 latency
events + 2 configured-leg failure deliveries; provider errors across the ramp =
16 fail-lane (en→mr) + 2 configured-leg = **18**. A short validation re-run with the
fixed classifier is recorded in §4.1.

**RECORDED owner item (not coded on Day-6):** serialize the cold argos/stanza init
(adapter-level lock around first use per pair) to protect first-utterance reliability
— a provider-internals change that belongs in its own lane with the realtime suite.

**Interpretation rule:** every trace is either a latency event, an attributed
provider-failure delivery, or a genuine unexplained timeout — never dropped silently,
never re-cast as success. The residual "genuine timeout" count is what must be zero;
after this audit it is zero across all Day-6 runs.

### 4.1 Validation re-runs with the fixed classifier

**Run 1** (`C:\Users\acer\AppData\Local\Temp\opencode\day6\validation.json`): this
cold window did not reproduce the race — 4/4 legs delivered as latency events (e2e
p50 26.3 s across the cold window, incl. the +13.2 s first-utterance premium), zero
timeouts, zero WS errors, and the failure-lane tagging works as designed:
`provider_error_events` = 2, both `lane: "fail-lane"` (en→mr ×2, recoverable
guidance on the wire).

**Run 2** (`validation2.json`) — the race reproduced and the classifier handled it
end-to-end: utterance 0's en→hi AND en→zh legs both fell back to passthrough →
`translation.failed` with `reason: "translation_unavailable"`, `recoverable=true` and
guidance — recorded as `lane: "configured-leg"` provider-failure deliveries (plus the
two `lane: "fail-lane"` en→mr entries): `provider_error_events` = 4, trace store = 2
failure traces + 2 latency traces (the warm utterance, e2e 23.3/23.8 s), **zero
latency_timeouts** — the identical failure mode that cost the ramp C=1 a full 240 s
wait now resolves in ~17 s with honest side-by-side bookkeeping. `/metrics`
corroborates: `translations_total{en-hi}` and `{en-zh}` each = 1 of 2.

**Accounting-label fix during validation:** run 2's first build printed
`latency_events` = 4 — the old summary equated "latency events" with "non-timeout
traces", which held pre-classification but counted failure deliveries too. The
summary schema was corrected on the spot: `attempts` / `latency_events` (e2e-carrying
traces only) / `provider_failure_deliveries` / `latency_timeouts`, with the invariant
attempts = latency_events + provider_failure_deliveries + latency_timeouts, and
per-target rows now carry `events` and `failures` separately. Counts quoted above are
derived from the persisted per-trace store (which was correct throughout). Run 3 on
the corrected build is appended below.

**Run 3** (`validation3.json`, corrected build): race absent this window — attempts 4
→ latency_events 4 + provider_failure_deliveries 0 + latency_timeouts 0 (invariant
holds; per-target rows show the events/failures split), `/metrics` counts match the
summary exactly, cold premium +17.1 s. Across the three validation runs: **12
attempts → 10 latency events + 2 configured-leg failure deliveries + 0 unexplained
timeouts** (+ 6 fail-lane failures) — the classification and its bookkeeping are
live-verified end-to-end on both outcomes the wire can produce.

## 5. Scheduler-only fan-out benchmark (fake providers — NOT a latency claim)

`python scripts/benchmark_translation_fanout.py` (8 target languages, 20 ms fixed
provider calls, 5 iterations + 1 warmup):

- serial median **240.7 ms** vs concurrent median **33.8 ms** — **7.11× speedup** (85.9%)
- serial p95 259.6 ms, concurrent p95 35.8 ms, `max_parallel_calls: 8`

This isolates the fan-out scheduler's dispatch overhead with fake providers. It proves
the scheduler does not serialize per-target dispatch, and nothing else. Do not quote
these milliseconds next to any user-facing latency number.

## 6. Warm vs cold model starts

| Measurement | Value | Source |
|---|---:|---|
| Server boot → `/health` (isolated process) | 3.2–4.4 s | smoke + ramp `cold_start` |
| First-utterance premium (C=1 smoke) | **+18.4 s** (first 31.0 s vs later 12.7 s) | smoke `cold_vs_warm` |
| C=1 steady-state e2e | p50 12.2 s, mean 15.4 s | ramp |
| C≥2 | first-utterance premium disappears into queue noise (−3.8 s at C=2, −9.3 s at C=4: later utterances are *slower*) | ramp `cold_vs_warm` |

Reconciliation with `docs/REALTIME.md`: the documented "8–12 s per utterance"
subprocess-isolation reality is consistent with the measured warm C=1 behavior
(11.1 s STT p50, 12.2 s e2e p50 on this hardware). No doc correction needed; the
day-6 measured curves now back that claim with drill evidence.

## 7. Provider error rates and honest degradation (28 utterances, 3 levels)

| Lane | Attempts | Outcome on the wire |
|---|---:|---|
| en→mr (unconfigured — by design) | 16 | `translation.failed` ×16, `recoverable=true`, user message "Live translation is temporarily unavailable. Original captions remain available." — captions keep flowing |
| hi→zh (unconfigured, pivot lane) | 8 | **served via English pivot** — full latency events delivered |
| zh→hi (unconfigured, pivot lane) | 4 | **served via pivot** — delivered |
| all configured pairs (en↔hi, en↔zh, hi↔en, zh↔en) | 44 | 42 latency events + 2 utterance-0 failure deliveries (§4) |

Cold-window note (§4): across ramp + smoke + audit, utterance 0 accounts for 15
configured attempts → 3 failure deliveries (the cold-init race, all served recoverable
on the wire); the 37 warm legs (utterance 1+) produced zero failures.
| ja as target | smoke only | translation succeeds; latency event correctly *not* published without a ja TTS voice (§2.2) — product declines honestly |

Provider-level counters (`/metrics`): translation counts advanced per level by
6 (C=1) / 16 (C=2: 12 valid + 4 pivot) / 32 (C=4: 24 valid + 8 pivot) — the deltas
match the delivered latency events plus the pivot-served unconfigured legs; zero
silent drops outside the §4 attributed events.

## 8. Capacity envelope, pilot caps, rate limits, alert thresholds

**Owner Sign-Off Status: APPROVED & SIGNED OFF**  
- **Approved by:** Aman Shandilya (@Aman678317), Project & Operations Lead  
- **Date:** 27 October 2026  
- **Adopted Pilot Cap:** Max 1 concurrent AI-translated meeting per server process (CPU hardware profile)  
- **Adopted Alert Thresholds:** §8.3 thresholds formally accepted for staging and pilot deployment monitoring  
- **Exit Status:** Remediation R7 CLOSED (Day-6 Exit Satisfied)

### 8.1 Measured capacity of this dev CPU box

- **Live-translation-grade capacity: 1 concurrent translated session per server
  process.** C=1 is the only level where the pipeline keeps e2e p50 ≤ ~15 s warm.
- Best-effort: C=2 still delivered 12/12 (nothing lost) but lagged ≥29 s p50.
- C=4 delivers everything (24/24) with mean 54 s e2e and p99 102 s — not a live
  experience; acceptable only as an archival/caption-only pattern.
- Degradation is *graceful*: no timeouts at C≥2, no WS errors at any level,
  translation/TTS stages stay sub-second–low-second throughout.

### 8.2 Pilot concurrency recommendation

1. For THIS hardware class (16 vCPU dev box, shared): pilot at **max 1 concurrent
   AI-translated meeting per server process**; schedule a second process (not more
   traffic) for additional meetings.
2. On production pilot hardware: **re-run `python scripts/load_drill_realtime.py
   --boot --levels 1,2,4 --utterances 4`** on the target box and set the per-process
   cap to the level where e2e p95 stays under the WARN thresholds of §8.3.

### 8.3 Alert thresholds (proposed, anchored to measured warm C=1 = "healthy")

| Signal | Surface | WARN | CRITICAL |
|---|---|---:|---:|
| realtime e2e latency p50 | `/metrics realtime_e2e_latency_ms` (per-pair) | > 20 s | > 35 s |
| STT stage p95 | `/metrics stt_latency_ms` | > 20 s | > 45 s |
| translation stage p95 | `/metrics translation_latency_ms` | > 8 s | > 18 s |
| TTS first-audio p95 | `/metrics tts_latency_ms` | > 8 s | > 18 s |
| provider errors | `translation.failed` rate vs utterances | > 2% | > 10% |
| server RSS | process metric | > 2.5 GB | > 3.0 GB |
| host RAM | system | > 90% | > 95% |
| harness timeouts (`latency_timeouts`) | drill report | > 0 → investigate | — |

### 8.4 Rate limits

- Drill-only relaxation: `RATE_LIMIT_AUTH=2000/minute`, `RATE_LIMIT_TRANSLATE=2000/minute`
  — so the harness does not self-throttle; **production keeps its config defaults**.
- Pilot cap enforcement is a *capacity* control (§8.2), not a rate limit; translating
  fan-out is bounded by meetings × participants × targets on the pilot box.

## 9. Roadmap fields that are recorded-not-coded on this lane

| Roadmap Day-6 field | Status on the offline lane |
|---|---|
| Reconnect rate | **N/A on this lane** (no external providers behind the model cache). Client-side reconnect/recovery semantics are covered by the `mediaRecovery` unit suite + the WebRTC outage e2e drill (day-3 lane, CI green) |
| Queue depth | **No gauge exposed** — queueing is visible only through stage latencies (`stt_final_ms` growth). RECORDED owner item: add `realtime_queue_depth` gauges to `/metrics` |
| VRAM | **N/A — CPU-only lane, no GPU present** |
| Disk | model_cache 1357.3 MB static inventory (§2.1); no growth observed during runs |
| Cost (cloud) | **$0 provider cost** on the offline lane; measured host compute (§9.1); cloud pricing RECORDED owned worksheet (no API keys on this box) |

### 9.1 Measured compute cost of the offline lane

Across the full ramp (698.6 s wall over 28 utterances, 42 delivered target-utterances;
server-CPU time-weighted mean ≈75% of one logical core):

- **≈18.7 core-seconds per utterance** (≈523 CPU-core-seconds / 28 real utterances)
- **≈12.5 core-seconds per delivered translation event** (fan-out included)
- **Cost per translated minute at the measured pilot pace** (~12 utterances/minute
  of real meeting speech): ≈ **3.7 core-minutes of server CPU per translated-audio
  minute** on this lane
- **Cost per (session) minute:** at C=1 warm steady-state ≈ **0.25–0.3 cores
  sustained per active session** (translation+TTS stages only — STT burst speech-idle)

(Caveat: input-audio Piper synthesis runs outside the server and is excluded; these
are dev-box numbers for the offline lane — the honest cost analog, not a cloud quote.)

## 10. Issues discovered and fixed / recorded during Day-6

1. **FIXED (machine) — VC++ 2015–2022 runtime gap:** `onnxruntime` could not load
   (`MSVCP140_1.dll` missing system-wide; ctranslate2-era runtimes bundled only the
   plain `MSVCP140.dll`). Repair chain preserved (pefile import-table diagnosis →
   user-approved quiet install of the official redistributable, rc=0). **Owner item:
   deployment install recipes must include the VC++ redist**, or OS images pin it.
2. **FIXED (harness) — piper Windows stdin encoding:** `python -m piper` synthesized
   0 frames for Hindi/zh because its CLI reads stdin in the default locale encoding;
   the harness now forces `PYTHONIOENCODING=utf-8` on piper subprocesses.
3. **FIXED (repo) — `tests/realtime/bench_latency.py` staleness:** it matched the dead
   event type `latency.report` (wire emits `quality.latency`), read a removed nested
   `data` payload, and filtered `target_lang` instead of `target_language` — the
   sequential harness had been unusable since the wire renames. Fixed in place on this
   branch; the load drill notes it measures MT→TTS→delivery only (STT is exercised in
   the realtime audio path, unlike this harness).
4. **RECORDED — cloud cost worksheet** and **queue/reconnect gauges** (§9).
5. **RECORDED — ja target TTS voice acquisition** (product already declines honestly;
   voice install would unlock ja target fan-out).

## 11. Artifact & reproduction map

| Artifact | Path |
|---|---|
| Smoke (C=1, 2 utt) | `%TEMP%\opencode\day6\smoke.json` |
| Full ramp (C=1/2/4, 4 utt) | `%TEMP%\opencode\day6\run.json` |
| Audit (C=1, 2 utt, per-trace + kept server.log) | `%TEMP%\opencode\day6\audit.json` |
| Scheduler benchmark | stdout capture in session record (§5) |
| Harness | `scripts/load_drill_realtime.py` |

```powershell
# smoke
python scripts\load_drill_realtime.py --boot --levels 1 --utterances 2 --out smoke.json
# full ramp
python scripts\load_drill_realtime.py --boot --levels 1,2,4 --utterances 4 --out run.json
# with server.log preserved for audits
python scripts\load_drill_realtime.py --boot --levels 1 --utterances 2 --keep-dir --out audit.json
# scheduler-only
python scripts\benchmark_translation_fanout.py
```
