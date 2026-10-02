/**
 * Realtime WebSocket client (PDD §38):
 * - exponential backoff + jitter reconnect
 * - session resume by last seen sequence (server replays missed events)
 * - sequence dedup so replays never duplicate UI state
 * - heartbeat ping + reconnect.required handling
 * - binary frames OUT: raw PCM16 mic audio
 * - binary frames IN: [16-byte speaker uuid][PCM16] original-audio relay
 */
import type { ServerEvent } from '@globaltalk/shared-types';

export type EventListener = (ev: ServerEvent) => void;
export type BinaryListener = (speakerId: string, pcm: Uint8Array) => void;
export type StatusListener = (status: ConnectionStatus) => void;

export type ConnectionStatus =
  | 'connecting' | 'open' | 'reconnecting' | 'closed' | 'failed';

export interface RealtimeClientOptions {
  url: string;                     // /ws/realtime?ticket=...
  onEvent: EventListener;
  onBinary?: BinaryListener;       // original-audio relay frames
  onStatus?: StatusListener;
  maxBackoffMs?: number;
}

export class RealtimeClient {
  private ws: WebSocket | null = null;
  private lastSequence = 0;
  private seenSequences = new Set<number>();
  private attempt = 0;
  private closedByUser = false;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private status: ConnectionStatus = 'closed';

  constructor(private opts: RealtimeClientOptions) {}

  connect(): void {
    this.closedByUser = false;
    this.setStatus(this.lastSequence > 0 ? 'reconnecting' : 'connecting');
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${window.location.host}${this.opts.url}`;
    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.setStatus('open');
      if (this.lastSequence > 0) {
        this.send({ type: 'session.resume',
                    data: { last_sequence: this.lastSequence } });
      }
      this.heartbeat = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          this.send({ type: 'ping', data: { ts: Date.now() } });
        }
      }, 25000);
    };

    ws.onmessage = (msg) => {
      if (typeof msg.data === 'string') {
        let ev: ServerEvent;
        try {
          ev = JSON.parse(msg.data) as ServerEvent;
        } catch {
          return;
        }
        // dedup by sequence: server sequences are monotonic per session, so
        // anything <= lastSequence (or already seen) is a replay artifact.
        if (ev.sequence > 0) {
          if (ev.sequence <= this.lastSequence || this.seenSequences.has(ev.sequence)) {
            return;
          }
          this.seenSequences.add(ev.sequence);
          if (this.seenSequences.size > 5000) {
            this.seenSequences = new Set([...this.seenSequences].slice(-2500));
          }
          this.lastSequence = ev.sequence;
        }
        if (ev.type === 'reconnect.required') {
          this.reconnectNow();
          return;
        }
        this.opts.onEvent(ev);
      } else if (msg.data instanceof ArrayBuffer && this.opts.onBinary) {
        const bytes = new Uint8Array(msg.data);
        if (bytes.length <= 16) return;
        const speakerId = decodeUuidBytes(bytes.slice(0, 16));
        this.opts.onBinary(speakerId, bytes.slice(16));
      }
    };

    ws.onclose = (ev) => {
      if (this.heartbeat) clearInterval(this.heartbeat);
      this.heartbeat = null;
      if (this.closedByUser) {
        this.setStatus('closed');
        return;
      }
      if (ev.code === 4401 || ev.code === 4404 || ev.code === 4410) {
        // auth/not-found/not-joinable — retrying won't help
        this.setStatus('failed');
        return;
      }
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose follows; nothing extra needed
    };
  }

  private setStatus(s: ConnectionStatus) {
    this.status = s;
    this.opts.onStatus?.(s);
  }

  getStatus(): ConnectionStatus { return this.status; }

  private scheduleReconnect() {
    this.setStatus('reconnecting');
    const base = Math.min(this.opts.maxBackoffMs ?? 20000,
                          500 * Math.pow(2, this.attempt));
    const jitter = Math.random() * base * 0.4;
    this.attempt += 1;
    setTimeout(() => {
      if (!this.closedByUser) this.connect();
    }, base + jitter);
  }

  private reconnectNow() {
    this.ws?.close();
    this.scheduleReconnect();
  }

  send(msg: { type: string; data?: Record<string, unknown>;
              sequence?: number }): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ version: 1, ...msg }));
    }
  }

  sendAudio(pcm16: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(pcm16);
    }
  }

  close(): void {
    this.closedByUser = true;
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.ws?.close();
    this.setStatus('closed');
  }
}

function decodeUuidBytes(b: Uint8Array): string {
  const hex = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
