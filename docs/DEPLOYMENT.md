# Deployment

## Docker Compose (single host)

```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build
# web  → http://localhost:8080   api → http://localhost:8000/docs
# postgres(pgvector) · redis · minio · livekit · api · worker · web · prometheus · grafana
# GPU inference worker:  --profile gpu   (NVIDIA container toolkit required)
docker compose -f infrastructure/docker/docker-compose.yml down
```

The api container runs `alembic upgrade head` before serving (migration job inline;
on k8s it's a separate Job).

## Azure realtime speech translation

The primary managed provider path is opt-in through server-side environment
variables. It keeps the existing room WebSocket and VAD/agent pipeline: Azure
Speech recognizes each finalized PCM16 utterance, Azure Translator handles the
canonical text fan-out, and Azure Speech TTS returns target-language WAV audio.
The adapters fail closed when credentials or a supported voice are missing; no
Azure key is ever placed in `VITE_*` variables or sent to the browser.

Install the normal API dependencies, plus the Speech SDK when the controller
runs with `azure_speech` credentials. The SDK is an opt-in, not a runtime pin:
its native wheel cannot fit the serverless manifest (Vercel's Python functions
are capped at 225 MB), credentials select the provider at runtime, and the
adapter fails closed with an install hint when the SDK is absent:

```powershell
python -m pip install -r services/api/requirements.txt
python -m pip install azure-cognitiveservices-speech
```

For a local PowerShell session, set the provider selection and server-only
credentials before starting the canonical API:

```powershell
$env:STT_PROVIDER = "azure_speech"
$env:TRANSLATION_PROVIDER = "azure_translator"
$env:TTS_PROVIDER = "azure_speech_tts"
$env:AZURE_SPEECH_KEY = "<server-only-key>"
$env:AZURE_SPEECH_REGION = "<resource-region>"
# Optional separate Translator resource; otherwise the Speech key/region is used.
$env:AZURE_TRANSLATOR_KEY = ""
$env:AZURE_TRANSLATOR_REGION = ""
$env:AZURE_SPEECH_VOICE_MAP = "en=en-US-JennyNeural,hi=hi-IN-SwaraNeural"
python run_api.py
```

`AZURE_SPEECH_AUTO_DETECT_LANGUAGES` may be set to a comma-separated list of
BCP-47 candidates. When it is blank, the adapter uses its built-in English,
Indic, Urdu, and Simplified Chinese candidate set. Add a voice to
`AZURE_SPEECH_VOICE_MAP` before enabling a target language that has no safe
default voice; the provider deliberately refuses to substitute an English voice
silently.

The current adapter uses the existing utterance boundaries for the canonical
path and does not claim that a completed REST request is a continuous stream.
Azure's Speech SDK continuous/intermediate events remain available for the next
latency optimization after the segmented path is measured in a real account.
See [`docs/REALTIME_PROVIDER_RESEARCH.md`](REALTIME_PROVIDER_RESEARCH.md) for
the provider comparison and the lip-sync boundary.

## Optional AirLLM GPU worker

AirLLM is intentionally not part of the normal API image. Build the optional
profile only on a host with the NVIDIA Container Toolkit and enough persistent
disk for the selected Hugging Face checkpoint plus AirLLM's layer shards:

```bash
export AIRLLM_MODEL_ID=meta-llama/Llama-3.1-70B-Instruct
export AIRLLM_HF_TOKEN=<server-side-token-if-the-model-is-gated>
docker compose -f infrastructure/docker/docker-compose.yml \
  --profile gpu up --build inference-worker
```

The profile uses `services/api/requirements-gpu.txt`, pins AirLLM and the CUDA
PyTorch wheel, sets `TRANSLATION_PROVIDER=airllm`, and keeps the regular API,
Vercel, and Render images CPU-safe. AirLLM's roughly 4 GB GPU working-set claim
does not describe the total checkpoint or shard storage; do not put weights or
`AIRLLM_HF_TOKEN` in Git. Set `AIRLLM_MODEL_ID` to another supported model if
you have a non-gated checkpoint.

## Kubernetes

`infrastructure/kubernetes/globaltalk.yaml`: namespace, Secret/ConfigMap (replace with
External Secrets/Vault), model-cache PVC (RWX), migrate Job, api Deployment (3 replicas,
readiness `/ready`, liveness `/health`, Prometheus annotations) + HPA (CPU 65%, 3→30),
worker Deployment (queue drain), inference-gpu Deployment (nvidia.com/gpu, nodeSelector
`globaltalk.ai/gpu`), web Deployment + Services, nginx Ingress with cert-manager TLS and
WebSocket timeouts (3600 s).

Scaling rules (section 58): API scales on CPU/connections; workers on queue depth
(KEDA on Redis list length recommended); inference on GPU utilization; LiveKit via its
own autoscaling. Never run heavy inference inside API pods — the queue boundary enforces it.

## Backups & DR

- Postgres: continuous WAL archiving + nightly base backups; restore drill quarterly.
- Object storage: versioning + cross-region replication for prod buckets.
- Model weights: reproducible via `scripts/download_models.sh` (pinned); cache PVC is
  disposable.
- Redis: cache/queue only — loss degrades to in-process mode, no source-of-truth data.

## Health semantics

`/health` = process alive (always 200 when serving). `/ready` = 200 only when required
dependencies answer (DB, storage, LiveKit *if configured*); cache degradation is reported
but tolerated (in-process fallback). Orchestrators must use `/ready` for traffic.

## TLS / reverse proxy

nginx conf (infrastructure/docker/nginx.conf) proxies /api, /ws (upgrade-aware), /docs,
/metrics, /internal and serves the SPA with security headers. In k8s the Ingress handles
termination; set `X-Forwarded-Proto` and trust proxy headers for audit IPs.

## Environments

`.env.example` (reference) · `.env.development` · `.env.test` · `.env.production.example`
(copy → fill secrets; never commit real values). Feature flags ship dark
(`agent_bridge`, `voice_preservation`, `enterprise_sso`, `seamless_research` off).

## Vercel multi-service deployment

The repository can run as three Vercel services behind a single domain:

- `web` root: `apps/web` — the main React app, catch-all frontend service.
- `api` root: `services/api` — the FastAPI API service with `app.main:app` as the entrypoint.
- `connect` root: `apps/amazon-connect-v2v/webapp` — the Amazon Connect V2V frontend mounted under `/connect/`.

Public routing is intentionally specific-first:

- `/api/*`, `/api-docs`, `/v2/*`, `/v3/*`, `/ws/*`, `/health`, `/healthz`, `/ready`, `/readyz`, `/metrics` → `api`
- `/connect` and `/connect/:path*` → `connect` while keeping the browser-visible URL prefix `/connect/`
- all remaining requests → `web`

`vercel.json` declares services as a map keyed by service name and routes them with top-level rewrites using `{ "service": "<name>" }` destinations. The Connect rewrite uses a service path for static-file lookup under the service root.

The API service installs the repository-local AI package as part of its Python dependency setup instead of deploying `ai` as a separate service. No service bindings are required for this configuration; browser code should stay on same-origin public API routes and the Connect app should receive external AWS Lambda proxy URLs via Vercel build-time environment variables.

Required environment variables for the Connect app in Vercel:

- `VITE_GET_LANGUAGES_PROXY` = the AWS Lambda URL used to fetch available languages.
- `VITE_REQUEST_SESSION_PROXY` = the AWS Lambda URL used to request a translation session.

These values are deployment configuration, not Vercel service bindings.

## Release process

CI (GitHub Actions): backend tests (SQLite + Postgres/pgvector/Redis lanes), realtime
golden call with downloaded weights, frontend typecheck/vitest/build, docker image builds.
Images tagged by git SHA; k8s rollout via migrate Job → api → workers. Rollback = previous
tag (migrations are additive; expand/contract discipline).
