/**
 * Agent console (P4 §D1) — pure helpers for the live-agent escalation board.
 *
 * The wire contract mirrors the backend exactly:
 * - `EscalationTicket`  ← services/api/app/routers/telephony.py (EscalationTicketOut)
 * - `CallTranscript`    ← services/api/app/telephony/call_transcript.py (assembler)
 *
 * Privacy invariant pre-checked here: caller speech is fingerprints ONLY
 * (text_len + text_sha256). The UI never renders a caller-text field because
 * the contract has none — fail-closed by type, not by discipline.
 */

export type EscalationState = "pending" | "claimed" | "resolved";

export interface EscalationTicket {
  ticket_id: string;
  call_sid: string;
  reason: string | null;
  summary: string | null;
  turns: number;
  age_seconds: number;
  state: EscalationState;
  claimed_by?: string | null;
  resolution?: string | null;
}

export interface TranscriptAgentLine {
  text: string;
  node: string | null;
  action: string | null;
  tts: string | null;
  frames_rendered: number | null;
}

export interface TranscriptCitation {
  node: string | null;
  from: string | null;
  to: string | null;
  inputs_sha256: string | null;
  output_sha256: string | null;
  escalation_reason: string | null;
}

export interface TranscriptTurn {
  turn: number;
  at: string | null;
  /** fingerprints only — NEVER raw caller text */
  caller: { text_len?: number; text_sha256?: string; confidence?: number; frames?: number };
  agent_lines: TranscriptAgentLine[];
  citations: TranscriptCitation[];
}

export interface CallTranscript {
  call: {
    id: string; call_sid: string; direction: string; mode: string; status: string;
    provider: string; caller_language: string; receiver_language: string;
    duration_seconds: number;
  };
  turns: TranscriptTurn[];
  outcome: {
    terminal: string | null; escalation_reason: string | null;
    summary: string | null; turns: number | null;
  } | null;
  escalations: Array<{ event: string; at: string | null; payload: Record<string, unknown> }>;
  meta: { turns?: number; events_total?: number };
}

/** 65 → "65s"; 130 → "2m 10s"; 5400 → "1h 30m". */
export function formatAge(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

const REASON_LABELS: Record<string, string> = {
  opt_out: "Opted out",
  human: "Requested a human",
  human_request: "Requested a human",
  payment: "Payment issue",
  budget: "Budget concern",
  stop: "Stop command",
  low_stt_confidence: "Could not hear the caller",
  next_step_requires_human: "Needs a human step",
};

/** Unknown reasons stay honest: the raw code, never a guess. */
export function reasonLabel(reason: string | null): string {
  if (!reason) return "Unspecified reason";
  return REASON_LABELS[reason] || reason;
}

/** e.g. "sha256:9f7c1a…" — used everywhere a caller fingerprint renders. */
export function fingerprintHint(sha: string | undefined | null): string | null {
  if (!sha) return null;
  return `sha256:${sha.slice(0, 12)}…`;
}

export function stateBadgeTone(state: EscalationState): "info" | "warn" | "neutral" {
  if (state === "pending") return "warn";
  if (state === "claimed") return "info";
  return "neutral";
}

/** Turn heading: turn 0 IS the greeting (the agent spoke before turn 1). */
export function turnHeadline(turn: TranscriptTurn): string {
  return turn.turn === 0 ? "Greeting" : `Turn ${turn.turn}`;
}
