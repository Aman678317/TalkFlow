/** Shared types mirroring the backend contracts (packages/shared-types for TS consumers). */

export interface LanguageCapability {
  code: string;
  name: string;
  native_name: string;
  speech_input_supported: boolean;
  speech_output_supported: boolean;
  translation_supported: boolean;
  realtime_supported: boolean;
  document_supported: boolean;
  stt_status: Status;
  tts_status: Status;
  mt_status: Status;
  stt_provider: string;
  tts_provider: string;
  mt_provider: string;
}
export type Status = "EXPERIMENTAL" | "BETA" | "SUPPORTED" | "PRODUCTION";

export interface TranslateResponse {
  translation_id: string;
  source_language: string;
  target_language: string;
  source_text: string;
  translated_text: string;
  model: string;
  provider: string;
  latency_ms: number;
  quality_flags: string[];
  from_translation_memory: boolean;
  detected_confidence: number;
  alternatives?: string[];
}

export interface Meeting {
  id: string;
  title: string;
  status: string;
  room_name: string;
  join_token: string;
  created_at: string;
  started_at?: string | null;
  ended_at?: string | null;
  has_summary: boolean;
  transport: "websocket" | "livekit";
  livekit_url?: string | null;
}

export interface ParticipantInfo {
  id: string;
  display_name: string;
  status: string;
  speaking_language: string;
  listening_language: string;
  audio_mode: AudioMode;
  caption_mode: CaptionMode;
}
export type AudioMode = "original" | "translated" | "mixed";
export type CaptionMode = "original" | "translated" | "both";
export type LatencyMode = "ultra_low_latency" | "balanced" | "high_accuracy";

export interface TranscriptItem {
  id: string;
  sequence: number;
  speaker: string;
  participant_id: string;
  language: string;
  text: string;
  confidence: number;
  stt_provider: string;
  stt_model: string;
  created_at: string;
  latency: Record<string, number | null>;
  translations: {
    id: string;
    target_language: string;
    text: string;
    provider: string;
    model: string;
    quality_flags: string[];
    tts_audio_key?: string | null;
  }[];
}

/* ---------------- realtime protocol (versioned events) ---------------- */

export type RealtimeEventType =
  | "session.created" | "session.updated" | "session.resumed"
  | "participant.joined" | "participant.left"
  | "audio.started" | "audio.stopped" | "speech.started" | "speech.ended"
  | "transcript.partial" | "transcript.final"
  | "translation.started" | "translation.partial" | "translation.final"
  | "tts.started" | "tts.chunk" | "tts.completed" | "audio.published"
  | "caption.updated" | "language.changed"
  | "chat.message" | "chat.translation"
  | "quality.degraded" | "quality.latency" | "translation.failed"
  | "reconnect.required" | "error" | "pong";

export interface RealtimeEvent {
  version: number;
  type: RealtimeEventType;
  session_id: string;
  conversation_id: string;
  sequence: number | null;
  timestamp: string;
  [key: string]: unknown;
}

export interface Preferences {
  speaking_language: string;
  listening_language: string;
  audio_mode: AudioMode;
  caption_mode: CaptionMode;
  latency_mode: LatencyMode;
}
