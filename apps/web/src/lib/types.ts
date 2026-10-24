/** Shared types mirroring the backend contracts (packages/shared-types for TS consumers). */

export interface LanguageCapability {
  code: string;
  name: string;
  native_name: string;
  script: string;
  rtl: boolean;
  speech_input_supported: boolean;
  speech_output_supported: boolean;
  translation_supported: boolean;
  realtime_supported: boolean;
  document_supported: boolean;
  // The API names these `*_status` (not `stt_status`/`mt_status`/`tts_status`)
  // — the old names never existed on the wire, so every language chip's
  // tooltip read "STT undefined, MT undefined, TTS undefined" (2026-10-21).
  translation_status: Status;
  speech_input_status: Status;
  speech_output_status: Status;
  realtime_status: Status;
  document_status: Status;
  tts_voices: string[];
}
export type Status = "EXPERIMENTAL" | "BETA" | "SUPPORTED" | "PRODUCTION";

/**
 * The API's translate envelope (services/api/app/schemas.py: TranslateResponse).
 *
 * The endpoint returns `{ translations: [...], request_id }` — the previous
 * client type described a SINGLE flat translation, so the name lied about
 * the shape every call site was already handling (issue #109 class 1).
 */
export interface TranslateResponse {
  translations: TranslationOut[];
  request_id: string;
}

/** One translation inside the envelope (mirrors the API's TranslationOut). */
export interface TranslationOut {
  translation_id: string;
  source_language: string;
  target_language: string;
  source_text: string;
  translated_text: string;
  model: string;
  provider: string;
  latency_ms: number;
  quality_flags: string[];
  tm_match: string | null;
  domain: string;
  alternatives: string[];
  /** Set only when a REQUESTED glossary was NOT applied (honest reason). */
  glossary_note?: string | null;
}

/**
 * What the normalizer accepts: the API's envelope, a single translation, or
 * a partial of either (the client stays defensive about a legacy flat
 * response). It replaces the `any` the normalizer used to take — the shapes
 * are named now, so a wrong field is a type error instead of `undefined` at
 * runtime.
 */
export interface TranslateResponseLike {
  request_id?: string;
  translations?: Partial<TranslationOut>[];
  translation_id?: string;
  source_language?: string;
  target_language?: string;
  source_text?: string;
  translated_text?: string;
  model?: string;
  provider?: string;
  latency_ms?: number;
  quality_flags?: string[];
  tm_match?: string | null;
  domain?: string;
  alternatives?: string[];
  glossary_note?: string | null;
  /** Client-side field: the API does not send a detection confidence. */
  detected_confidence?: number;
}

/**
 * The flat view the client normalizes the envelope into for the UI.
 * Not an API shape — see `normalizeTranslationResponse` in lib/translation.ts.
 */
export interface NormalizedTranslation {
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
  /** Set only when a REQUESTED glossary was NOT applied (honest reason). */
  glossary_note?: string | null;
  alternatives?: string[];
}

/** Result of translating the readable text of a public web page. */
export interface PageTranslateResponse {
  url: string;
  final_url: string;
  title: string;
  source_text: string;
  translated_text: string;
  source_language: string;
  target_language: string;
  model: string;
  provider: string;
  latency_ms: number;
  quality_flags: string[];
  /** The page text was longer than the character budget. */
  truncated: boolean;
  /** Set only when a REQUESTED glossary was NOT applied (honest reason). */
  glossary_note?: string | null;
}

export interface Meeting {
  id: string;
  title: string;
  status: string;
  room_name: string;
  created_at: string;
  started_at?: string | null;
  ended_at?: string | null;
  has_summary: boolean;
  transport: "websocket" | "livekit";
  livekit_url?: string | null;
}

export interface JoinMeetingRequest {
  display_name?: string;
  speak_lang: string;
  hear_lang: string;
  audio_mode?: AudioMode;
  /** server-issued seat continuation key ("" = new seat) */
  session_key?: string;
  /** open an additional unbound guest seat (logged-in user, second person) */
  as_guest?: boolean;
}

export interface JoinMeetingResponse {
  meeting_id: string;
  participant_id: string;
  session_key: string;
  rt_url: string;
  livekit?: string | null;
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

/**
 * A transcript segment as the API returns it (mirrors the API's
 * TranscriptSegmentOut, services/api/app/schemas.py).
 *
 * The previous client type described a different shape entirely
 * (`sequence`/`speaker`/`language`/`text` + fields the API never sends), so
 * the first consumer would have read all-undefined values (issue #109
 * class 1). The API is the contract: the client mirrors it field for field.
 */
export interface TranscriptSegment {
  id: string;
  seq: number;
  speaker_name: string;
  source_lang: string;
  source_text: string;
  start_ms: number | null;
  end_ms: number | null;
  is_final: boolean;
  confidence: number | null;
  stt_model: string;
  created_at: string;
  translations: TranslationSegment[];
}

/** One translation of a segment (mirrors the API's TranslationSegmentOut). */
export interface TranslationSegment {
  id: string;
  target_lang: string;
  target_text: string;
  model: string;
  latency_ms: number;
  quality_flags_json: string[];
  created_at: string;
}

/** A chat message as the API returns it (mirrors the API's ChatMessageOut). */
export interface ChatMessage {
  id: string;
  meeting_id: string;
  sender_name: string;
  original_text: string;
  detected_lang: string;
  kind: string;
  seq: number;
  translations_json: Record<string, string>;
  created_at: string;
}

/**
 * The list envelope the contacts/campaigns endpoints return: a bare array
 * read would be silently empty, so the client reads `items` (issue #109
 * class 1).
 */
export interface ItemsEnvelope<T> {
  items: T[];
  total?: number;
}

/* ---------------- realtime protocol (versioned events) ---------------- */

export type RealtimeEventType =
  | "session.created" | "session.updated" | "session.resumed"
  | "participant.joined" | "participant.left"
  | "audio.started" | "audio.stopped" | "speech.started" | "speech.ended"
  | "transcript.partial" | "transcript.final"
  | "translation.transcript.partial" | "translation.transcript.final"
  | "translation.started" | "translation.partial" | "translation.final" | "translation.segment.final" | "translation.segment.translated"
  | "tts.started" | "tts.chunk" | "tts.completed" | "translation.tts.ready" | "audio.published"
  | "caption.updated" | "language.changed" | "language.detected"
  | "chat.message" | "chat.translation"
  | "media.state"
  | "quality.degraded" | "quality.latency" | "latency.report" | "translation.failed" | "translation.error"
  | "playback.flush" | "playback.interrupt"
  | "reconnect.required" | "error" | "pong" | "signal" | "diagnostic";

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
  /** Server-side caption fan-out. Omitted by older callers = enabled. */
  captions_enabled?: boolean;
  /** Volume for ducked original audio in mixed mode (0.0 to 1.0, default 0.15). */
  original_audio_volume?: number;
}
