import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useAuth } from "../stores/auth";
import * as apiModule from "../lib/api";
import { ErrorBoundary } from "../components/common/ErrorBoundary";

describe("Phase 14: Frontend Production Hardening", () => {
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

  describe("1. Prevention of Stale Cached Identity Display", () => {
    it("does NOT display stale cached identity when auth verification fails", async () => {
      // Simulate stale leftover user profile in localStorage from prior session
      localStorage.setItem(
        "gt.local_user",
        JSON.stringify({ id: "usr_stale", email: "stale@example.com", name: "Stale Ghost" })
      );
      localStorage.setItem("gt.local_org", JSON.stringify({ id: "org_stale", name: "Stale Org" }));

      // Mock api to fail with 401 Unauthorized
      vi.spyOn(apiModule, "api").mockRejectedValue(
        new apiModule.ApiError(401, {
          error: { code: "authentication_required", message: "Token expired or revoked" },
        })
      );

      await useAuth.getState().refreshMe();

      const state = useAuth.getState();
      expect(state.status).toBe("unauthed");
      expect(state.user).toBeNull();
      expect(state.org).toBeNull();
      expect(localStorage.getItem("gt.local_user")).toBeNull();
      expect(localStorage.getItem("gt.local_org")).toBeNull();
    });

    it("clears cached state and broadcasts logout on logout()", async () => {
      localStorage.setItem("gt.local_user", JSON.stringify({ id: "usr_active", email: "active@example.com" }));
      useAuth.setState({
        user: { id: "usr_active", email: "active@example.com", is_platform_admin: false, email_verified: true },
        status: "authed",
      });

      vi.spyOn(apiModule, "api").mockResolvedValue({});

      await useAuth.getState().logout();

      const state = useAuth.getState();
      expect(state.status).toBe("unauthed");
      expect(state.user).toBeNull();
      expect(localStorage.getItem("gt.local_user")).toBeNull();
    });
  });

  describe("2. Multi-Tab Token Synchronization & Deduplication", () => {
    it("deduplicates concurrent refresh attempts into a single operation", async () => {
      let fetchCalls = 0;
      vi.stubGlobal(
        "fetch",
        vi.fn().mockImplementation(async () => {
          fetchCalls++;
          // simulate slight network delay
          await new Promise((resolve) => setTimeout(resolve, 10));
          return {
            ok: true,
            status: 200,
            json: async () => ({
              access_token: "new-access-token-999",
              refresh_token: "new-refresh-token-999",
            }),
          };
        })
      );

      // Trigger multiple concurrent tryRefresh calls
      const [res1, res2, res3] = await Promise.all([
        apiModule.tryRefresh(),
        apiModule.tryRefresh(),
        apiModule.tryRefresh(),
      ]);

      expect(res1).toBe(true);
      expect(res2).toBe(true);
      expect(res3).toBe(true);
      expect(fetchCalls).toBe(1);
      expect(apiModule.getAccessToken()).toBe("new-access-token-999");
    });

    it("resets auth state when receiving cross-tab LOGOUT broadcast", () => {
      useAuth.setState({
        user: { id: "usr_tab", email: "tab@example.com", is_platform_admin: false, email_verified: true },
        status: "authed",
      });

      // Trigger cross-tab logout broadcast
      apiModule.broadcastLogout();

      const state = useAuth.getState();
      expect(state.status).toBe("unauthed");
      expect(state.user).toBeNull();
      expect(apiModule.getAccessToken()).toBeNull();
    });
  });

  describe("3. Error Boundaries & Friendly Recovery States", () => {
    it("renders children cleanly when no errors occur", () => {
      render(
        <ErrorBoundary sectionName="TestSafe">
          <div data-testid="safe-content">All systems nominal</div>
        </ErrorBoundary>
      );

      expect(screen.getByTestId("safe-content")).toBeDefined();
      expect(screen.getByText("All systems nominal")).toBeDefined();
    });

    it("catches render crashes and renders a friendly recovery UI with Try Again and Reload", () => {
      // Silence React error boundary console log for test
      const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      function BrokenComponent(): JSX.Element {
        throw new Error("WebRTC peer connection abruptly disconnected");
      }

      const onResetMock = vi.fn();

      render(
        <ErrorBoundary sectionName="TestCrash" onReset={onResetMock}>
          <BrokenComponent />
        </ErrorBoundary>
      );

      // Verify friendly error message rendered
      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText("WebRTC peer connection abruptly disconnected")).toBeDefined();
      expect(screen.getByText("Try Again")).toBeDefined();
      expect(screen.getByText("Reload Page")).toBeDefined();
      expect(screen.getByText("Dashboard")).toBeDefined();

      // Test Try Again button triggers onReset
      fireEvent.click(screen.getByText("Try Again"));
      expect(onResetMock).toHaveBeenCalledTimes(1);

      consoleErrorSpy.mockRestore();
    });
  });
});
