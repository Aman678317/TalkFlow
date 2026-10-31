# Agent 07 Architecture: Audio Synchronization & Delivery

## 1. System Overview

Agent 07 acts as the final buffer, pacing, routing, and delivery engine of TalkFlow.

```
                    +-----------------------------+
                    | Agent 06 (TTS Chunks)       |
                    +--------------+--------------+
                                   | HTTP / JSON Event
                                   v
                    +-----------------------------+
                    | Ingestion & Provenance Gate |
                    | (synthetic=True validation) |
                    +--------------+--------------+
                                   |
                                   v
                    +-----------------------------+
                    | Stale Detector & Timeline   |
                    | (deadline < 1500ms check)   |
                    +--------------+--------------+
                                   |
                                   v
                    +-----------------------------+
                    | Jitter Buffer & Reassembly  |
                    | (reorder out-of-order chunks|
                    +--------------+--------------+
                                   |
                                   v
                    +-----------------------------+
                    | Participant Router & Fanout |
                    | (room isolation, loop guard)|
                    +-------+--------------+------+
                            |              |
          LiveKit WebRTC    |              | Binary WebSocket (0x54)
                            v              v
               +---------------+     +---------------+
               | LiveKit Track |     | Participant WS|
               +---------------+     +---------------+
```

## 2. Jitter Absorption & Chunk Reassembly

When streaming synthesis runs across multi-core workers or networks, chunks can arrive out of order (e.g. chunk 1 arrives before chunk 0).

1. **UtteranceChunkBuffer**:
   - Stores incoming chunks indexed by `chunk_index`.
   - Tracks `next_expected_index`.
   - Pops strictly contiguous indices (`0, 1, 2, ...`).
   - If a missing index is delayed longer than `reorder_wait_ms` (60ms), it skips the missing index to avoid blocking live playback.
2. **Deduplication**:
   - Tracks emitted indices. Repeated arrivals of the same index are discarded immediately.

## 3. Conversational Freshness & Stale Detection

In live conversations, a delayed audio response is worse than silence if a new topic or human turn has started.

- `start_wall_ms`: Timestamp recorded when the human speaker began talking.
- If current wall clock exceeds `start_wall_ms` by `max_stale_delay_ms` (1500ms), the chunk is dropped.
- If the speaker has already initiated a higher sequence turn (`seq_new > seq_old`), earlier turns are dropped.

## 4. Multi-Participant Fan-Out & Feedback Loop Safety

- **Translate-once, Fan-out-to-many**: One synthesized chunk for language $L$ is distributed to all room participants listening in $L$.
- **Speaker Exclusion**: If speaker $A$ speaks in Hindi, their seat never receives Hindi-translated audio. This prevents their microphone from capturing the synthesized output and feeding it back into Agent 01/02 STT.
- **Tenant Isolation**: Rooms enforce `tenant_id` boundaries. Participants from tenant $B$ cannot register or listen to room sessions from tenant $A$.

