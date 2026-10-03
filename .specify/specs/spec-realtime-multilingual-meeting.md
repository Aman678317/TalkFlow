# Feature Specification: Realtime Multilingual Meeting Engine

## 1. Overview & Objective
GlobalTalk AI enables live multilingual meetings where each participant speaks in their native language and receives audio/captions in their chosen target language in real time (< 2.5s end-to-end latency on capable infrastructure).

### Core Philosophy: Translate Once, Fan Out
1. A speaker's microphone streams 16kHz PCM16 audio blocks (~100ms) to the server.
2. The server applies noise-gating, Voice Activity Detection (VAD), and speech segmentation.
3. Streaming STT (`faster-whisper`) produces a transcript and identifies the source language.
4. The transcript becomes an **immutable canonical source segment**.
5. The canonical segment fans out to independent MT tasks for each distinct target language requested in the meeting room.
6. Synthesized audio (TTS via `Kokoro-ONNX` or `Piper`) and synchronized captions are routed directly to listeners according to their language preferences.

---

## 2. User Stories & Acceptance Criteria

### User Story 1: Language Preference & Room Joining
- **As a** meeting participant,
- **I want to** select my spoken language and my preferred listening language upon entering the room,
- **So that** I hear everyone translated into my preferred language and they understand my speech.
- **Acceptance Criteria**:
  - Room supports multiple concurrent participants.
  - Participant state contains `speaker_lang`, `listener_lang`, and audio output preference (`audio+captions`, `captions_only`, `original_audio`).
  - Listeners sharing the same target language receive deduplicated translation outputs (one MT execution per language).

### User Story 2: Canonical Source & Translation Integrity
- **As a** meeting auditor or compliance officer,
- **I want** the original spoken transcript preserved exactly as uttered,
- **So that** meeting minutes and translations are verifiable and free of cascading translation errors.
- **Acceptance Criteria**:
  - The canonical source segment is immutable once committed to the database.
  - No chained translations (e.g. Hindi → English → Spanish) are permitted; all translations are generated directly from the canonical source.
  - TTS output is tagged as synthetic and never looped back into speech recognition.

### User Story 3: Honest Degradation & Resilience
- **As a** participant experiencing poor network or an unsupported language pair,
- **I want** transparent fallbacks rather than system crashes or hallucinations,
- **So that** I can continue following the meeting.
- **Acceptance Criteria**:
  - If STT fails, original audio continues to be relayed to peers.
  - If MT fails for a specific target language, an explicit recoverable error event is emitted to that listener while other listeners are unaffected.
  - If TTS fails, translated captions are still displayed.
  - Reconnecting clients resume from their last received event sequence number without duplicate utterances.

---

## 3. Data Contracts & Realtime Events

### WebSocket / LiveKit Event Envelopes
- `session.join`: `{ meeting_id, participant_id, name, spoken_lang, target_lang }`
- `audio.chunk`: Binary PCM16 mono 16kHz frame (~100ms chunks).
- `transcript.partial`: `{ utterance_id, text, is_final: false, source_lang }`
- `transcript.final`: `{ utterance_id, text, is_final: true, source_lang, start_ms, end_ms }`
- `translation.delta`: `{ utterance_id, target_lang, text, is_final }`
- `audio.synthesis`: `{ utterance_id, target_lang, pcm_bytes | audio_url, sample_rate: 16000 }`
- `session.reconnect`: `{ meeting_id, participant_id, last_seq }`
