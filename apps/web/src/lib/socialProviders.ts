/**
 * Phase 2: real social sign-in. Every provider flow here yields a credential the
 * SERVER verifies (Google ID token via JWKS, Apple identity token via JWKS, GitHub
 * authorization code via token exchange). The SPA never asserts an identity itself,
 * and a provider without a configured client id fails loudly instead of pretending.
 */

export type SocialProvider = "google" | "github" | "apple";

const env = import.meta.env as Record<string, string | undefined>;

export function providerClientId(p: SocialProvider): string | null {
  const key = p === "google" ? "VITE_GOOGLE_CLIENT_ID" : p === "github" ? "VITE_GITHUB_CLIENT_ID" : "VITE_APPLE_CLIENT_ID";
  return env[key]?.trim() || null;
}

export function providerConfigured(p: SocialProvider): boolean {
  return providerClientId(p) !== null;
}

export function randomHex(bytes = 16): string {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("");
}

const loadedScripts = new Map<string, Promise<void>>();

function loadScript(src: string): Promise<void> {
  let p = loadedScripts.get(src);
  if (!p) {
    p = new Promise<void>((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(s);
    });
    loadedScripts.set(src, p);
  }
  return p;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(config: { client_id: string; callback: (r: { credential: string }) => void }): void;
          prompt(): void;
        };
      };
    };
    AppleID?: {
      auth: {
        init(config: Record<string, unknown>): void;
        signIn(): Promise<{ detail?: { authorization?: { id_token?: string; code?: string } } }>;
      };
    };
  }
}

/** Resolve a real Google ID token (JWT) via Google Identity Services. */
export async function googleIdToken(): Promise<string> {
  const clientId = providerClientId("google");
  if (!clientId) throw new Error("Google sign-in is not configured on this deployment.");
  await loadScript("https://accounts.google.com/gsi/client");
  if (!window.google) throw new Error("Google sign-in failed to initialize.");
  return new Promise<string>((resolve, reject) => {
    window.google!.accounts.id.initialize({
      client_id: clientId,
      callback: (r) => (r?.credential ? resolve(r.credential) : reject(new Error("Google sign-in returned no credential."))),
    });
    window.google!.accounts.id.prompt();
  });
}

/** Resolve a real Apple identity token bound to a fresh nonce. */
export async function appleIdToken(): Promise<{ token: string; nonce: string }> {
  const clientId = providerClientId("apple");
  if (!clientId) throw new Error("Apple sign-in is not configured on this deployment.");
  await loadScript("https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js");
  if (!window.AppleID) throw new Error("Apple sign-in failed to initialize.");
  const nonce = randomHex(32);
  window.AppleID.auth.init({ clientId, scope: "name email", nonce, usePopup: true });
  const res = await window.AppleID.auth.signIn();
  const token = res?.detail?.authorization?.id_token;
  if (!token) throw new Error("Apple sign-in returned no identity token.");
  return { token, nonce };
}

/** Build the GitHub authorization redirect (code lands on /auth/callback/github). */
export function githubAuthorizeUrl(): string {
  const clientId = providerClientId("github");
  if (!clientId) throw new Error("GitHub sign-in is not configured on this deployment.");
  const state = randomHex(16);
  try {
    sessionStorage.setItem("gt.oauth.state", state);
  } catch { /* private mode */ }
  const redirectUri = `${window.location.origin}/auth/callback/github`;
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: "read:user user:email",
    state,
  });
  return `https://github.com/login/oauth/authorize?${params.toString()}`;
}
