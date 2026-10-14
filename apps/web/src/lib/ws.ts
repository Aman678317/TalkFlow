/**
 * Realtime WebSocket client (protocol v1).
 * - reconnect with exponential backoff + jitter
 * - session resume via last_sequence (server replays missed events)
 * - typed event emitter, binary frame decoding (original relay + TTS PCM)
 * - heartbeat ping/pong with connection-quality estimate
 */
import type { Preferences, RealtimeEvent } from "./types";
import { api, getAccessToken, getApiBaseUrl } from "./api";

export type BinaryFrameKind = "original" | "tts";
export interface BinaryFrame {
  kind: BinaryFrameKind;
  shortId: string;
  language: string;
  pcm: ArrayBuffer;
}

type Listener = (evt: RealtimeEvent) => void;
type BinListener = (frame: BinaryFrame) => void;

export interface MeetingSocketOptions {
  meetingId: string;
  /** server-issued seat key; every (re)connect mints a fresh single-use ticket from it */
  sessionKey?: string;
  ticket?: string;
  displayName: string;
  preferences: Preferences;
  participantId?: string;
  onEvent: Listener;
  onBinary: BinListener;
  onStateChange: (state: SocketState) => void;
}

export type SocketState = "connecting" | "joined" | "reconnecting" | "closed" | "error";

const TEXT_DECODER = new TextDecoder();

/**
 * Canonical 16-char id used as the audio queue tag.
 *
 * The server writes it three ways: inside binary frames as UUID-hex with dashes
 * stripped and NUL padding, inside JSON events as a raw UUID, and (Tree B) padded
 * with the ASCII character "0". Every one of those collapses to this value, which
 * is what makes cross-transport dedup of the same TTS chunk possible at all.
 *
 * The 16-char cut comes FIRST and padding is stripped after it. Stripping first
 * made the two transports disagree whenever a segment's 16th hex digit was a
 * literal "0" — the JSON key kept it, the 16-char binary key lost it — and that
 * chunk was played twice instead of deduped (~6% of segments).
 */
export function normId(id: string): string {
  return id.replace(/-/g, "").slice(0, 16).replace(/[\s0\u0000]+$/, "");
}

export function decodeBinaryFrame(buf: ArrayBuffer): BinaryFrame {
  const view = new Uint8Array(buf);
  const kind: BinaryFrameKind = view[0] === 0x4f ? "original" : "tts";
  // Tree A pads with NUL, Tree B with the ASCII character "0" — strip both so the
  // binary tag matches the JSON tag for the same audio and dedup can work.
  const shortId = normId(TEXT_DECODER.decode(view.slice(1, 17)));
  if (kind === "tts") {
    const n = view[17];
    const language = TEXT_DECODER.decode(view.slice(18, 18 + n));
    return { kind, shortId, language, pcm: buf.slice(18 + n) };
  }
  return { kind, shortId, language: "", pcm: buf.slice(17) };
}

export class MeetingSocket {
  private ws: WebSocket | null = null;
  private opts: MeetingSocketOptions;
  private lastSequence = 0;
  private everJoined = false;
  private attempt = 0;
  private quickFailures = 0;
  private mintFailures = 0;
  private pendingTicket: string | null = null;
  private connectStartedAt = 0;
  private closedByUser = false;
  private pingTimer: number | undefined;
  /** utterance short-id → speaker participant id (from speech.started events) */
  readonly utteranceSpeakers = new Map<string, string>();

  constructor(opts: MeetingSocketOptions) {
    this.opts = opts;
  }

  connect() {
    this.closedByUser = false;
    void this.open();
  }

  private async mintTicket(): Promise<string | null> {
    if (!this.opts.sessionKey) return null;
    try {
      const r = await api<{ ticket: string }>(
        `/api/v1/meetings/${this.opts.meetingId}/join-ticket`,
        { method: "POST", body: { session_key: this.opts.sessionKey } },
      );
      return r?.ticket ?? null;
    } catch {
      return null;
    }
  }

  private async open() {
    this.setState(this.everJoined ? "reconnecting" : "connecting");
    if (this.opts.sessionKey) {
      // Tickets are single-use and expire in 120s, so every (re)connect mints
      // a fresh one; the WS URL never carries a long-lived credential.
      const ticket = await this.mintTicket();
      if (!ticket) {
        this.mintFailures += 1;
        if (this.mintFailures >= 5) {
          this.setState("error");
          return;
        }
        this.scheduleReconnect();
        return;
      }
      this.mintFailures = 0;
      this.pendingTicket = ticket;
    }
    const ws = new WebSocket(this.wsUrl());
    ws.binaryType = "arraybuffer";
    this.ws = ws;
    this.connectStartedAt = Date.now();

    ws.onopen = () => {
      const p = this.opts.preferences;
      ws.send(
        JSON.stringify({
          version: 1,
          type: "session.join",
          participant_id: this.opts.participantId ?? null,
          display_name: this.opts.displayName,
          speaking_language: p.speaking_language,
          listening_language: p.listening_language,
          audio_mode: p.audio_mode,
          caption_mode: p.caption_mode,
          latency_mode: p.latency_mode,
          last_sequence: this.everJoined ? this.lastSequence : 0,
          resume: this.everJoined,
        }),
      );
    };

    ws.onmessage = (msg) => {
      if (typeof msg.data !== "string") {
        const frame = decodeBinaryFrame(msg.data as ArrayBuffer);
        this.opts.onBinary(frame);
        return;
      }
      const evt = JSON.parse(msg.data) as RealtimeEvent;
      if (typeof evt.sequence === "number" && evt.sequence > this.lastSequence) {
        this.lastSequence = evt.sequence;
      }
      if (evt.type === "speech.started" && typeof evt.speaker_id === "string") {
        this.utteranceSpeakers.set(String(evt.utterance_id ?? ""), evt.speaker_id);
      }
      if (evt.type === "session.created" || evt.type === "session.updated" ||
        evt.type === "session.resumed") {
        this.everJoined = true;
        this.attempt = 0;
        this.quickFailures = 0;
        this.setState("joined");
        this.startHeartbeat();
      }
      this.opts.onEvent(evt);
    };

    ws.onclose = (ev) => {
      this.stopHeartbeat();
      if (this.closedByUser) {
        this.setState("closed");
        return;
      }
      // 4401/4404 are permanent failures — do not hammer the server
      if (ev.code === 4401 || ev.code === 4404) {
        this.setState("error");
        return;
      }
      // A server that rejects the handshake pre-accept surfaces as 1006 with
      // the close code lost. Never-joined quick failures mean the credential
      // or room state is bad — stop after 5 instead of retrying forever.
      if (!this.everJoined && Date.now() - this.connectStartedAt < 3_000) {
        this.quickFailures += 1;
        if (this.quickFailures >= 5) {
          this.setState("error");
          return;
        }
      }
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      /* onclose follows; state handled there */
    };
  }

  private wsUrl(): string {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const params = new URLSearchParams();
    if (this.opts.sessionKey && this.pendingTicket) {
      params.set("ticket", this.pendingTicket);
    } else if (this.opts.ticket) {
      params.set("ticket", this.opts.ticket);
    } else {
      const jwt = getAccessToken();
      if (jwt) params.set("token", jwt);
    }
    const q = params.toString();
    // Resolve the API host exactly like REST traffic does (api.ts). A Vercel
    // preview build has no baked VITE_API_BASE_URL, so without this the REST
    // calls would hit same-origin while the WS fell back to Render and failed.
    const rawBase = getApiBaseUrl();
    let host = location.host;
    let customProto = proto;
    if (rawBase) {
      try {
        const parsed = new URL(rawBase);
        host = parsed.host;
        customProto = parsed.protocol === "https:" ? "wss" : "ws";
      } catch {
        host = rawBase.replace(/^https?:\/\//, "").replace(/\/+$/, "");
      }
    }
    return `${customProto}://${host}/ws/meetings/${this.opts.meetingId}${q ? `?${q}` : ""}`;
  }

  private setState(s: SocketState) {
    this.opts.onStateChange(s);
  }

  private scheduleReconnect() {
    if (this.closedByUser) return;
    this.setState("reconnecting");
    const base = Math.min(30_000, 500 * 2 ** this.attempt);
    const jitter = base * (0.5 + Math.random() * 0.5);
    this.attempt += 1;
    window.setTimeout(() => {
      if (!this.closedByUser) this.open();
    }, jitter);
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.pingTimer = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ version: 1, type: "ping", ts: Date.now() }));
      }
    }, 20_000);
  }

  private stopHeartbeat() {
    if (this.pingTimer) window.clearInterval(this.pingTimer);
    this.pingTimer = undefined;
  }

  private droppedAudioFrames = 0;
  private backpressureActive = false;

  sendAudio(pcm16: ArrayBuffer) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    // Phase 2 backpressure: drop frames if socket buffer exceeds 64KB (~2s audio)
    const MAX_BUFFERED_BYTES = 64 * 1024;
    if (this.ws.bufferedAmount > MAX_BUFFERED_BYTES) {
      this.droppedAudioFrames++;
      if (!this.backpressureActive) {
        this.backpressureActive = true;
        this.opts.onEvent({
          version: 1,
          type: "quality.degraded",
          session_id: "",
          conversation_id: "",
          sequence: null,
          timestamp: new Date().toISOString(),
          data: {
            reason: "client_audio_backpressure",
            message: "Local network congestion: audio frames dropped to preserve real-time latency.",
            recoverable: true,
          },
          user_message: "Local network congestion: audio frames dropped to preserve real-time latency.",
        });
      }
      return;
    }

    if (this.backpressureActive && this.ws.bufferedAmount < 16 * 1024) {
      this.backpressureActive = false;
    }

    this.ws.send(pcm16);
  }

  sendJson(evt: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN)
      this.ws.send(JSON.stringify({ version: 1, ...evt }));
  }

  updatePreferences(p: Partial<Preferences>) {
    Object.assign(this.opts.preferences, p);
    this.sendJson({ type: "preferences.update", ...p });
  }

  sendChat(text: string) {
    this.sendJson({ type: "chat.send", text });
  }

  /** Inject a canned transcript (dev/test only — server guards with
   *  is_dev_mode + 403 when STT is real and configured). Used to verify the
   *  translation + TTS fan-out end-to-end on Render where no STT model is
   *  installed. */
  injectTranscript(text: string, language: string) {
    this.sendJson({ type: "transcript.inject", text, language });
  }

  close() {
    this.closedByUser = true;
    this.stopHeartbeat();
    this.ws?.close(1000);
    this.setState("closed");
  }

  reconnectNow() {
    this.closedByUser = false;
    this.attempt = 0;
    this.stopHeartbeat();
    try {
      this.ws?.close();
    } catch { }
    this.open();
  }

  get currentSequence() {
    return this.lastSequence;
  }
}
