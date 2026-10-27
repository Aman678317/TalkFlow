import { describe, expect, it } from "vitest";
import { decodeBinaryFrame, normId } from "./ws";

describe("normId", () => {
  it("strips dashes from UUIDs and truncates to 16 hex chars", () => {
    const rawUuid = "123e4567-e89b-12d3-a456-426614174000";
    // 123e4567e89b12d3
    expect(normId(rawUuid)).toBe("123e4567e89b12d3");
  });

  it("strips trailing NUL characters from binary frame padding", () => {
    const withNuls = "segment123\u0000\u0000\u0000\u0000\u0000\u0000";
    expect(normId(withNuls)).toBe("segment123");
  });

  it("strips trailing ASCII '0' padding from legacy Tree B encoders", () => {
    const withZeros = "abc1230000000000";
    expect(normId(withZeros)).toBe("abc123");
  });

  it("handles short ids without extra padding", () => {
    expect(normId("shortid")).toBe("shortid");
  });
});

describe("decodeBinaryFrame", () => {
  it("decodes original audio frame (0x4f 'O')", () => {
    const encoder = new TextEncoder();
    // 1 byte kind (0x4f) + 16 bytes shortId + PCM payload
    const shortIdBytes = encoder.encode("user-speaker-123"); // 16 bytes
    const pcmBytes = new Uint8Array([0x01, 0x02, 0x03, 0x04]);

    const buffer = new Uint8Array(1 + 16 + pcmBytes.length);
    buffer[0] = 0x4f; // 'O'
    buffer.set(shortIdBytes, 1);
    buffer.set(pcmBytes, 17);

    const frame = decodeBinaryFrame(buffer.buffer);
    expect(frame.kind).toBe("original");
    expect(frame.shortId).toBe(normId("user-speaker-123"));
    expect(frame.language).toBe("");
    expect(new Uint8Array(frame.pcm)).toEqual(pcmBytes);
    expect(frame.chunkIndex).toBeUndefined();
  });

  it("decodes legacy TTS audio frame (0x54 'T') without chunk index extension", () => {
    const encoder = new TextEncoder();
    const shortIdBytes = encoder.encode("tts-segment-0001"); // 16 bytes
    const lang = "es";
    const langBytes = encoder.encode(lang);
    const wavBytes = new Uint8Array([0x52, 0x49, 0x46, 0x46]); // "RIFF"

    const buffer = new Uint8Array(1 + 16 + 1 + langBytes.length + wavBytes.length);
    buffer[0] = 0x54; // 'T'
    buffer.set(shortIdBytes, 1);
    buffer[17] = langBytes.length;
    buffer.set(langBytes, 18);
    buffer.set(wavBytes, 18 + langBytes.length);

    const frame = decodeBinaryFrame(buffer.buffer);
    expect(frame.kind).toBe("tts");
    expect(frame.shortId).toBe(normId("tts-segment-0001"));
    expect(frame.language).toBe("es");
    expect(frame.chunkIndex).toBeUndefined();
    expect(new Uint8Array(frame.pcm)).toEqual(wavBytes);
  });

  it("decodes extended TTS audio frame with chunk index marker 0x01 and uint32 index", () => {
    const encoder = new TextEncoder();
    const shortIdBytes = encoder.encode("tts-segment-0002"); // 16 bytes
    const lang = "hi";
    const langBytes = encoder.encode(lang);
    const chunkIndex = 42;
    const wavBytes = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0xaa, 0xbb]);

    const headerLen = 1 + 16 + 1 + langBytes.length; // 18 + 2 = 20
    const buffer = new Uint8Array(headerLen + 1 + 4 + wavBytes.length);
    buffer[0] = 0x54; // 'T'
    buffer.set(shortIdBytes, 1);
    buffer[17] = langBytes.length;
    buffer.set(langBytes, 18);

    // Extension marker 0x01
    buffer[headerLen] = 0x01;
    // 4-byte uint32 big-endian chunk index
    new DataView(buffer.buffer, headerLen + 1, 4).setUint32(0, chunkIndex);
    // Payload bytes
    buffer.set(wavBytes, headerLen + 5);

    const frame = decodeBinaryFrame(buffer.buffer);
    expect(frame.kind).toBe("tts");
    expect(frame.shortId).toBe(normId("tts-segment-0002"));
    expect(frame.language).toBe("hi");
    expect(frame.chunkIndex).toBe(42);
    expect(new Uint8Array(frame.pcm)).toEqual(wavBytes);
  });
});
