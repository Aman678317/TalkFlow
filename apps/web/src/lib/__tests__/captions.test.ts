/**
 * Phase 3 — captions align, in the browser, without guessing.
 *
 * "Captions align" is the browser's job, because three events that describe one
 * turn arrive out of order by nature: the partial while the speaker is still
 * talking, the final when they stop, and the translation some hundreds of
 * milliseconds later — after another speaker may already have started. The old
 * code attached a translation to "the last untranslated caption from a speaker
 * with that display name", which is a guess, and the server's transcript events
 * never said when the turn happened at all.
 *
 * These tests drive the reducer with events shaped exactly as
 * `ServerEvent.to_json` delivers them (data spread onto the envelope), so the
 * identity and timeline fields the client depends on are under test rather than
 * assumed.
 */
import { describe, expect, it } from "vitest";
import {
  reduceCaptions,
  setPlayback,
  type CaptionLine,
  type CaptionView,
} from "../captions";
import type { RealtimeEvent, RealtimeEventType } from "../types";

const AMAN = "6f1c2d3e-4b5a-4c6d-8e9f-0a1b2c3d4e5f";
const BETH = "b1bb1e50-1111-4c6d-8e9f-0a1b2c3d4e5f";
const SEG = "c0c0c0c0-1111-4c6d-8e9f-0a1b2c3d4e5f";
const TURN = "d1d1d1d1-1111-4c6d-8e9f-0a1b2c3d4e5f";

function evt(type: RealtimeEventType, data: Record<string, unknown>): RealtimeEvent {
  // The server merges the payload into the envelope, so handlers read flat keys.
  return {
    version: 1, type, session_id: "sess", conversation_id: "meet",
    sequence: 1, timestamp: "2026-10-13T00:00:00Z", ...data, data,
  } as RealtimeEvent;
}

const VIEW: CaptionView = {
  caption_mode: "both", listening_language: "en", speakerNames: {},
};

function final(over: Record<string, unknown> = {}) {
  return evt("transcript.final", {
    speaker_id: AMAN, display_name: "Aman", utterance_id: TURN, segment_id: SEG,
    seq: 3, language: "hi", text: "नमस्ते", is_final: true,
    start_wall_ms: 1000, duration_ms: 900, ...over,
  });
}

function translated(over: Record<string, unknown> = {}) {
  return evt("translation.final", {
    speaker_id: AMAN, display_name: "Aman", utterance_id: TURN, segment_id: SEG,
    seq: 3, source_language: "hi", target_language: "en", text: "Hello",
    latency_ms: 420, start_wall_ms: 1000, duration_ms: 900, ...over,
  });
}

const ids = (lines: CaptionLine[]) => lines.map((c) => c.id);

describe("caption reducer", () => {
  it("keeps one line per turn from the partial through the final", () => {
    let lines = reduceCaptions([], evt("transcript.partial", {
      speaker_id: AMAN, display_name: "Aman", utterance_id: TURN, seq: 3,
      language: "hi", text: "नम", is_final: false,
    }), VIEW);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({ id: TURN, original: "नम", partial: true,
      originalFinal: false });

    lines = reduceCaptions(lines, final(), VIEW);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      id: TURN, original: "नमस्ते", partial: false, originalFinal: true,
      segmentId: SEG, seq: 3, startWallMs: 1000, durationMs: 900,
    });
  });

  it("puts the translation on the turn it translates, not on the newest line", () => {
    // Aman's turn is still in flight when Beth's identical-name caption arrives:
    // a name-based match would translate the wrong line.
    let lines = reduceCaptions([], final(), VIEW);
    lines = reduceCaptions(lines, final({
      speaker_id: BETH, utterance_id: "eeeeeeee-1111-4c6d-8e9f-0a1b2c3d4e5f",
      segment_id: "ffffffff-1111-4c6d-8e9f-0a1b2c3d4e5f", seq: 4, text: "अन्य बात",
    }), VIEW);

    lines = reduceCaptions(lines, translated(), VIEW);

    expect(lines).toHaveLength(2);
    expect(lines[0].translated).toBe("Hello");
    expect(lines[1].translated).toBeUndefined();
  });

  it("matches on the turn id, never on the speaker label", () => {
    // Two different people, one display name: the only thing that can tell their
    // captions apart is the id the server put on them.
    const bethTurn = "eeeeeeee-1111-4c6d-8e9f-0a1b2c3d4e5f";
    let lines = reduceCaptions([], final(), VIEW);
    lines = reduceCaptions(lines, final({
      speaker_id: BETH, utterance_id: bethTurn, seq: 4,
      segment_id: "cccccccc-1111-4c6d-8e9f-0a1b2c3d4e5f", text: "दूसरी बात",
    }), VIEW);
    lines = reduceCaptions(lines, translated({
      utterance_id: bethTurn, seq: 4, segment_id: "cccccccc-1111-4c6d-8e9f-0a1b2c3d4e5f",
    }), VIEW);

    expect(lines.map((c) => c.translated)).toEqual([undefined, "Hello"]);
    expect(ids(lines)).toEqual([TURN, bethTurn]);   // one line each, in turn order
    expect(lines.every((c) => c.speaker === "Aman")).toBe(true);
    expect(setPlayback(lines, bethTurn, "playing")[1].playback).toBe("playing");
  });

  it("replaces a duplicate translation for the same turn and language", () => {
    let lines = reduceCaptions([], final(), VIEW);
    lines = reduceCaptions(lines, translated(), VIEW);
    lines = reduceCaptions(lines, translated({ text: "Hello.", latency_ms: 500 }), VIEW);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({ translated: "Hello.", latencyMs: 500 });
  });

  it("creates its own line for a translation whose caption was never seen", () => {
    // A reconnect replays translations without the originals they belong to.
    const lines = reduceCaptions([], translated(), VIEW);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      id: `tr:${TURN}:en`, translated: "Hello",
      startWallMs: 1000, durationMs: 900,
    });
    expect(lines[0].original).toBeUndefined();
  });

  it("keeps a line that has a translation when the original is hidden", () => {
    const translatedOnly: CaptionView = { ...VIEW, caption_mode: "translated" };
    let lines = reduceCaptions([], final(), translatedOnly);
    expect(lines[0].original).toBeUndefined();
    lines = reduceCaptions(lines, translated(), translatedOnly);
    expect(lines[0].translated).toBe("Hello");
  });

  it("ignores other languages and the original-only caption mode", () => {
    expect(reduceCaptions([], final(), VIEW)).toHaveLength(1);
    expect(reduceCaptions([], translated({ target_language: "ur" }), VIEW)).toHaveLength(0);
    expect(reduceCaptions([], translated(), { ...VIEW, caption_mode: "original" }))
      .toHaveLength(0);
  });

  it("reports the latency of the turn that was measured", () => {
    let lines = reduceCaptions([], final(), VIEW);
    lines = reduceCaptions(lines, translated(), VIEW);
    // A second, later turn that has not been measured must not steal the report.
    lines = reduceCaptions(lines, final({
      utterance_id: "aaaaaaaa-2222-4c6d-8e9f-0a1b2c3d4e5f",
      segment_id: "bbbbbbbb-2222-4c6d-8e9f-0a1b2c3d4e5f", seq: 4, text: "अगला",
    }), VIEW);
    lines = reduceCaptions(lines, evt("latency.report", {
      utterance_id: TURN, segment_id: SEG, target_language: "en", seq: 3,
      total_e2e_latency_ms: 1500,
    }), VIEW);

    expect(lines[0].latencyMs).toBe(1500);
    expect(lines[1].latencyMs).toBeUndefined();
  });

  it("falls back to the segment id when an older server sent no utterance id", () => {
    let lines = reduceCaptions([], final({ utterance_id: undefined }), VIEW);
    lines = reduceCaptions(lines, translated({ utterance_id: undefined }), VIEW);
    expect(lines).toHaveLength(1);
    expect(lines[0].translated).toBe("Hello");
  });

  it("records a failed translation once per segment", () => {
    const failure = evt("translation.failed", {
      speaker_id: AMAN, segment_id: SEG, target_language: "en",
      user_message: "Translation unavailable",
    });
    let lines = reduceCaptions([], failure, VIEW);
    lines = reduceCaptions(lines, failure, VIEW);
    expect(lines).toHaveLength(1);
    expect(lines[0].failed).toBe("Translation unavailable");
  });

  it("ignores a failed translation destined for another listener's language", () => {
    // The server broadcasts one failure per (segment, target language); a
    // listener who never asked for that language must not see a red line.
    const other = evt("translation.failed", {
      speaker_id: AMAN, segment_id: SEG, target_language: "hi",
      user_message: "Translation unavailable",
    });
    expect(reduceCaptions([], other, VIEW)).toHaveLength(0);
  });

  it("says the turn failed with the server's own message", () => {
    // `translation.failed` carries `message`; older builds used `user_message`.
    const lines = reduceCaptions([], evt("translation.failed", {
      speaker_id: AMAN, segment_id: SEG, target_language: "en",
      message: "Translation is taking longer than expected.",
    }), VIEW);
    expect(lines[0].failed).toBe("Translation is taking longer than expected.");
  });

  it("retires a partial caption for a turn that produced no words", () => {
    let lines = reduceCaptions([], evt("transcript.partial", {
      speaker_id: AMAN, utterance_id: TURN, seq: 3, language: "hi", text: "नम",
    }), VIEW);
    lines = reduceCaptions(lines, evt("speech.ended", {
      speaker_id: AMAN, utterance_id: TURN, empty: true,
    }), VIEW);
    expect(lines).toHaveLength(0);
  });

  it("keeps the newest lines when the list is bounded", () => {
    let lines: CaptionLine[] = [];
    for (let i = 0; i < 120; i++) {
      lines = reduceCaptions(lines, final({ utterance_id: `u${i}`, seq: i }), VIEW);
    }
    expect(lines.length).toBeLessThanOrEqual(80);
    expect(lines[lines.length - 1].id).toBe("u119");
  });

  it("uses the speaker name the room already knows for this participant", () => {
    const lines = reduceCaptions([], final({ display_name: undefined }), {
      ...VIEW, speakerNames: { [AMAN]: "Aman K." },
    });
    expect(lines[0].speaker).toBe("Aman K.");
  });

  it("leaves the list alone for events that are not captions", () => {
    const lines = reduceCaptions([], final(), VIEW);
    expect(reduceCaptions(lines, evt("pong", {}), VIEW)).toBe(lines);
  });
});

describe("caption playback state", () => {
  it("marks only the named turn", () => {
    let lines = reduceCaptions([], final(), VIEW);
    lines = reduceCaptions(lines, final({
      utterance_id: "zzzzzzzz-1111-4c6d-8e9f-0a1b2c3d4e5f",
      segment_id: "yyyyyyyy-1111-4c6d-8e9f-0a1b2c3d4e5f",
    }), VIEW);
    lines = setPlayback(lines, TURN, "playing");
    expect(lines[0].playback).toBe("playing");
    expect(lines[1].playback).toBe("idle");

    lines = setPlayback(lines, TURN, "played");
    expect(lines[0].playback).toBe("played");
    // a finished line never goes backwards when the player reports another
    lines = setPlayback(lines, "unknown-turn", "playing");
    expect(lines[0].playback).toBe("played");
  });

  it("marks a flushed turn's translated audio as dropped", () => {
    let lines = reduceCaptions(reduceCaptions([], final(), VIEW), translated(), VIEW);
    lines = setPlayback(lines, TURN, "dropped");
    expect(lines[0].playback).toBe("dropped");
    // the caption text itself survives a barge-in flush
    expect(lines[0].translated).toBe("Hello");
  });

  it("finds the turn when only the translated line is on screen", () => {
    // After a reconnect the replay carries translations but not the originals,
    // so the line is keyed `tr:<turn>:<lang>` while the player names the turn.
    let lines = reduceCaptions([], translated(), VIEW);
    expect(lines[0].id).toBe(`tr:${TURN}:en`);
    lines = setPlayback(lines, TURN, "playing");
    expect(lines[0].playback).toBe("playing");
  });
});
