/**
 * The caption list, as a pure reducer over realtime events.
 *
 * A caption line is keyed by the *turn* it describes, because three events build
 * one line and they do not arrive in order: `transcript.partial` while the
 * speaker is still talking, `transcript.final` when they stop, and
 * `translation.final` some hundreds of ms later — by which time another speaker
 * may already have a line on screen. Everything that joins those events together
 * is identity (`utterance_id`, or `segment_id` for a server that sends neither),
 * and everything that places them on the timeline is `start_wall_ms` /
 * `duration_ms`, which the pipeline measures from the audio rather than from
 * arrival.
 */
import type { CaptionMode, RealtimeEvent } from "./types";

/** `idle` = never heard yet; `dropped` = cut off by a barge-in before finishing. */
export type PlaybackState = "idle" | "playing" | "played" | "dropped";

export interface CaptionLine {
  /** Turn identity: the utterance id, falling back to the segment id. */
  id: string;
  speakerId: string;
  speaker: string;
  /** Source language of the turn. */
  language: string;
  segmentId?: string;
  seq?: number;
  original?: string;
  originalFinal: boolean;
  translated?: string;
  translatedLang?: string;
  partial: boolean;
  failed?: string;
  latencyMs?: number;
  /** Wall-clock ms when the speaker started the turn, and how long it ran. */
  startWallMs?: number;
  durationMs?: number;
  playback: PlaybackState;
}

export interface CaptionView {
  caption_mode: CaptionMode;
  listening_language: string;
  /** participant id -> display name, for events that arrive without a name. */
  speakerNames?: Record<string, string>;
}

/** Check if two language tags match (handling regional subtags like 'en-US' vs 'en', case variations, etc.) */
export function isSameLanguage(a?: string | null, b?: string | null): boolean {
  if (!a || !b) return false;
  const cleanA = a.trim().toLowerCase().replace("_", "-");
  const cleanB = b.trim().toLowerCase().replace("_", "-");
  if (cleanA === cleanB) return true;
  return cleanA.split("-")[0] === cleanB.split("-")[0];
}

/** Bound on the live list; the durable transcript is the server's job. */
export const MAX_CAPTION_LINES = 80;

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** The turn an event describes. Never the speaker's label: two people can share one. */
function turnId(evt: RealtimeEvent): string | undefined {
  return str(evt.utterance_id) ?? str(evt.segment_id);
}

function speakerLabel(evt: RealtimeEvent, view: CaptionView): string {
  const id = str(evt.speaker_id);
  return str(evt.display_name) ?? (id ? view.speakerNames?.[id] : undefined) ?? "Speaker";
}

function trim(lines: CaptionLine[]): CaptionLine[] {
  return lines.length > MAX_CAPTION_LINES ? lines.slice(-MAX_CAPTION_LINES) : lines;
}

function replace(lines: CaptionLine[], index: number, next: CaptionLine): CaptionLine[] {
  const copy = lines.slice();
  copy[index] = next;
  return copy;
}

function timeline(evt: RealtimeEvent) {
  const startWallMs = num(evt.start_wall_ms);
  const durationMs = num(evt.duration_ms);
  return {
    ...(startWallMs !== undefined ? { startWallMs } : {}),
    ...(durationMs !== undefined ? { durationMs } : {}),
  };
}

function newLine(evt: RealtimeEvent, view: CaptionView, id: string): CaptionLine {
  return {
    id,
    speakerId: str(evt.speaker_id) ?? "",
    speaker: speakerLabel(evt, view),
    language: str(evt.language) ?? str(evt.source_language) ?? "",
    seq: num(evt.seq) ?? num(evt.sequence),
    originalFinal: false,
    partial: true,
    playback: "idle",
  };
}

/** A translated-only line, for a translation whose source caption was never seen. */
function translatedKey(turn: string, lang: string): string {
  return `tr:${turn}:${lang}`;
}

function indexByTurn(lines: CaptionLine[], turn: string, segmentId?: string): number {
  const byTurn = lines.findIndex((c) => c.id === turn);
  if (byTurn !== -1) return byTurn;
  return segmentId ? lines.findIndex((c) => c.segmentId === segmentId) : -1;
}

function applyTranscript(lines: CaptionLine[], evt: RealtimeEvent, view: CaptionView,
  isFinal: boolean): CaptionLine[] {
  const turn = turnId(evt);
  if (!turn) return lines;
  const language = str(evt.language) ?? str(evt.source_language) ?? "";
  // In "translated" mode a source caption in someone else's language is noise —
  // but a final still opens the line, because the translation has to land on it.
  const showOriginal = view.caption_mode !== "translated"
    || isSameLanguage(language, view.listening_language);
  if (!showOriginal && !isFinal) return lines;

  const index = lines.findIndex((c) => c.id === turn);
  const text = str(evt.text);
  if (index === -1) {
    const line: CaptionLine = {
      ...newLine(evt, view, turn),
      language,
      segmentId: str(evt.segment_id),
      ...(text !== undefined && showOriginal ? { original: text } : {}),
      originalFinal: isFinal && showOriginal,
      partial: !isFinal,
      ...timeline(evt),
    };
    return trim([...lines, line]);
  }
  const prev = lines[index];
  const next: CaptionLine = {
    ...prev,
    segmentId: str(evt.segment_id) ?? prev.segmentId,
    language: language || prev.language,
    seq: num(evt.seq) ?? prev.seq,
    ...(text !== undefined && showOriginal ? { original: text } : {}),
    originalFinal: isFinal ? true : prev.originalFinal,
    partial: !isFinal,
    speaker: prev.speaker || speakerLabel(evt, view),
    ...timeline(evt),
  };
  return replace(lines, index, next);
}

function applyTranslation(lines: CaptionLine[], evt: RealtimeEvent,
  view: CaptionView): CaptionLine[] {
  const targetLang = str(evt.target_language) ?? str(evt.target_lang);
  const turn = turnId(evt);
  if (!turn || !targetLang || !isSameLanguage(targetLang, view.listening_language)) return lines;
  // "Original" caption mode is a deliberate choice not to read translations.
  if (view.caption_mode === "original") return lines;

  const text = str(evt.text) ?? str(evt.translated_text);
  const latencyMs = num(evt.latency_ms);
  const segmentId = str(evt.segment_id);
  const patch = {
    ...(text !== undefined ? { translated: text } : {}),
    translatedLang: targetLang,
    ...(latencyMs !== undefined ? { latencyMs } : {}),
    ...timeline(evt),
  };

  // A retry of the same translation replaces it, wherever it lives.
  const standalone = lines.findIndex((c) => c.id === translatedKey(turn, targetLang));
  if (standalone !== -1) return replace(lines, standalone, { ...lines[standalone], ...patch });

  const index = indexByTurn(lines, turn, segmentId);
  if (index !== -1) return replace(lines, index, { ...lines[index], ...patch });

  const line: CaptionLine = {
    ...newLine(evt, view, translatedKey(turn, targetLang)),
    id: translatedKey(turn, targetLang),
    language: str(evt.source_language) ?? str(evt.language) ?? "",
    segmentId,
    originalFinal: true,
    partial: false,
    ...patch,
  };
  return trim([...lines, line]);
}

function applyTranslationFailed(lines: CaptionLine[], evt: RealtimeEvent,
  view: CaptionView): CaptionLine[] {
  // A failed translation to somebody else's language is not my problem. When the
  // event names no target there is nothing to route on, so it is shown.
  const targetLang = str(evt.target_language) ?? str(evt.target_lang);
  if (targetLang && !isSameLanguage(targetLang, view.listening_language)) return lines;
  const segmentId = str(evt.segment_id);
  if (!segmentId) return lines;
  const id = `fail:${segmentId}`;
  if (lines.some((c) => c.id === id)) return lines;
  const message = str(evt.user_message) ?? str(evt.message) ?? "Translation unavailable";
  return trim([...lines, {
    ...newLine(evt, view, id),
    id,
    language: str(evt.source_language) ?? str(evt.target_language) ?? "",
    originalFinal: true,
    partial: false,
    failed: message,
  }]);
}

function applyLatencyReport(lines: CaptionLine[], evt: RealtimeEvent,
  view: CaptionView): CaptionLine[] {
  const targetLang = str(evt.target_language);
  if (targetLang && !isSameLanguage(targetLang, view.listening_language)) return lines;
  const turn = turnId(evt);
  if (!turn) return lines;
  const ms = num(evt.total_e2e_latency_ms);
  if (ms === undefined) return lines;
  const index = indexByTurn(lines, turn, str(evt.segment_id));
  if (index === -1) return lines;
  return replace(lines, index, { ...lines[index], latencyMs: ms, ...timeline(evt) });
}

/** A turn that produced no words retires its own dangling partial. */
function dropTurn(lines: CaptionLine[], turn: string): CaptionLine[] {
  return lines.filter((c) => c.id !== turn && !c.id.startsWith(`tr:${turn}`));
}

export function reduceCaptions(lines: CaptionLine[], evt: RealtimeEvent,
  view: CaptionView): CaptionLine[] {
  switch (evt.type) {
    case "transcript.partial":
      return applyTranscript(lines, evt, view, false);
    case "transcript.final":
      return applyTranscript(lines, evt, view, true);
    case "translation.final":
    case "translation.segment.final":
      return applyTranslation(lines, evt, view);
    case "translation.failed":
      return applyTranslationFailed(lines, evt, view);
    case "latency.report":
      return applyLatencyReport(lines, evt, view);
    case "speech.ended": {
      if (evt.empty !== true) return lines;
      const turn = turnId(evt);
      return turn ? dropTurn(lines, turn) : lines;
    }
    default:
      return lines;
  }
}

/**
 * Playback state comes from the player, not from the event: a caption is "the
 * listener has heard this" only once its audio actually started, and a barge-in
 * flush marks the dropped turn rather than removing its text.
 */
export function setPlayback(lines: CaptionLine[], turn: string,
  state: PlaybackState): CaptionLine[] {
  const index = lines.findIndex((c) => c.id === turn || c.id.startsWith(`tr:${turn}:`));
  if (index === -1) return lines;
  return replace(lines, index, { ...lines[index], playback: state });
}
