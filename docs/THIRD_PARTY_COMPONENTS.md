# Third-Party Components — License & Security Review

Machine-readable source of truth: `third_party_components.yaml` (repo root).
Policy (sections 77/82/116): **pinned versions only** · weights downloaded at bootstrap,
never committed · license + model-card + dataset terms reviewed **before production use** ·
"open source" ≠ "commercially unrestricted" (code, weights and datasets can differ) ·
every component is consumed through an internal adapter, never by cloning repos into the
business layer.

| Component | Role | Version (pin) | License | Review | Sandbox status |
|---|---|---|---|---|---|
| LiveKit server | Realtime SFU (prod media) | v1.7.2 image | Apache-2.0 | ✅ approved | NOT_CONFIGURED (WS transport) |
| LiveKit Agents | Agent runtime | 0.11.x | Apache-2.0 | ✅ approved | OPTIONAL |
| faster-whisper | Primary STT + audio LID | pkg 1.2.1; weights `Systran/faster-whisper-tiny|base|small|large-v3` | MIT (code+weights) | ✅ approved | **ACTIVE (PASS)** |
| Argos Translate | Offline NMT (primary CPU MT) | pkg 1.9.6; packages from official index | MIT code; **per-package model licenses vary (NLLB-derived often CC-BY-NC)** | ⚠ per-package review required before commercial routing | **ACTIVE (PASS)** en↔hi/ja/zh/es |
| Marian (opus-mt) | Pair filler (e.g. en↔mr) | Helsinki-NLP/opus-mt-{en-mr,mr-en} | model cards: mostly CC-BY-4.0 (verify each) | ⚠ per-model | adapter present; disabled <2 GB RAM |
| Piper TTS | Primary open neural TTS | piper-tts 1.8.0; voices: lessac/pratham/huayan/davefx (medium) | MIT code; voices per-voice (open) | ✅ approved (per-voice recorded) | **ACTIVE (PASS)** en/hi/zh/es |
| Kokoro TTS | Alt TTS (en/ja/zh/es/fr) | kokoro-onnx 0.9.x + v1.0 weights | Apache-2.0 | ✅ code approved; weights repo gated from sandbox | OPTIONAL |
| IndicConformer ASR | Indic STT route (Phase 2) | pinned release | check per release (often CC-BY-SA) | ⏳ pending | NOT_CONFIGURED |
| Indic Parler TTS | Indic voices (Phase 5) | pinned revision | check model card | ⏳ pending | NOT_CONFIGURED |
| Silero VAD | VAD upgrade | v5 | MIT code; **model CC-BY-NC** | ⚠ blocked until review — energy VAD default | OPTIONAL |
| Docling | Document parsing upgrade | 2.67.x | MIT | ✅ approved | OPTIONAL (built-in parsers active) |
| pgvector | Vector search | pg16 image | PostgreSQL License | ✅ approved | NOT_CONFIGURED (SQLite dev) |
| vLLM | Local LLM serving | pinned per GPU image | Apache-2.0 engine; models per-deployment | ✅ engine / ⚠ models | NOT_CONFIGURED (extractive fallback) |
| Seamless (M4T) | S2ST research only | research pin | **CC-BY-NC 4.0** | ⛔ blocked for commercial | DISABLED behind flag |
| DeepFilterNet · Asteroid · pyannote · NeMo · SpeechBrain · FunASR · sherpa-onnx · whisper.cpp | Phase 3/4 audio pipeline (denoise/separation/diarization/alt-STT) | per deployment | mixed (verify each; pyannote models gated + non-commercial restrictions) | ⏳ pending | NOT_CONFIGURED (adapters reserved) |
| langid | Text language ID | 1.1.6 | MIT | ✅ approved | ACTIVE |
| pypdf · python-docx · python-pptx · openpyxl · reportlab | Document parse/rebuild | pinned in requirements | BSD/MIT/Apache | ✅ approved | ACTIVE |
| React · Vite · Tailwind · TanStack Query · Zustand · React Router | Frontend | pinned package.json | MIT | ✅ approved | ACTIVE |
| FastAPI · SQLAlchemy · Alembic · Pydantic · uvicorn | Backend | pinned requirements | MIT/Apache/BSD | ✅ approved | ACTIVE |
| Noto fonts (google/fonts) | PDF reconstruction scripts | variable TTF | OFL-1.1 | ✅ approved (attribution: fonts © Google, OFL) | downloaded at bootstrap |

## Voice/model term notes

- **NLLB-derived Argos packages**: several are CC-BY-NC — commercial deployments must
  either restrict those pairs (`private_only`/tenant policy) or substitute licensed models;
  the router + registry make substitution a config change, not a code change.
- **Silero VAD weights**: CC-BY-NC — hence the deterministic energy VAD default.
- **Piper voices**: check each voice's training-data statement before cloning/voice
  preservation features; voice preservation itself is consent-gated and flag-off by default.
- **Whisper weights (Systran conversions)**: MIT — cleared.

## Security review procedure (per component, recorded in the YAML)

1. Inspect LICENSE + model card + dataset terms. 2. Pin version/tag/commit.
3. `pip-audit`/`npm audit` + image scan in CI. 4. Record review date + reviewer.
5. Adapter-only integration (no vendored code). 6. Re-review on every upgrade.
