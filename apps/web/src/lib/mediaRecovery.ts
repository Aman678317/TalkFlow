/**
 * Recovery bookkeeping for the LiveKit room's bounded reconnect loop.
 *
 * The bounded retry (see hooks/useLiveKitRoom) must never be defeated by an
 * enemy network that blinks: the LiveKit signal handshake can complete in the
 * same instant the socket is cut (an outage drilled at the socket boundary
 * closes the WebSocket ~25 ms after construction), so a `Connected` state can
 * last only milliseconds. Counting such a blip as recovery — resetting the
 * attempt counter — would loop Connected → Disconnected forever and hold the
 * seat in a phantom eternal "Reconnecting" instead of the honest error state.
 *
 * Policy: a connected spell counts as RECOVERY (and may reset the bounded
 * attempt counter) only once it has HELD for `RECOVERY_CONFIRM_MS`. The reset
 * is evaluated when the outage re-asserts itself (connect failure or room
 * disconnect): a long-lived connection that later dies is a genuinely fresh
 * outage and starts from attempt 1; a blip that dies within the confirm
 * window is part of the outage still in progress, so the counter keeps
 * accruing and the loop still ends in bounded, honest failure.
 */

/** How long a connected spell must hold before it may reset the bounded
 * reconnect attempts. Far above any real handshake blip (the outage drill
 * cuts at 25 ms) and far below a real join/recovery. */
export const RECOVERY_CONFIRM_MS = 10_000;

/** True when the connected spell that started at `connectedSince` counts as
 * real recovery at time `now` — i.e., the bounded attempt counter may be
 * reset before counting the next failure. `null` means nothing is connected. */
export function isConfirmedRecovery(
  connectedSince: number | null,
  now: number,
): boolean {
  return connectedSince !== null && now - connectedSince >= RECOVERY_CONFIRM_MS;
}
