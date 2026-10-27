import { describe, expect, it } from "vitest";
import {
  MAX_CAPTION_LINES,
  reduceCaptions,
  setPlayback,
  isSameLanguage,
  type CaptionLine,
  type CaptionView,
} from "./captions";
import type { RealtimeEvent } from "./types";

describe("reduceCaptions", () => {
  const view: CaptionView = {
    caption_mode: "both",
    listening_language: "en",
    speakerNames: { "user-1": "Alice" },
  };

  function makeEvt(type: string, data: Record<string, unknown> = {}): RealtimeEvent {
    return {
      version: 1,
      type: type as any,
      session_id: "test-sess",
      conversation_id: "test-conv",
      sequence: 1,
      timestamp: "2026-10-27T00:00:00Z",
      ...data,
    };
  }

  it("handles transcript.partial followed by transcript.final", () => {
    let lines: CaptionLine[] = [];

    const partialEvt: RealtimeEvent = makeEvt("transcript.partial", {
      utterance_id: "turn-101",
      speaker_id: "user-1",
      language: "es",
      text: "Hola como",
      start_wall_ms: 1000,
    });

    lines = reduceCaptions(lines, partialEvt, view);
    expect(lines).toHaveLength(1);
    expect(lines[0].id).toBe("turn-101");
    expect(lines[0].original).toBe("Hola como");
    expect(lines[0].partial).toBe(true);
    expect(lines[0].originalFinal).toBe(false);
    expect(lines[0].speaker).toBe("Alice");

    const finalEvt: RealtimeEvent = makeEvt("transcript.final", {
      utterance_id: "turn-101",
      speaker_id: "user-1",
      language: "es",
      text: "Hola como estas?",
      duration_ms: 1500,
    });

    lines = reduceCaptions(lines, finalEvt, view);
    expect(lines).toHaveLength(1);
    expect(lines[0].original).toBe("Hola como estas?");
    expect(lines[0].partial).toBe(false);
    expect(lines[0].originalFinal).toBe(true);
    expect(lines[0].durationMs).toBe(1500);
  });

  it("attaches translation.final to an existing turn", () => {
    let lines: CaptionLine[] = [];

    lines = reduceCaptions(
      lines,
      makeEvt("transcript.final", {
        utterance_id: "turn-202",
        speaker_id: "user-1",
        language: "es",
        text: "Buenos dias",
      }),
      view,
    );

    const transEvt: RealtimeEvent = makeEvt("translation.final", {
      utterance_id: "turn-202",
      target_language: "en",
      text: "Good morning",
      latency_ms: 420,
    });

    lines = reduceCaptions(lines, transEvt, view);
    expect(lines).toHaveLength(1);
    expect(lines[0].translated).toBe("Good morning");
    expect(lines[0].translatedLang).toBe("en");
    expect(lines[0].latencyMs).toBe(420);
  });

  it("ignores translations intended for other listening languages", () => {
    let lines: CaptionLine[] = [];

    lines = reduceCaptions(
      lines,
      makeEvt("transcript.final", {
        utterance_id: "turn-303",
        speaker_id: "user-1",
        language: "en",
        text: "Hello",
      }),
      view,
    );

    const transEvt: RealtimeEvent = makeEvt("translation.final", {
      utterance_id: "turn-303",
      target_language: "de", // listening_language is 'en'
      text: "Hallo",
    });

    lines = reduceCaptions(lines, transEvt, view);
    expect(lines[0].translated).toBeUndefined();
  });

  it("records translation.failed for listener's target language", () => {
    let lines: CaptionLine[] = [];

    const failEvt: RealtimeEvent = makeEvt("translation.failed", {
      segment_id: "seg-fail-1",
      target_language: "en",
      user_message: "Neural MT timeout",
    });

    lines = reduceCaptions(lines, failEvt, view);
    expect(lines).toHaveLength(1);
    expect(lines[0].id).toBe("fail:seg-fail-1");
    expect(lines[0].failed).toBe("Neural MT timeout");
  });

  it("drops turn on speech.ended with empty: true", () => {
    let lines: CaptionLine[] = [];

    lines = reduceCaptions(
      lines,
      makeEvt("transcript.partial", {
        utterance_id: "turn-empty",
        speaker_id: "user-1",
        language: "en",
        text: "",
      }),
      view,
    );
    expect(lines).toHaveLength(1);

    lines = reduceCaptions(
      lines,
      makeEvt("speech.ended", {
        utterance_id: "turn-empty",
        empty: true,
      }),
      view,
    );
    expect(lines).toHaveLength(0);
  });

  it("enforces MAX_CAPTION_LINES boundary", () => {
    let lines: CaptionLine[] = [];
    for (let i = 0; i < MAX_CAPTION_LINES + 20; i++) {
      lines = reduceCaptions(
        lines,
        makeEvt("transcript.final", {
          utterance_id: `turn-batch-${i}`,
          speaker_id: "user-1",
          language: "en",
          text: `Line ${i}`,
        }),
        view,
      );
    }
    expect(lines.length).toBe(MAX_CAPTION_LINES);
    expect(lines[lines.length - 1].id).toBe(`turn-batch-${MAX_CAPTION_LINES + 19}`);
  });
});

describe("setPlayback", () => {
  it("transitions turn playback state to playing, played, and dropped", () => {
    let lines: CaptionLine[] = [
      {
        id: "turn-p1",
        speakerId: "user-1",
        speaker: "Alice",
        language: "en",
        originalFinal: true,
        partial: false,
        playback: "idle",
      },
    ];

    lines = setPlayback(lines, "turn-p1", "playing");
    expect(lines[0].playback).toBe("playing");

    lines = setPlayback(lines, "turn-p1", "played");
    expect(lines[0].playback).toBe("played");

    // Interrupted by barge-in
    lines = setPlayback(lines, "turn-p1", "dropped");
    expect(lines[0].playback).toBe("dropped");
  });

  it("handles standalone translated key prefixes (tr:turn:lang)", () => {
    let lines: CaptionLine[] = [
      {
        id: "tr:turn-p2:en",
        speakerId: "user-1",
        speaker: "Alice",
        language: "es",
        originalFinal: true,
        partial: false,
        playback: "idle",
      },
    ];

    lines = setPlayback(lines, "turn-p2", "dropped");
    expect(lines[0].playback).toBe("dropped");
  });
});

describe("isSameLanguage & subtag tolerance", () => {
  it("matches identical languages and regional subtags", () => {
    expect(isSameLanguage("en", "en")).toBe(true);
    expect(isSameLanguage("en-US", "en")).toBe(true);
    expect(isSameLanguage("en", "EN-US")).toBe(true);
    expect(isSameLanguage("es-ES", "es")).toBe(true);
    expect(isSameLanguage("es", "es-MX")).toBe(true);
    expect(isSameLanguage("zh-CN", "zh")).toBe(true);
    expect(isSameLanguage("en", "es")).toBe(false);
  });

  it("attaches translation.final when target_language has regional subtag (en-US vs en)", () => {
    const view: CaptionView = {
      caption_mode: "both",
      listening_language: "en",
      speakerNames: { "user-1": "Alice" },
    };
    let lines: CaptionLine[] = reduceCaptions(
      [],
      {
        version: 1,
        type: "transcript.final" as any,
        session_id: "s1",
        conversation_id: "c1",
        sequence: 1,
        timestamp: "2026-10-27T00:00:00Z",
        utterance_id: "turn-regional-1",
        speaker_id: "user-1",
        language: "es",
        text: "Hola amigos",
      },
      view
    );

    lines = reduceCaptions(
      lines,
      {
        version: 1,
        type: "translation.final" as any,
        session_id: "s1",
        conversation_id: "c1",
        sequence: 2,
        timestamp: "2026-10-27T00:00:01Z",
        utterance_id: "turn-regional-1",
        target_language: "en-US",
        text: "Hello friends",
        latency_ms: 250,
      },
      view
    );

    expect(lines).toHaveLength(1);
    expect(lines[0].translated).toBe("Hello friends");
  });
});
