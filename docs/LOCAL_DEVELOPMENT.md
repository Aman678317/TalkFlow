# Local Development

Requirements: Python 3.11+, Node 20+. Docker optional. ~2 GB disk for models (CPU profile).

## Quick start

```bash
git clone <repo> && cd globaltalk-ai
make bootstrap        # toolchain check, deps, .env, DB init+seed, model weights, verify
make dev              # backend :8088 + Web :5173 (Vite proxies /api and /ws to :8088)
```

Both commands run **`services/api`** — the tree Render deploys (`app.main:app`, module
`app.*`). The legacy tree `apps/api` (module `globaltalk.*`, port 8000) is still
available with `make api-legacy` / `make migrate-legacy`, but the web app cannot reach
it without editing the Vite proxy, so use it only for the golden test that drives it.

Open http://localhost:5173 — sign up, or use the seeded dev account
`admin@globaltalk.dev` / `Demo1234!` (platform admin, org "GlobalTalk Demo", seeded glossary).

## The golden demo (3+ browser tabs)

1. Meetings → New meeting → you land in the room (tab 1 = Aarav).
2. Copy invite → open in tab 2 (Beth), tab 3 (Chen). Different display names per tab.
3. Set per tab: **I speak** / **I want to hear** / audio mode.
   Sandbox-validated combos: hi↔en (voice+captions), en↔es/zh (voice), en/ja→hi…
   The Admin page (`/admin`, signed in as the seeded account) shows which components
   are actually installed; its data comes from `GET /api/v1/admin/model-health`.
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
make migrate                   # alembic upgrade head on services/api (prod-style)
make migrate-legacy            # the same, on the apps/api tree
MODEL_PROFILE=INDIC bash scripts/download_models.sh   # more Argos Indic pairs
```

## Environment knobs that matter locally

- `GT_LOW_MEMORY=auto|true|false` — subprocess-isolated inference on small machines.
- `ARGOS_MAX_CACHED_PAIRS`, `PIPER_MAX_CACHED_VOICES` — warm-pool sizes.
- `STT_MODEL` (`Systran/faster-whisper-tiny|base|small`), `STT_COMPUTE_TYPE=int8`.
- `VAD_PROVIDER=energy|silero`, `REALTIME_LATENCY_MODE`.
- `VAD_MIN_SPEECH_MS`, `VAD_MIN_SILENCE_MS`, `VAD_MAX_SPEECH_MS`,
  `VAD_PARTIAL_INTERVAL_MS` — when a turn ends and how often live captions update.
  `VAD_MIN_SILENCE_MS` is added directly to the latency before translation starts.
- `REDIS_URL` — unset/unreachable ⇒ in-process cache/queue (single node).
- `LIVEKIT_URL/API_KEY/API_SECRET` — set ⇒ LiveKit transport & tokens.

## Project layout pointers

Deployed backend entry `services/api/app/main.py` (import name `app.*`); realtime
`services/api/app/realtime/*`; AI facade `services/api/app/ai.py` over the providers,
registry and router in `services/api/gt_ai/*`; web app `apps/web/src`.

The legacy tree has its own copies of all of that — entry `apps/api/globaltalk/main.py`
(import name `globaltalk.*`), AI engine `ai/gt_ai/*` — and it is the tree `run_api.py`,
`make api` and the Vite proxy do **not** use. `ai/model_router/router.py` is a third,
separate implementation. Import order is what keeps them apart: pytest takes
`pythonpath = services/api, apps/api, ai, .` (pyproject.toml) and the Makefile exports
`PYTHONPATH=services/api:apps/api:.`, so `services/api` wins in both.
