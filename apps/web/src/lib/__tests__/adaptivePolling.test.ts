import { describe, expect, it } from "vitest";
import {
  DOCUMENTS_ACTIVE_POLL_MS,
  ROSTER_FAST_POLL_MS,
  ROSTER_JOINED_POLL_MS,
  documentsPollingMs,
  rosterPollingMs,
} from "../adaptivePolling";

/**
 * 2026-10-20 localhost audit round 2: fixed-cadence polls ran forever even when
 * nothing could change (documents list polled every 3 s with every row settled;
 * a joined room re-fetched the roster every 5 s while the socket already
 * delivers join/leave events). The helpers must adapt, and an UNKNOWN document
 * status must keep polling (fail-open on states we don't know — stopping would
 * strand a row mid-pipeline).
 */
describe("documentsPollingMs", () => {
  it("stops once every row is settled", () => {
    expect(documentsPollingMs(["ready", "ready", "failed"], false)).toBe(false);
    expect(documentsPollingMs([], false)).toBe(false);
  });

  it("keeps the 3 s progress poll while any row is in the pipeline", () => {
    for (const inflight of [
      "uploaded",
      "queued",
      "scanning",
      "parsing",
      "translating",
      "reconstructing",
      "quality_check",
    ]) {
      expect(documentsPollingMs(["ready", inflight], false)).toBe(
        DOCUMENTS_ACTIVE_POLL_MS,
      );
    }
  });

  it("keeps polling on an unrecognized status (never strands a row)", () => {
    expect(documentsPollingMs(["ready", "mystery_state"], false)).toBe(
      DOCUMENTS_ACTIVE_POLL_MS,
    );
  });

  it("pauses while the page is hidden, regardless of statuses", () => {
    expect(documentsPollingMs(["parsed" /* unknown => inflight */], true)).toBe(false);
    expect(documentsPollingMs(["ready"], true)).toBe(false);
  });
});

describe("rosterPollingMs", () => {
  it("uses the slow correctional poll while the socket is joined (events are primary)", () => {
    expect(rosterPollingMs("joined", false)).toBe(ROSTER_JOINED_POLL_MS);
  });

  it("keeps the fast poll for every non-delivering socket state", () => {
    for (const state of ["connecting", "reconnecting", "closed", "error"]) {
      expect(rosterPollingMs(state, false)).toBe(ROSTER_FAST_POLL_MS);
    }
  });

  it("pauses while the page is hidden", () => {
    expect(rosterPollingMs("joined", true)).toBe(false);
    expect(rosterPollingMs("error", true)).toBe(false);
  });
});
