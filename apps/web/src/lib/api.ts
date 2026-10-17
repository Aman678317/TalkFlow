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
let authSeq = 0;
let onUnauthorized: () => void = () => { };
let refreshInFlight: Promise<boolean> | null = null;
let lastRefreshSuccess = 0;
let lastRefreshError: "invalid" | "network" | null = null;
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
      authSeq = Math.max(authSeq, event.data?.seq ?? (authSeq + 1));
      accessToken = null;
      onUnauthorized();
    } else if (event.data?.type === "TOKEN_REFRESHED" && event.data?.accessToken) {
      if (!event.data?.seq || event.data.seq >= authSeq) {
        authSeq = Math.max(authSeq, event.data?.seq ?? (authSeq + 1));
        accessToken = event.data.accessToken;
        if (event.data?.timestamp) {
          lastRefreshSuccess = event.data.timestamp;
        }
      }
    } else if (event.data?.type === "LOGIN" && event.data?.accessToken) {
      if (!event.data?.seq || event.data.seq >= authSeq) {
        authSeq = Math.max(authSeq, event.data?.seq ?? (authSeq + 1));
        accessToken = event.data.accessToken;
      }
    }
  };
}

export function setTokens(access: string | null) {
  authSeq++;
  accessToken = access;
  if (access && authChannel) {
    authChannel.postMessage({ type: "TOKEN_REFRESHED", accessToken: access, timestamp: Date.now(), seq: authSeq });
  }
}

export function broadcastLogout() {
  authSeq++;
  accessToken = null;
  if (authChannel) {
    authChannel.postMessage({ type: "LOGOUT", seq: authSeq });
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

export interface ResolveApiOptions {
  envUrl?: string;
  isProduction?: boolean;
  vercelEnv?: string;
  mode?: string;
  isStaging?: boolean;
  isPreview?: boolean;
  currentOrigin?: string;
}

/**
 * Validate and normalize a candidate API base URL.
 * Ensures the URL is well-formed, uses an approved HTTP/HTTPS protocol,
 * strips trailing slashes, and verifies a non-empty hostname.
 */
export function validateApiUrl(urlStr: string): string {
  const trimmed = urlStr.trim();
  if (!trimmed) {
    throw new Error("Invalid API base URL: URL string cannot be empty.");
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(`Invalid API base URL: "${trimmed}" is not a valid URL.`);
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(
      `Invalid API base URL: unsupported protocol "${parsed.protocol}". Only "http:" and "https:" are supported.`
    );
  }

  if (!parsed.hostname) {
    throw new Error(`Invalid API base URL: "${trimmed}" is missing a hostname.`);
  }

  // Prevent browser mixed-content blocks: upgrade http to https when running on https origin
  if (
    typeof window !== "undefined" &&
    window.location?.protocol === "https:" &&
    parsed.protocol === "http:" &&
    parsed.hostname !== "localhost" &&
    parsed.hostname !== "127.0.0.1"
  ) {
    parsed.protocol = "https:";
  }

  return `${parsed.protocol}//${parsed.host}${parsed.pathname === "/" ? "" : parsed.pathname}`.replace(/\/+$/, "");
}

/**
 * Resolve the API origin used by both REST and WebSocket traffic.
 *
 * Rules:
 * 1. If explicit envUrl (VITE_API_BASE_URL) is supplied, validate, normalize, and return it.
 * 2. If no override is provided:
 *    - In local development (isProduction = false), preserve same-origin ("").
 *    - In preview or staging deployments (where environment isolation is required),
 *      preserve same-origin ("") to prevent accidentally targeting production.
 *    - In pure production deployments, fall back to DEFAULT_PRODUCTION_API_BASE_URL.
 */
export function resolveApiBaseUrl(
  envUrlOrOpts?: string | ResolveApiOptions,
  isProductionArg?: boolean,
  extraOpts?: Partial<ResolveApiOptions>,
): string {
  let envUrl: string | undefined;
  let isProduction = false;
  let vercelEnv: string | undefined;
  let mode: string | undefined;
  let isStaging = false;
  let isPreview = false;

  if (typeof envUrlOrOpts === "object" && envUrlOrOpts !== null) {
    envUrl = envUrlOrOpts.envUrl;
    isProduction = envUrlOrOpts.isProduction ?? false;
    vercelEnv = envUrlOrOpts.vercelEnv;
    mode = envUrlOrOpts.mode;
    isStaging = envUrlOrOpts.isStaging ?? false;
    isPreview = envUrlOrOpts.isPreview ?? false;
  } else {
    envUrl = envUrlOrOpts;
    isProduction = isProductionArg ?? false;
    if (extraOpts) {
      vercelEnv = extraOpts.vercelEnv;
      mode = extraOpts.mode;
      isStaging = extraOpts.isStaging ?? false;
      isPreview = extraOpts.isPreview ?? false;
    }
  }

  const configured = envUrl?.trim();
  if (configured) {
    return validateApiUrl(configured);
  }

  // Detect staging / preview environments where environment isolation is required
  const envIsPreviewOrStaging =
    isStaging ||
    isPreview ||
    vercelEnv === "preview" ||
    vercelEnv === "staging" ||
    mode === "preview" ||
    mode === "staging";

  if (envIsPreviewOrStaging) {
    // Prevent staging/preview from silently targeting production
    return "";
  }

  return isProduction ? DEFAULT_PRODUCTION_API_BASE_URL : "";
}

export const getApiBaseUrl = (): string =>
  resolveApiBaseUrl(
    import.meta.env.VITE_API_BASE_URL as string | undefined,
    import.meta.env.PROD,
    {
      vercelEnv: (import.meta.env.VITE_VERCEL_ENV || import.meta.env.VERCEL_ENV) as string | undefined,
      mode: import.meta.env.MODE as string | undefined,
    },
  );

/**
 * Derive WebSocket base URL (wss:// or ws://) from the validated API base URL.
 * When the API base URL is HTTPS, the WebSocket connection uses WSS.
 * When the API base URL is same-origin (""), the browser's current location protocol is respected.
 */
export function resolveWsBaseUrl(
  apiBaseUrl?: string,
  currentOrigin?: string,
): string {
  const base = apiBaseUrl !== undefined ? apiBaseUrl : getApiBaseUrl();
  if (base) {
    const validated = validateApiUrl(base);
    const parsed = new URL(validated);
    const wsProto = parsed.protocol === "https:" ? "wss:" : "ws:";
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    return `${wsProto}//${parsed.host}${path}`.replace(/\/+$/, "");
  }

  // Same-origin fallback
  const origin =
    currentOrigin ||
    (typeof window !== "undefined" && window.location?.origin
      ? window.location.origin
      : "");

  if (origin) {
    try {
      const parsed = new URL(origin);
      const wsProto = parsed.protocol === "https:" ? "wss:" : "ws:";
      return `${wsProto}//${parsed.host}`.replace(/\/+$/, "");
    } catch {
      // ignore
    }
  }

  return "ws://localhost:5173";
}

/**
 * Construct a full, validated WebSocket URL for a meeting or realtime path.
 */
export function resolveWsUrl(
  path: string,
  params?: Record<string, string | null | undefined> | URLSearchParams,
  apiBaseUrl?: string,
  currentOrigin?: string,
): string {
  const base = resolveWsBaseUrl(apiBaseUrl, currentOrigin);
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  let query = "";
  if (params) {
    const searchParams = params instanceof URLSearchParams ? params : new URLSearchParams();
    if (!(params instanceof URLSearchParams)) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "") {
          searchParams.set(k, v);
        }
      }
    }
    const qStr = searchParams.toString();
    if (qStr) query = `?${qStr}`;
  }
  return `${base}${cleanPath}${query}`;
}

async function doRefreshRequest(): Promise<boolean> {
  // If another tab just refreshed within the dedupe window and we have an accessToken, reuse it
  if (Date.now() - lastRefreshSuccess < REFRESH_DEDUPE_MS && accessToken) {
    lastRefreshError = null;
    return true;
  }

  // A page can start its silent cookie refresh at the same time that the user
  // submits login or signup. If that request finishes with the old unauthenticated
  // result after the explicit auth call succeeds, it must not clear the new session.
  const seqAtStart = authSeq;
  const tokenAtStart = accessToken;
  lastRefreshError = null;

  try {
    const base = getApiBaseUrl();
    // Cookie-only: the HttpOnly refresh cookie authenticates this call; we never
    // hold or send a refresh token from JS. /auth/refresh is CSRF-exempt server-side.
    const r = await fetch(`${base}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include", // transport HttpOnly SameSite refresh cookie
      body: "{}",
    });
    if (!r.ok) {
      if (r.status === 401) {
        lastRefreshError = "invalid";
        if (authSeq === seqAtStart && accessToken === tokenAtStart) {
          broadcastLogout();
        }
      } else {
        lastRefreshError = "invalid";
      }
      return false;
    }
    // An explicit login/signup or another tab may have established a newer token
    // while this request was in flight. Preserve that token rather than replacing
    // it with a stale cookie-refresh response.
    if (authSeq !== seqAtStart || accessToken !== tokenAtStart) {
      lastRefreshError = null;
      return true;
    }
    const data = await r.json();
    // The server rotates the cookie (Set-Cookie) and blanks refresh in the body;
    // only the access token is read back, into memory.
    authSeq++;
    accessToken = data.access_token || null;
    lastRefreshSuccess = Date.now();
    lastRefreshError = null;
    if (accessToken && authChannel) {
      authChannel.postMessage({
        type: "TOKEN_REFRESHED",
        accessToken,
        timestamp: lastRefreshSuccess,
        seq: authSeq,
      });
    }
    return true;
  } catch {
    // Network error: preserve local state; do not broadcast logout or log out user
    lastRefreshError = "network";
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
    const base = getApiBaseUrl();
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    return fetch(`${base}${cleanPath}`, {
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
  const isAuthRoute =
    path.includes("/auth/login") ||
    path.includes("/auth/signup") ||
    path.includes("/auth/refresh") ||
    path.includes("/auth/social-login");
  if (res.status === 401 && !isAuthRoute) {
    if (await tryRefresh()) {
      if (accessToken) {
        headers.set("Authorization", `Bearer ${accessToken}`);
      }
      try {
        res = await doFetch();
      } catch (err: any) {
        if (err?.name === "AbortError") {
          throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s. Please check connection and try again.`);
        }
        throw err;
      }
      if (res.status === 401) {
        if (accessToken) {
          accessToken = null;
          onUnauthorized();
        }
      }
    } else if (lastRefreshError === "invalid") {
      if (accessToken) {
        accessToken = null;
        onUnauthorized();
      }
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
