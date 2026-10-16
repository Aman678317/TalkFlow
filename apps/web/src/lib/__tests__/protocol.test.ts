import { describe, expect, it } from "vitest";
import { decodeBinaryFrame, normId } from "../ws";
import { ApiError } from "../api";
import { b64ToBytes } from "../audio";

function encodeOriginal(shortId: string, pcm: Uint8Array): ArrayBuffer {
  const head = new Uint8Array(17);
  head[0] = 0x4f; // 'O'
  head.set(new TextEncoder().encode(shortId.padEnd(16, "0").slice(0, 16)), 1);
  const out = new Uint8Array(17 + pcm.length);
  out.set(head, 0);
  out.set(pcm, 17);
  return out.buffer;
}

function encodeTts(shortId: string, lang: string, pcm: Uint8Array): ArrayBuffer {
  const langBytes = new TextEncoder().encode(lang);
  const out = new Uint8Array(18 + langBytes.length + pcm.length);
  out[0] = 0x54; // 'T'
  out.set(new TextEncoder().encode(shortId.padEnd(16, "0").slice(0, 16)), 1);
  out[17] = langBytes.length;
  out.set(langBytes, 18);
  out.set(pcm, 18 + langBytes.length);
  return out.buffer;
}

function encodeIndexedTts(shortId: string, lang: string, chunkIndex: number, pcm: Uint8Array): ArrayBuffer {
  const langBytes = new TextEncoder().encode(lang);
  const payloadStart = 18 + langBytes.length + 5;
  const out = new Uint8Array(payloadStart + pcm.length);
  out[0] = 0x54;
  out.set(new TextEncoder().encode(shortId.padEnd(16, "0").slice(0, 16)), 1);
  out[17] = langBytes.length;
  out.set(langBytes, 18);
  out[18 + langBytes.length] = 0x01;
  new DataView(out.buffer).setUint32(19 + langBytes.length, chunkIndex);
  out.set(pcm, payloadStart);
  return out.buffer;
}

describe("realtime binary protocol", () => {
  it("decodes original-audio relay frames", () => {
    const pcm = new Uint8Array([1, 2, 3, 4, 250, 251]);
    const frame = decodeBinaryFrame(encodeOriginal("abc123", pcm));
    expect(frame.kind).toBe("original");
    expect(frame.shortId).toBe("abc123");
    expect(new Uint8Array(frame.pcm)).toEqual(pcm);
  });

  it("decodes translated TTS frames with language", () => {
    const pcm = new Uint8Array([9, 8, 7]);
    const frame = decodeBinaryFrame(encodeTts("seg42", "hi", pcm));
    expect(frame.kind).toBe("tts");
    expect(frame.shortId).toBe("seg42");
    expect(frame.language).toBe("hi");
    expect(new Uint8Array(frame.pcm)).toEqual(pcm);
  });

  it("reads an explicit TTS chunk index when the server provides one", () => {
    const frame = decodeBinaryFrame(encodeIndexedTts("seg42", "hi", 7, new Uint8Array([9, 8])));
    expect(frame.chunkIndex).toBe(7);
    expect(new Uint8Array(frame.pcm)).toEqual(new Uint8Array([9, 8]));
  });
  // The deployed backend pads the binary short-id with NUL bytes
  // (services/api/app/realtime/pipeline.py: `…[:16].ljust(16, "\x00")`), not with the
  // ASCII character "0". Padding must be stripped for BOTH, otherwise the binary tag
  // and the JSON tag for the same audio never match and cross-transport dedup is
  // impossible. encodeTts above keeps "0" padding (Tree B's layout) to cover both.
  function encodeTtsNulPadded(shortId: string, lang: string, payload: Uint8Array): ArrayBuffer {
    const head = new Uint8Array(18 + lang.length);
    head[0] = 0x54;
    head.set(new TextEncoder().encode(shortId), 1);
    head.set(new Uint8Array(16 - shortId.length), 1 + shortId.length); // NUL padding
    head[17] = lang.length;
    head.set(new TextEncoder().encode(lang), 18);
    const out = new Uint8Array(head.length + payload.length);
    out.set(head, 0);
    out.set(payload, head.length);
    return out.buffer;
  }

  it("strips NUL padding from server-produced TTS short ids", () => {
    const frame = decodeBinaryFrame(encodeTtsNulPadded("a1b2c3d4", "hi", new Uint8Array([1])));
    expect(frame.kind).toBe("tts");
    expect(frame.shortId).toBe("a1b2c3d4");
  });

  it("strips ASCII-zero padding too (Tree B layout)", () => {
    const frame = decodeBinaryFrame(encodeTts("a1b2c3d4", "hi", new Uint8Array([1])));
    expect(frame.shortId).toBe("a1b2c3d4");
  });

  // The dedup contract: the binary short id and the JSON `segment_id` must key to the
  // same value, or the same TTS chunk is played twice (tests/unit/test_tts_transport_identity.py).
  it("keys binary and JSON transports to the same chunk identity", () => {
    const segmentId = "6f1c2d3e-4b5a-4c6d-8e9f-0a1b2c3d4e5f";
    const hex = segmentId.replace(/-/g, "");
    const frame = decodeBinaryFrame(
      encodeTtsNulPadded(hex.slice(0, 16), "hi", new Uint8Array([1]))
    );
    expect(frame.shortId).toBe(normId(segmentId));
    expect(frame.shortId).toBe(normId(hex));
  });

  // A literal "0" as the 16th hex digit is part of the id, not padding. Stripping
  // padding before the 16-char cut truncated the binary key only, so that one chunk
  // arrived under two tags and the listener heard it twice (~6% of segments).
  it("keys a segment whose prefix ends in zero once, not twice", () => {
    const segmentId = "cd58e898-050d-4280-9c3e-1a2b3c4d5e6f";
    const hex = segmentId.replace(/-/g, "");
    expect(hex[15]).toBe("0");
    const frame = decodeBinaryFrame(
      encodeTtsNulPadded(hex.slice(0, 16), "hi", new Uint8Array([1]))
    );
    expect(frame.shortId).toBe(normId(segmentId));
    expect(frame.shortId).toBe(normId(hex));
    expect(frame.shortId).toBe("cd58e898050d428");
  });
});

describe("api error contract", () => {
  it("normalizes backend structured errors", () => {
    const err = new ApiError(429, {
      error: {
        code: "rate_limited", message: "Slow down", request_id: "r1", trace_id: "t1",
        recoverable: true, details: { retry_after_seconds: 60 },
      },
    });
    expect(err.code).toBe("rate_limited");
    expect(err.message).toBe("Slow down");
    expect(err.requestId).toBe("r1");
    expect(err.recoverable).toBe(true);
    expect(err.status).toBe(429);
  });

  it("survives malformed error bodies", () => {
    const err = new ApiError(500, null);
    expect(err.code).toBe("http_500");
    expect(err.recoverable).toBe(false);
  });
});

describe("base64 audio payloads", () => {
  it("round-trips WAV bytes", () => {
    const bytes = new Uint8Array([82, 73, 70, 70, 0, 1, 2, 3]);
    const b64 = btoa(String.fromCharCode(...bytes));
    expect(b64ToBytes(b64)).toEqual(bytes);
  });
});
