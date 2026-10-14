# Realtime AI Provider Deployment Requirements

This document captures what an operator **must** do to make live translation
(STT → MT → TTS) actually work in production. Skipping any of these steps
causes silent degradation: captions stop, no translated audio reaches the
listener, and the UI shows "Connected · Realtime Translation Active" because
the WebSocket handshake succeeded — but the pipeline never produces audio.

For the diagnosis behind each requirement, see
`docs/superpowers/plans/2026-10-12-share-link-translation-debug.md`.

---

## TL;DR — Production AI deploy checklist

| Step | Why | Where |
|---|---|---|
| Add `faster-whisper>=1.0.0` (and optionally `piper-tts`, `kokoro-onnx`) to `services/api/requirements.txt` | Providers are lazy-imported; if the package is missing the import raises `ProviderUnavailable` and STT/TTS silently fail over to dev_* | `services/api/requirements.txt` |
| Set `MODEL_CACHE_PATH` to a **persistent, mounted** directory | Render's local disk is ephemeral — model weights downloaded at build time are wiped on every redeploy | Render Dashboard → Disk OR persistent volume (S3/R2/Supabase Storage with `hf://` cache shim) |
| Raise the service to **≥2 GiB RAM** (Standard plan or higher) | `faster-whisper` `small` (int8) needs ~600 MB; `piper` needs ~300 MB; MyMemory/Google HTTP MT is unbounded | `render.yaml` `plan: standard` (or larger) |
| Set `STT_PROVIDER=faster_whisper` and `TTS_PROVIDER=piper` (or `auto`) in the Render env | Operator override beats lazy auto-resolution; without this, `auto` falls through to providers whose packages may not be installed | `render.yaml` envVars |
| Run `bash scripts/download_models.sh` at **build time** (Render `buildCommand`) | Models are downloaded once into `MODEL_CACHE_PATH`; if the cache is persistent they survive redeploy. If ephemeral, the build still pre-downloads so the **first** request after a cold start doesn't hang | `render.yaml` `buildCommand` (extend the existing one) |
| Add the AI providers' runtime probes to the `/ready` endpoint | Production failures are silent because the SPINUP path is lazy | `app/main.py` startup probes |

If any of these are missing the platform degrades **honestly** (no fabricated
audio) but **invisibly** (UI says "translation active", reality says
"captions only").

---

## 1. STT (Speech → Text)

### Why `faster-whisper`

Configured STT order: `faster_whisper → stt_http → dev_text`.

- `faster_whisper`: local Whisper inference via CTranslate2. No API key, no
  network egress, deterministic, GPU-optional.
- `stt_http`: HTTP proxy to a managed service. Optional operator URL.
- `dev_text`: **honest dev fallback** — returns empty transcripts ("never
  fabricate text from audio"). Causes zero output when enabled. NOT a
  production-quality provider.

### Production requirements

**1. Python package**

```diff
 # services/api/requirements.txt
 # AI/ML dependencies
 langid>=1.1.6
 numpy>=1.26.0
 langdetect>=1.0.9
+faster-whisper>=1.0.0
```

(The dev file `requirements-dev.txt` already lists this. Move it to the base
file OR add it to Render's install command explicitly.)

**2. Model weights**

```bash
export MODEL_CACHE_PATH=/var/data/globaltalk-models   # persistent volume
bash scripts/download_models.sh    # downloads whisper base (~150 MB)
```

For Hindi / Indic accuracy pick `STT_SIZE=small` (default in INDIC profile).
For multilingual ZH/JA: `STT_SIZE=small` minimum.

**3. Memory**

| Plan | RAM | Whisper `tiny` | Whisper `base` | Whisper `small` |
|---|---|---|---|---|
| Render Starter | 512 MB | ✅ | ❌ OOM | ❌ |
| Render Standard | 2 GB | ✅ | ✅ | ⚠️ risky under load |
| Render Pro / k8s 4 GB | 4 GB+ | ✅ | ✅ | ✅ |

Set `STT_SIZE=tiny` or `=base` when RAM is tight.

**4. Environment**

```yaml
# render.yaml — example
- key: STT_PROVIDER
  value: faster_whisper
- key: STT_SIZE
  value: base            # tiny | base | small (int8)
- key: MODEL_CACHE_PATH
  value: /var/data/globaltalk-models
```

### Failure symptom (the one the user reported)

`transcript.final` events fire, but every one has `text=""`. The MT fan-out
is skipped (the `_finalize_utterance` branch checks `if not text: return`), so
no `translation.final`, no `tts.started`, no `audio.published`. The translated
listener **silently** hears nothing while the captions row still updates with
the partial-from-the-other-speaker.

The diagnostic event the new instrumentation emits looks like:

```json
{
  "type": "diagnostic",
  "stage": "stt_failed",
  "provider": "faster_whisper",
  "error": "No module named 'faster_whisper'",
  "hint": "Install gt-ai[whisper] or use stt_http"
}
```

---

## 2. MT (Translation)

MT is the **least** of the deployment worries. The first provider in the chain
is `neural_online`, which proxies MyMemory/Google Web and works without any
API key. It should "just work" on Render's free plan.

Setting `DEEPL_API_KEY` adds the DeepL text-translation API as a managed
provider: the router auto-promotes `deepl` ahead of `neural_online` for the
pairs DeepL supports. `DEEPL_API_KEY` is your own authorized key; nothing is
sent anywhere without it, and no DeepL content is redistributed with this repo.

CPU memory pressure matters for Argos (`argos-translate`) — only enable if
you have ≥2 GiB. Otherwise `GT_ENABLE_ARGOS=false` keeps the chain short.

---

## 3. TTS (Text → Speech)

### Why Piper (not Kokoro)

Configured TTS order: `kokoro → piper → tts_http → dev_tone`.

- `kokoro`: best quality but gated (HF repo currently closed).
- `piper`: open-source ONNX voices, runs on CPU, ~300 MB resident.
- `tts_http`: HTTP proxy to a managed TTS endpoint.
- `dev_tone`: real audible tone WAV but not linguistic — honest placeholder.

### Production requirements

**1. Python package**

```diff
 # services/api/requirements.txt
+piper-tts>=1.2.0        # ONNX runtime + phonemization
+# kokoro-onnx is OPTIONAL — gated, fallback to piper
```

**2. Voice weights**

```bash
bash scripts/download_models.sh    # downloads en/hi/ja/zh/es Piper voices
```

Each voice is ~30 MB; bundled into the model cache.

**3. Memory**

Same table as STT — `piper` adds ~300 MB; budget 2 GiB minimum for TTS.

**4. Environment**

```yaml
- key: TTS_PROVIDER
  value: piper
```

### Failure symptom

`translation.final` and `tts.started` fire, but the binary `T` frames never
land on the WebSocket (or land as 22 ms of garbage — see the WAV-vs-PCM bug
fixed in this PR). The listener hears nothing.

---

## 4. Diagnostic instrumentation (already shipped on this branch)

Every pipeline stage emits a structured `diagnostic` event the frontend
surfaces in the translation status banner. To verify live:

```bash
# Tail Render logs while two browsers are in a meeting
render logs -t 10m --only api
```

Look for:

```
[D] pipeline.stt_enter provider=faster_whisper size=base
[D] pipeline.stt_exit confidence=0.91 lang=hi text="नमस्ते"
[D] pipeline.fanout_start source=hi targets=['en']
[D] pipeline.mt_exit lang=en text="hello"
[D] pipeline.tts_enter provider=piper voice=en_US-lessac-medium
[D] pipeline.tts_first_audio latency_ms=480 bytes=16128
[D] pipeline.tts_exit total_bytes=96144 chunks=6
```

A **silent** failure looks like:

```
[D] pipeline.stt_failed provider=faster_whisper error="No module named 'faster_whisper'"
[D] pipeline.fanout_skipped reason="empty_text"
```

The frontend log mirror (`import.meta.env.DEV`) prints these on the
verification toolbar.

---

## 5. Local-dev vs production parity matrix

| Capability | Local dev (`requirements-dev.txt`) | Production Render (`requirements.txt`) |
|---|---|---|
| Whisper STT | ✅ faster-whisper installed | ❌ package missing → falls back to dev_text |
| Piper TTS | ✅ piper-tts installed | ❌ package missing → falls back to dev_tone |
| Model cache | `/tmp/globaltalk-models` (local FS) | ephemeral disk → wiped every redeploy |
| Transcript.inject (dev affordance) | ✅ `import.meta.env.DEV` | ✅ path no longer gated on is_production (this PR) |
| Real-time diagnostics | ✅ console.debug + UI banner | ✅ same code path — visible in `render logs` |

**The asymmetry is the bug.** The fix is to make `requirements.txt` reflect
what the runtime actually needs.
