# Clarification & Edge Cases: Realtime Multilingual Meeting Engine

## 1. Latency Assumptions & Degradation Budgets
- **Production Budget (GPU / Capable Multi-Core)**: 1.5s – 2.5s total end-to-end (Capture: 100ms → VAD/STT: 400-800ms → MT: 200-400ms → TTS: 300-600ms → Network Delivery: ~100ms).
- **Development / Low-RAM CPU Budget**: 8s – 12s per utterance. In memory-constrained environments, `MemoryGuard` and subprocess isolation ensure the system does not encounter Out-Of-Memory (OOM) fatal crashes, even if latency temporarily increases.
- **Degradation Rule**: When CPU or memory watermarks exceed 85%, TTS synthesis is throttled first, prioritizing text captions and canonical audio relay.

## 2. Unsupported Language Pairs
- If no translation model exists between `source_lang` and `target_lang` (e.g. rare dialects):
  - Do NOT hallucinate via unverified intermediary pivots.
  - Return an explicit event: `translation.unsupported { source_lang, target_lang, fallback: "original_audio" }`.
  - The listener receives original audio and a visual indicator that translation for this pair is unavailable.

## 3. Audio & Caption Edge Cases
- **Simultaneous Speakers**: Handled via participant-isolated VAD tracks. Each participant's stream generates distinct canonical segments tagged with `speaker_id`.
- **Mute / Background Noise**: Silero VAD filters low-energy / non-speech noise before sending frames to STT, saving inference compute.
- **Audio Feedback Prevention**: Synthesized TTS audio played back to listeners is never fed into the speaker's input stream. Client-side echo cancellation and server-side synthetic tagging enforce this boundary.

## 4. Reconnect & Resume Semantics
- Each event sent over the meeting channel contains a monotonically increasing `seq` integer per room.
- If a client drops and reconnects, it sends `session.reconnect { meeting_id, participant_id, last_seq }`.
- The server replays missed transcript events from `last_seq` without re-synthesizing or duplicating translations.

## 5. Security & Data Retention
- Meeting sessions are strictly scoped to the tenant `org_id` and authorized via meeting join tokens or JWT.
- In-memory PCM audio buffers are cleared upon segment finalization; temporary recording files are scrubbed according to tenant retention policies.
