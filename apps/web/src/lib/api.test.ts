import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  broadcastLogout,
  DEFAULT_PRODUCTION_API_BASE_URL,
  getAccessToken,
  getApiBaseUrl,
  resolveApiBaseUrl,
  resolveWsBaseUrl,
  resolveWsUrl,
  setTokens,
  setUnauthorizedHandler,
  validateApiUrl,
} from "./api";
import { MeetingSocket, type SocketState } from "./ws";

describe("API origin resolution & URL validation", () => {
  it("honors the explicit Vercel API origin and strips trailing slashes", () => {
    expect(resolveApiBaseUrl("https://api.example.com///", true)).toBe("https://api.example.com");
    expect(resolveApiBaseUrl("http://localhost:8000/", false)).toBe("http://localhost:8000");
  });

  it("uses the durable backend for production when Vercel has no override", () => {
    expect(resolveApiBaseUrl(undefined, true)).toBe(DEFAULT_PRODUCTION_API_BASE_URL);
  });

  it("keeps local development same-origin when no override is supplied", () => {
    expect(resolveApiBaseUrl(undefined, false)).toBe("");
  });

  it("isolates preview deployments from accidentally targeting production", () => {
    // Vercel preview deployment with no override should stay same-origin ("")
    expect(resolveApiBaseUrl(undefined, true, { vercelEnv: "preview" })).toBe("");
    expect(resolveApiBaseUrl({ isProduction: true, vercelEnv: "preview" })).toBe("");
  });

  it("isolates staging deployments from accidentally targeting production", () => {
    expect(resolveApiBaseUrl(undefined, true, { mode: "staging" })).toBe("");
    expect(resolveApiBaseUrl({ isProduction: true, isStaging: true })).toBe("");
  });

  it("normalizes and validates URLs properly", () => {
    expect(validateApiUrl("  https://my-api.com:8443/api//  ")).toBe("https://my-api.com:8443/api");
    expect(validateApiUrl("http://localhost:8088")).toBe("http://localhost:8088");
  });

  it("rejects unsupported protocols and malformed URLs", () => {
    expect(() => validateApiUrl("ftp://files.example.com")).toThrow(/unsupported protocol/i);
    expect(() => validateApiUrl("javascript:alert(1)")).toThrow(/unsupported protocol/i);
    expect(() => validateApiUrl("ws://websocket.example.com")).toThrow(/unsupported protocol/i);
    expect(() => validateApiUrl("http://")).toThrow(/invalid.*url/i);
    expect(() => validateApiUrl("not_a_url")).toThrow(/invalid.*url/i);
    expect(() => validateApiUrl("   ")).toThrow(/empty/i);
  });
});

describe("WebSocket URL generation & HTTPS/WSS behavior", () => {
  it("derives wss:// when API base URL is https://", () => {
    expect(resolveWsBaseUrl("https://api.talkflow.ai")).toBe("wss://api.talkflow.ai");
    expect(resolveWsBaseUrl("https://talkflow-csbw.onrender.com")).toBe("wss://talkflow-csbw.onrender.com");
  });

  it("derives ws:// when API base URL is http://", () => {
    expect(resolveWsBaseUrl("http://localhost:8000")).toBe("ws://localhost:8000");
  });

  it("falls back to current window origin when API base is same-origin", () => {
    expect(resolveWsBaseUrl("", "https://preview.vercel.app")).toBe("wss://preview.vercel.app");
    expect(resolveWsBaseUrl("", "http://localhost:5173")).toBe("ws://localhost:5173");
  });

  it("constructs full websocket URLs with query parameters", () => {
    const wsUrl = resolveWsUrl(
      "/ws/meetings/room-456",
      { ticket: "tkt-abc123xyz" },
      "https://talkflow-csbw.onrender.com"
    );
    expect(wsUrl).toBe("wss://talkflow-csbw.onrender.com/ws/meetings/room-456?ticket=tkt-abc123xyz");

    const localWsUrl = resolveWsUrl(
      "/ws/meetings/room-789",
      new URLSearchParams({ token: "jwt-token-999" }),
      "",
      "http://localhost:5173"
    );
    expect(localWsUrl).toBe("ws://localhost:5173/ws/meetings/room-789?token=jwt-token-999");
  });
});

describe("REST request destinations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("dispatches requests to the configured API base URL", async () => {
    let requestedUrl = "";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        requestedUrl = url;
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: "ok" }),
          headers: new Headers(),
        };
      })
    );

    const base = getApiBaseUrl();
    await api("/api/v1/health");
    expect(requestedUrl).toBe(`${base}/api/v1/health`);
  });
});

describe("Authentication refresh & logout regressions", () => {
  beforeEach(() => {
    setTokens(null);
    vi.restoreAllMocks();
  });

  it("keeps access token in memory only", () => {
    expect(getAccessToken()).toBeNull();
    setTokens("memory-token-123");
    expect(getAccessToken()).toBe("memory-token-123");
    setTokens(null);
    expect(getAccessToken()).toBeNull();
  });

  it("clears authentication state on broadcastLogout", () => {
    let unauthorizedTriggered = false;
    setUnauthorizedHandler(() => {
      unauthorizedTriggered = true;
    });

    setTokens("active-token-999");
    expect(getAccessToken()).toBe("active-token-999");

    broadcastLogout();
    expect(getAccessToken()).toBeNull();
    expect(unauthorizedTriggered).toBe(true);
  });
});

describe("MeetingSocket ticket renewal & reconnect behavior", () => {
  class MockWebSocket {
    static instances: MockWebSocket[] = [];
    url: string;
    readyState = 0;
    binaryType = "blob";
    onopen: (() => void) | null = null;
    onclose: ((ev: { code: number; reason?: string }) => void) | null = null;
    onmessage: ((ev: { data: string }) => void) | null = null;
    onerror: (() => void) | null = null;

    constructor(url: string) {
      this.url = url;
      MockWebSocket.instances.push(this);
    }
    send() {}
    close(code = 1000) {
      this.readyState = 3;
      this.onclose?.({ code });
    }
  }

  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("mints a fresh single-use ticket when sessionKey is present", async () => {
    let mintCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) => {
        if (url.includes("/join-ticket")) {
          mintCalls++;
          return {
            ok: true,
            status: 200,
            json: async () => ({ ticket: `fresh-ticket-${mintCalls}` }),
          };
        }
        return { ok: true, status: 200, json: async () => ({}) };
      })
    );

    const states: SocketState[] = [];
    const socket = new MeetingSocket({
      meetingId: "m-test-1",
      sessionKey: "session-key-secret",
      displayName: "Tester",
      preferences: {
        speaking_language: "en",
        listening_language: "es",
        audio_mode: "original",
        caption_mode: "original",
        latency_mode: "balanced",
      },
      onEvent: () => {},
      onBinary: () => {},
      onStateChange: (s) => states.push(s),
    });

    socket.connect();
    await vi.waitFor(() => {
      expect(MockWebSocket.instances).toHaveLength(1);
    });

    expect(mintCalls).toBe(1);
    expect(MockWebSocket.instances[0].url).toContain("ticket=fresh-ticket-1");
  });

  it("fails closed on permanent 4401 authentication error without infinite loop", async () => {
    const states: SocketState[] = [];
    const socket = new MeetingSocket({
      meetingId: "m-test-2",
      ticket: "expired-or-invalid-ticket",
      displayName: "Guest",
      preferences: {
        speaking_language: "en",
        listening_language: "en",
        audio_mode: "original",
        caption_mode: "original",
        latency_mode: "balanced",
      },
      onEvent: () => {},
      onBinary: () => {},
      onStateChange: (s) => states.push(s),
    });

    socket.connect();
    await Promise.resolve();

    const ws = MockWebSocket.instances[0];
    expect(ws).toBeDefined();

    // Server rejects with 4401 (Unauthorized)
    ws.onclose?.({ code: 4401, reason: "Invalid ticket" });

    // Must transition to error immediately, not reconnecting
    expect(states).toContain("error");
    expect(states[states.length - 1]).toBe("error");

    // Advance time to verify no reconnect happens
    await vi.advanceTimersByTimeAsync(10000);
    expect(MockWebSocket.instances).toHaveLength(1); // No second socket spawned
  });
});
