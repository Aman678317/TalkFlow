/**
 * P2P mesh resilience (meeting/video remediation P1).
 *
 * Three failures that used to end or lie about a call:
 *   1. Every Wi-Fi -> mobile handoff routes the PC through 'disconnected' for a
 *      few seconds — the manager used to kill the peer instantly, so the call
 *      died on any network switch. Now: grace, then one ICE restart, then a
 *      clean re-dial.
 *   2. ICE configurations were a hardcoded STUN list; most mobile-carrier
 *      networks need TURN, so the mesh silently never connected. ICE servers
 *      are now deployment-configurable (room-member endpoint, test 3).
 *   3. A 'failed' state that never recovered kept the tile forever while the
 *      connectionInfo pill said "Connected · Realtime Translation Active".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// --------------------------------------------------------------------------- //
// Fake RTCPeerConnection: enough surface for createPeerConnection + signaling
// --------------------------------------------------------------------------- //

type FakeSender = {
  _kind?: string;
  track: MediaStreamTrack | null;
  replaceTrack: ReturnType<typeof vi.fn>;
};

class FakeRTCPeerConnection {
  static instances: FakeRTCPeerConnection[] = [];

  signalingState = "stable" as RTCSignalingState;
  connectionState = "new" as RTCPeerConnectionState;
  onicecandidate: ((e: any) => void) | null = null;
  onnegotiationneeded: (() => void) | null = null;
  ontrack: ((e: any) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  senders: FakeSender[] = [];
  offers: Array<Record<string, unknown>> = [];
  localDescriptions: Array<Record<string, unknown>> = [];
  closed = 0;

  constructor(public config: RTCConfiguration) {
    FakeRTCPeerConnection.instances.push(this);
  }

  addTransceiver(kind: "audio" | "video", _opts: unknown) {
    const sender: FakeSender = {
      _kind: kind,
      track: null,
      replaceTrack: vi.fn().mockResolvedValue(undefined),
    };
    this.senders.push(sender);
    return { sender, receiver: {}, direction: "sendrecv", mid: `${kind}-0` };
  }

  async createOffer(opts: Record<string, unknown> = {}) {
    if (typeof opts.iceRestart === "boolean") {
      this.offers.push({ ...opts });
    }
    return { type: "offer" as const, sdp: "v=0-fake-offer" };
  }

  async setLocalDescription(desc: Record<string, unknown>) {
    this.localDescriptions.push({ ...desc });
  }

  setRemoteDescription(_desc: unknown) { /* not exercised here */ }
  async addIceCandidate(_c: unknown) { /* not exercised here */ }

  getSenders(): RTCRtpSender[] {
    return this.senders as unknown as RTCRtpSender[];
  }

  close() {
    this.closed += 1;
    this.connectionState = "closed";
  }

  dispatchState(state: RTCPeerConnectionState) {
    this.connectionState = state;
    this.onconnectionstatechange?.();
  }
}

vi.stubGlobal("RTCPeerConnection", FakeRTCPeerConnection);

import {
  WebRTCManager,
  currentIceServers,
  setIceServers,
  type SignalMessage,
} from "../webrtc";

const signals: Array<{ targetId: string; signal: SignalMessage }> = [];

function makeManager() {
  const removed: string[] = [];
  const streams: Array<[string, MediaStream]> = [];
  const mgr = new WebRTCManager({
    localParticipantId: "me",
    onRemoteStream: (pid, stream) => streams.push([pid, stream]),
    onRemoteStreamRemoved: (pid) => removed.push(pid),
    sendSignal: (targetId, signal) => signals.push({ targetId, signal }),
  });
  return { mgr, removed, streams };
}

beforeEach(() => {
  FakeRTCPeerConnection.instances = [];
  signals.length = 0;
  vi.useFakeTimers();
  setIceServers(null); // defaults for every test
});

afterEach(() => {
  vi.useRealTimers();
});

async function openPeer() {
  const { mgr, removed } = makeManager();
  const p = mgr.initiateCallTo("peer-a");
  // createPeerConnection awaits fake replaceTracks; flush microtasks.
  await vi.advanceTimersByTimeAsync(0);
  await p;
  expect(FakeRTCPeerConnection.instances).toHaveLength(1);
  return { mgr, pc: FakeRTCPeerConnection.instances[0], removed };
}

describe("P2P mesh reconnect", () => {
  it("survives a transient disconnected state that recovers (network switch)", async () => {
    const { mgr, pc } = await openPeer();

    pc.dispatchState("disconnected");
    expect(mgr.hasPeer("peer-a")).toBe(true); // not killed on the spot

    await vi.advanceTimersByTimeAsync(2_500); // grace window elapses
    // The recovery offer IS an ICE restart:
    expect(pc.offers.some((o) => o.iceRestart === true)).toBe(true);

    pc.dispatchState("connected");
    await vi.advanceTimersByTimeAsync(30_000);
    expect(mgr.hasPeer("peer-a")).toBe(true); // connection survived the switch
  });

  it("re-dials a permanently dead peer after one restart attempt", async () => {
    const { mgr, pc, removed } = await openPeer();

    pc.dispatchState("disconnected");
    await vi.advanceTimersByTimeAsync(2_500);
    expect(pc.offers.some((o) => o.iceRestart === true)).toBe(true); // restart tried

    await vi.advanceTimersByTimeAsync(5_000); // restart window elapses, still dead
    expect(removed).toContain("peer-a"); // tile dropped so the roster re-dials
    expect(mgr.hasPeer("peer-a")).toBe(false);
    expect(pc.closed).toBeGreaterThan(0);
  });

  it("kills failed peers only after a bounded restart window", async () => {
    const { mgr, pc, removed } = await openPeer();

    pc.dispatchState("failed");
    // Not instant: the old code removed the peer inside the same tick.
    expect(removed).not.toContain("peer-a");
    await vi.advanceTimersByTimeAsync(5_000);
    expect(removed).toContain("peer-a");
    expect(mgr.hasPeer("peer-a")).toBe(false);
  });
});

describe("ICE server configuration", () => {
  it("defaults to public STUN with no credentials", () => {
    expect(currentIceServers().every((s) => String(s.urls).startsWith("stun:"))).toBe(true);
  });

  it("uses deployment TURN servers for new peer connections", async () => {
    setIceServers([{
      urls: "turn:turn.example.com:3478?transport=udp",
      username: "room",
      credential: "pw",
    }]);
    await openPeer();
    const config = FakeRTCPeerConnection.instances[0].config;
    expect(config.iceServers?.[0]).toMatchObject({ username: "room" });
  });

  it("falls back to defaults when handed an empty list", () => {
    setIceServers(undefined);
    expect(currentIceServers().length).toBeGreaterThan(0);
  });
});
