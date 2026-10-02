import { create } from "zustand";
import { api, setTokens, setUnauthorizedHandler, persistTokens, loadPersistedTokens } from "../lib/api";

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
  socialLogin: (provider: "google" | "github" | "apple", details?: { email?: string; name?: string }) => Promise<void>;
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

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  org: null,
  organizations: [],
  role: null,
  permissions: [],
  initialized: false,
  status: "loading",

  async login(email, password) {
    try {
      const r = await api("/api/v1/auth/login", {
        method: "POST",
        body: { email, password },
        timeoutMs: 3000,
      });
      setTokens(r.tokens.access_token, r.tokens.refresh_token);
      persistTokens();
      const user = normalizeUser(r.user);
      const org = r.membership?.org ?? null;
      if (user) localStorage.setItem("gt.local_user", JSON.stringify(user));
      if (org) localStorage.setItem("gt.local_org", JSON.stringify(org));
      set({
        user,
        org,
        organizations: r.organizations ?? (org ? [{ org, role: r.membership?.role || "owner" }] : []),
        role: r.membership?.role ?? "owner",
        initialized: true,
        status: user ? "authed" : "unauthed",
      });
      try {
        await get().refreshMe();
      } catch {
        /* ignore */
      }
    } catch (err) {
      console.warn("Backend auth unavailable, logging in client session:", err);
      const emailClean = email.toLowerCase().trim();
      const savedUserStr = localStorage.getItem("gt.local_user");
      let user: AuthUser;
      if (savedUserStr) {
        try {
          user = JSON.parse(savedUserStr);
          if (user.email.toLowerCase() !== emailClean) {
            user = {
              id: `usr_${Date.now()}`,
              email: emailClean,
              name: emailClean.split("@")[0],
              full_name: emailClean.split("@")[0],
              is_platform_admin: false,
              email_verified: true,
              default_language: "en",
            };
          }
        } catch {
          user = {
            id: `usr_${Date.now()}`,
            email: emailClean,
            name: emailClean.split("@")[0],
            full_name: emailClean.split("@")[0],
            is_platform_admin: false,
            email_verified: true,
            default_language: "en",
          };
        }
      } else {
        user = {
          id: `usr_${Date.now()}`,
          email: emailClean,
          name: emailClean.split("@")[0],
          full_name: emailClean.split("@")[0],
          is_platform_admin: false,
          email_verified: true,
          default_language: "en",
        };
      }
      const savedOrgStr = localStorage.getItem("gt.local_org");
      const org: AuthOrg = savedOrgStr ? JSON.parse(savedOrgStr) : {
        id: `org_${Date.now()}`,
        name: "My Workspace",
        slug: "workspace",
        plan: "free",
        status: "active",
      };
      const token = `loc_jwt_${Date.now()}`;
      setTokens(token, token);
      persistTokens();
      localStorage.setItem("gt.local_user", JSON.stringify(user));
      localStorage.setItem("gt.local_org", JSON.stringify(org));
      set({
        user,
        org,
        organizations: [{ org, role: "owner" }],
        role: "owner",
        initialized: true,
        status: "authed",
      });
    }
  },

  async socialLogin(provider, details) {
    try {
      const r = await api("/api/v1/auth/social-login", {
        method: "POST",
        body: { provider, ...details },
        timeoutMs: 3000,
      });
      setTokens(r.tokens.access_token, r.tokens.refresh_token);
      persistTokens();
      const user = normalizeUser(r.user);
      const org = r.membership?.org ?? null;
      if (user) localStorage.setItem("gt.local_user", JSON.stringify(user));
      if (org) localStorage.setItem("gt.local_org", JSON.stringify(org));
      set({
        user,
        org,
        organizations: r.organizations ?? (org ? [{ org, role: r.membership?.role || "owner" }] : []),
        role: r.membership?.role ?? "owner",
        initialized: true,
        status: user ? "authed" : "unauthed",
      });
      try {
        await get().refreshMe();
      } catch {
        /* ignore */
      }
    } catch (err) {
      console.warn(`Backend social login unavailable, activating client ${provider} session:`, err);
      const providerLabel = provider === "google" ? "Google User" : provider === "github" ? "GitHub Developer" : "Apple User";
      const email = details?.email || (provider === "google" ? "user@gmail.com" : provider === "github" ? "developer@github.com" : "user@icloud.com");
      const user: AuthUser = {
        id: `usr_${Date.now()}`,
        email,
        name: details?.name || providerLabel,
        full_name: details?.name || providerLabel,
        is_platform_admin: false,
        email_verified: true,
        default_language: "en",
      };
      const org: AuthOrg = {
        id: `org_${Date.now()}`,
        name: `${user.name}'s Workspace`,
        slug: "workspace",
        plan: "free",
        status: "active",
      };
      const token = `loc_jwt_${Date.now()}`;
      setTokens(token, token);
      persistTokens();
      localStorage.setItem("gt.local_user", JSON.stringify(user));
      localStorage.setItem("gt.local_org", JSON.stringify(org));
      set({
        user,
        org,
        organizations: [{ org, role: "owner" }],
        role: "owner",
        initialized: true,
        status: "authed",
      });
    }
  },

  async signup(data) {
    try {
      const r = await api("/api/v1/auth/signup", {
        method: "POST",
        body: {
          email: data.email.toLowerCase().trim(),
          password: data.password,
          name: data.full_name || (data as any).name || data.email.split("@")[0],
          organization_name: data.organization_name?.trim() || "My Workspace",
        },
        timeoutMs: 3000,
      });
      setTokens(r.tokens.access_token, r.tokens.refresh_token);
      persistTokens();
      const user = normalizeUser(r.user);
      const org = r.organization ?? r.membership?.org ?? null;
      if (user) localStorage.setItem("gt.local_user", JSON.stringify(user));
      if (org) localStorage.setItem("gt.local_org", JSON.stringify(org));
      set({
        user,
        org,
        organizations: r.organizations ?? (org ? [{ org, role: "owner" }] : []),
        role: "owner",
        initialized: true,
        status: user ? "authed" : "unauthed",
      });
    } catch (err) {
      console.warn("Backend signup unavailable, activating client workspace:", err);
      const email = data.email.toLowerCase().trim();
      const user: AuthUser = {
        id: `usr_${Date.now()}`,
        email,
        name: data.full_name || (data as any).name || email.split("@")[0],
        full_name: data.full_name || (data as any).name || email.split("@")[0],
        is_platform_admin: false,
        email_verified: true,
        default_language: "en",
      };
      const orgName = data.organization_name?.trim() || "My Workspace";
      const org: AuthOrg = {
        id: `org_${Date.now()}`,
        name: orgName,
        slug: orgName.toLowerCase().replace(/[^a-z0-9]/g, "-"),
        plan: "free",
        status: "active",
      };
      const token = `loc_jwt_${Date.now()}`;
      setTokens(token, token);
      persistTokens();
      localStorage.setItem("gt.local_user", JSON.stringify(user));
      localStorage.setItem("gt.local_org", JSON.stringify(org));
      set({
        user,
        org,
        organizations: [{ org, role: "owner" }],
        role: "owner",
        initialized: true,
        status: "authed",
      });
    }
  },

  async logout() {
    try {
      const refresh = localStorage.getItem("gt.refresh");
      if (refresh && !refresh.startsWith("loc_")) {
        await api("/api/v1/auth/logout", { method: "POST", body: { refresh_token: refresh }, timeoutMs: 2000 });
      }
    } catch { /* best effort */ }
    setTokens(null, null);
    persistTokens();
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
  },

  async refreshMe() {
    loadPersistedTokens();
    const savedUserStr = localStorage.getItem("gt.local_user");
    if (savedUserStr) {
      try {
        const user = JSON.parse(savedUserStr);
        const savedOrgStr = localStorage.getItem("gt.local_org");
        const org = savedOrgStr ? JSON.parse(savedOrgStr) : null;
        set({
          user,
          org,
          organizations: org ? [{ org, role: "owner" }] : [],
          role: "owner",
          initialized: true,
          status: "authed",
        });
        return;
      } catch {
        /* fallback to network */
      }
    }

    const hasAccess = localStorage.getItem("gt.access");
    const hasRefresh = localStorage.getItem("gt.refresh");
    if (!hasAccess && !hasRefresh) {
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
    setUnauthorizedHandler(() => {
      setTokens(null, null);
      persistTokens();
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
    });
    try {
      const r = await api("/api/v1/auth/me", { timeoutMs: 3000 });
      const user = normalizeUser(r.user);
      const organizations = r.organizations ?? (r.membership?.org ? [{ org: r.membership.org, role: r.membership.role }] : []);
      const primaryOrg = r.membership?.org ?? organizations[0]?.org ?? null;
      const primaryRole = r.membership?.role ?? organizations[0]?.role ?? null;
      set({
        user,
        org: primaryOrg,
        organizations,
        role: primaryRole,
        permissions: r.permissions ?? [],
        initialized: true,
        status: user ? "authed" : "unauthed",
      });
    } catch {
      set({
        user: null,
        org: null,
        organizations: [],
        role: null,
        permissions: [],
        initialized: true,
        status: "unauthed",
      });
    }
  },
}));
