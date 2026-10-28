/**
 * Audio engine:
 * - capture: mic → AudioWorklet → 16 kHz mono PCM16 frames → WebSocket
 * - playback: queue for translated TTS WAVs + original-audio PCM relay streams,
 *   with per-utterance and per-speaker cancellation (stale output detection, §10).
 *
 * The browser never does translation: all synthesis happens server-side and arrives
 * as real audio (base64 WAV or binary PCM frames). speechSynthesis is NOT used.
 */
import { normId } from "./ws";

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
  /**
   * The live input stopped producing a track — unplugged, taken by another
   * app, or revoked. Nothing else notices: the worklet simply never fires
   * again, so without this the user keeps talking into a dead microphone
   * while the room still says "Connected".
   */
  onLost?: (reason: "ended" | "mute") => void;
}

export class MicCapture {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private scriptProcessor: ScriptProcessorNode | null = null;
  private silentGain: GainNode | null = null;
  private isClonedTrack = false;
  private stopped = false;

  get mediaStream(): MediaStream | null {
    return this.stream;
  }

  get isCloned(): boolean {
    return this.isClonedTrack;
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
    await this.initPipeline(micStream, targetSampleRate, onFrame, options?.onLost);
  }

  /**
   * Tap an existing audio track by cloning it so WebRTC / LiveKit call audio is untouched.
   */
  async startFromTrack(
    track: MediaStreamTrack,
    targetSampleRate: number,
    onFrame: (pcm16: ArrayBuffer) => void,
    onLost?: MicCaptureOptions["onLost"]
  ): Promise<void> {
    const cloned = track.clone();
    this.isClonedTrack = true;
    const stream = new MediaStream([cloned]);
    await this.initPipeline(stream, targetSampleRate, onFrame, onLost);
  }

  private async initPipeline(
    stream: MediaStream,
    targetSampleRate: number,
    onFrame: (pcm16: ArrayBuffer) => void,
    onLost?: MicCaptureOptions["onLost"]
  ): Promise<void> {
    this.stream = stream;
    const AudioCtxCtor = window.AudioContext || (window as any).webkitAudioContext;
    this.ctx = new AudioCtxCtor();
    if (this.ctx.state === "suspended") {
      await this.ctx.resume().catch(() => {});
    }

    let workletSuccess = false;
    if (this.ctx.audioWorklet) {
      try {
        const blobUrl = URL.createObjectURL(
          new Blob([WORKLET_CODE], { type: "application/javascript" }),
        );
        await this.ctx.audioWorklet.addModule(blobUrl);
        setTimeout(() => {
          try { URL.revokeObjectURL(blobUrl); } catch { }
        }, 2000);

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
        workletSuccess = true;
      } catch (workletErr) {
        console.warn("AudioWorklet unavailable, activating ScriptProcessor fallback:", workletErr);
      }
    }

    if (!workletSuccess) {
      // ScriptProcessor fallback for 100% browser compatibility
      const bufferSize = 4096;
      const scriptNode = this.ctx.createScriptProcessor(bufferSize, 1, 1);
      const resampleRatio = this.ctx.sampleRate / targetSampleRate;
      const frameSize = Math.floor(targetSampleRate * 0.05); // 800 samples
      let accBuffer = new Float32Array(8192);
      let accLen = 0;
      let fraction = 0;

      scriptNode.onaudioprocess = (e) => {
        if (this.stopped) return;
        const channel = e.inputBuffer.getChannelData(0);
        if (!channel || channel.length === 0) return;

        let pos = fraction;
        const chLen = channel.length;
        while (pos < chLen) {
          const idx0 = Math.floor(pos);
          const idx1 = Math.min(idx0 + 1, chLen - 1);
          const frac = pos - idx0;
          const sample = channel[idx0] * (1 - frac) + channel[idx1] * frac;

          if (accLen >= accBuffer.length) {
            const next = new Float32Array(accBuffer.length * 2);
            next.set(accBuffer);
            accBuffer = next;
          }
          accBuffer[accLen++] = sample;
          pos += resampleRatio;

          if (accLen >= frameSize) {
            const pcm16 = new Int16Array(frameSize);
            for (let i = 0; i < frameSize; i++) {
              const s = Math.max(-1, Math.min(1, accBuffer[i]));
              pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
            }
            onFrame(pcm16.buffer);

            const remaining = accLen - frameSize;
            if (remaining > 0) {
              accBuffer.copyWithin(0, frameSize, accLen);
            }
            accLen = remaining;
          }
        }
        fraction = pos - chLen;
      };

      const source = this.ctx.createMediaStreamSource(this.stream);
      source.connect(scriptNode);
      const silentGain = this.ctx.createGain();
      silentGain.gain.value = 0;
      scriptNode.connect(silentGain);
      silentGain.connect(this.ctx.destination);

      this.scriptProcessor = scriptNode;
      this.silentGain = silentGain;
    }

    const track = this.stream.getAudioTracks()[0];
    if (track && onLost) {
      track.addEventListener("ended", () => {
        if (!this.stopped) onLost("ended");
      });
      track.addEventListener("mute", () => {
        if (!this.stopped) onLost("mute");
      });
    }
  }

  stop() {
    this.stopped = true;
    this.node?.disconnect();
    this.scriptProcessor?.disconnect();
    this.silentGain?.disconnect();
    if (this.stream) {
      this.stream.getTracks().forEach((t) => {
        t.stop();
      });
    }
    this.ctx?.close().catch(() => {});
    this.node = null;
    this.scriptProcessor = null;
    this.silentGain = null;
    this.stream = null;
    this.ctx = null;
    this.isClonedTrack = false;
  }
}

export interface PlayQueueOptions {
  sequence?: number;
  chunkIndex?: number;
  utteranceId?: string;
  speakerId?: string;
  /** Which transport delivered this chunk. Binary is primary, JSON is the fallback. */
  source?: "binary" | "json";
}

interface PlayQueueItem {
  buffer: AudioBuffer;
  tag: string;
  sequence: number;
  chunkIndex: number;
  utteranceId?: string;
  speakerId?: string;
  enqueuedAt: number;
}

/** Sequential audio playback queue with utterance-scoped cancellation and sequence ordering. */
export class AudioPlayer {
  /** Grace period for the binary chunk to arrive before the JSON fallback plays it. */
  static readonly JSON_FALLBACK_GRACE_MS = 350;
  /** Bound on the cross-transport dedup registry (FIFO eviction). */
  static readonly MAX_DELIVERIES = 512;

  private ctx: AudioContext;
  private current: AudioBufferSourceNode | null = null;
  private queue: PlayQueueItem[] = [];
  private playingTag: string | null = null;
  private lastPlayedSeqPerSpeaker: Map<string, number> = new Map();
  /** (tag, chunkIndex) -> transport that actually enqueued it. Bounded by MAX_DELIVERIES. */
  private deliveredChunks: Map<string, "binary" | "json"> = new Map();
  private pendingDeliveries: Map<string, ReturnType<typeof setTimeout>> = new Map();
  /**
   * Queue tag -> speaker, learned from the JSON `tts.chunk` events. The binary
   * frame carries only the segment's short id, so without this the player could
   * not tell whose audio a queued chunk is — which is exactly what a barge-in
   * flush has to know to drop one speaker without silencing another.
   */
  private speakerByTag: Map<string, string> = new Map();
  /**
   * Queue tag -> turn (utterance id), learned the same way: the JSON event names
   * both, the binary frame names neither. Playback state is reported per turn
   * because that is what a caption is keyed by.
   */
  private turnByTag: Map<string, string> = new Map();
  private playedCount = 0;
  private playingTurn: string | null = null;

  private gainNode: GainNode | null = null;
  private autoResumeHandler: (() => void) | null = null;

  constructor(
    /** Decode/resume failures must reach the UI — a silent player is the bug we are fixing. */
    private onPlaybackError?: (message: string) => void,
    /** Turn-level transitions, so a caption can say what the listener has heard. */
    private onPlaybackState?: (
      turn: string,
      state: "playing" | "played" | "dropped",
    ) => void,
    /** State changes of AudioContext (e.g. suspended vs running on mobile devices). */
    private onContextState?: (state: AudioContextState) => void,
  ) {
    this.ctx = new AudioContext();
    if (typeof this.ctx.createGain === "function") {
      this.gainNode = this.ctx.createGain();
      this.gainNode.connect(this.ctx.destination);
    }
    if (typeof this.ctx.addEventListener === "function") {
      this.ctx.addEventListener("statechange", () => {
        this.onContextState?.(this.ctx.state);
      });
    }
    // Safari iOS AudioContext orientation & visibility auto-resume (ISSUE-201)
    if (typeof window !== "undefined") {
      this.autoResumeHandler = () => {
        if (this.ctx && this.ctx.state === "suspended") {
          void this.ctx.resume().catch(() => {});
        }
      };
      window.addEventListener("orientationchange", this.autoResumeHandler);
      window.addEventListener("resize", this.autoResumeHandler);
      if (typeof document !== "undefined") {
        document.addEventListener("visibilitychange", this.autoResumeHandler);
      }
    }
  }

  get isSuspended(): boolean {
    return this.ctx.state === "suspended";
  }

  get contextState(): AudioContextState {
    return this.ctx.state;
  }

  /** Set playback volume (0.0 to 1.0) */
  setVolume(vol: number) {
    if (this.gainNode) {
      const v = Math.max(0, Math.min(1, vol));
      this.gainNode.gain.setValueAtTime(v, this.ctx.currentTime);
    }
  }

  /** Duck audio smoothly during local speech interruption to prevent acoustic feedback */
  setDucking(ducked: boolean) {
    if (this.gainNode) {
      const targetGain = ducked ? 0.2 : 1.0;
      if (typeof this.gainNode.gain.setTargetAtTime === "function") {
        this.gainNode.gain.setTargetAtTime(targetGain, this.ctx.currentTime, 0.05);
      } else {
        this.gainNode.gain.value = targetGain;
      }
    }
  }

  /** One transition per turn: chunks of a turn are silent, and a cut turn is dropped. */
  private noteTurn(turn: string | null) {
    if (turn === this.playingTurn) return;
    const previous = this.playingTurn;
    this.playingTurn = turn;
    if (previous) this.onPlaybackState?.(previous, "played");
    if (turn) this.onPlaybackState?.(turn, "playing");
  }

  private reportPlaybackError(err: unknown, stage: string) {
    const name = err instanceof Error ? err.name : "PlaybackError";
    const message =
      name === "NotAllowedError"
        ? "Browser blocked audio playback — tap anywhere once to allow translated speech."
        : `Translated audio could not be ${stage}.`;
    this.onPlaybackError?.(message);
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

  /** Enqueue decoded WAV bytes (TTS events). Plays segments in strictly monotonic order. */
  async enqueueWav(
    bytes: Uint8Array,
    tag: string,
    opts?: PlayQueueOptions,
    onDone?: () => void
  ) {
    const seq = opts?.sequence ?? 0;
    const chunkIdx = opts?.chunkIndex ?? 0;
    const speakerKey = this.speakerOf(tag, opts);
    if (speakerKey && seq > 0) {
      const lastPlayed = this.lastPlayedSeqPerSpeaker.get(speakerKey) ?? 0;
      if (seq < lastPlayed) {
        // Discard stale audio segment that arrived out-of-order or after reconnection
        return;
      }
    }

    let buffer: AudioBuffer;
    try {
      buffer = await this.ctx.decodeAudioData(bytes.slice().buffer as ArrayBuffer);
    } catch (err) {
      this.reportPlaybackError(err, "decoded");
      throw err;
    }
    // NOTE: no same-tag eviction here. Earlier chunks of the same utterance are valid
    // audio that has not played yet; bulk removal is `cancelTag`'s job only.
    this.queue.push({
      buffer,
      tag,
      sequence: seq,
      chunkIndex: chunkIdx,
      utteranceId: opts?.utteranceId ?? this.turnByTag.get(tag),
      speakerId: this.speakerOf(tag, opts),
      enqueuedAt: Date.now(),
    });

    // Ensure queue is ordered strictly by sequence, chunkIndex, and arrival time
    this.queue.sort((a, b) => {
      if (a.sequence !== b.sequence) return a.sequence - b.sequence;
      if (a.chunkIndex !== b.chunkIndex) return a.chunkIndex - b.chunkIndex;
      return a.enqueuedAt - b.enqueuedAt;
    });

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
    this.queue.push({
      buffer,
      tag,
      sequence: 0,
      chunkIndex: 0,
      enqueuedAt: Date.now(),
    });
    void this.playNext();
  }

  /** Cancel everything belonging to an utterance (stale output detection). */
  cancelTag(tag: string) {
    const prefix = `${tag}:`;
    for (const key of [...this.pendingDeliveries.keys()]) {
      if (key.startsWith(prefix)) this.cancelDelivery(key);
    }
    for (const key of [...this.deliveredChunks.keys()]) {
      if (key.startsWith(prefix)) this.deliveredChunks.delete(key);
    }
    this.queue = this.queue.filter((q) => q.tag !== tag);
    this.stopIfPlaying(tag);
  }

  /**
   * Barge-in: drop one speaker's stale audio and nothing else's.
   *
   * A translated turn is streamed under the segment's short id, which the binary
   * frame carries alone, so ownership comes from the JSON events that name both
   * the segment and the speaker. Original relay frames are tagged with the
   * speaker's own short id, so they resolve directly.
   *
   * Returns how many chunks were dropped, which is what the caller reports.
   * Each interrupted turn is additionally reported once as "dropped" — never as
   * "played" — so its caption can say the listener did not hear it.
   */
  cancelSpeaker(speakerId: string): number {
    const tags = this.tagsOfSpeaker(speakerId);
    for (const tag of tags) {
      const prefix = `${tag}:`;
      for (const key of [...this.pendingDeliveries.keys()]) {
        if (key.startsWith(prefix)) this.cancelDelivery(key);
      }
      for (const key of [...this.deliveredChunks.keys()]) {
        if (key.startsWith(prefix)) this.deliveredChunks.delete(key);
      }
    }
    const wanted = new Set(tags);
    const droppedTurns = new Set<string>();
    let dropped = 0;
    const kept: PlayQueueItem[] = [];
    for (const item of this.queue) {
      if (wanted.has(item.tag)) {
        dropped += 1;
        if (item.utteranceId) droppedTurns.add(item.utteranceId);
      } else {
        kept.push(item);
      }
    }
    this.queue = kept;
    for (const tag of tags) {
      if (this.playingTag === tag && this.current) {
        // Cleared before stopping: the chained playNext must not announce the
        // audio it is about to cut off as having finished.
        const liveTurn = this.playingTurn;
        this.playingTurn = null;
        if (this.stopIfPlaying(tag)) {
          dropped += 1;
          if (liveTurn) droppedTurns.add(liveTurn);
        }
      }
    }
    for (const turn of droppedTurns) this.onPlaybackState?.(turn, "dropped");
    return dropped;
  }

  /** Tags that currently belong to one speaker, translated and original alike. */
  private tagsOfSpeaker(speakerId: string): string[] {
    const owners = new Set([speakerId, normId(speakerId)]);
    const tags = new Set<string>([`orig-${normId(speakerId)}`]);
    for (const [tag, owner] of this.speakerByTag) if (owners.has(owner)) tags.add(tag);
    for (const item of this.queue) if (item.speakerId && owners.has(item.speakerId)) tags.add(item.tag);
    return [...tags];
  }

  private stopIfPlaying(tag: string): boolean {
    if (this.playingTag !== tag || !this.current) return false;
    // onended must not fire: it would run the chunk's own completion callback and
    // chain playback on from audio the caller just declared stale.
    this.current.onended = null;
    this.current.stop();
    this.current = null;
    this.playingTag = null;
    void this.playNext();
    return true;
  }

  /**
   * Remember whose audio and which turn a queue tag belongs to. The binary TTS
   * frame carries only the segment's short id, so both cross-transport
   * cancellation and per-turn playback state depend on what the JSON events name.
   */
  noteOwnership(tag: string, owner: { speakerId?: string; utteranceId?: string }) {
    if (owner.speakerId) this.remember(this.speakerByTag, tag, owner.speakerId);
    if (owner.utteranceId) this.remember(this.turnByTag, tag, owner.utteranceId);
  }

  /** FIFO-evicting registry, so a long meeting cannot grow these without bound. */
  private remember<T>(map: Map<string, T>, key: string, value: T) {
    map.set(key, value);
    while (map.size > AudioPlayer.MAX_DELIVERIES) {
      const oldest = map.keys().next().value;
      if (oldest === undefined) break;
      map.delete(oldest);
    }
  }

  private speakerOf(tag: string, opts?: PlayQueueOptions): string | undefined {
    return opts?.speakerId ?? this.speakerByTag.get(tag);
  }

  /**
   * Deliver one translated TTS chunk, exactly once.
   *
   * The server sends every chunk on two transports (binary frame + JSON
   * `tts.chunk`). Binary is primary; a JSON chunk is held briefly and only
   * enqueued if the binary half never shows up. Whichever transport wins, the
   * `(tag, chunkIndex)` key is recorded so the loser is dropped.
   */
  async deliver(
    bytes: Uint8Array,
    tag: string,
    opts: PlayQueueOptions,
    onDone?: () => void
  ): Promise<void> {
    const key = `${tag}:${opts.chunkIndex ?? 0}`;
    const source = opts.source ?? "binary";
    this.noteOwnership(tag, opts);
    const winner = this.deliveredChunks.get(key);
    if (winner) {
      this.cancelDelivery(key);
      return;
    }
    if (source === "json") {
      // Await the binary half for one grace period before falling back.
      const timer = setTimeout(() => {
        this.pendingDeliveries.delete(key);
        void this.enqueueDelivered(key, source, bytes, tag, opts, onDone);
      }, AudioPlayer.JSON_FALLBACK_GRACE_MS);
      this.pendingDeliveries.set(key, timer);
      return;
    }
    await this.enqueueDelivered(key, source, bytes, tag, opts, onDone);
  }

  private async enqueueDelivered(
    key: string,
    source: "binary" | "json",
    bytes: Uint8Array,
    tag: string,
    opts: PlayQueueOptions,
    onDone?: () => void
  ) {
    if (this.deliveredChunks.has(key)) return;
    this.rememberDelivery(key, source);
    await this.enqueueWav(bytes, tag, opts, onDone);
  }

  private cancelDelivery(key: string) {
    const timer = this.pendingDeliveries.get(key);
    if (timer) {
      clearTimeout(timer);
      this.pendingDeliveries.delete(key);
    }
  }

  private rememberDelivery(key: string, source: "binary" | "json") {
    if (this.deliveredChunks.size >= AudioPlayer.MAX_DELIVERIES) {
      const oldest = this.deliveredChunks.keys().next().value;
      if (oldest !== undefined) this.deliveredChunks.delete(oldest);
    }
    this.deliveredChunks.set(key, source);
  }

  /** Test/inspection hook: how many decoded chunks are waiting to play. */
  debugQueueLength(): number {
    return this.queue.length;
  }

  /** Test/inspection hook: how many chunks actually reached an AudioBufferSourceNode. */
  debugPlayedCount(): number {
    return this.playedCount;
  }

  /** Stop the current source and drop everything queued (barge-in, language change). */
  async stopAll(): Promise<void> {
    for (const timer of this.pendingDeliveries.values()) clearTimeout(timer);
    this.pendingDeliveries.clear();
    const droppedTurns = new Set<string>();
    for (const item of this.queue) {
      if (item.utteranceId) droppedTurns.add(item.utteranceId);
    }
    const liveTurn = this.playingTurn;
    // Cleared before stopping: the caption must read "not heard", not "played".
    this.playingTurn = null;
    this.queue = [];
    if (this.current) {
      this.current.onended = null;
      this.current.stop();
      this.current = null;
      this.playingTag = null;
      if (liveTurn) droppedTurns.add(liveTurn);
    }
    for (const turn of droppedTurns) this.onPlaybackState?.(turn, "dropped");
  }

  private async playNext(onDone?: () => void) {
    if (this.current) return;
    const item = this.queue.shift();
    if (!item) {
      // Nothing left to hear: whatever turn was playing has now finished.
      this.noteTurn(null);
      onDone?.();
      return;
    }

    if (item.speakerId && item.sequence > 0) {
      this.lastPlayedSeqPerSpeaker.set(
        item.speakerId,
        Math.max(this.lastPlayedSeqPerSpeaker.get(item.speakerId) ?? 0, item.sequence)
      );
    }

    // A rejected resume() (autoplay block) or a failed start() must not kill the
    // player: report it, release the slot, and let the next enqueue retry.
    try {
      await this.resumeContext();
      const src = this.ctx.createBufferSource();
      src.buffer = item.buffer;
      if (this.gainNode) {
        src.connect(this.gainNode);
      } else {
        src.connect(this.ctx.destination);
      }
      this.current = src;
      this.playingTag = item.tag;
      this.playedCount++;
      src.onended = () => {
        this.current = null;
        this.playingTag = null;
        onDone?.();
        void this.playNext();
      };
      src.start();
      // Only after start(): a failed start re-queues the item and must not have
      // claimed to the UI that the listener is hearing it.
      this.noteTurn(item.utteranceId ?? null);
    } catch (err) {
      this.reportPlaybackError(err, "started");
      this.current = null;
      this.playingTag = null;
      this.queue.unshift(item);
    }
  }

  dispose() {
    if (typeof window !== "undefined" && this.autoResumeHandler) {
      window.removeEventListener("orientationchange", this.autoResumeHandler);
      window.removeEventListener("resize", this.autoResumeHandler);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", this.autoResumeHandler);
      }
      this.autoResumeHandler = null;
    }
    void this.stopAll();
    this.deliveredChunks.clear();
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
