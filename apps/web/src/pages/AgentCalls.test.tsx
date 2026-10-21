import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AgentCalls from "./AgentCalls";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ api: apiMock }));

const pendingTicket = {
  ticket_id: "esc-1",
  call_sid: "talkflow-call-1",
  reason: "human_request",
  summary: null,
  turns: 2,
  age_seconds: 42,
  state: "pending",
  claimed_by: null,
};

const claimedTicket = {
  ...pendingTicket,
  ticket_id: "esc-2",
  call_sid: "talkflow-call-2",
  state: "claimed",
  claimed_by: "Amara",
};

const claimedAfter = { ...pendingTicket, state: "claimed", claimed_by: "ui-agent" };
const resolvedAfter = { ...claimedTicket, state: "resolved", resolution: "handled_by_human" };

const transcript = {
  call: { id: "c1", call_sid: "talkflow-call-1", direction: "outbound", mode: "ai_agent",
          status: "connected", provider: "asterisk", caller_language: "en",
          receiver_language: "hi", duration_seconds: 30 },
  turns: [
    {
      turn: 0, at: "2026-10-20T12:00:00Z", caller: {},
      agent_lines: [{ text: "AI disclosure line.", node: "disclose", action: "speak", tts: "absent", frames_rendered: 0 }],
      citations: [{ node: "disclose", from: "disclose", to: "disclose",
                    inputs_sha256: "inp-0", output_sha256: "out-0", escalation_reason: null }],
    },
    {
      turn: 1, at: "2026-10-20T12:00:05Z",
      caller: { text_len: 9, text_sha256: "abc123def4567890", confidence: 0.42, frames: 20 },
      agent_lines: [],
      citations: [{ node: "escalate", from: "disclose", to: "escalate",
                    inputs_sha256: "inp-1", output_sha256: "out-1", escalation_reason: "human_request" }],
    },
  ],
  outcome: { terminal: "escalated", escalation_reason: "human_request", summary: "human", turns: 1 },
  escalations: [],
  media_timeline: [],
  unsurfaced_events: {},
  meta: { turns: 2, events_total: 5 },
};

function renderConsole() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AgentCalls />
    </QueryClientProvider>,
  );
}

describe("AgentCalls live-agent console", () => {
  beforeEach(() => {
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path === "/api/v1/telephony/escalations" && !options) {
        return Promise.resolve([pendingTicket, claimedTicket]);
      }
      if (path === "/api/v1/telephony/escalations/esc-1/claim" && options?.method === "POST") {
        return Promise.resolve(claimedAfter);
      }
      if (path === "/api/v1/telephony/escalations/esc-2/resolve" && options?.method === "POST") {
        return Promise.resolve(resolvedAfter);
      }
      if (path.startsWith("/api/v1/telephony/calls/") && path.endsWith("/transcript")) {
        return Promise.resolve(transcript);
      }
      return Promise.resolve(null);
    });
  });

  afterEach(() => {
    cleanup();
    apiMock.mockReset();
  });

  it("renders honest reasons, durations and sections — and claims a ticket with the exact contract", async () => {
    renderConsole();

    const reasonRows = await screen.findAllByText("Requested a human");
    expect(reasonRows.length).toBe(2);              // both seeded tickets
    expect(screen.getByTestId("board-pending")).toBeInTheDocument();
    expect(screen.getByTestId("board-claimed-by-agents")).toBeInTheDocument();
    expect(screen.getByText(/talkflow-call-1/)).toBeInTheDocument();
    expect((await screen.findAllByText(/waiting 42s/)).length).toBe(2);

    const claimButtons = await screen.findAllByRole("button", { name: "Claim" });
    fireEvent.click(claimButtons[0]);

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      "/api/v1/telephony/escalations/esc-1/claim",
      { method: "POST", body: {} },
    ));
  });

  it("resolves a claimed ticket with the selected resolution code", async () => {
    renderConsole();

    const selects = await screen.findAllByLabelText("Resolution");
    fireEvent.change(selects[0], { target: { value: "called_back_by_agent" } });

    const resolveButtons = await screen.findAllByRole("button", { name: "Resolve" });
    fireEvent.click(resolveButtons[0]);

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      "/api/v1/telephony/escalations/esc-2/resolve",
      { method: "POST", body: { resolution: "called_back_by_agent" } },
    ));
  });

  it("shows the transcript with caller fingerprints ONLY + citations — never caller text", async () => {
    renderConsole();

    const viewButtons = await screen.findAllByRole("button", { name: "View call" });
    fireEvent.click(viewButtons[0]);

    const turns = await screen.findAllByTestId("transcript-turn"); // greeting + turn 1
    expect(turns.length).toBe(2);
    expect(screen.getByTestId("agent-line")).toHaveTextContent("AI disclosure line.");
    expect(screen.getByTestId("caller-fingerprint")).toHaveTextContent("sha256:abc123def456");
    expect(screen.getByTestId("caller-fingerprint")).toHaveTextContent("9 chars");
    expect(screen.getByTestId("caller-fingerprint")).toHaveTextContent("fingerprint only");
    const citations = await screen.findAllByTestId("citation-line");
    expect(citations[0]).toHaveTextContent("disclose→disclose");
    expect(citations[1]).toHaveTextContent("disclose→escalate");

    // The word "chars" proves we render len, not text; raw caller text has no
    // field in the wire contract at all.
    expect(screen.queryByTestId("caller-raw-text")).not.toBeInTheDocument();
  });

  it("keeps the closed section out of the board until a ticket is resolved", async () => {
    renderConsole();
    await screen.findAllByText("Requested a human"); // board loaded
    expect(screen.queryByTestId("board-resolved")).not.toBeInTheDocument();
  });
});
