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
 *   5. A barge-in flush is scoped to ONE speaker: cancelSpeaker must drop that
 *      speaker's queued chunks, live source and pending JSON fallback, and leave
 *      every other speaker's audio alone (Phase 3 gate).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { normId } from "../ws";

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

/**
 * Barge-in. The server's `playback.flush` names a SPEAKER, because that is the
 * only scope an interruption has: Ana starting to talk again makes Ana's
 * previous turn stale, and has nothing to say about Ben's.
 *
 * Ownership is learned from the JSON `tts.chunk` events — the binary frame that
 * carries the same audio holds nothing but the segment's short id — so these
 * tests deliver through the same transport order the browser sees.
 */
const ANA = "6f1c2d3e-4b5a-4c6d-8e9f-0a1b2c3d4e5f";
const BEN = "b1bb1e50-1111-4c6d-8e9f-0a1b2c3d4e5f";
const anaOpts = (chunkIndex: number) => ({ sequence: 3, chunkIndex, speakerId: ANA });
const benOpts = (chunkIndex: number) => ({ sequence: 4, chunkIndex, speakerId: BEN });

describe("AudioPlayer.cancelSpeaker — barge-in is scoped to one speaker", () => {
  it("drops the interrupted speaker's queued chunks and live source, not the other's", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();

    await player.deliver(wav(10), "tts-ana", { ...anaOpts(0), source: "json" });
    await player.deliver(wav(11), "tts-ana", { ...anaOpts(1), source: "json" });
    await player.deliver(wav(30), "tts-ben", { ...benOpts(0), source: "json" });
    await vi.advanceTimersByTimeAsync(400); // grace expires, all three are enqueued
    await settle();
    expect(player.debugPlayedCount()).toBe(1);
    expect(player.debugQueueLength()).toBe(2);

    const dropped = player.cancelSpeaker(ANA);

    expect(dropped).toBe(2); // the queued chunk plus the source that was playing
    expect(created[0].stopped).toBe(true); // Ana's live chunk was cut off

    // Ben's audio survives, and releasing the player slot resumes it at once.
    await vi.advanceTimersByTimeAsync(0);
    await settle();
    expect(created.map((s) => (s.buffer as any).id)).toEqual(["decoded:10", "decoded:30"]);
    expect(player.debugPlayedCount()).toBe(2);
    expect(player.debugQueueLength()).toBe(0);
  });

  it("cancels a JSON fallback still waiting for its binary half", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();
    await player.stopAll();

    await player.deliver(wav(40), "tts-ana", { ...anaOpts(0), source: "json" }); // held
    await player.deliver(wav(50), "tts-ben", { ...benOpts(0), source: "json" }); // held
    expect(player.debugPlayedCount()).toBe(0);

    player.cancelSpeaker(ANA);

    await vi.advanceTimersByTimeAsync(2000);
    await settle();
    // Only Ben's fallback survives the flush; Ana's never reaches the queue.
    expect(player.debugPlayedCount()).toBe(1);
    expect((created[0].buffer as any).id).toBe("decoded:50");
  });

  it("clears the dedup keys so a re-delivered chunk for that speaker is not lost", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();
    await player.stopAll();

    await player.deliver(wav(10), "tts-ana", anaOpts(0)); // binary, plays
    await settle();
    expect(player.debugPlayedCount()).toBe(1);

    player.cancelSpeaker(ANA);
    await settle();

    // Server retried the turn; the flushed (tag, chunkIndex) must not be
    // remembered as already delivered, or the listener hears nothing.
    await player.deliver(wav(10), "tts-ana", anaOpts(0));
    await settle();
    expect(player.debugPlayedCount()).toBe(2);
  });

  it("drops the speaker's delayed original-relay frames by their own tag", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();
    await player.stopAll();

    // Relay frames are tagged with the SPEAKER's short id, not a segment id.
    // One is claimed by the player, the rest queue behind it.
    player.enqueuePcm16(new ArrayBuffer(3200), 16000, `orig-${normId(ANA)}`);
    await settle();
    player.enqueuePcm16(new ArrayBuffer(3200), 16000, `orig-${normId(ANA)}`);
    await settle();
    player.enqueuePcm16(new ArrayBuffer(3200), 16000, `orig-${normId(BEN)}`);
    await settle();
    expect(player.debugPlayedCount()).toBe(1);
    expect(player.debugQueueLength()).toBe(2);

    const dropped = player.cancelSpeaker(ANA);

    expect(dropped).toBe(2); // one queued plus the frame that was playing
    expect(created[0].stopped).toBe(true);

    await vi.advanceTimersByTimeAsync(0);
    await settle();
    expect(player.debugQueueLength()).toBe(0);
    expect(player.debugPlayedCount()).toBe(2);
    expect(created[1].stopped).toBe(false); // Ben's relay keeps playing
  });

  it("does nothing for a speaker with no audio in flight", async () => {
    const { AudioPlayer } = await import("../audio");
    const player = new AudioPlayer();

    await player.deliver(wav(10), "tts-ana", anaOpts(0));
    await settle();
    const before = player.debugPlayedCount();
    expect(before).toBe(1);

    expect(player.cancelSpeaker("00000000-0000-4000-8000-000000000000")).toBe(0);
    expect(player.debugQueueLength()).toBe(0);
    expect(created[0].stopped).toBe(false);
    expect(player.debugPlayedCount()).toBe(before);
  });
});
