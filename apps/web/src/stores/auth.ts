import { create } from "zustand";
import { api, setTokens, setUnauthorizedHandler, persistTokens, loadPersistedTokens } from "../lib/api";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  email_verified: boolean;
  default_language: string;
}
export interface AuthOrg {
  id: string;
  name: string;
  slug: string;
  plan: string;
}

interface AuthState {
  user: AuthUser | null;
  org: AuthOrg | null;
  role: string | null;
  initialized: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: { email: string; password: string; full_name: string; organization_name: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  org: null,
  role: null,
  initialized: false,

  async login(email, password) {
    const r = await api("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setTokens(r.tokens.access_token, r.tokens.refresh_token);
    persistTokens();
    set({ user: r.user, org: r.membership?.org ?? null, role: r.membership?.role ?? null });
  },

  async signup(data) {
    const r = await api("/api/v1/auth/signup", { method: "POST", body: data });
    setTokens(r.tokens.access_token, r.tokens.refresh_token);
    persistTokens();
    set({ user: r.user, org: r.membership?.org ?? null, role: r.membership?.role ?? null });
  },

  async logout() {
    try {
      const refresh = localStorage.getItem("gt.refresh");
      if (refresh) await api("/api/v1/auth/logout", { method: "POST", body: { refresh_token: refresh } });
    } catch { /* best effort */ }
    setTokens(null, null);
    persistTokens();
    set({ user: null, org: null, role: null });
  },

  async refreshMe() {
    loadPersistedTokens();
    setUnauthorizedHandler(() => {
      setTokens(null, null);
      persistTokens();
      set({ user: null, org: null, role: null, initialized: true });
    });
    try {
      const r = await api("/api/v1/auth/me");
      set({ user: r.user?.id ? r.user : null, org: r.membership?.org ?? null,
            role: r.membership?.role ?? null, initialized: true });
    } catch {
      set({ user: null, org: null, role: null, initialized: true });
    }
  },
}));
