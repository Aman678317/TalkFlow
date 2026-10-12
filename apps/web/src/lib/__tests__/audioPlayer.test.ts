/**
 * AudioPlayer translated-TTS chunk semantics.
 *
 * Locked-in invariants (the "translated speech is not being heard" bug):
 *   1. Streamed chunks of ONE utterance share a tag. Enqueuing a later chunk
 *      must NOT evict earlier chunks that are still queued.
 *   2. The server delivers the same chunk over two transports (binary frame +
 *      JSON tts.chunk). Exactly one of them may reach the queue.
 *   3. Binary is primary; JSON is an explicit, tested fallback that fires only
 *      when the binary chunk never arrives.
 *   4. cancelTag is the only implicit bulk-evict path.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

type FakeSource = {
  buffer: unknown;
  started: boolean;
  stopped: boolean;
  onended: (() => void) | null;
  connect: (dest: unknown) => void;
  start: () => void;
  stop: () => void;
};

const created: FakeSource[] = [];
const queueDepthAfter: number[] = [];

function installFakeAudioContext() {
  created.length = 0;
  class FakeAudioContext {
    state = "running";
    destination = { id: "destination" };
    resume = vi.fn(async () => {
      this.state = "running";
    });
    close = vi.fn(async () => {});
    decodeAudioData = vi.fn(async (buf: ArrayBuffer) => ({ id: `decoded:${buf.byteLength}` }));
    createBuffer = vi.fn((channels: number, length: number, sampleRate: number) => ({
      channels,
      length,
      sampleRate,
      getChannelData: () => new Float32Array(length),
    }));
    createBufferSource = vi.fn(() => {
      const src: FakeSource = {
        buffer: null,
        started: false,
        stopped: false,
        onended: null,
        connect: () => {},
        start: () => {
          src.started = true;
        },
        stop: () => {
          src.stopped = true;
        },
      };
      created.push(src);
      return src;
    });
  }
  vi.stubGlobal("AudioContext", FakeAudioContext);
}

beforeEach(() => {
  installFakeAudioContext();
  vi.useFakeTimers();
});

const wav = (n: number) => new Uint8Array(n);
const opts = (sequence: number, chunkIndex: number) => ({ sequence, chunkIndex });

/** The watchdog callback chains through await decodeAudioData; drain those microtasks. */
async function settle() {
  for (let i = 0; i < 12; i++) await Promise.resolve();
}

async function enqueue(player: any, bytes: Uint8Array, tag: string, o?: any) {
  await (o === undefined ? player.enqueueWav(bytes, tag) : player.deliver(bytes, tag, o));
  queueDepthAfter.push(player.debugQueueLength());
}

describe("AudioPlayer.deliver — streamed TTS chunks", () => {
  it("keeps every queued chunk of one utterance instead of replacing same-tag items", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();

    await enqueue(player, wav(10), "tts-abc", opts(7, 0)); // starts playing immediately
    await enqueue(player, wav(11), "tts-abc", opts(7, 1));
    await enqueue(player, wav(12), "tts-abc", opts(7, 2));

    // chunk 0 is playing, chunks 1 and 2 must still be queued — none evicted.
    expect(player.debugQueueLength()).toBe(2);
    expect(player.debugPlayedCount()).toBe(1);
  });

  it("plays chunks in chunkIndex order and starts each source exactly once", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();

    await enqueue(player, wav(10), "tts-abc", opts(7, 0));
    await enqueue(player, wav(12), "tts-abc", opts(7, 2));
    await enqueue(player, wav(11), "tts-abc", opts(7, 1)); // arrives out of order

    // Let chunk 0 finish so the queue drains in order.
    created[0].onended?.();
    await vi.advanceTimersByTimeAsync(0);
    created[1].onended?.();
    await vi.advanceTimersByTimeAsync(0);

    expect(created.map((s) => (s.buffer as any).id)).toEqual([
      "decoded:10",
      "decoded:11",
      "decoded:12",
    ]);
    expect(created.every((s) => s.started)).toBe(true);
  });

  it("ignores the second transport for the same (tag, chunkIndex)", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();

    await enqueue(player, wav(20), "tts-abc", opts(7, 0)); // binary arrives first
    await player.deliver(wav(20), "tts-abc", { ...opts(7, 0), source: "json" });

    expect(player.debugQueueLength()).toBe(0); // chunk 0 is playing, nothing duplicated
    expect(player.debugPlayedCount()).toBe(1);
  });

  it("never schedules the JSON fallback once the binary chunk has been seen", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();
    await player.stopAll();

    await player.deliver(wav(30), "tts-xyz", { ...opts(9, 3), source: "json" });
    await player.deliver(wav(30), "tts-xyz", { ...opts(9, 3), source: "binary" });

    await vi.advanceTimersByTimeAsync(2000);
    await settle();
    // The binary half played; the held JSON chunk was suppressed, not queued behind it.
    expect(player.debugPlayedCount()).toBe(1);
    expect(player.debugQueueLength()).toBe(0);
  });

  it("fires the JSON fallback when no binary chunk arrives", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();
    await player.stopAll();

    await player.deliver(wav(40), "tts-lost", { ...opts(9, 4), source: "json" });
    expect(player.debugPlayedCount()).toBe(0); // held back, awaiting binary

    await vi.advanceTimersByTimeAsync(2000);
    await settle();
    expect(player.debugPlayedCount()).toBe(1); // delivered over the fallback path
  });

  it("cancelTag drops queued chunks and the JSON fallback still in flight", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();

    await enqueue(player, wav(10), "tts-abc", opts(7, 0)); // playing
    await enqueue(player, wav(11), "tts-abc", opts(7, 1)); // queued
    await player.deliver(wav(12), "tts-abc", { ...opts(7, 2), source: "json" }); // held, awaiting binary
    player.cancelTag("tts-abc");

    await vi.advanceTimersByTimeAsync(2000);
    await settle();
    expect(player.debugQueueLength()).toBe(0);
    expect(player.debugPlayedCount()).toBe(1); // chunk 0 only — 1 and 2 never played
  });
});
