/**
 * TalkFlow REST client used by the MCP tool handlers.
 * Authenticates with a bearer token: either an explicit TALKFLOW_TOKEN or a
 * short-lived login using TALKFLOW_EMAIL / TALKFLOW_PASSWORD (defaults to the
 * seeded demo workspace account so the server works out of the box locally).
 */

const DEFAULT_BASE = "http://127.0.0.1:8088";

export class TalkFlowClient {
  constructor(opts = {}) {
    this.base = (opts.baseUrl || process.env.TALKFLOW_API_BASE || DEFAULT_BASE).replace(/\/+$/, "");
    this.token = opts.token || process.env.TALKFLOW_TOKEN || null;
    this.email = opts.email || process.env.TALKFLOW_EMAIL || "demo@globaltalk.local";
    this.password = opts.password || process.env.TALKFLOW_PASSWORD || "demo1234";
    this.timeoutMs = opts.timeoutMs ?? 30_000;
  }

  async ensureToken() {
    if (this.token) return this.token;
    const r = await this.#raw("/api/v1/auth/login", {
      method: "POST",
      body: { email: this.email, password: this.password },
    });
    this.token = r?.tokens?.access_token || null;
    if (!this.token) throw new Error("TalkFlow login failed (no access token returned)");
    return this.token;
  }

  async #raw(path, { method = "GET", body, form, headers = {} } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const init = { method, headers: { ...headers }, signal: ctrl.signal };
      if (form) {
        init.body = form;
      } else if (body !== undefined) {
        init.headers["content-type"] = "application/json";
        init.body = JSON.stringify(body);
      }
      const res = await fetch(`${this.base}${path}`, init);
      const ctype = res.headers.get("content-type") || "";
      const data = ctype.includes("application/json") ? await res.json() : await res.text();
      if (!res.ok) {
        const msg = typeof data === "object" && data ? data?.error?.message || JSON.stringify(data) : String(data);
        const err = new Error(`TalkFlow API ${res.status}: ${msg}`);
        err.status = res.status;
        throw err;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  async request(path, opts = {}) {
    const token = await this.ensureToken();
    const headers = { authorization: `Bearer ${token}`, ...(opts.headers || {}) };
    try {
      return await this.#raw(path, { ...opts, headers });
    } catch (err) {
      // One transparent re-login on auth expiry, then retry once.
      if (err.status === 401 && !process.env.TALKFLOW_TOKEN) {
        this.token = null;
        const fresh = await this.ensureToken();
        return this.#raw(path, { ...opts, headers: { authorization: `Bearer ${fresh}`, ...(opts.headers || {}) } });
      }
      throw err;
    }
  }

  get(path) {
    return this.request(path, { method: "GET" });
  }

  post(path, body) {
    return this.request(path, { method: "POST", body });
  }

  async upload(path, form) {
    return this.request(path, { method: "POST", form });
  }

  async downloadBytes(path) {
    const token = await this.ensureToken();
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.base}${path}`, {
        headers: { authorization: `Bearer ${token}` },
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`TalkFlow API ${res.status} on download`);
      return Buffer.from(await res.arrayBuffer());
    } finally {
      clearTimeout(timer);
    }
  }
}
