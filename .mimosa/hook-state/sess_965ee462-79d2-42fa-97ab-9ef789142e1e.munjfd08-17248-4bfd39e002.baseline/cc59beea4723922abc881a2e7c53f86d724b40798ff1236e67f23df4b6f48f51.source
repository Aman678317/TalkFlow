/**
 * Audio engine:
 * - capture: mic → AudioWorklet → 16 kHz mono PCM16 frames → WebSocket
 * - playback: queue for translated TTS WAVs + original-audio PCM relay streams,
 *   with per-utterance cancellation (stale output detection, section 10).
 *
 * The browser never does translation: all synthesis happens server-side and arrives
 * as real audio (base64 WAV or binary PCM frames). speechSynthesis is NOT used.
 */

const WORKLET_CODE = `
class PCMCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch = input[0];
    // forward Float32 100ms-ish blocks; downsampling done on main thread
    this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor('pcm-capture', PCMCaptureProcessor);
`;

export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;

  get mediaStream(): MediaStream | null {
    return this.stream;
  }

  async start(targetSampleRate: number, onFrame: (pcm16: ArrayBuffer) => void): Promise<void> {
    this.ctx = new AudioContext({ sampleRate: targetSampleRate });
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const blobUrl = URL.createObjectURL(
      new Blob([WORKLET_CODE], { type: "application/javascript" }),
    );
    await this.ctx.audioWorklet.addModule(blobUrl);
    URL.revokeObjectURL(blobUrl);
    const source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "pcm-capture", {
      numberOfOutputs: 0,
      channelCount: 1,
    });
    const inRate = this.ctx.sampleRate;
    this.node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      const resampled = this.toRate(e.data, inRate, targetSampleRate);
      const pcm16 = new Int16Array(resampled.length);
      for (let i = 0; i < resampled.length; i++) {
        const s = Math.max(-1, Math.min(1, resampled[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      onFrame(pcm16.buffer);
    };
    source.connect(this.node);
  }

  private toRate(input: Float32Array, from: number, to: number): Float32Array {
    if (from === to) return input;
    const ratio = from / to;
    const outLen = Math.floor(input.length / ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const pos = i * ratio;
      const i0 = Math.floor(pos);
      const i1 = Math.min(i0 + 1, input.length - 1);
      const frac = pos - i0;
      out[i] = input[i0] * (1 - frac) + input[i1] * frac;
    }
    return out;
  }

  stop() {
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close().catch(() => {});
    this.node = null;
    this.stream = null;
    this.ctx = null;
  }
}

/** Sequential audio playback queue with utterance-scoped cancellation. */
export class AudioPlayer {
  private ctx: AudioContext;
  private current: AudioBufferSourceNode | null = null;
  private queue: { buffer: AudioBuffer; tag: string }[] = [];
  private playingTag: string | null = null;

  constructor() {
    this.ctx = new AudioContext();
  }

  async resumeContext() {
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  /** Enqueue decoded WAV bytes (TTS events). Replaces anything with the same tag. */
  async enqueueWav(bytes: Uint8Array, tag: string, onDone?: () => void) {
    const buffer = await this.ctx.decodeAudioData(bytes.slice().buffer as ArrayBuffer);
    this.queue = this.queue.filter((q) => q.tag !== tag);
    this.queue.push({ buffer, tag });
    void this.playNext(onDone);
  }

  /** Enqueue raw PCM16 relay frames (original audio). Tag = utterance short id. */
  enqueuePcm16(pcm: ArrayBuffer, sampleRate: number, tag: string) {
    if (this.playingTag && this.playingTag !== tag) {
      // translated audio has priority; drop relay while TTS plays (mixed handled by UI)
    }
    const view = new Int16Array(pcm);
    if (view.length === 0) return;
    const buffer = this.ctx.createBuffer(1, view.length, sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < view.length; i++) data[i] = view[i] / 0x8000;
    this.queue.push({ buffer, tag });
    void this.playNext();
  }

  /** Cancel everything belonging to an utterance (stale output detection). */
  cancelTag(tag: string) {
    this.queue = this.queue.filter((q) => q.tag !== tag);
    if (this.playingTag === tag && this.current) {
      this.current.stop();
      this.current = null;
      this.playingTag = null;
    }
  }

  private async playNext(onDone?: () => void) {
    if (this.current) return;
    const item = this.queue.shift();
    if (!item) return;
    await this.resumeContext();
    const src = this.ctx.createBufferSource();
    src.buffer = item.buffer;
    src.connect(this.ctx.destination);
    this.current = src;
    this.playingTag = item.tag;
    src.onended = () => {
      this.current = null;
      this.playingTag = null;
      onDone?.();
      void this.playNext();
    };
    src.start();
  }

  dispose() {
    this.queue = [];
    this.current?.stop();
    this.ctx.close().catch(() => {});
  }
}

/** Decode a base64 WAV payload into bytes. */
export function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
