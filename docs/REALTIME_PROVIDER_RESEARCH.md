# Realtime translation provider research

Decision date: 2026-10-16

## Decision

Use **Azure Speech standard speech translation through the server-side Python
Speech SDK** as the primary realtime provider path. Keep the existing TalkFlow
pipeline as the source of truth:

```text
WebRTC/WS audio -> VAD -> provider recognition/translation -> canonical source
                 -> per-listener translation/caption routing -> TTS/audio
```

Azure is the only researched option that documents all of the MVP-critical
properties in one supported product surface: continuous recognition,
intermediate (`recognizing`) results, final (`recognized`) results, translation
targets, and optional synthesized speech. The provider is configured only on
the backend; the browser continues to send PCM16 frames to the existing room
WebSocket.

This is an adapter decision, not a media-architecture decision. It does not
replace WebRTC/LiveKit, the meeting WebSocket, the canonical transcript, or
the per-recipient routing already implemented in `app.realtime.pipeline`.

## Comparison

| Provider | Realtime evidence | Coverage / output | Cost / hardware | Decision |
|---|---|---|---|---|
| **Azure Speech** | Official docs describe real-time speech translation and the Speech SDK exposes continuous recognition plus intermediate and final events. | Speech-to-text translation, multiple target languages, optional speech synthesis; exact pair support must be checked against the capability registry. | Managed, metered service; Microsoft gives illustrative speech-translation pricing and charges additional translation targets. No local GPU. | **Primary MVP path** |
| **Bhashini.ai** | Official OpenAPI exposes REST `/v1` and `/v2` ASR, translate, and synthesize endpoints. No streaming endpoint appears in the published schema. | Strong Indic language list; text/audio requests and responses; 32-character `X-API-KEY` or JWT auth. | Managed REST service; rate limits/premium voices depend on account. No local GPU. | Segmented fallback/research path, not primary realtime |
| **Meta Seamless M4T v2** | Official repository/model card provide self-hosted speech translation capabilities, but no managed low-latency room-session API was verified. | 96-language model card claims, ASR/audio-to-audio/TTS capabilities. | Requires model downloads and significant local GPU/CPU operations; license and deployment constraints require explicit review. | Local research option only |
| **Sync Labs** | Official docs describe URL/upload/asset-based generation and model jobs that usually take minutes. | Lip-sync video/audio generation, not the live speech translation transport. | Per-generated-video-second pricing; plan-dependent duration limits; no evidence yet for interactive room streaming. | Separate lip-sync experiment only |

## Official sources

- Azure overview: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-translation
- Azure Python how-to: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-translate-speech
- Azure language support: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=speech-translation
- Azure Python SDK reference: https://learn.microsoft.com/en-us/python/api/azure-cognitiveservices-speech/azure.cognitiveservices.speech.translation
- Bhashini OpenAPI: https://tts.bhashini.ai/openapi
- Seamless repository: https://github.com/facebookresearch/seamless_communication
- Seamless model card: https://huggingface.co/facebook/seamless-m4t-v2
- Sync Labs introduction: https://sync.so/docs/introduction
- Sync Labs quickstart: https://sync.so/docs/quickstart.md
- Sync Labs lip-sync models: https://sync.so/docs/models/lipsync.md

## Integration boundaries

The first implementation should expose three server-side provider settings:

- `AZURE_SPEECH_KEY` — secret; never sent to the browser.
- `AZURE_SPEECH_REGION` — Azure Speech resource region.
- `AZURE_SPEECH_VOICE_MAP` — optional target-language voice map, for example
  `en=en-US-AriaNeural,hi=hi-IN-SwaraNeural`.

The provider must fail closed when the SDK or credentials are missing. The
meeting must remain usable with original audio and captions, and the existing
`translation.failed`, `quality.degraded`, and diagnostic events must identify
the unavailable provider rather than returning fabricated translated text or a
test tone in production.

The first vertical slice will use the existing utterance boundaries for the
canonical final path while preserving the existing partial-caption cadence.
The SDK's continuous/intermediate event model is the follow-up optimization
after the adapter is proven against the current agent interfaces; it must not
be simulated by claiming that a batch request is a streaming session.

## Lip-sync boundary

Lip-sync remains a separate feature flag and experiment. Sync Labs output is
generated video, not a replacement for the live camera track. It may be
evaluated using recorded short clips after the speech-translation path has
measured speech-to-caption and speech-to-first-audio latency.
