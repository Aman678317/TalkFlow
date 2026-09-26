import { describe, expect, it } from "vitest";
import { decodeBinaryFrame } from "../ws";
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
