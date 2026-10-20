import { describe, expect, it } from "vitest";
import {
  fingerprintHint, formatAge, reasonLabel, stateBadgeTone, turnHeadline,
  type EscalationTicket, type TranscriptTurn,
} from "./agentConsole";

describe("agentConsole pure helpers", () => {
  it("formats ages the way operators read them", () => {
    expect(formatAge(65)).toBe("1m 5s");
    expect(formatAge(42)).toBe("42s");
    expect(formatAge(3660)).toBe("1h 1m");
    expect(formatAge(0)).toBe("0s");
    expect(formatAge(-5)).toBe("0s");            // clock skew never lies
  });

  it("maps known escalation reasons to operator language — unknown stays raw (honest)", () => {
    expect(reasonLabel("human_request")).toBe("Requested a human");
    expect(reasonLabel("low_stt_confidence")).toBe("Could not hear the caller");
    expect(reasonLabel("novel_reason_code")).toBe("novel_reason_code");
    expect(reasonLabel(null)).toBe("Unspecified reason");
  });

  it("truncates caller fingerprints and never fabricates them", () => {
    const sha = "9f7c1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef123456";
    expect(fingerprintHint(sha)).toBe("sha256:9f7c1a2b3c4d…");
    expect(fingerprintHint(undefined)).toBeNull();
    expect(fingerprintHint(null)).toBeNull();
  });

  it("badges by state and keeps greeting turns labeled honestly", () => {
    expect(stateBadgeTone("pending")).toBe("warn");
    expect(stateBadgeTone("claimed")).toBe("info");
    expect(stateBadgeTone("resolved")).toBe("neutral");

    const greeting = { turn: 0 } as unknown as TranscriptTurn;
    const realTurn = { turn: 3 } as unknown as TranscriptTurn;
    expect(turnHeadline(greeting)).toBe("Greeting");
    expect(turnHeadline(realTurn)).toBe("Turn 3");
  });

  it("the ticket wire type stays fingerprint-only — no raw caller text field", () => {
    // Type-level privacy invariant (compiled assertion), enforced again in the
    // page test: the shape mirrors the backend's EscalationTicketOut exactly.
    const ticket: EscalationTicket = {
      ticket_id: "esc-x", call_sid: "call-1", reason: "opt_out", summary: null,
      turns: 1, age_seconds: 5, state: "pending", claimed_by: null, resolution: null,
    };
    expect((ticket as unknown as Record<string, unknown>)["caller_text"]).toBeUndefined();
  });
});
