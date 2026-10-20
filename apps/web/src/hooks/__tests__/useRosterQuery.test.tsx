/**
 * Regression tests for the adaptive roster poll.
 *
 * 2026-10-20, webrtc-smoke lane: all four e2e tests failed on their first
 * DOM assertion (`locator('#lobby-name')` never appeared) and the failure
 * screenshot was a completely blank page. The Playwright trace carried the
 * cause:
 *
 *   ReferenceError: Cannot access 'S' before initialization
 *     at refetchInterval (…) at P (…/query-*.js) at Ge.ue at Ge.setOptions
 *
 * React-Query builds its query observer DURING the first render — the
 * observer constructor calls `setOptions()`, which calls
 * `#computeRefetchInterval()`, which INVOKES a function-form `refetchInterval`
 * right there. A callback that closed over a component-scope `const` declared
 * LATER in the component body therefore ran inside the temporal dead zone and
 * React tore the whole tree down.
 *
 * These tests pin the mechanism (so nobody "simplifies" it away) and pin the
 * structural fix: the interval callback lives in a hook and closes over
 * function parameters only.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import React from "react";
import { useRosterQuery } from "../useRosterQuery";
import type { SocketState } from "../../lib/ws";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", () => ({ api: apiMock }));

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(client: QueryClient, ui: React.ReactNode) {
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** Captures a render error instead of letting React log it as an unhandled error. */
class Boundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) return <output data-testid="err">{this.state.error.message}</output>;
    return this.props.children;
  }
}

function Harness(props: { socketState: SocketState; pageHidden: boolean; participantId?: string }) {
  useRosterQuery("m1", props.participantId, props.socketState, props.pageHidden);
  return <output data-testid="ok">rendered</output>;
}

/** Reads the interval the observer actually computed for the roster query. */
function computedInterval(client: QueryClient, participantId: string): number | false | undefined {
  const q = client.getQueryCache().find({ queryKey: ["meeting", "m1", "participants", participantId] });
  const observer = q?.observers?.[0];
  const interval = observer?.options?.refetchInterval;
  if (typeof interval === "function") return interval(q as never);
  return interval as number | false | undefined;
}

beforeEach(() => {
  apiMock.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  apiMock.mockReset();
});

describe("the temporal-dead-zone trap (mechanism)", () => {
  it("react-query evaluates a function-form refetchInterval during the FIRST render", () => {
    // `later` is declared AFTER the query — the callback reads it while it is
    // still in the temporal dead zone.
    function Trap() {
      useQuery({
        queryKey: ["tdz-trap"],
        queryFn: () => Promise.resolve(1),
        refetchInterval: () => later,
      });
      const later = 5;
      return null;
    }

    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      wrap(makeClient(), (
        <Boundary>
          <Trap />
        </Boundary>
      ));
      expect(screen.getByTestId("err").textContent).toMatch(/before initialization/);
    } finally {
      spy.mockRestore();
    }
  });
});

describe("useRosterQuery", () => {
  it("renders without a temporal-dead-zone error (the blank-page regression)", () => {
    const client = makeClient();
    wrap(client, (
      <Boundary>
        <Harness socketState="joined" pageHidden={false} participantId="p1" />
      </Boundary>
    ));
    expect(screen.queryByTestId("err")).toBeNull();
    expect(screen.getByTestId("ok").textContent).toBe("rendered");
  });

  it("polls fast while the socket is not delivering events", () => {
    const client = makeClient();
    wrap(client, <Harness socketState="connecting" pageHidden={false} participantId="p1" />);
    expect(computedInterval(client, "p1")).toBe(5_000);
  });

  it("polls slowly while the socket is joined (events are the primary channel)", () => {
    const client = makeClient();
    wrap(client, <Harness socketState="joined" pageHidden={false} participantId="p1" />);
    expect(computedInterval(client, "p1")).toBe(30_000);
  });

  it("stops polling while the page is hidden", () => {
    const client = makeClient();
    wrap(client, <Harness socketState="joined" pageHidden participantId="p1" />);
    expect(computedInterval(client, "p1")).toBe(false);
  });

  it("stays disabled until the participant has a seat", async () => {
    const client = makeClient();
    wrap(client, <Harness socketState="joined" pageHidden={false} />);
    await waitFor(() => expect(apiMock).not.toHaveBeenCalled());
    expect(computedInterval(client, "")).toBeUndefined();
  });

  it("fetches the roster once a seat exists", async () => {
    const client = makeClient();
    apiMock.mockResolvedValue([{ participant_id: "p1", name: "Ana" }]);
    wrap(client, <Harness socketState="joined" pageHidden={false} participantId="p1" />);
    await waitFor(() =>
      expect(apiMock).toHaveBeenCalledWith("/api/v1/meetings/m1/participants?participant_id=p1"),
    );
  });
});
