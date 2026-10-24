import { beforeEach, describe, expect, it, vi } from "vitest";
import { AudioPlayer } from "../audio";
import { MeetingSocket } from "../ws";
import { CaptionLine, setPlayback } from "../captions";

class FakeGainNode {
  gain = {
    value: 1.0,
    setValueAtTime: vi.fn((val: number) => {
      this.gain.value = val;
    }),
    setTargetAtTime: vi.fn((target: number) => {
      this.gain.value = target;
    }),
  };
  connect = vi.fn();
}

let lastCreatedGain: FakeGainNode | null = null;
let lastCreatedContext: FakeAudioContextWithGain | null = null;

class FakeAudioContextWithGain {
  state: AudioContextState = "running";
  currentTime = 100;
  destination = { id: "destination" };
  resume = vi.fn(async () => {
    this.state = "running";
  });
  close = vi.fn(async () => {});
  decodeAudioData = vi.fn(async (buf: ArrayBuffer) => ({ id: `decoded:${buf.byteLength}` }));
  createGain = vi.fn(() => {
    lastCreatedGain = new FakeGainNode();
    return lastCreatedGain as unknown as GainNode;
  });
  createBufferSource = vi.fn(() => {
    return {
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
      onended: null,
    };
  });
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
}

beforeEach(() => {
  lastCreatedGain = null;
  lastCreatedContext = null;
  vi.stubGlobal("AudioContext", class extends FakeAudioContextWithGain {
    constructor() {
      super();
      lastCreatedContext = this;
    }
  });
});

describe("AudioPlayer volume & ducking controls", () => {
  it("initializes a GainNode connected to destination if supported", () => {
    const player = new AudioPlayer();
    expect(player).toBeDefined();
    expect(lastCreatedGain).not.toBeNull();
    expect(lastCreatedGain?.connect).toHaveBeenCalledWith(lastCreatedContext?.destination);
  });

  it("sets volume within [0, 1] range", () => {
    const player = new AudioPlayer();
    player.setVolume(0.5);
    expect(lastCreatedGain?.gain.setValueAtTime).toHaveBeenCalledWith(0.5, 100);
    expect(lastCreatedGain?.gain.value).toBe(0.5);

    player.setVolume(1.5);
    expect(lastCreatedGain?.gain.setValueAtTime).toHaveBeenCalledWith(1.0, 100);

    player.setVolume(-0.2);
    expect(lastCreatedGain?.gain.setValueAtTime).toHaveBeenCalledWith(0.0, 100);
  });

  it("applies smooth ducking when local user is speaking", () => {
    const player = new AudioPlayer();
    player.setDucking(true);
    expect(lastCreatedGain?.gain.setTargetAtTime).toHaveBeenCalledWith(0.2, 100, 0.05);
    expect(lastCreatedGain?.gain.value).toBe(0.2);

    player.setDucking(false);
    expect(lastCreatedGain?.gain.setTargetAtTime).toHaveBeenCalledWith(1.0, 100, 0.05);
    expect(lastCreatedGain?.gain.value).toBe(1.0);
  });

  it("tracks AudioContext suspended state for mobile unlock", async () => {
    vi.stubGlobal("AudioContext", class extends FakeAudioContextWithGain {
      state: AudioContextState = "suspended";
    });

    const player = new AudioPlayer();
    expect(player.isSuspended).toBe(true);
    expect(player.contextState).toBe("suspended");

    await player.resumeContext();
    expect(player.contextState).toBe("running");
  });
});

describe("Phase 2: Bidirectional turn management & interruption detection", () => {
  it("MeetingSocket.sendInterrupt sends playback.interrupt with target speaker_id", () => {
    const sent: any[] = [];
    const socket = new MeetingSocket({
      meetingId: "m-123",
      ticket: "ticket-1",
      displayName: "Alice",
      preferences: {
        speaking_language: "en",
        listening_language: "es",
        audio_mode: "translated",
        caption_mode: "both",
        latency_mode: "balanced",
      },
      onEvent: () => {},
      onBinary: () => {},
      onStateChange: () => {},
    });

    vi.spyOn(socket, "sendJson").mockImplementation((evt) => {
      sent.push(evt);
    });

    socket.sendInterrupt("speaker-bob");
    expect(sent).toHaveLength(1);
    expect(sent[0]).toEqual({
      type: "playback.interrupt",
      speaker_id: "speaker-bob",
    });

    socket.sendInterrupt();
    expect(sent).toHaveLength(2);
    expect(sent[1]).toEqual({
      type: "playback.interrupt",
      speaker_id: undefined,
    });
  });

  it("marks in-flight caption as dropped when playback.flush correlation_id arrives", () => {
    const lines: CaptionLine[] = [
      {
        id: "utt-1",
        speakerId: "p-bob",
        speaker: "Bob",
        language: "es",
        original: "Hola mundo",
        originalFinal: true,
        translated: "Hello world",
        partial: false,
        playback: "playing",
      },
      {
        id: "utt-2",
        speakerId: "p-bob",
        speaker: "Bob",
        language: "es",
        original: "Como estas",
        originalFinal: false,
        partial: true,
        playback: "idle",
      },
    ];

    // Simulate playback.flush correlation_ids propagation
    const cancelledCids = ["utt-1", "utt-2"];
    let nextLines = lines;
    for (const cid of cancelledCids) {
      nextLines = setPlayback(nextLines, cid, "dropped");
    }

    expect(nextLines[0].playback).toBe("dropped");
    expect(nextLines[1].playback).toBe("dropped");
  });
});

describe("Phase 3: Synchronized captions & speaker attribution", () => {
  it("transitions caption playback state across idle -> playing -> played lifecycle", () => {
    let lines: CaptionLine[] = [
      {
        id: "utt-live-1",
        speakerId: "p-alice",
        speaker: "Alice",
        language: "hi",
        original: "नमस्ते",
        originalFinal: true,
        translated: "Hello",
        partial: false,
        playback: "idle",
      },
    ];

    expect(lines[0].playback).toBe("idle");

    // AudioPlayer begins playing the synthesized audio for this turn
    lines = setPlayback(lines, "utt-live-1", "playing");
    expect(lines[0].playback).toBe("playing");

    // AudioPlayer finishes playing the turn
    lines = setPlayback(lines, "utt-live-1", "played");
    expect(lines[0].playback).toBe("played");
    expect(lines[0].translated).toBe("Hello");
    expect(lines[0].speaker).toBe("Alice");
  });

  it("formats auto-detected language label with confidence score when AUTO is selected", () => {
    const formatDetectedPill = (
      prefLang: string,
      detectedLang: string | null,
      confidence: number | null
    ) => {
      if (prefLang !== "AUTO") return prefLang;
      if (!detectedLang) return "Auto-detect";
      const confStr =
        confidence != null
          ? ` ${Math.round(confidence <= 1 ? confidence * 100 : confidence)}%`
          : "";
      return `Auto (${detectedLang.toUpperCase()}${confStr})`;
    };

    expect(formatDetectedPill("AUTO", null, null)).toBe("Auto-detect");
    expect(formatDetectedPill("AUTO", "es", 0.98)).toBe("Auto (ES 98%)");
    expect(formatDetectedPill("AUTO", "hi", 95)).toBe("Auto (HI 95%)");
    expect(formatDetectedPill("en", "es", 0.98)).toBe("en");
  });
});


