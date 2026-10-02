/**
 * HTTP client — low-level transport layer.
 *
 * Diagram layer: API transport [client.ts]
 *
 * All SDK classes that need to communicate with the GlobalTalk AI API
 * go through this class — never through raw fetch/https directly.
 *
 * Responsibilities:
 *  - Inject `Authorization: Desi-Auth-Key {key}` on every request
 *  - Retry with exponential back-off on 429, 502, 503, 504
 *  - Map HTTP errors → typed SDK exceptions via `errors.ts`
 *  - Expose typed helpers: `get()`, `post()`, `postForm()`, `delete()`
 */

import { createApiError, NetworkError } from "./errors.js";
import { backoffMs, buildQuery, safeJson, sleep, timeoutSignal } from "./utils.js";

const RETRY_STATUSES = new Set([429, 502, 503, 504]);
const MAX_RETRIES    = 4;
const TIMEOUT_MS     = 30_000;

export interface HttpClientOptions {
  /** GlobalTalk AI API base URL. Default: `http://127.0.0.1:8088` */
  baseUrl?:    string;
  /** Request timeout in milliseconds. Default: 30 000 */
  timeoutMs?:  number;
  /** Maximum retry attempts on transient errors. Default: 4 */
  maxRetries?: number;
}

/** Internal request options */
interface RequestOptions {
  params?:  Record<string, unknown>;
  json?:    unknown;
  form?:    Record<string, string | Blob>;
  signal?:  AbortSignal;
  /** Expected response content-type ("json" | "text" | "binary"). Default: "json" */
  responseType?: "json" | "text" | "binary";
}

export class HttpClient {
  private readonly baseUrl:    string;
  private readonly authHeader: string;
  private readonly timeoutMs:  number;
  private readonly maxRetries: number;

  constructor(authKey: string, options: HttpClientOptions = {}) {
    this.baseUrl    = (options.baseUrl ?? "http://127.0.0.1:8088").replace(/\/$/, "");
    this.authHeader = `Desi-Auth-Key ${authKey}`;
    this.timeoutMs  = options.timeoutMs  ?? TIMEOUT_MS;
    this.maxRetries = options.maxRetries ?? MAX_RETRIES;
  }

  // ── Public helpers ─────────────────────────────────────────────────────────

  async get<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    return this._request<T>("GET", path, opts);
  }

  async post<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    return this._request<T>("POST", path, opts);
  }

  async postForm<T>(path: string, form: Record<string, string | Blob>): Promise<T> {
    return this._request<T>("POST", path, { form });
  }

  async delete<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    return this._request<T>("DELETE", path, opts);
  }

  /** Download raw bytes (e.g. translated document result). */
  async download(path: string): Promise<Buffer> {
    const raw = await this._request<Buffer>("GET", path, { responseType: "binary" });
    return raw;
  }

  // ── Core request implementation ────────────────────────────────────────────

  private async _request<T>(
    method: string,
    path: string,
    opts: RequestOptions,
  ): Promise<T> {
    const url = this.baseUrl + path + buildQuery(opts.params ?? {});
    let lastError: unknown;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      if (attempt > 0) {
        await sleep(backoffMs(attempt - 1));
      }

      try {
        const headers: Record<string, string> = {
          Authorization: this.authHeader,
          "User-Agent":  "GlobalTalkAI-NodeSDK/0.1.0",
        };

        let body: string | FormData | undefined;

        if (opts.json !== undefined) {
          headers["Content-Type"] = "application/json";
          body = JSON.stringify(opts.json);
        } else if (opts.form !== undefined) {
          const fd = new FormData();
          for (const [k, v] of Object.entries(opts.form)) {
            fd.append(k, v);
          }
          body = fd;
          // Let fetch set Content-Type with boundary for multipart
        }

        const resp = await fetch(url, {
          method,
          headers,
          body,
          signal: opts.signal ?? timeoutSignal(this.timeoutMs),
        });

        const requestId = resp.headers.get("x-request-id") ?? undefined;

        // Success path
        if (resp.ok) {
          if (opts.responseType === "binary") {
            const buf = await resp.arrayBuffer();
            return Buffer.from(buf) as unknown as T;
          }
          if (opts.responseType === "text") {
            return (await resp.text()) as unknown as T;
          }
          const text = await resp.text();
          return (safeJson(text) ?? {}) as unknown as T;
        }

        // Retryable?
        if (RETRY_STATUSES.has(resp.status) && attempt < this.maxRetries) {
          lastError = resp.status;
          continue;
        }

        // Map to typed error
        const text = await resp.text();
        const body2 = safeJson(text) ?? { message: text };
        throw createApiError(resp.status, body2, requestId);

      } catch (err: unknown) {
        // Re-throw SDK errors immediately — don't retry auth/parse errors
        if (err instanceof Error && err.name.endsWith("Error") &&
            err.name !== "TypeError") {
          throw err;
        }
        // Network / abort errors
        if (attempt < this.maxRetries) {
          lastError = err;
          continue;
        }
        throw new NetworkError(
          `Request failed after ${this.maxRetries + 1} attempts: ${String(err)}`,
          err,
        );
      }
    }

    throw new NetworkError(`Request failed after ${this.maxRetries + 1} attempts`, lastError);
  }
}
