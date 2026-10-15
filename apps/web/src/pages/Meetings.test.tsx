import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import Meetings from "./Meetings";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ api: apiMock }));

const meeting = {
  id: "meeting-123",
  title: "Planning session",
  status: "scheduled",
  room_name: "planning-session-a1b2c3",
  created_at: "2026-01-01T00:00:00Z",
  started_at: null,
  ended_at: null,
  has_summary: false,
  transport: "websocket",
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function renderMeetings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/meetings"]}>
      <QueryClientProvider client={queryClient}>
        <Meetings />
        <LocationProbe />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function postCalls() {
  return apiMock.mock.calls.filter(([, options]) => options?.method === "POST");
}

describe("Meetings new meeting menu", () => {
  beforeEach(() => {
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === "POST") return Promise.resolve(meeting);
      if (path === "/api/v1/meetings") return Promise.resolve([]);
      return Promise.resolve(null);
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    apiMock.mockReset();
  });

  it("opens exactly three keyboard-accessible options and prevents duplicate instant submits", async () => {
    let resolvePost!: (value: typeof meeting) => void;
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (options?.method === "POST") return new Promise((resolve) => { resolvePost = resolve; });
      if (path === "/api/v1/meetings") return Promise.resolve([]);
      return Promise.resolve(null);
    });

    renderMeetings();
    fireEvent.click(screen.getByRole("button", { name: "New meeting" }));

    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
    expect(screen.getByRole("menuitem", { name: "Start an instant meeting" })).toBeEnabled();
    expect(screen.getByRole("menuitem", { name: "Create a meeting for later" })).toBeEnabled();
    expect(screen.getByRole("menuitem", { name: "Schedule in Google Calendar" })).toBeEnabled();

    fireEvent.click(screen.getByRole("menuitem", { name: "Start an instant meeting" }));
    await waitFor(() => expect(postCalls()).toHaveLength(1));
    expect(screen.getByRole("button", { name: /Creating/ })).toBeDisabled();
    resolvePost(meeting);

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/meeting/meeting-123"));
  });

  it("shows the real invite URL for later meetings and opens a prefilled calendar draft", async () => {
    renderMeetings();
    fireEvent.click(screen.getByRole("button", { name: "New meeting" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Create a meeting for later" }));

    const inviteUrl = `${window.location.origin}/meeting/meeting-123`;
    await screen.findByText(inviteUrl);
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
  });

  it("creates the room before exposing Google Calendar", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderMeetings();
    fireEvent.click(screen.getByRole("button", { name: "New meeting" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Schedule in Google Calendar" }));

    const calendarButton = await screen.findByRole("button", { name: "Open Google Calendar" });
    expect(postCalls()).toHaveLength(1);
    fireEvent.click(calendarButton);

    expect(open).toHaveBeenCalledTimes(1);
    const calendarUrl = String(open.mock.calls[0][0]);
    const query = new URL(calendarUrl).searchParams;
    expect(query.get("action")).toBe("TEMPLATE");
    expect(query.get("text")).toBe("Planning session");
    const inviteUrl = `${window.location.origin}/meeting/meeting-123`;
    expect(query.get("details")).toContain(inviteUrl);
    expect(query.get("location")).toBe(inviteUrl);
  });
});
