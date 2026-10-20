import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminTelephony from "./AdminTelephony";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ api: apiMock }));

const opsSimulated = {
  provider: {
    active_provider: "simulated",
    real_pstn_available: false,
    caller_number: "+12025550199",
    peer_webrtc_available: true,
    setup_required: true,
    setup_guide: {
      simulated: { step_1: "Run with default env", step_2: "No PSTN will be dialed" },
    },
  },
  flags: {
    telephony_provider: "auto",
    call_worker_enabled: false,
    asterisk_telephony_enabled: false,
    asterisk_inbound_enabled: false,
    asterisk_media_enabled: false,
  },
  process: {
    call_worker_ticker_running: false,
    asterisk_media_runtime_armed: false,
  },
  queues: { telephony: 0 },
};

const calls = [{
  id: "c-1", call_sid: "CA-1", direction: "outbound", status: "ended",
  mode: "human_to_human", provider: "simulated", duration_seconds: 54,
  total_cost_cents: 0, started_at: "2026-10-20T12:00:00Z", ended_at: null,
}];

function renderOps() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminTelephony />
    </QueryClientProvider>,
  );
}

describe("AdminTelephony ops surface", () => {
  beforeEach(() => {
    apiMock.mockImplementation((path: string) => {
      if (path === "/api/v1/admin/telephony-ops") return Promise.resolve(opsSimulated);
      if (path.startsWith("/api/v1/telephony/calls")) return Promise.resolve(calls);
      return Promise.resolve(null);
    });
  });

  afterEach(() => {
    cleanup();
    apiMock.mockReset();
  });

  it("never advertises PSTN on the simulated lane — says so explicitly", async () => {
    renderOps();
    expect(await screen.findByTestId("flags-table")).toBeInTheDocument();
    expect(screen.queryByText("REAL PSTN")).not.toBeInTheDocument();
    expect(screen.getByText("local / simulated — NOT PSTN")).toBeInTheDocument();
    expect(screen.getByTestId("setup-guide")).toBeInTheDocument();
    expect(screen.getByText("No PSTN will be dialed")).toBeInTheDocument();
  });

  it("keeps configured separate from armed — nothing armed shows not-armed rows", async () => {
    renderOps();
    const table = await screen.findByTestId("flags-table");
    const rows = within(table).getAllByRole("row");
    expect(rows.length).toBe(5);                      // header + 4 components
    expect(within(table).getAllByText("not armed").length).toBe(2);
    expect(within(table).getAllByText("off").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId("queue-depth")).toHaveTextContent("0");
    // recent calls table shows the seeded session with honest cost column
    expect(screen.getByText("CA-1")).toBeInTheDocument();
  });
});

