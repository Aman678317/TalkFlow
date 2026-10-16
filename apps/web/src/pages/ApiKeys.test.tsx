import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ApiKeys from "./ApiKeys";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({ api: apiMock }));

const activeKey = {
  id: "key-1",
  name: "production-backend",
  prefix: "gtk_live_abc",
  scopes: ["translate", "detect"],
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  last_used_at: null,
  expires_at: null,
};

function renderApiKeys() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiKeys />
    </QueryClientProvider>,
  );
}

describe("ApiKeys canonical service contract", () => {
  beforeEach(() => {
    apiMock.mockImplementation((path: string, options?: { method?: string; body?: unknown }) => {
      if (path === "/api/v1/api-keys" && options?.method === "POST") {
        return Promise.resolve({ ...activeKey, plaintext_key: "gtk_live_new_secret" });
      }
      if (path === "/api/v1/api-keys" && !options) return Promise.resolve([activeKey]);
      return Promise.resolve(null);
    });
  });

  afterEach(() => {
    cleanup();
    apiMock.mockReset();
  });

  it("shows the canonical plaintext_key after creation", async () => {
    renderApiKeys();
    fireEvent.click(await screen.findByRole("button", { name: "+ New key" }));
    fireEvent.change(screen.getByPlaceholderText("production-backend"), {
      target: { value: "ci-backend" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create key" }));

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      "/api/v1/api-keys",
      { method: "POST", body: { name: "ci-backend", scopes: ["translate", "detect"] } },
    ));
    expect(await screen.findByText("gtk_live_new_secret")).toBeInTheDocument();
  });

  it("uses status to hide actions for revoked keys", async () => {
    apiMock.mockImplementation((path: string) => path === "/api/v1/api-keys"
      ? Promise.resolve([{ ...activeKey, status: "revoked" }])
      : Promise.resolve(null));

    renderApiKeys();
    expect(await screen.findByText("revoked")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rotate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });

  it("shows plaintext_key returned by rotation", async () => {
    apiMock.mockImplementation((path: string, options?: { method?: string }) => {
      if (path === "/api/v1/api-keys" && !options) return Promise.resolve([activeKey]);
      if (path === "/api/v1/api-keys/key-1/rotate") {
        return Promise.resolve({ ...activeKey, name: "production-backend", plaintext_key: "gtk_live_rotated" });
      }
      return Promise.resolve(null);
    });

    renderApiKeys();
    fireEvent.click(await screen.findByRole("button", { name: "Rotate" }));
    expect(await screen.findByText("gtk_live_rotated")).toBeInTheDocument();
  });
});
