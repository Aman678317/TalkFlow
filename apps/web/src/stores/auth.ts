import { create } from "zustand";
import { api, ApiError, setTokens, setUnauthorizedHandler, getAccessToken, tryRefresh } from "../lib/api";

export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  full_name?: string;
  is_platform_admin: boolean;
  email_verified: boolean;
  default_language?: string;
  speak_lang?: string;
  hear_lang?: string;
}

export interface AuthOrg {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status?: string;
}

export interface AuthOrgMember {
  org: AuthOrg;
  role: string;
}

interface AuthState {
  user: AuthUser | null;
  org: AuthOrg | null;
  organizations: AuthOrgMember[];
  role: string | null;
  permissions: string[];
  initialized: boolean;
  status: "loading" | "authed" | "unauthed";
  login: (email: string, password: string) => Promise<void>;
  socialLogin: (
    provider: "google" | "github" | "apple",
    payload?: { token?: string; code?: string; nonce?: string; redirect_uri?: string },
  ) => Promise<void>;
  signup: (data: { email: string; password: string; full_name: string; organization_name: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

function normalizeUser(u: any): AuthUser | null {
  if (!u || !u.id) return null;
  return {
    ...u,
    name: u.name || u.full_name || u.email || "",
    full_name: u.full_name || u.name || u.email || "",
    default_language: u.default_language || u.speak_lang || "en",
  };
}

function getCachedIdentity() {
  // Cache is identity-only (name/org for instant paint). It is NEVER the source of
  // "am I logged in?" — that is decided by the cookie-based refresh in refreshMe().
  try {
    if (typeof localStorage === "undefined") {
      return { user: null as AuthUser | null, org: null as AuthOrg | null };
    }
    const rawUser = localStorage.getItem("gt.local_user");
    const rawOrg = localStorage.getItem("gt.local_org");
    return {
      user: rawUser ? (JSON.parse(rawUser) as AuthUser) : null,
      org: rawOrg ? (JSON.parse(rawOrg) as AuthOrg) : null,
    };
  } catch {
    return { user: null as AuthUser | null, org: null as AuthOrg | null };
  }
}

const cachedIdentity = getCachedIdentity();

export const useAuth = create<AuthState>((set, get) => ({
  user: cachedIdentity.user,
  org: cachedIdentity.org,
  organizations: cachedIdentity.org ? [{ org: cachedIdentity.org, role: "owner" }] : [],
  role: "owner",
  permissions: [],
  initialized: false,
  status: "loading",

  async login(email, password) {
    const r = await api("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
      timeoutMs: 10000,
    });
    setTokens(r.tokens.access_token);
    const user = normalizeUser(r.user);
    const org = r.membership?.org ?? null;
    if (user) localStorage.setItem("gt.local_user", JSON.stringify(user));
    if (org) localStorage.setItem("gt.local_org", JSON.stringify(org));
    localStorage.removeItem("gt.logged_out");
    set({
      user,
      org,
      organizations: r.organizations ?? (org ? [{ org, role: r.membership?.role || "owner" }] : []),
      role: r.membership?.role ?? "owner",
      initialized: true,
      status: user ? "authed" : "unauthed",
    });
    void get().refreshMe().catch(() => {});
  },

  async socialLogin(
    provider: "google" | "github" | "apple",
    payload?: { token?: string; code?: string; nonce?: string; redirect_uri?: string },
  ) {
    const r = await api("/api/v1/auth/social-login", {
      method: "POST",
      // Phase 2: the server only accepts provider-verified credentials. Any
      // client-asserted email/name is neither sent nor honored.
      body: { provider, ...(payload ?? {}) },
      timeoutMs: 10000,
    });
    setTokens(r.tokens.access_token);
    const user = normalizeUser(r.user);
    const org = r.membership?.org ?? null;
    if (user) localStorage.setItem("gt.local_user", JSON.stringify(user));
    if (org) localStorage.setItem("gt.local_org", JSON.stringify(org));
    localStorage.removeItem("gt.logged_out");
    set({
      user,
      org,
      organizations: r.organizations ?? (org ? [{ org, role: r.membership?.role || "owner" }] : []),
      role: r.membership?.role ?? "owner",
      initialized: true,
      status: user ? "authed" : "unauthed",
    });
    void get().refreshMe().catch(() => {});
  },

  async signup(data) {
    const r = await api("/api/v1/auth/signup", {
      method: "POST",
      body: {
        email: data.email.toLowerCase().trim(),
        password: data.password,
        name: data.full_name || (data as any).name || data.email.split("@")[0],
        organization_name: data.organization_name?.trim() || "My Workspace",
      },
      timeoutMs: 10000,
    });
    setTokens(r.tokens.access_token);
    const user = normalizeUser(r.user);
    const org = r.organization ?? r.membership?.org ?? null;
    if (user) localStorage.setItem("gt.local_user", JSON.stringify(user));
    if (org) localStorage.setItem("gt.local_org", JSON.stringify(org));
    localStorage.removeItem("gt.logged_out");
    set({
      user,
      org,
      organizations: r.organizations ?? (org ? [{ org, role: "owner" }] : []),
      role: "owner",
      initialized: true,
      status: user ? "authed" : "unauthed",
    });
  },

  async logout() {
    try {
      await api("/api/v1/auth/logout", { method: "POST", body: {}, timeoutMs: 3000 });
    } catch { /* best effort */ }
    setTokens(null);
    localStorage.removeItem("gt.local_user");
    localStorage.removeItem("gt.local_org");
    localStorage.setItem("gt.logged_out", "true");
    set({
      user: null,
      org: null,
      organizations: [],
      role: null,
      permissions: [],
      initialized: true,
      status: "unauthed",
    });
  },

  async refreshMe() {
    // Silent cookie bootstrap. This tab holds no in-memory access token on a fresh
    // load, so if the browser still carries a valid HttpOnly refresh cookie, exchange
    // it for an access token before querying /me. An explicit logout (gt.logged_out)
    // skips the bootstrap until the user signs back in. No credential is read from
    // storage — presence of the cookie is the only signal.
    const loggedOut =
      typeof localStorage !== "undefined" && localStorage.getItem("gt.logged_out");
    if (!getAccessToken() && !loggedOut) {
      await tryRefresh();
    }

    // No access token (no valid cookie) and no explicit sign-back-in: there is no
    // live session. Drop any stale cached identity so we never paint a previous
    // user, then resolve as unauthed.
    if (!getAccessToken()) {
      if (typeof localStorage !== "undefined") {
        localStorage.removeItem("gt.local_user");
        localStorage.removeItem("gt.local_org");
      }
      set({
        user: null,
        org: null,
        organizations: [],
        role: null,
        permissions: [],
        initialized: true,
        status: "unauthed",
      });
      return;
    }

    try {
      const r = await api("/api/v1/auth/me", { timeoutMs: 10000 });
      const user = normalizeUser(r.user);
      const organizations = r.organizations ?? (r.membership?.org ? [{ org: r.membership.org, role: r.membership.role }] : []);
      const primaryOrg = r.membership?.org ?? organizations[0]?.org ?? null;
      const primaryRole = r.membership?.role ?? organizations[0]?.role ?? null;
      if (user) localStorage.setItem("gt.local_user", JSON.stringify(user));
      if (primaryOrg) localStorage.setItem("gt.local_org", JSON.stringify(primaryOrg));
      set({
        user,
        org: primaryOrg,
        organizations,
        role: primaryRole,
        permissions: r.permissions ?? [],
        initialized: true,
        status: user ? "authed" : "unauthed",
      });
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 401) {
        // Prevent displaying stale cached identities when authentication fails
        setTokens(null);
        localStorage.removeItem("gt.local_user");
        localStorage.removeItem("gt.local_org");
        set({
          user: null,
          org: null,
          organizations: [],
          role: null,
          permissions: [],
          initialized: true,
          status: "unauthed",
        });
      } else {
        // Network timeout / transient error: do not wipe active session
        set((state) => ({
          initialized: true,
          status: state.user ? "authed" : "unauthed",
        }));
      }
    }
  },
}));

setUnauthorizedHandler(() => {
  setTokens(null);
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem("gt.local_user");
    localStorage.removeItem("gt.local_org");
  }
  useAuth.setState({
    user: null,
    org: null,
    organizations: [],
    role: null,
    permissions: [],
    initialized: true,
    status: "unauthed",
  });
});

if (typeof window !== "undefined" && typeof BroadcastChannel !== "undefined") {
  try {
    const channel = new BroadcastChannel("talkflow_auth_channel");
    channel.addEventListener("message", (event) => {
      if (event.data?.type === "LOGOUT") {
        useAuth.setState({
          user: null,
          org: null,
          organizations: [],
          role: null,
          permissions: [],
          initialized: true,
          status: "unauthed",
        });
      } else if (event.data?.type === "LOGIN") {
        void useAuth.getState().refreshMe();
      }
    });
  } catch {
    /* BroadcastChannel unsupported or restricted */
  }
}
