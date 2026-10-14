/**
 * Media resilience (roadmap Phase 6).
 *
 * Two failures that used to be invisible:
 *   1. A WebSocket can be half-open — readyState stays OPEN while the network
 *      drops every frame. The room kept reading "Connected" and the speaker's
 *      audio went nowhere. The heartbeat must notice the silence and reconnect.
 *   2. A microphone can be unplugged or taken by another app mid-turn. The
 *      AudioWorklet simply stops producing frames, so the user kept talking to
 *      nothing while the UI said everything was fine. The capture track's own
 *      ended/mute events have to reach the UI — and our deliberate teardown
 *      must not be reported as a loss.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  api: vi.fn(),
  getAccessToken: () => "jwt",
  getApiBaseUrl: () => "",
}));

import { MeetingSocket, type SocketState } from "../ws";
import { MicCapture } from "../audio";

// --------------------------------------------------------------------------- //
// Fake WebSocket
// --------------------------------------------------------------------------- //

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  readyState = 0;
  binaryType = "blob";
  bufferedAmount = 0;
  sent: string[] = [];
  closed = 0;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code?: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) { this.sent.push(String(data)); }
  close() { this.closed += 1; this.readyState = FakeWebSocket.CLOSED; this.onclose?.({ code: 1006 }); }

  simulateOpen() { this.readyState = FakeWebSocket.OPEN; this.onopen?.(); }
  simulateMessage(obj: unknown) { this.onmessage?.({ data: JSON.stringify(obj) }); }
  pingsSent() { return this.sent.filter((s) => s.includes('"ping"')).length; }
}

const envelope = (type: string, data: Record<string, unknown> = {}) => ({
  version: 1, type, session_id: "s1", conversation_id: "m1",
  sequence: null, timestamp: "2026-10-14T00:00:00Z", data,
});

function makeSocket(states: SocketState[], quality: number[]) {
  return new MeetingSocket({
    meetingId: "m1",
    displayName: "Test",
    preferences: {
      speaking_language: "en", listening_language: "hi",
      audio_mode: "translated", caption_mode: "translated", latency_mode: "balanced",
    },
    onEvent: () => {},
    onBinary: () => {},
    onStateChange: (s) => states.push(s),
    onQuality: (rtt) => quality.push(rtt),
  });
}

describe("MeetingSocket heartbeat", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("measures the round trip from the pong the server echoes", () => {
    const states: SocketState[] = [];
    const quality: number[] = [];
    makeSocket(states, quality).connect();
    const ws = FakeWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage(envelope("session.created"));

    // The server echoes our own client_ts, so one clock measures the round trip.
    ws.simulateMessage(envelope("pong", { client_ts: Date.now() - 180 }));
    expect(quality).toHaveLength(1);
    expect(quality[0]).toBeGreaterThanOrEqual(175);
    expect(quality[0]).toBeLessThan(1000);
  });

  it("keeps pinging while the server answers", () => {
    const states: SocketState[] = [];
    const socket = makeSocket(states, []);
    socket.connect();
    const ws = FakeWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage(envelope("session.created"));

    for (let i = 0; i < 3; i++) {
      vi.advanceTimersByTime(20_000);
      ws.simulateMessage(envelope("pong", { client_ts: Date.now() - 40 }));
    }
    expect(ws.pingsSent()).toBe(3);
    expect(ws.closed).toBe(0);
    expect(states).not.toContain("reconnecting");
  });

  it("declares an OPEN-but-silent socket dead and reconnects", () => {
    const states: SocketState[] = [];
    const socket = makeSocket(states, []);
    socket.connect();
    const ws = FakeWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage(envelope("session.created"));
    expect(states).toContain("joined");

    // Nothing arrives at all: not a close, not a message — the half-open case.
    // readyState stays OPEN the whole time.
    vi.advanceTimersByTime(65_000);
    expect(ws.closed).toBe(0); // still patient at one missed cycle
    vi.advanceTimersByTime(20_000);

    expect(ws.closed).toBe(1);
    expect(states[states.length - 1]).toBe("reconnecting");
  });

  it("treats any inbound frame as proof of life, not only a pong", () => {
    const states: SocketState[] = [];
    const socket = makeSocket(states, []);
    socket.connect();
    const ws = FakeWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage(envelope("session.created"));

    // Two minutes of captions and audio, zero pongs (an older server).
    for (let i = 0; i < 6; i++) {
      vi.advanceTimersByTime(20_000);
      ws.simulateMessage(envelope("transcript.partial", { text: "hello" }));
    }
    expect(ws.closed).toBe(0);
    expect(states).not.toContain("reconnecting");
  });
});

// --------------------------------------------------------------------------- //
// MicCapture device loss
// --------------------------------------------------------------------------- //

class FakeTrack {
  kind = "audio";
  listeners: Record<string, Array<() => void>> = {};
  addEventListener(type: string, fn: () => void) {
    (this.listeners[type] ||= []).push(fn);
  }
  removeEventListener() {}
  emit(type: string) { (this.listeners[type] || []).forEach((fn) => fn()); }
  stop() {}
  asTrack() { return this as unknown as MediaStreamTrack; }
}

function installFakeCaptureEnv() {
  const track = new FakeTrack();
  class FakeCtx {
    state = "running";
    audioWorklet = { addModule: vi.fn(async () => {}) };
    resume = vi.fn(async () => {});
    close = vi.fn(async () => {});
    createMediaStreamSource = vi.fn(() => ({ connect: vi.fn() }));
  }
  class FakeNode {
    port = { onmessage: null as ((e: MessageEvent) => void) | null };
    connect() {}
    disconnect() {}
  }
  vi.stubGlobal("AudioContext", FakeCtx);
  vi.stubGlobal("AudioWorkletNode", FakeNode);
  vi.stubGlobal("MediaStream", class {
    constructor(public tracks: unknown[]) {}
    getAudioTracks() { return this.tracks as MediaStreamTrack[]; }
    getTracks() { return this.tracks as MediaStreamTrack[]; }
  });
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => new MediaStream([track.asTrack()])) },
  });
  vi.stubGlobal("Blob", class { constructor(public parts: unknown[]) {} });
  vi.stubGlobal("URL", Object.assign(vi.fn(), {
    createObjectURL: vi.fn(() => "blob:x"),
    revokeObjectURL: vi.fn(),
  }));
  return track;
}

describe("MicCapture device loss", () => {
  beforeEach(() => { vi.unstubAllGlobals(); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("reports the input dying so the room can say so", async () => {
    const track = installFakeCaptureEnv();
    const lost: Array<"ended" | "mute"> = [];
    const mic = new MicCapture();
    await mic.start(16000, () => {}, { onLost: (r) => lost.push(r) });

    track.emit("ended");
    track.emit("mute");
    expect(lost).toEqual(["ended", "mute"]);
    mic.stop();
  });

  it("does not report a loss the app caused by stopping or switching", async () => {
    const track = installFakeCaptureEnv();
    const lost: Array<"ended" | "mute"> = [];
    const mic = new MicCapture();
    await mic.start(16000, () => {}, { onLost: (r) => lost.push(r) });

    mic.stop(); // every device switch and the leave-room path run through here
    track.emit("ended");
    track.emit("mute");
    expect(lost).toEqual([]);
  });
});
