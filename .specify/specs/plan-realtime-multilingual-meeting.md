# Technical Implementation Plan: Realtime Multilingual Meeting Engine

## 1. System Architecture & Reused Modules
The plan directly leverages the existing TalkFlow codebase without rebuilding working components:

### A. Control Plane & REST Endpoints
- **Location**: `apps/api/globaltalk/api/v1/meetings.py`, `voice.py`, `auth.py`.
- **Functionality**:
  - `POST /api/v1/meetings`: Creates room, allocates `room_name` (e.g. `gt-xxxx`), generates `join_token`.
  - `POST /api/v1/voice/session?meeting_id=...`: Negotiates realtime transport (`websocket` or `livekit`), emits signed session token and URL.
  - `GET /api/v1/meetings/{id}`: Returns metadata, participants, and status.

### B. Realtime Data Plane & Pipeline
- **Location**: `services/api/app/realtime/pipeline.py`, `session.py`.
- **Flow**:
  1. WebSocket accepts binary frames (PCM16, 16kHz mono) and JSON control frames.
  2. Frame buffering & Silero VAD energy detection segments speech into utterances.
  3. `SpeechToTextPipeline` transcribes audio into canonical text (`TranscriptSegment`).
  4. `TranslationPipeline` queries target languages from all active room participants, deduplicates languages, and calls MT providers concurrently.
  5. `TTSPipeline` synthesizes speech for each required language and broadcasts audio frames exclusively to subscribed listeners.
  6. `TranscriptManager` commits the canonical source segment and translations to the database.

### C. Frontend Presentation Layer
- **Location**: `apps/web/src/pages/MeetingRoom.tsx`, `apps/web/src/components/voice/`
- **Audio Worklet**: `audio-capture-processor.js` streams 16kHz PCM blocks without blocking the UI thread.
- **Audio Playback**: Web Audio API AudioBufferSourceNode plays translated streams with jitter buffering.
- **Captions & Chat**: Synchronized transcript UI displays original speaker text and listener-specific translated text.

---

## 2. Component Mapping & File Boundaries

| Subsystem | Existing Path | Key Responsibilities |
| :--- | :--- | :--- |
| **Realtime Engine** | `services/api/app/realtime/` | Audio frame ingestion, VAD, fan-out translation, TTS routing |
| **AI Providers** | `ai/providers/` | Faster-Whisper, Kokoro TTS, Argos NMT, Silero VAD |
| **Database Models** | `apps/api/globaltalk/models/`, `services/api/app/db/models.py` | `Meeting`, `MeetingParticipant`, `TranscriptSegment`, `Translation` |
| **Frontend UI** | `apps/web/src/pages/MeetingRoom.tsx` | Live room, mic toggle, language pickers, caption overlay, audio playback |
| **Frontend State** | `apps/web/src/stores/voice.ts`, `auth.ts` | Room connection state, participant roster, volume, latency metrics |

---

## 3. Testing & Verification Gates
1. `tests/unit/`: Verify VAD windowing, token generators, and translation deduplication logic.
2. `tests/integration/`: Verify meeting lifecycle, join token validation, and transcript persistence.
3. `tests/realtime/`: Realtime golden call test with simulated multi-participant audio streaming.
4. `apps/web`: Strict TypeScript typecheck (`npx tsc -b`) and unit tests (`npx vitest run`).
5. Live health check: `curl http://127.0.0.1:8088/health` and `/ready`.
