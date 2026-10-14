import { describe, it, expect, beforeEach, vi } from "vitest";
import { useAuth } from "./auth";
import * as apiModule from "../lib/api";

// Phase 1 invariant: no credential ever lands in localStorage. The access token
// lives only in the api module's memory; the refresh token only in an HttpOnly
// cookie the browser owns. These tests pin that — including that a refresh_token
// present in the login body is IGNORED.

describe("useAuth store", () => {
  beforeEach(() => {
    localStorage.clear();
    apiModule.setTokens(null);
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

  it("logs in, keeps the access token in memory only, and never stores credentials", async () => {
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
    // Access token held in memory…
    expect(apiModule.getAccessToken()).toBe("jwt-access-123");
    // …and the body's refresh_token is ignored — nothing token-like in storage.
    expect(localStorage.getItem("gt.access")).toBeNull();
    expect(localStorage.getItem("gt.refresh")).toBeNull();
    expect(localStorage.getItem("jwt-refresh-123")).toBeNull();
    // Identity cache (name/org) is fine; it is not a credential.
    expect(JSON.parse(localStorage.getItem("gt.local_user")!).email).toBe("alice@example.com");
  });

  it("propagates error on invalid credentials and does NOT forge a local fake session", async () => {
    vi.spyOn(apiModule, "api").mockRejectedValue(new apiModule.ApiError(401, {
      error: { message: "Invalid email or password" }
    }));

    await expect(
      useAuth.getState().login("intruder@example.com", "wrongpass")
    ).rejects.toThrow("Invalid email or password");

    const state = useAuth.getState();
    expect(state.status).toBe("unauthed");
    expect(state.user).toBeNull();
    expect(apiModule.getAccessToken()).toBeNull();
    expect(localStorage.getItem("gt.access")).toBeNull();
    expect(localStorage.getItem("gt.refresh")).toBeNull();
  });

  it("logout clears the in-memory token, never stored credentials, and marks logged_out", async () => {
    apiModule.setTokens("existing-access");
    localStorage.setItem("gt.local_user", JSON.stringify({ id: "usr_1", email: "alice@example.com" }));

    vi.spyOn(apiModule, "api").mockResolvedValue({});

    await useAuth.getState().logout();

    const state = useAuth.getState();
    expect(state.status).toBe("unauthed");
    expect(state.user).toBeNull();
    expect(apiModule.getAccessToken()).toBeNull();
    expect(localStorage.getItem("gt.access")).toBeNull();
    expect(localStorage.getItem("gt.refresh")).toBeNull();
    expect(localStorage.getItem("gt.local_user")).toBeNull();
    expect(localStorage.getItem("gt.logged_out")).toBe("true");
  });

  it("silent cookie bootstrap on a fresh load authenticates via refresh then /me", async () => {
    // No in-memory token, no explicit logout. The HttpOnly cookie is what authorises
    // the app; refreshMe must attempt a cookie refresh before trusting /me.
    apiModule.setTokens(null);
    const tryRefresh = vi.spyOn(apiModule, "tryRefresh").mockImplementation(async () => {
      apiModule.setTokens("refreshed-access");
      return true;
    });
    vi.spyOn(apiModule, "api").mockResolvedValue({
      user: { id: "usr_1", email: "alice@example.com", is_platform_admin: false, email_verified: true },
      membership: { org: { id: "org_1", name: "Acme", slug: "acme", plan: "pro" }, role: "owner" },
    });

    await useAuth.getState().refreshMe();

    expect(tryRefresh).toHaveBeenCalled();
    expect(useAuth.getState().status).toBe("authed");
    expect(useAuth.getState().user?.email).toBe("alice@example.com");
  });

  it("skips the cookie bootstrap after an explicit logout", async () => {
    localStorage.setItem("gt.logged_out", "true");
    apiModule.setTokens(null);
    const tryRefresh = vi.spyOn(apiModule, "tryRefresh").mockResolvedValue(false);
    const api = vi.spyOn(apiModule, "api");

    await useAuth.getState().refreshMe();

    expect(tryRefresh).not.toHaveBeenCalled();
    expect(api).not.toHaveBeenCalled();
    expect(useAuth.getState().status).toBe("unauthed");
  });
});
