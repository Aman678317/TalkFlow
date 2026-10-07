/**
 * GlobalTalk AI — shared protocol & API types.
 * Mirror of the backend contracts (services/api/app/schemas.py and
 * app/realtime/protocol.py). Versioned; keep in sync when bumping protocol.
 */

export const PROTOCOL_VERSION = 1;

// ---------------------------------------------------------------------------
// Realtime WebSocket protocol
// ---------------------------------------------------------------------------

export type ServerEventType =
  | 'session.created' | 'session.updated' | 'session.resumed'
  | 'participant.joined' | 'participant.left'
  | 'audio.started' | 'audio.stopped'
  | 'speech.started' | 'speech.ended'
  | 'transcript.partial' | 'transcript.final'
  | 'translation.started' | 'translation.partial' | 'translation.final'
  | 'tts.started' | 'tts.chunk' | 'tts.completed'
  | 'audio.published' | 'caption.updated' | 'language.changed'
  | 'quality.degraded' | 'translation.failed' | 'reconnect.required'
  | 'chat.message' | 'latency.report' | 'pong' | 'error'
  | 'media.state' | 'signal'
  | 'audio.relay';

export type ClientEventType =
  | 'session.join' | 'session.resume'
  | 'audio.start' | 'audio.chunk' | 'audio.stop'
  | 'transcript.inject' | 'preferences.update' | 'chat.send'
  | 'media.state' | 'signal' | 'ping';

export interface ServerEvent<T = Record<string, unknown>> {
  version: number;
  type: ServerEventType;
  session_id: string;
  conversation_id: string;
  speaker_id: string | null;
  sequence: number;
  timestamp: string;
  data: T;
}

export interface SessionCreatedData {
  meeting_id: string;
  room_name: string;
  mode: 'ws' | 'livekit';
  participant_id: string;
  display_name: string;
  speak_lang: string;
  hear_lang: string;
  audio_mode: AudioMode;
  protocol_version: number;
  server_sequence: number;
  ai: { translation: string; dev_mode: Record<string, boolean> };
  participants: ParticipantSnapshot[];
}

export interface ParticipantSnapshot {
  participant_id: string;
  display_name: string;
  speak_lang: string;
  hear_lang: string;
  audio_mode: AudioMode;
  connected: boolean;
}

export interface TranscriptFinalData {
  segment_id: string;
  seq: number;
  speaker_name: string;
  language: string;
  text: string;
  is_final: boolean;
  confidence?: number | null;
  stt_model?: string;
  latency?: Partial<LatencyTrace>;
}

export interface TranslationFinalData {
  segment_id: string;
  seq: number;
  target_lang: string;
  text: string;
  model: string;
  quality_flags: string[];
  latency_ms: number;
}

export interface TtsChunkData {
  segment_id: string;
  seq: number;
  target_lang: string;
  chunk_index: number;
  audio_base64: string;
  format: 'wav' | 'pcm_s16le' | 'mp3';
  sample_rate: number;
  is_dev: boolean;
  model: string;
}

export interface LatencyTrace {
  segment_id: string;
  seq: number;
  source_lang: string;
  target_lang: string;
  audio_capture_ms: number;
  stt_first_partial_ms: number;
  stt_final_ms: number;
  translation_ms: number;
  tts_first_audio_ms: number;
  delivery_ms: number;
  total_e2e_latency_ms: number;
  stale_dropped: boolean;
}

export interface ChatMessageData {
  id: string;
  seq: number;
  sender_name: string;
  original_text: string;
  detected_lang: string;
  translations: Record<string, { text: string | null; model?: string; flags?: string[]; error?: string }>;
  created_at: string;
}

export type AudioMode = 'original' | 'translated' | 'mixed' | 'captions_only';

// ---------------------------------------------------------------------------
// REST API types
// ---------------------------------------------------------------------------

export interface ApiError {
  code: string;
  message: string;
  request_id: string | null;
  trace_id: string | null;
  recoverable: boolean;
  details: Record<string, unknown>;
}

export interface Language {
  code: string;
  name: string;
  native_name: string;
  script: string;
  rtl: boolean;
  translation_supported: boolean;
  speech_input_supported: boolean;
  speech_output_supported: boolean;
  realtime_supported: boolean;
  document_supported: boolean;
  translation_status: QualityStatus;
  speech_input_status: QualityStatus;
  speech_output_status: QualityStatus;
  realtime_status: QualityStatus;
  document_status: QualityStatus;
  tts_voices: string[];
}

export type QualityStatus = 'EXPERIMENTAL' | 'BETA' | 'SUPPORTED' | 'PRODUCTION';

export interface TranslationResult {
  translation_id: string;
  source_language: string;
  target_language: string;
  source_text: string;
  translated_text: string;
  model: string;
  provider: string;
  latency_ms: number;
  quality_flags: string[];
  tm_match?: 'exact' | 'fuzzy' | 'semantic' | null;
  domain: string;
}

export interface TranslateResponse {
  translations: TranslationResult[];
  request_id: string;
}

export interface User {
  id: string;
  email: string;
  name: string;
  locale: string;
  speak_lang: string;
  hear_lang: string;
  email_verified: boolean;
  mfa_enabled: boolean;
  is_platform_admin: boolean;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status: string;
  created_at: string;
}

export interface Meeting {
  id: string;
  title: string;
  status: 'scheduled' | 'live' | 'ended' | 'archived';
  mode: 'ws' | 'livekit';
  room_name: string;
  created_at: string;
  started_at?: string | null;
  ended_at?: string | null;
  participants?: ParticipantDetail[];
  livekit?: { url: string; token: string } | null;
}

export interface ParticipantDetail {
  participant: {
    id: string; display_name: string; role: string; status: string;
    joined_at?: string | null;
  };
  preference: {
    speak_lang: string; hear_lang: string; audio_mode: AudioMode;
    captions_enabled: boolean;
  } | null;
}

export interface JoinResponse {
  meeting_id: string;
  participant_id: string;
  session_key: string;
  rt_url: string;
  livekit?: { url: string; token: string } | null;
}

export interface DocumentItem {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  source_lang: string;
  detected_lang: string;
  target_lang: string;
  status: string;
  progress: number;
  error_code?: string | null;
  error_message?: string | null;
  page_count: number;
  char_count: number;
  model_version: string;
  created_at: string;
  ready_at?: string | null;
}

export interface Glossary {
  id: string;
  name: string;
  source_lang: string;
  target_lang: string;
  version: number;
  status: 'draft' | 'active' | 'archived';
  description: string;
  created_at: string;
  terms: GlossaryTerm[];
}

export interface GlossaryTerm {
  id: string;
  source_text: string;
  target_text: string;
  case_sensitive: boolean;
  spoken_variants_json: string[];
  notes: string;
}

export interface TranslationMemoryItem {
  id: string;
  name: string;
  source_lang: string;
  target_lang: string;
  domain: string;
  version: number;
  entry_count: number;
  created_at: string;
}

export interface StyleProfile {
  id: string;
  name: string;
  kind: string;
  version: number;
  config_json: Record<string, unknown>;
  status: string;
  org_id: string | null;
}

export interface Summary {
  meeting_id: string;
  summary: string;
  key_points: string[];
  decisions: string[];
  action_items: string[];
  unanswered_questions: string[];
  topics: string[];
  method: string;
  generated_at: string;
}

export interface UsageSummary {
  period: string;
  totals: Record<string, number>;
  by_product: Record<string, Record<string, number>>;
  by_day: Array<Record<string, string | number>>;
}

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
  translations: Array<{
    id: string; target_lang: string; target_text: string; model: string;
    latency_ms: number; quality_flags_json: string[]; created_at: string;
  }>;
}

