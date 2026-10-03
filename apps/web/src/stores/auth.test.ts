import { describe, it, expect, beforeEach, vi } from "vitest";
import { useAuth } from "./auth";
import * as apiModule from "../lib/api";

describe("useAuth store", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    useAuth.setState({
      user: null,
      org: null,
      organizations: [],
      role: null,
      permissions: [],
      initialized: false,
      status: "unauthed",
    });
  });

  it("successfully logs in and stores tokens and user state", async () => {
    const mockApiResponse = {
      tokens: { access_token: "jwt-access-123", refresh_token: "jwt-refresh-123" },
      user: { id: "usr_1", email: "alice@example.com", name: "Alice", is_platform_admin: false, email_verified: true },
      membership: { org: { id: "org_1", name: "Acme", slug: "acme", plan: "pro" }, role: "owner" },
      organizations: [{ org: { id: "org_1", name: "Acme", slug: "acme", plan: "pro" }, role: "owner" }],
    };

    vi.spyOn(apiModule, "api").mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/login") return mockApiResponse;
      if (path === "/api/v1/auth/me") return mockApiResponse;
      throw new Error(`Unexpected path: ${path}`);
    });

    await useAuth.getState().login("alice@example.com", "validpass123");

    const state = useAuth.getState();
    expect(state.status).toBe("authed");
    expect(state.user?.email).toBe("alice@example.com");
    expect(state.org?.name).toBe("Acme");
    expect(localStorage.getItem("gt.access")).toBe("jwt-access-123");
    expect(localStorage.getItem("gt.refresh")).toBe("jwt-refresh-123");
  });

  it("propagates error on invalid credentials and does NOT forge local fake session", async () => {
    vi.spyOn(apiModule, "api").mockRejectedValue(new apiModule.ApiError(401, {
      error: { message: "Invalid email or password" }
    }));

    await expect(
      useAuth.getState().login("intruder@example.com", "wrongpass")
    ).rejects.toThrow("Invalid email or password");

    const state = useAuth.getState();
    expect(state.status).toBe("unauthed");
    expect(state.user).toBeNull();
    expect(localStorage.getItem("gt.access")).toBeNull();
    expect(localStorage.getItem("gt.refresh")).toBeNull();
  });

  it("logout clears tokens and localStorage", async () => {
    localStorage.setItem("gt.access", "existing-token");
    localStorage.setItem("gt.refresh", "existing-refresh");
    localStorage.setItem("gt.local_user", JSON.stringify({ id: "usr_1", email: "alice@example.com" }));

    vi.spyOn(apiModule, "api").mockResolvedValue({});

    await useAuth.getState().logout();

    const state = useAuth.getState();
    expect(state.status).toBe("unauthed");
    expect(state.user).toBeNull();
    expect(localStorage.getItem("gt.access")).toBeNull();
    expect(localStorage.getItem("gt.refresh")).toBeNull();
    expect(localStorage.getItem("gt.local_user")).toBeNull();
  });
});
