/**
 * Browser E2E for the meeting/video flow — the layer the WS golden-call test
 * cannot see: real getUserMedia devices, real WebRTC media, real browser
 * autoplay rules, real SPA routing over the compose nginx same-origin proxy.
 *
 * Targets the docker-compose stack (`docker compose up -d`):
 *   web   → http://localhost:5173   (SPA + nginx proxy of /api and /ws)
 *   api   → health via the same origin (/health)
 *   livekit → ws://localhost:7880 (browser-facing per LIVEKIT_PUBLIC_URL)
 *
 * Chromium runs with fake media devices — every participant gets a synthetic
 * camera+mic, permission prompts auto-grant, and autoplay is allowed. Tests
 * drive real joins, real media-token minting, real LiveKit subscriptions, and
 * the dev transcript-inject path (server-side guarded to non-production).
 */
import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_WEB_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  // Meeting pipelines include real model/provider calls on the compose stack.
  timeout: 120_000,
  expect: { timeout: 45_000 },
  fullyParallel: false,
  workers: 2,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }]]
    : [["list"]],
  outputDir: "./test-results",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
  },
  projects: [
    {
      name: "chromium-media",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: [
            "--use-fake-ui-for-media-stream", // auto-grant camera/mic prompts
            "--use-fake-device-for-media-stream", // synthetic camera + tone mic
            "--autoplay-policy=no-user-gesture-required",
          ],
        },
      },
    },
  ],
});
