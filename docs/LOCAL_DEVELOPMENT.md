# Local Development

Requirements: Python 3.11+, Node 20+. Docker optional. ~2 GB disk for models (CPU profile).

## Quick start

```bash
git clone <repo> && cd globaltalk-ai
make bootstrap        # toolchain check, deps, .env, DB init+seed, model weights, verify
make dev              # API :8000 + Web :5173 (Vite proxies /api and /ws)
```

Open http://localhost:5173 — sign up, or use the seeded dev account
`admin@globaltalk.dev` / `Demo1234!` (platform admin, org "GlobalTalk Demo", seeded glossary).

## The golden demo (3+ browser tabs)

1. Meetings → New meeting → you land in the room (tab 1 = Aarav).
2. Copy invite → open in tab 2 (Beth), tab 3 (Chen). Different display names per tab.
3. Set per tab: **I speak** / **I want to hear** / audio mode.
   Sandbox-validated combos: hi↔en (voice+captions), en↔es/zh (voice), en/ja→hi…
   (see /admin component health for what's installed).
4. Click the mic, speak. Watch: partial captions → final original caption → translated
   caption → translated audio (per listener) → `quality.latency` breakdown.
5. Chat in any language — readers see originals + their language beneath.
6. Kill/reload a tab — it resumes (`session.resumed`) with replayed events.
7. After the meeting: Transcript tab (canonical + derivatives, export CSV), Summary tab
   (AI assistant on the stable transcript).

## Useful commands

```bash
make test                  # unit + integration + realtime golden call
make verify-ai-stack       # honest component report
python scripts/run_evaluation.py --promote   # eval datasets + pair promotion
cd apps/api && alembic upgrade head          # migrations (prod-style)
MODEL_PROFILE=INDIC bash scripts/download_models.sh   # more Argos Indic pairs
```

## Environment knobs that matter locally

- `GT_LOW_MEMORY=auto|true|false` — subprocess-isolated inference on small machines.
- `ARGOS_MAX_CACHED_PAIRS`, `PIPER_MAX_CACHED_VOICES` — warm-pool sizes.
- `STT_MODEL` (`Systran/faster-whisper-tiny|base|small`), `STT_COMPUTE_TYPE=int8`.
- `VAD_PROVIDER=energy|silero`, `REALTIME_LATENCY_MODE`.
- `REDIS_URL` — unset/unreachable ⇒ in-process cache/queue (single node).
- `LIVEKIT_URL/API_KEY/API_SECRET` — set ⇒ LiveKit transport & tokens.

## Project layout pointers

Backend entry `apps/api/globaltalk/main.py`; realtime `globaltalk/realtime/*`;
AI adapters `ai/providers/*`; router `ai/model_router/router.py`; web app `apps/web/src`.
