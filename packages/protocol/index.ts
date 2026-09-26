/** Realtime protocol v1 — mirrors apps/api/globaltalk/realtime/protocol.py */
export const PROTOCOL_VERSION = 1;

export const EventType = {
  SESSION_CREATED: "session.created",
  SESSION_UPDATED: "session.updated",
  SESSION_RESUMED: "session.resumed",
  PARTICIPANT_JOINED: "participant.joined",
  PARTICIPANT_LEFT: "participant.left",
  AUDIO_STARTED: "audio.started",
  AUDIO_STOPPED: "audio.stopped",
  SPEECH_STARTED: "speech.started",
  SPEECH_ENDED: "speech.ended",
  TRANSCRIPT_PARTIAL: "transcript.partial",
  TRANSCRIPT_FINAL: "transcript.final",
  TRANSLATION_STARTED: "translation.started",
  TRANSLATION_PARTIAL: "translation.partial",
  TRANSLATION_FINAL: "translation.final",
  TTS_STARTED: "tts.started",
  TTS_CHUNK: "tts.chunk",
  TTS_COMPLETED: "tts.completed",
  AUDIO_PUBLISHED: "audio.published",
  CAPTION_UPDATED: "caption.updated",
  LANGUAGE_CHANGED: "language.changed",
  CHAT_MESSAGE: "chat.message",
  CHAT_TRANSLATION: "chat.translation",
  QUALITY_DEGRADED: "quality.degraded",
  QUALITY_LATENCY: "quality.latency",
  TRANSLATION_FAILED: "translation.failed",
  RECONNECT_REQUIRED: "reconnect.required",
  ERROR: "error",
  PONG: "pong",
} as const;

/** Binary frame codec: 'O' original relay | 'T' translated TTS PCM (see docs/REALTIME.md) */
export function encodeOriginalFrame(shortId: string, pcm: Uint8Array): Uint8Array {
  const out = new Uint8Array(17 + pcm.length);
  out[0] = 0x4f;
  out.set(new TextEncoder().encode(shortId.padEnd(16, "0").slice(0, 16)), 1);
  out.set(pcm, 17);
  return out;
}

export function encodeTtsFrame(shortId: string, language: string, pcm: Uint8Array): Uint8Array {
  const lang = new TextEncoder().encode(language.slice(0, 8));
  const out = new Uint8Array(18 + lang.length + pcm.length);
  out[0] = 0x54;
  out.set(new TextEncoder().encode(shortId.padEnd(16, "0").slice(0, 16)), 1);
  out[17] = lang.length;
  out.set(lang, 18);
  out.set(pcm, 18 + lang.length);
  return out;
}
