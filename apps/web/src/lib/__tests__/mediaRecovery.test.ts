/**
 * Recovery-window policy (lib/mediaRecovery): a Connected spell only counts
 * as recovery — i.e., only may reset the bounded reconnect attempts — once
 * it has held for RECOVERY_CONFIRM_MS. This is the unit-level contract for
 * the e2e outage drill (livekit-outage.spec.ts): a hostile network that
 * blinks at connect time (handshake answered, socket cut ms later) must
 * never restart the bounded loop.
 */
import { describe, expect, it } from "vitest";
import { RECOVERY_CONFIRM_MS, isConfirmedRecovery } from "../mediaRecovery";

describe("isConfirmedRecovery", () => {
  it("confirms a spell that held the full window", () => {
    const t0 = 1_000_000;
    expect(isConfirmedRecovery(t0, t0 + RECOVERY_CONFIRM_MS)).toBe(true);
  });

  it("confirms long-lived connections (real recovery)", () => {
    const t0 = 1_000_000;
    expect(isConfirmedRecovery(t0, t0 + 5 * 60_000)).toBe(true);
  });

  it("rejects a spell one millisecond short of the window", () => {
    const t0 = 1_000_000;
    expect(isConfirmedRecovery(t0, t0 + RECOVERY_CONFIRM_MS - 1)).toBe(false);
  });

  it("rejects single-digit-millisecond blips (the outage drill's 25 ms cut)", () => {
    const t0 = 1_000_000;
    expect(isConfirmedRecovery(t0, t0 + 25)).toBe(false);
    expect(isConfirmedRecovery(t0, t0 + 1)).toBe(false);
    expect(isConfirmedRecovery(t0, t0 + 0)).toBe(false);
  });

  it("rejects when nothing is connected", () => {
    expect(isConfirmedRecovery(null, 1_000_000 + RECOVERY_CONFIRM_MS)).toBe(false);
  });

  it("keeps a sane window far above handshake blips and far below joins", () => {
    // The drill's cut lands ~25 ms after construction; a real join needs
    // hundreds of ms. The window must sit strictly between the two so a
    // blip can never confirm itself and a real recovery can never be
    // denied by slow machines.
    expect(RECOVERY_CONFIRM_MS).toBeGreaterThan(1_000);
    expect(RECOVERY_CONFIRM_MS).toBeLessThan(60_000);
  });
});
