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
  constructor(options) {
    super();
    this.targetSampleRate = (options && options.processorOptions && options.processorOptions.targetSampleRate) || 16000;
    // 50ms frames at 16000 Hz = 800 samples = 1600 bytes PCM16
    this.frameSize = (options && options.processorOptions && options.processorOptions.frameSize) || 800;
    this.resampleRatio = sampleRate / this.targetSampleRate;
    this.accBuffer = new Float32Array(4096);
    this.accLen = 0;
    this.fraction = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    // Resample incoming audio block in audio rendering thread (off main UI thread)
    const ratio = this.resampleRatio;
    let pos = this.fraction;
    const chLen = channel.length;

    while (pos < chLen) {
      const idx0 = Math.floor(pos);
      const idx1 = Math.min(idx0 + 1, chLen - 1);
      const frac = pos - idx0;
      const sample = channel[idx0] * (1 - frac) + channel[idx1] * frac;

      if (this.accLen >= this.accBuffer.length) {
        const next = new Float32Array(this.accBuffer.length * 2);
        next.set(this.accBuffer);
        this.accBuffer = next;
      }
      this.accBuffer[this.accLen++] = sample;
      pos += ratio;

      // When accumulated a complete frame (e.g. 50ms = 800 samples at 16kHz)
      if (this.accLen >= this.frameSize) {
        const pcm16 = new Int16Array(this.frameSize);
        for (let i = 0; i < this.frameSize; i++) {
          const s = Math.max(-1, Math.min(1, this.accBuffer[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        // Transfer ArrayBuffer to main thread (zero-copy memory transfer)
        this.port.postMessage(pcm16.buffer, [pcm16.buffer]);

        // Shift remaining samples in accumulator
        const remaining = this.accLen - this.frameSize;
        if (remaining > 0) {
          this.accBuffer.copyWithin(0, this.frameSize, this.accLen);
        }
        this.accLen = remaining;
      }
    }
    this.fraction = pos - chLen;
    return true;
  }
}
registerProcessor('pcm-capture', PCMCaptureProcessor);
`;

export interface MicCaptureOptions {
  deviceId?: string;
  echoCancellation?: boolean;
  noiseSuppression?: boolean;
  autoGainControl?: boolean;
}

export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private isClonedTrack = false;

  get mediaStream(): MediaStream | null {
    return this.stream;
  }

  async start(
    targetSampleRate: number,
    onFrame: (pcm16: ArrayBuffer) => void,
    options?: MicCaptureOptions
  ): Promise<void> {
    const audioConstraints: MediaTrackConstraints = {
      channelCount: 1,
      echoCancellation: options?.echoCancellation ?? true,
      noiseSuppression: options?.noiseSuppression ?? true,
      autoGainControl: options?.autoGainControl ?? true,
    };
    if (options?.deviceId) {
      audioConstraints.deviceId = { exact: options.deviceId };
    }
    const micStream = await navigator.mediaDevices.getUserMedia({
      audio: audioConstraints,
    });
    this.isClonedTrack = false;
    await this.initPipeline(micStream, targetSampleRate, onFrame);
  }

  /**
   * Tap an existing audio track by cloning it so WebRTC / LiveKit call audio is untouched.
   */
  async startFromTrack(
    track: MediaStreamTrack,
    targetSampleRate: number,
    onFrame: (pcm16: ArrayBuffer) => void
  ): Promise<void> {
    const cloned = track.clone();
    this.isClonedTrack = true;
    const stream = new MediaStream([cloned]);
    await this.initPipeline(stream, targetSampleRate, onFrame);
  }

  private async initPipeline(
    stream: MediaStream,
    targetSampleRate: number,
    onFrame: (pcm16: ArrayBuffer) => void
  ): Promise<void> {
    this.stream = stream;
    this.ctx = new AudioContext();
    if (this.ctx.state === "suspended") {
      await this.ctx.resume().catch(() => {});
    }

    const blobUrl = URL.createObjectURL(
      new Blob([WORKLET_CODE], { type: "application/javascript" }),
    );
    try {
      await this.ctx.audioWorklet.addModule(blobUrl);
    } finally {
      URL.revokeObjectURL(blobUrl);
    }

    // AudioWorkletNode with numberOfOutputs: 0 ensures mic audio is NEVER routed to local speakers (no self-echo)
    this.node = new AudioWorkletNode(this.ctx, "pcm-capture", {
      numberOfOutputs: 0,
      channelCount: 1,
      processorOptions: {
        targetSampleRate,
        frameSize: Math.floor(targetSampleRate * 0.05), // 50ms frames (800 samples at 16kHz)
      },
    });

    this.node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      onFrame(e.data);
    };

    const source = this.ctx.createMediaStreamSource(this.stream);
    source.connect(this.node);
  }

  stop() {
    this.node?.disconnect();
    if (this.stream) {
      this.stream.getTracks().forEach((t) => {
        // If this was a cloned track, stop it; if not cloned, stop it as well
        t.stop();
      });
    }
    this.ctx?.close().catch(() => {});
    this.node = null;
    this.stream = null;
    this.ctx = null;
    this.isClonedTrack = false;
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

  /** Set speaker output device if supported by browser */
  async setSinkId(deviceId: string): Promise<boolean> {
    if ("setSinkId" in this.ctx && typeof (this.ctx as any).setSinkId === "function") {
      try {
        await (this.ctx as any).setSinkId(deviceId);
        return true;
      } catch (e) {
        console.warn("setSinkId failed", e);
      }
    }
    return false;
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
