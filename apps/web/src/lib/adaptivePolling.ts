/**
 * Adaptive client polling (2026-10-20 localhost audit, round 2).
 *
 * Both the documents list and the in-room roster previously polled forever at a
 * fixed cadence even when nothing could change: the Documents page fetched the
 * whole list every 3 s while every row was already settled, and a joined
 * meeting room re-fetched the roster every 5 s even though the connected
 * realtime socket already delivers `participant.joined`/`participant.left`
 * events. The API log during the audit showed the fixed cadences never yield.
 *
 * Polling now adapts:
 *  - Documents: only while any row is still inside the processing pipeline
 *    (any status OUTSIDE the settled set keeps the 3 s progress poll; an
 *    UNRECOGNIZED status is treated as in-flight — never stop on a state we
 *    don't know).
 *  - Roster: 5 s while the socket is not delivering events; a slow 30 s
 *    correctional poll while the socket is `joined` (WS events are the
 *    primary freshness channel); paused entirely while the page is hidden.
 *  - The wiring re-renders on visibilitychange via state, so a hidden page
 *    stops and a re-shown page resumes.
 */
export const DOCUMENT_SETTLED_STATUSES: ReadonlySet<string> = new Set([
  "ready",
  "failed",
]);

export const DOCUMENTS_ACTIVE_POLL_MS = 3_000;
export const ROSTER_FAST_POLL_MS = 5_000;
export const ROSTER_JOINED_POLL_MS = 30_000;

export function documentsPollingMs(
  statuses: string[],
  pageHidden: boolean,
): number | false {
  if (pageHidden) return false;
  const inflight = statuses.some((s) => !DOCUMENT_SETTLED_STATUSES.has(s));
  return inflight ? DOCUMENTS_ACTIVE_POLL_MS : false;
}

export function rosterPollingMs(
  socketState: string,
  pageHidden: boolean,
): number | false {
  if (pageHidden) return false;
  return socketState === "joined" ? ROSTER_JOINED_POLL_MS : ROSTER_FAST_POLL_MS;
}
