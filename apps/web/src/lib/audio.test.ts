import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AudioPlayer, b64ToBytes } from "./audio";

// Setup Web Audio Mock
class MockAudioBufferSourceNode {
  buffer: any = null;
  onended: (() => void) | null = null;
  started = false;
  stopped = false;

  connect(_dest: any) {}
  start() {
    this.started = true;
  }
  stop() {
    this.stopped = true;
    if (this.onended) {
      const cb = this.onended;
      this.onended = null;
      cb();
    }
  }
}

class MockGainNode {
  gain = {
    value: 1.0,
    setValueAtTime: vi.fn(),
    setTargetAtTime: vi.fn(),
  };
  connect(_dest: any) {}
  disconnect() {}
}

class MockAudioContext {
  state: AudioContextState = "suspended";
  currentTime = 0;
  destination = {};
  private listeners: Record<string, (() => void)[]> = {};

  addEventListener(event: string, cb: () => void) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(cb);
  }

  async resume() {
    this.state = "running";
    this.listeners["statechange"]?.forEach((cb) => cb());
  }

  async close() {
    this.state = "closed";
    this.listeners["statechange"]?.forEach((cb) => cb());
  }

  createGain() {
    return new MockGainNode();
  }

  createBufferSource() {
    return new MockAudioBufferSourceNode();
  }

  async decodeAudioData(buf: ArrayBuffer): Promise<any> {
    return {
      duration: 1.0,
      length: buf.byteLength,
      sampleRate: 16000,
      numberOfChannels: 1,
    };
  }
}

describe("b64ToBytes", () => {
  it("decodes base64 strings into Uint8Array", () => {
    // "RIFF" in base64 is "UklGRg=="
    const bytes = b64ToBytes("UklGRg==");
    expect(bytes).toEqual(new Uint8Array([0x52, 0x49, 0x46, 0x46]));
  });
});

describe("AudioPlayer", () => {
  let originalAudioContext: any;

  beforeEach(() => {
    originalAudioContext = (globalThis as any).AudioContext;
    (globalThis as any).AudioContext = MockAudioContext;
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    (globalThis as any).AudioContext = originalAudioContext;
  });

  it("handles AudioContext suspended state and reports state transitions", async () => {
    const onState = vi.fn();
    const player = new AudioPlayer(undefined, undefined, onState);

    expect(player.isSuspended).toBe(true);
    await player.resumeContext();
    expect(player.isSuspended).toBe(false);
    expect(onState).toHaveBeenCalledWith("running");

    player.dispose();
  });

  it("deduplicates binary and JSON deliveries of the same chunk", async () => {
    const errorCb = vi.fn();
    const stateCb = vi.fn();
    const player = new AudioPlayer(errorCb, stateCb);

    const dummyWav = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0x00, 0x00]);
    const tag = "utterance123";

    // 1. Deliver binary chunk (primary)
    await player.deliver(dummyWav, tag, {
      source: "binary",
      sequence: 1,
      chunkIndex: 0,
      speakerId: "speaker-1",
      utteranceId: "turn-1",
    });

    // 2. Deliver JSON chunk for the same chunk index (fallback / duplicate)
    await player.deliver(dummyWav, tag, {
      source: "json",
      sequence: 1,
      chunkIndex: 0,
      speakerId: "speaker-1",
      utteranceId: "turn-1",
    });

    // Advance grace timer
    vi.advanceTimersByTime(500);

    // Queue should have only played 1 item, not duplicate
    expect(player.debugPlayedCount()).toBe(1);
    expect(player.debugQueueLength()).toBe(0);

    player.dispose();
  });

  it("barge-in cancelSpeaker drops in-flight chunks and transitions turn to dropped", async () => {
    const errorCb = vi.fn();
    const stateCb = vi.fn();
    const player = new AudioPlayer(errorCb, stateCb);

    const dummyWav = new Uint8Array([0x52, 0x49, 0x46, 0x46]);
    const tag = "utt-speaker-1";

    // Enqueue 2 chunks
    await player.deliver(dummyWav, tag, {
      source: "binary",
      sequence: 1,
      chunkIndex: 0,
      speakerId: "spk-1",
      utteranceId: "turn-spk-1",
    });

    await player.deliver(dummyWav, tag, {
      source: "binary",
      sequence: 1,
      chunkIndex: 1,
      speakerId: "spk-1",
      utteranceId: "turn-spk-1",
    });

    // Interruption / barge-in happens
    const droppedCount = player.cancelSpeaker("spk-1");
    expect(droppedCount).toBeGreaterThanOrEqual(1);

    // Turn should be reported as dropped to captions
    expect(stateCb).toHaveBeenCalledWith("turn-spk-1", "dropped");

    player.dispose();
  });

  it("cancelTag drops queued chunks for a specific utterance tag", async () => {
    const player = new AudioPlayer();
    const dummyWav = new Uint8Array([0x52, 0x49, 0x46, 0x46]);

    await player.deliver(dummyWav, "tag-cancel", {
      source: "binary",
      sequence: 1,
      chunkIndex: 0,
    });

    player.cancelTag("tag-cancel");
    expect(player.debugQueueLength()).toBe(0);

    player.dispose();
  });

  it("stopAll drops all pending items and notifies dropped state", async () => {
    const stateCb = vi.fn();
    const player = new AudioPlayer(undefined, stateCb);
    const dummyWav = new Uint8Array([0x52, 0x49, 0x46, 0x46]);

    await player.deliver(dummyWav, "tag-all-1", {
      source: "binary",
      sequence: 1,
      chunkIndex: 0,
      utteranceId: "turn-all-1",
    });

    await player.deliver(dummyWav, "tag-all-2", {
      source: "binary",
      sequence: 1,
      chunkIndex: 0,
      utteranceId: "turn-all-2",
    });

    await player.stopAll();
    expect(player.debugQueueLength()).toBe(0);
    expect(stateCb).toHaveBeenCalledWith("turn-all-1", "dropped");

    player.dispose();
  });
});
