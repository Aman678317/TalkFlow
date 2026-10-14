"""TalkFlow realtime agents (implementation guide §4-§5, Phase 2).

Four *logical* agents — typed async modules, not four services and not an LLM
call per audio frame:

  Agent 1 :class:`app.realtime.agents.listening.ListeningAgent`
      audio ingestion, VAD boundaries, STT, stable TranscriptSegment
  Agent 2 :class:`app.realtime.agents.translation.TranslationAgent`
      contextual translation, one call per distinct target language, per
      recipient fan-out
  Agent 3 :class:`app.realtime.agents.voice.VoiceAgent`
      TTS chunks, audio declaration, delivery hand-off
  Agent 4 :class:`app.realtime.agents.supervisor.Supervisor`
      lifecycle state, ordering, cancellation, timing metrics, fallback policy

They are adapters over the providers the repository already uses
(``app.ai.ai``, ``app.services.translation_service``), connected by
:class:`app.realtime.agents.bus.AgentBus`. Nothing here replaces room
management, auth, storage, WebRTC/LiveKit or the wire protocol.
"""
from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import (
    AGENT_CONTRACT_VERSION,
    RealtimeEvent,
    Stage,
    TranscriptSegment,
    TranslationSegment,
    TtsChunkReady,
)
from app.realtime.agents.listening import ListeningAgent, RealtimeSttProvider
from app.realtime.agents.supervisor import Supervisor
from app.realtime.agents.translation import (
    RealtimeTranslatorProvider,
    TranslationAgent,
)
from app.realtime.agents.voice import RealtimeTtsProvider, VoiceAgent

__all__ = [
    "AGENT_CONTRACT_VERSION",
    "AgentBus",
    "ListeningAgent",
    "RealtimeEvent",
    "RealtimeSttProvider",
    "RealtimeTranslatorProvider",
    "RealtimeTtsProvider",
    "Stage",
    "Supervisor",
    "TranscriptSegment",
    "TranslationAgent",
    "TranslationSegment",
    "TtsChunkReady",
    "VoiceAgent",
]
