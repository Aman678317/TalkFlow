/**
 * API client: single fetch wrapper with JWT/API-key auth, request-id propagation and
 * normalized error handling matching the backend error contract
 * ({error: {code, message, request_id, trace_id, recoverable, details}}).
 */

export class ApiError extends Error {
  code: string;
  requestId: string;
  traceId: string;
  recoverable: boolean;
  details: Record<string, unknown>;
  status: number;

  constructor(status: number, body: any) {
    const err = body?.error ?? {};
    super(err.message ?? `Request failed (${status})`);
    this.status = status;
    this.code = err.code ?? `http_${status}`;
    this.requestId = err.request_id ?? "";
    this.traceId = err.trace_id ?? "";
    this.recoverable = err.recoverable ?? false;
    this.details = err.details ?? {};
  }
}

let accessToken: string | null = null;
let onUnauthorized: () => void = () => { };
let refreshInFlight: Promise<boolean> | null = null;
let lastRefreshSuccess = 0;
const REFRESH_DEDUPE_MS = 3000;

// Phase 1: the access token lives only in this module's memory (never persisted),
// and the refresh token lives only in an HttpOnly cookie the browser sends. No
// credential ever touches localStorage.

// Read the JS-readable double-submit CSRF cookie set by the backend on login.
function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export const authChannel = typeof window !== "undefined" && typeof BroadcastChannel !== "undefined"
  ? new BroadcastChannel("talkflow_auth_channel")
  : null;

if (authChannel) {
  authChannel.onmessage = (event) => {
    if (event.data?.type === "LOGOUT") {
      accessToken = null;
      onUnauthorized();
    } else if (event.data?.type === "TOKEN_REFRESHED" && event.data?.accessToken) {
      accessToken = event.data.accessToken;
      if (event.data?.timestamp) {
        lastRefreshSuccess = event.data.timestamp;
      }
    } else if (event.data?.type === "LOGIN" && event.data?.accessToken) {
      accessToken = event.data.accessToken;
    }
  };
}

export function setTokens(access: string | null) {
  accessToken = access;
  if (access && authChannel) {
    authChannel.postMessage({ type: "TOKEN_REFRESHED", accessToken: access, timestamp: Date.now() });
  }
}

export function broadcastLogout() {
  accessToken = null;
  if (authChannel) {
    authChannel.postMessage({ type: "LOGOUT" });
  }
  onUnauthorized();
}

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export function getAccessToken() {
  return accessToken;
}

export const DEFAULT_PRODUCTION_API_BASE_URL = "https://talkflow-csbw.onrender.com";

/**
 * Resolve the API origin used by both REST and WebSocket traffic.
 *
 * Vercel serves the SPA, but it is not a durable database or WebSocket host.
 * The previous `.vercel.app` special case forced preview builds back to same-
 * origin `/api` and `/ws` routes, which made login state disappear between
 * serverless invocations and caused meeting seats to be rejected. A deployment
 * may still override this with VITE_API_BASE_URL, but production defaults to
 * the durable API service when no override is supplied.
 */
export function resolveApiBaseUrl(envUrl: string | undefined, isProduction: boolean): string {
  const configured = envUrl?.trim().replace(/\/+$/, "");
  if (configured) return configured;
  return isProduction ? DEFAULT_PRODUCTION_API_BASE_URL : "";
}

export const getApiBaseUrl = (): string =>
  resolveApiBaseUrl(
    import.meta.env.VITE_API_BASE_URL as string | undefined,
    import.meta.env.PROD,
  );

const BASE = getApiBaseUrl();

async function doRefreshRequest(): Promise<boolean> {
  // If another tab just refreshed within the dedupe window and we have an accessToken, reuse it
  if (Date.now() - lastRefreshSuccess < REFRESH_DEDUPE_MS && accessToken) {
    return true;
  }

  // A page can start its silent cookie refresh at the same time that the user
  // submits login or signup. If that request finishes with the old unauthenticated
  // result after the explicit auth call succeeds, it must not clear the new session.
  const tokenAtStart = accessToken;

  try {
    // Cookie-only: the HttpOnly refresh cookie authenticates this call; we never
    // hold or send a refresh token from JS. /auth/refresh is CSRF-exempt server-side.
    const r = await fetch(`${BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include", // transport HttpOnly SameSite refresh cookie
      body: "{}",
    });
    if (!r.ok) {
      if (r.status === 401 && accessToken === tokenAtStart) {
        broadcastLogout();
      }
      return false;
    }
    // An explicit login/signup or another tab may have established a newer token
    // while this request was in flight. Preserve that token rather than replacing
    // it with a stale cookie-refresh response.
    if (accessToken !== tokenAtStart) {
      return true;
    }
    const data = await r.json();
    // The server rotates the cookie (Set-Cookie) and blanks refresh in the body;
    // only the access token is read back, into memory.
    accessToken = data.access_token || null;
    lastRefreshSuccess = Date.now();
    if (accessToken && authChannel) {
      authChannel.postMessage({
        type: "TOKEN_REFRESHED",
        accessToken,
        timestamp: lastRefreshSuccess,
      });
    }
    return true;
  } catch {
    return false;
  }
}

export async function tryRefresh(): Promise<boolean> {
  if (refreshInFlight) {
    return refreshInFlight;
  }

  refreshInFlight = (async () => {
    try {
      if (typeof navigator !== "undefined" && "locks" in navigator && typeof navigator.locks?.request === "function") {
        return await navigator.locks.request("talkflow_refresh_lock", async () => {
          return await doRefreshRequest();
        });
      } else {
        return await doRefreshRequest();
      }
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  form?: FormData;
  raw?: boolean;
  timeoutMs?: number;
}

export async function api<T = any>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  if (accessToken && !headers.has("Authorization"))
    headers.set("Authorization", `Bearer ${accessToken}`);
  if (opts.body !== undefined && !headers.has("content-type"))
    headers.set("content-type", "application/json");

  const timeoutMs = opts.timeoutMs ?? (opts.form ? 60000 : 15000);
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  // Double-submit CSRF: state-changing requests carry the header matching the
  // csrf_token cookie. Harmless when an Authorization header is present (the server
  // exempts bearer-authed calls), required for any cookie-only mutation.
  const safeMethod = method === "GET" || method === "HEAD" || method === "OPTIONS";
  if (!safeMethod && !headers.has("X-TalkFlow-CSRF")) {
    const csrf = getCsrfToken();
    if (csrf) headers.set("X-TalkFlow-CSRF", csrf);
  }
  const doFetch = () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const signal = opts.signal || controller.signal;
    return fetch(`${BASE}${path}`, {
      ...opts,
      method,
      signal,
      headers,
      credentials: "include",
      body: opts.form ?? (opts.body !== undefined ? (typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body)) : undefined),
    }).finally(() => clearTimeout(timeoutId));
  };

  let res: Response;
  try {
    res = await doFetch();
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s. Please check connection and try again.`);
    }
    throw err;
  }
  const isAuthRoute = path.includes("/auth/login") || path.includes("/auth/signup") || path.includes("/auth/refresh");
  if (res.status === 401 && !isAuthRoute) {
    if (await tryRefresh()) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      try {
        res = await doFetch();
      } catch (err: any) {
        if (err?.name === "AbortError") {
          throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s. Please check connection and try again.`);
        }
        throw err;
      }
    }
  }
  if (res.status === 401 && !isAuthRoute) {
    if (accessToken) {
      onUnauthorized();
    }
  }
  if (opts.raw) {
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
    return res as unknown as T;
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

api.get = <T = any>(path: string, opts?: RequestOptions) =>
  api<T>(path, { ...opts, method: "GET" });

api.post = <T = any>(path: string, body?: unknown, opts?: RequestOptions) =>
  api<T>(path, { ...opts, method: "POST", body });

api.put = <T = any>(path: string, body?: unknown, opts?: RequestOptions) =>
  api<T>(path, { ...opts, method: "PUT", body });

api.delete = <T = any>(path: string, opts?: RequestOptions) =>
  api<T>(path, { ...opts, method: "DELETE" });

export function friendlyMessage(err: unknown): string {
  if (!err) return "An unexpected error occurred.";
  if (err instanceof ApiError) {
    if (err.message && err.message !== `Request failed (${err.status})`) {
      return err.message;
    }
    if (err.details && typeof err.details === "object" && Object.keys(err.details).length > 0) {
      return JSON.stringify(err.details);
    }
    return `Request failed with status ${err.status}`;
  }
  if (err instanceof Error) {
    if (err.name === "AbortError" || err.message.includes("timed out")) {
      return "Request timed out. Please check your connection or service status.";
    }
    return err.message;
  }
  if (typeof err === "string") {
    return err;
  }
  if (typeof err === "object" && "message" in (err as any)) {
    return String((err as any).message);
  }
  return "An error occurred. Please try again.";
}
