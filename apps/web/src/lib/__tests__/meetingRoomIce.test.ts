import { describe, expect, it } from "vitest";
import { iceQueryEnabled, iceQueryKey, iceQueryUrl } from "../meetingRoomIce";

/**
 * The room seat id lands asynchronously (join handshake). A single
 * `participant_id=undefined` 404 must not poison the ICE query for its whole
 * TTL — that silently drops any configured TURN edge from the P2P mesh
 * (2026-10-20 local audit, GET /api/v1/meetings/{id}/ice-servers).
 */
describe("meetingRoomIce helpers", () => {
  it("does not enable the query before a seat identity exists", () => {
    expect(iceQueryEnabled("in", undefined)).toBe(false);
    expect(iceQueryEnabled("in", null)).toBe(false);
    expect(iceQueryEnabled("in", "")).toBe(false);
    expect(iceQueryEnabled("lobby", undefined)).toBe(false);
  });

  it("never enables outside lobby/in phases even with a seat", () => {
    expect(iceQueryEnabled("prejoin", "seat-1")).toBe(false);
    expect(iceQueryEnabled("left", "seat-1")).toBe(false);
    expect(iceQueryEnabled("error", "seat-1")).toBe(false);
  });

  it("enables once the phase allows it AND a seat exists", () => {
    expect(iceQueryEnabled("in", "seat-1")).toBe(true);
    expect(iceQueryEnabled("lobby", "seat-1")).toBe(true);
  });

  it("keys the cache per seat so a late seat identity refetches", () => {
    const early = iceQueryKey("m1", undefined);
    const late = iceQueryKey("m1", "seat-1");
    expect(early).toEqual(["meeting", "m1", "ice-servers", "anonymous"]);
    expect(late).toEqual(["meeting", "m1", "ice-servers", "seat-1"]);
    expect(iceQueryKey("m1", "seat-1")).not.toEqual(early);
    // A different meeting must never share a cache entry.
    expect(iceQueryKey("m2", "seat-1")).not.toEqual(late);
  });

  it("builds the endpoint URL with an encoded, always-present participant id", () => {
    expect(iceQueryUrl("m1", "seat-1")).toBe(
      "/api/v1/meetings/m1/ice-servers?participant_id=seat-1",
    );
    // Encoding guards against ids with query/signature characters.
    expect(iceQueryUrl("m1", "a&b=c d")).toBe(
      "/api/v1/meetings/m1/ice-servers?participant_id=a%26b%3Dc%20d",
    );
  });
});
