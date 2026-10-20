/**
 * ICE-server resolve helpers for the meeting room (WS-transport P2P mesh;
 * see GET /api/v1/meetings/{id}/ice-servers).
 *
 * The room's own seat id arrives asynchronously (join handshake ⇒
 * `myParticipantId` is set late). The ICE query must therefore:
 *   - not fire before a seat identity exists (a guest seat is otherwise
 *     indistinguishable from "anonymous" and the endpoint fails closed 404);
 *   - key its cache entry by the seat id, so a LATE seat refetches instead of
 *     a single `participant_id=undefined` 404 poising the query for its TTL
 *     and silently dropping any configured TURN edge from the mesh.
 */
export function iceQueryEnabled(
  phase: string,
  participantId: string | null | undefined,
): boolean {
  const phaseOk = phase === "in" || phase === "lobby";
  return phaseOk && !!participantId && participantId.length > 0;
}

export function iceQueryKey(
  meetingId: string,
  participantId: string | null | undefined,
): readonly unknown[] {
  return ["meeting", meetingId, "ice-servers", participantId ?? "anonymous"];
}

export function iceQueryUrl(
  meetingId: string,
  participantId: string | null | undefined,
): string {
  return `/api/v1/meetings/${meetingId}/ice-servers?participant_id=${encodeURIComponent(
    participantId ?? "",
  )}`;
}
