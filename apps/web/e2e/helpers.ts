/**
 * Shared E2E fixtures: seed a meeting through the real public API (signup →
 * login → create), then drive the invite link through the actual guest lobby
 * (name → language → "Add to call") with Chromium fake media devices.
 */
import { expect, type APIRequestContext, type Browser, type BrowserContext, type Page } from "@playwright/test";

const WEB = process.env.E2E_WEB_URL ?? "http://localhost:5173";

export type MeetingMode = "ws" | "livekit";

export interface SeededMeeting {
  token: string;
  meetingId: string;
  inviteUrl: string;
  mode: MeetingMode;
}

function uniqueEmail(): string {
  const salt = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  return `e2e-${salt}@globaltalk.test`;
}

function extractToken(data: Record<string, unknown>): string | null {
  // Both /signup and /login return `tokens: {access_token, ...}`; some shapes
  // have exposed the token at the top level historically. Accept both.
  const tokens = (data.tokens ?? {}) as Record<string, unknown>;
  return (data.access_token ?? data.token ?? data.access ??
    tokens.access_token ?? tokens.token ?? tokens.access) as string | null;
}

async function postJson(ctx: APIRequestContext, path: string, body: unknown, token?: string) {
  return ctx.post(path, {
    data: body,
    headers: token ? { authorization: `Bearer ${token}` } : undefined,
    failOnStatusCode: false,
  });
}

async function authedToken(ctx: APIRequestContext): Promise<string> {
  const email = uniqueEmail();
  const password = "e2e-Strong-Passphrase-1!";
  // A fresh CI database starts zero-organization; POST /meetings requires an
  // org membership (require_org_user), so the host signs up WITH an
  // organization — the same onboarding path the signup page uses.
  let res = await postJson(ctx, "/api/v1/auth/signup", {
    email,
    password,
    name: "E2E Host",
    locale: "en",
    organization_name: `E2E Org ${email}`,
  });
  let token = extractToken((await res.json().catch(() => ({}))) as Record<string, unknown>);
  if (!token) {
    // Signup returns 201/JSON token; re-login covers token-less signup shapes.
    res = await postJson(ctx, "/api/v1/auth/login", { email, password });
    token = extractToken((await res.json().catch(() => ({}))) as Record<string, unknown>);
  }
  expect(token, `auth should mint a token (status ${res.status()})`).toBeTruthy();
  return token as string;
}

/** Creates a meeting through the API the Meetings page itself uses. */
export async function seedMeeting(ctx: APIRequestContext, mode: MeetingMode): Promise<SeededMeeting> {
  const token = await authedToken(ctx);
  const res = await postJson(ctx, "/api/v1/meetings", {
    title: `E2E ${mode} meeting`,
    mode,
    speak_lang: "auto",
    hear_lang: "en",
  }, token);
  expect(res.status(), await res.text()).toBeLessThan(300);
  const data = (await res.json()) as { id: string };
  return {
    token,
    meetingId: data.id,
    // The public no-auth room route is /meeting/:id (singular). /meetings is
    // the PROTECTED meetings list, and unmatched paths fall through the
    // router's catch-all to the landing page — the lobby never renders.
    inviteUrl: `${WEB}/meeting/${data.id}`,
    mode,
  };
}

/**
 * Drives the guest lobby for one seated participant: fill name, pick the
 * language to hear, click "Add to call", and wait until the room is really
 * live (leave button + truth strip) rather than merely routed.
 */
export async function joinAsGuest(
  browser: Browser,
  inviteUrl: string,
  name: string,
  hearLangCode: string,
  opts?: { preBlocked?: boolean },
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(45_000);
  // Installed before the first navigation so the room's WebSocket frames are
  // recorded from the first page load; the capture backs every chip failure
  // and hosts the outage handles when a drill pre-blocks media sockets.
  await attachWsDiagCapture(page, { preBlocked: opts?.preBlocked });

  await page.goto(inviteUrl);
  // The lobby only renders once the meeting detail arrives (guests are
  // allowed to read it anonymously).
  await expect(page.locator("#lobby-name")).toBeVisible();
  await page.fill("#lobby-name", name);
  await page.selectOption('[aria-label="Translate incoming speech into"]', hearLangCode);
  await page.getByRole("button", { name: "Add to call" }).click();

  await expect(page.locator('[aria-label="Leave call"]')).toBeVisible();
  return { context, page };
}

/** Records every JSON room frame each page receives (type:stage only) and
 * keeps native kill/allow handles for the media (LiveKit) sockets, so an
 * outage can be simulated at the real socket boundary from the page:
 * killing an open socket looks like a genuine TCP cut to the transport,
 * and refusing new ports looks like the server being gone. */
export async function attachWsDiagCapture(page: Page, opts?: { preBlocked?: boolean }) {
  await page.addInitScript((preBlocked: boolean) => {
    const store = window as unknown as {
      __wsDiag?: string[];
      __mediaSockets?: { url: string; close: (code?: number) => void }[];
      __wsBlock?: boolean;
    };
    store.__wsDiag = [];
    store.__mediaSockets = [];
    store.__wsBlock = !!preBlocked;

    const Orig = window.WebSocket;
    window.WebSocket = class extends Orig {
      constructor(url: Parameters<typeof Orig>[0], ...rest: ConstructorParameters<typeof Orig>) {
        const u = String(url);
        const isMedia = /localhost:7880/.test(u);
        super(url, ...(rest));
        if (isMedia) {
          store.__mediaSockets.push({ url: u, close: (code?: number) => this.close(code ?? 4001, "media server outage") });
          if (store.__wsBlock) {
            // Refused port: the handshake is answered then cut immediately —
            // the "connection reset" outage shape, independent of how the
            // SDK wraps its connect promise.
            setTimeout(() => { try { this.close(4001, "media server outage"); } catch { /* already closed */ } }, 25);
          }
        }
        this.addEventListener("message", (ev) => {
          try {
            const d = JSON.parse(String((ev as MessageEvent).data)) as Record<string, unknown>;
            if (d && typeof d.type === "string") {
              store.__wsDiag!.push(`${d.type}${d.stage ? `:${d.stage}` : ""}`);
            }
          } catch {
            /* binary/audio frames etc. */
          }
        });
      }
    };
  }, opts?.preBlocked ?? false);
}

/** The last room frames a page received (newest first, capped for a failure message). */
export async function receivedFrames(page: Page, filter = ""): Promise<string[]> {
  const all = (await page.evaluate(
    () => (window as unknown as { __wsDiag?: string[] }).__wsDiag ?? [],
  )) as string[];
  const hit = all.filter((f) => f.includes(filter));
  return hit.slice(-30).reverse();
}

/** Kills every live media socket in the page — the page-level equivalent of
 * an abrupt network cut to the media server. */
export async function killMediaSockets(page: Page) {
  await page.evaluate(() => {
    const store = window as unknown as { __mediaSockets?: { close: (code?: number) => void }[] };
    (store.__mediaSockets ?? []).forEach((s) => s.close(4001));
    store.__mediaSockets = [];
  });
}

/** Refuses NEW media socket opens (server unreachable), or grants them back. */
export async function setMediaReachable(page: Page, reachable: boolean) {
  await page.evaluate((ok) => {
    const store = window as unknown as { __wsBlock?: boolean };
    store.__wsBlock = !ok;
  }, reachable);
}

/** Reads one truth chip's level color class (emerald=ok, amber=degraded, red=down). */
export async function chipLevel(page: Page, key: string): Promise<"ok" | "degraded" | "down" | "idle"> {
  // The level color lives on the chip's INNER dot (aria-hidden span); the
  // testid'd outer span only carries the level's TEXT color classes.
  const classes = await page
    .locator(`[data-testid="chip-${key}"] span`)
    .getAttribute("class");
  if (classes?.includes("bg-emerald-400")) return "ok";
  if (classes?.includes("bg-amber-400")) return "degraded";
  if (classes?.includes("bg-red-500")) return "down";
  return "idle";
}

/** Waits until a chip is at the wanted level (polls — chips update via events).
 * On timeout the failure carries the last room frames the page received,
 * separating "pipeline never emitted" from "emitted but not applied". */
export async function expectChip(
  page: Page,
  key: string,
  level: "ok" | "degraded" | "down",
  timeout = 45_000,
) {
  try {
    await expect
      .poll(async () => (await chipLevel(page, key)) === level, { timeout, intervals: [500, 1000, 2000] })
      .toBe(true);
  } catch (e) {
    const diag = await receivedFrames(page, "diagnostic:").catch(() => [] as string[]);
    const all = await receivedFrames(page).catch(() => [] as string[]);
    throw new Error(
      `chip ${key} never reached "${level}". Room frames received (type:stage, newest first):\n` +
      `  diagnostics: ${diag.length ? diag.join(", ") : "(none — pipeline emitted nothing to this page)"}\n` +
      `  recent frames: ${all.slice(0, 15).join(", ")}\n` +
      `original error: ${e instanceof Error ? e.message.split("\n")[0] : String(e)}`);
  }
}
