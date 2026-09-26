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
let refreshToken: string | null = null;
let onUnauthorized: () => void = () => {};
let refreshInFlight: Promise<boolean> | null = null;

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access;
  refreshToken = refresh;
}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}
export function getAccessToken() {
  return accessToken;
}

const BASE = ""; // same-origin via Vite proxy in dev; reverse proxy in prod

async function tryRefresh(): Promise<boolean> {
  if (!refreshToken) return false;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const r = await fetch(`${BASE}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!r.ok) return false;
        const data = await r.json();
        accessToken = data.access_token;
        refreshToken = data.refresh_token;
        persistTokens();
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export function persistTokens() {
  try {
    if (accessToken) localStorage.setItem("gt.access", accessToken);
    else localStorage.removeItem("gt.access");
    if (refreshToken) localStorage.setItem("gt.refresh", refreshToken);
    else localStorage.removeItem("gt.refresh");
  } catch {
    /* private mode */
  }
}

export function loadPersistedTokens() {
  try {
    accessToken = localStorage.getItem("gt.access");
    refreshToken = localStorage.getItem("gt.refresh");
  } catch {
    /* ignore */
  }
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  form?: FormData;
  raw?: boolean;
}

export async function api<T = any>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  if (accessToken && !headers.has("Authorization"))
    headers.set("Authorization", `Bearer ${accessToken}`);
  if (opts.body !== undefined && !headers.has("content-type"))
    headers.set("content-type", "application/json");

  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      ...opts,
      headers,
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
    });

  let res = await doFetch();
  if (res.status === 401 && refreshToken) {
    if (await tryRefresh()) {
      headers.set("Authorization", `Bearer ${accessToken}`);
      res = await doFetch();
    }
  }
  if (res.status === 401) {
    onUnauthorized();
  }
  if (opts.raw) {
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
    return res as unknown as T;
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}
