# VoiceStudio sidecar integration

TalkFlow can use [VoiceStudio](https://github.com/debpalash/VoiceStudio) as an
optional local speech provider. VoiceStudio remains a separate AGPL-3.0
application; TalkFlow does **not** copy or bundle its source. The integration
uses VoiceStudio's documented OpenAI-compatible HTTP endpoints:

- `POST /v1/audio/transcriptions` for speech-to-text
- `POST /v1/audio/speech` for text-to-speech

## Install VoiceStudio

Use the upstream installer for the platform, then start its local backend. On
Windows PowerShell, follow the upstream instructions:

```powershell
irm https://voicestudio.sh/install | iex
```

The default local service is `http://127.0.0.1:3900`. Install and download
models in VoiceStudio itself; TalkFlow never downloads VoiceStudio models in a
request path.

## Configure TalkFlow

In the backend environment (never in `VITE_*` variables):

```dotenv
VOICESTUDIO_URL=http://127.0.0.1:3900
# Set only when VoiceStudio is configured with OMNIVOICE_API_KEY.
VOICESTUDIO_API_KEY=
STT_PROVIDER=voicestudio_stt
TTS_PROVIDER=voicestudio_tts
VOICESTUDIO_STT_MODEL=whisper-1
VOICESTUDIO_TTS_MODEL=tts-1
VOICESTUDIO_TTS_VOICE=default
VOICESTUDIO_TTS_FORMAT=wav
```

Restart the canonical API after changing provider settings. The existing
realtime pipeline still owns room authorization, language fan-out, captions,
original-audio relay, and honest `translation.failed` degradation. VoiceStudio
supplies STT/TTS only; it does not replace TalkFlow meetings or telephony.

## Verify the connection

```powershell
curl http://127.0.0.1:3900/health
curl http://127.0.0.1:3900/v1/models
curl http://127.0.0.1:8088/ready
```

Then exercise one text translation and one browser voice session. If the
sidecar is unavailable, TalkFlow falls back through its configured provider
chain rather than fabricating audio or translated text.

## Calls and telephony boundary

VoiceStudio's local speech service does not provide PSTN access. TalkFlow's
carrier/Asterisk controls, consent gates, call authorization and original-call
fallback remain mandatory. Do not advertise carrier-connected translated calls
until the selected carrier or SIP lab has its own real evidence and disclosure
approval.
