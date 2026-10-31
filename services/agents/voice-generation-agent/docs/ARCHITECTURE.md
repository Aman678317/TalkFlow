# TalkFlow Agent 06: Voice Generation Agent Architecture

## 1. System Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │    Agent 05 Translation Quality QA    │
                      └───────────────────┬────────────────────┘
                                          │ POST /api/v1/tts/segment
                                          ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   Agent 06: Voice Generation Agent (Port 8006)                   │
│                                                                                  │
│   ┌────────────────────────┐         ┌────────────────────────┐                  │
│   │   Quality Gate Check   ├────────►│   Identity Validation  │                  │
│   │ (ACCEPT/WARN only)     │         │ (session/seg/trans/hash│                  │
│   └────────────────────────┘         └───────────┬────────────┘                  │
│                                                  │                               │
│                                                  ▼                               │
│   ┌────────────────────────┐         ┌────────────────────────┐                  │
│   │   Voice Selector       │◄────────┤   Idempotency Cache    │                  │
│   │ (5-Tier Fallback)      │         │ (LRU result cache)     │                  │
│   └───────────┬────────────┘         └────────────────────────┘                  │
│               │                                                                  │
│               ▼                                                                  │
│   ┌──────────────────────────────────────────────────────────┐                   │
│   │                    Provider Router                       │                   │
│   │   ┌──────────────┐ ┌──────────────┐ ┌────────────────┐   │                   │
│   │   │  DevTone     │ │ Windows SAPI │ │  Kokoro/Piper  │   │                   │
│   │   │ (Formant Syn)│ │ (pyttsx3)    │ │  (ONNX Neural) │   │                   │
│   │   └──────────────┘ └──────────────┘ └────────────────┘   │                   │
│   └───────────────────────────┬──────────────────────────────┘                   │
│                               │                                                  │
│                               ▼                                                  │
│   ┌──────────────────────────────────────────────────────────┐                   │
│   │                 Audio Signal Processing                  │                   │
│   │   ┌─────────────────────┐      ┌─────────────────────┐   │                   │
│   │   │   Normalizer        │      │   Wire Framing      │   │                   │
│   │   │ (24 kHz PCM16 Mono) │      │ (0x54 magic prefix) │   │                   │
│   │   └─────────────────────┘      └─────────────────────┘   │                   │
│   └───────────────────────────┬──────────────────────────────┘                   │
│                               │                                                  │
│                               ▼                                                  │
│   ┌──────────────────────────────────────────────────────────┐                   │
│   │                    Agent 07 Publisher                    │                   │
│   │          (tts.started, tts.chunk, tts.completed)         │                   │
│   └───────────────────────────┬──────────────────────────────┘                   │
└───────────────────────────────┼──────────────────────────────────────────────────┘
                                │ POST /api/v1/audio/sync/chunk
                                ▼
                      ┌────────────────────────────────────────┐
                      │ Agent 07 Audio Synchronization/Delivery │
                      └────────────────────────────────────────┘
```

## 2. TalkFlow Binary Wire Frame Specification

The wire frame follows TalkFlow's binary audio format:

```
+------------+--------------------+-------------------+---------------+------+-------------------+--------------------+
| 0x54 ('T') | Short ID (16 bytes)| Lang Len (1 byte) | Lang (N bytes)| 0x01 | Chunk Idx (4-byte)| Raw PCM16 Payload  |
+------------+--------------------+-------------------+---------------+------+-------------------+--------------------+
```

- **Byte 0**: Magic byte `0x54` (ASCII `'T'`).
- **Bytes 1-16**: Utterance short ID (ASCII / UTF-8, padded with null bytes).
- **Byte 17**: Length of target language tag in bytes.
- **Bytes 18 to 18+N**: UTF-8 bytes of target language code (e.g. `hi`, `mr`, `en`).
- **Byte 18+N**: Extension marker `0x01`.
- **Next 4 Bytes**: Big-endian unsigned 32-bit integer chunk index (`struct.pack('>I', chunk_index)`).
- **Remaining Bytes**: Raw linear PCM16 mono audio samples (24,000 Hz or 16,000 Hz).

## 3. Five-Tier Voice Selection Logic

1. **Tier 1 (Participant Preference)**:
   - Evaluates caller's requested `preferred_voice_id`.
   - Strictly validates target language compatibility (`voice.language == target_language`).
   - Verifies opt-in consent if custom or cloned.
2. **Tier 2 (Neural Models)**:
   - Selects language-matching ONNX voice from Kokoro (`hf_alpha`, `jf_alpha`, etc.) or Piper (`mr_IN-google-medium`, `bn_BD-google-medium`, etc.).
3. **Tier 3 (Local System SAPI)**:
   - Selects native OS voice (Windows Microsoft David Desktop or Microsoft Zira Desktop) for English.
4. **Tier 4 (DevTone Synthesizer)**:
   - Deterministic harmonic formant synthesizer producing clear, audible, multi-tone speech waveforms matching sentence lengths without downloading neural weights.
5. **Tier 5 (Fail-Closed)**:
   - If the language is unsupported or outside configured capabilities, raises `UnsupportedLanguageError`.

