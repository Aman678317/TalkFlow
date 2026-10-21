/**
 * Roster query for the meeting room.
 *
 * The adaptive roster poll lives in a hook on purpose. React-Query builds its
 * query observer DURING the first render — `new Observer(client, options)`
 * calls `setOptions()`, which calls `#computeRefetchInterval()`, which
 * INVOKES a function-form `refetchInterval` right there. A callback that
 * closed over a component-scope binding declared LATER in the component body
 * therefore ran inside the temporal dead zone: "Cannot access 'socketState'
 * before initialization" — React tore the tree down and the page rendered
 * blank (webrtc-smoke, 2026-10-20: all four e2e tests failed on their first
 * DOM assertion, `locator('#lobby-name')` never appeared).
 *
 * Inside a hook the callback closes over FUNCTION PARAMETERS only, which are
 * always initialized, so the trap cannot recur. Keep it that way: do not
 * capture component state in this callback — pass it in as a parameter.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { rosterPollingMs } from "../lib/adaptivePolling";
import type { ParticipantInfo } from "../lib/types";
import type { SocketState } from "../lib/ws";

export function useRosterQuery(
  id: string,
  participantId: string | undefined,
  socketState: SocketState,
  pageHidden: boolean,
) {
  return useQuery({
    queryKey: ["meeting", id, "participants", participantId],
    queryFn: () =>
      api<ParticipantInfo[]>(`/api/v1/meetings/${id}/participants?participant_id=${participantId}`),
    enabled: !!participantId,
    // Events are the primary freshness channel while the socket is joined, so
    // the poll is only a slow correction then; a hidden page stops polling.
    refetchInterval: () => rosterPollingMs(socketState, pageHidden),
  });
}
