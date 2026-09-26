"""LiveKit Agents runtime integration (section 77.2).

Production topology: SpeechAgent / TranslationAgent / VoiceAgent / TimingAgent /
LanguageRouterAgent run as livekit-agents workers connecting to the LiveKit SFU.
Deterministic infrastructure (the GlobalTalk hub) owns timing, sequences, routing,
identity and canonical-source state; agents only transform media/text.

When LIVEKIT_* is not configured, the identical pipeline runs over the WebSocket
transport (globaltalk.realtime) — same hub, same routing rules, same events.
"""
