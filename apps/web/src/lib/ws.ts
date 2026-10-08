/**
 * Realtime WebSocket client (protocol v1).
 * - reconnect with exponential backoff + jitter
 * - session resume via last_sequence (server replays missed events)
 * - typed event emitter, binary frame decoding (original relay + TTS PCM)
 * - heartbeat ping/pong with connection-quality estimate
 */
import type { Preferences, RealtimeEvent } from "./types";
import { getAccessToken } from "./api";

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
  joinToken?: string;
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

export function decodeBinaryFrame(buf: ArrayBuffer): BinaryFrame {
  const view = new Uint8Array(buf);
  const kind: BinaryFrameKind = view[0] === 0x4f ? "original" : "tts";
  const shortId = TEXT_DECODER.decode(view.slice(1, 17)).replace(/0+$/, "");
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
  private closedByUser = false;
  private pingTimer: number | undefined;
  /** utterance short-id → speaker participant id (from speech.started events) */
  readonly utteranceSpeakers = new Map<string, string>();

  constructor(opts: MeetingSocketOptions) {
    this.opts = opts;
  }

  connect() {
    this.closedByUser = false;
    this.open();
  }

  private wsUrl(): string {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const params = new URLSearchParams();
    if (this.opts.ticket) {
      params.set("ticket", this.opts.ticket);
    } else {
      const jwt = getAccessToken();
      if (jwt) {
        params.set("token", jwt);
      } else {
        let jt = this.opts.joinToken;
        if (!jt) {
          try {
            jt = sessionStorage.getItem(`gt_guest_${this.opts.meetingId}`) || undefined;
            if (!jt) {
              jt = `guest-${Math.random().toString(36).substring(2, 10)}${Date.now().toString(36)}`;
              sessionStorage.setItem(`gt_guest_${this.opts.meetingId}`, jt);
            }
          } catch {
            // ignore storage errors
          }
        }
        if (jt) params.set("join_token", jt);
      }
    }
    const q = params.toString();
    return `${proto}://${location.host}/ws/meetings/${this.opts.meetingId}${q ? `?${q}` : ""}`;
  }

  private setState(s: SocketState) {
    this.opts.onStateChange(s);
  }

  private open() {
    this.setState(this.everJoined ? "reconnecting" : "connecting");
    const ws = new WebSocket(this.wsUrl());
    ws.binaryType = "arraybuffer";
    this.ws = ws;

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
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      /* onclose follows; state handled there */
    };
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

  sendAudio(pcm16: ArrayBuffer) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(pcm16);
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
