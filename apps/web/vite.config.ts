import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

let reactPlugin: any = null;
try {
  const reactMod = await import("@vitejs/plugin-react");
  reactPlugin = reactMod.default ?? reactMod;
} catch {
  console.warn("\x1b[33m[@globaltalk/web] Notice: @vitejs/plugin-react not found in node_modules. Falling back to built-in esbuild JSX. Run 'npm install' in apps/web for full Fast-Refresh.\x1b[0m");
}

import net from "node:net";

async function detectBackendPort(): Promise<number> {
  const envPort = process.env.VITE_BACKEND_PORT || process.env.BACKEND_PORT;
  if (envPort) return parseInt(envPort, 10);

  const check = (port: number) =>
    new Promise<boolean>((resolve) => {
      const s = net.createConnection({ port, host: "127.0.0.1", timeout: 200 }, () => {
        s.destroy();
        resolve(true);
      });
      s.on("error", () => {
        s.destroy();
        resolve(false);
      });
      s.on("timeout", () => {
        s.destroy();
        resolve(false);
      });
    });

  // The canonical backend is always 8088. Do not auto-select the legacy
  // compatibility service on 8000: it has a different route surface and can
  // make valid auth calls appear to be 404s when both services are running.
  if (await check(8088)) return 8088;
  return 8088;
}

export default defineConfig(async () => {
  const backendPort = await detectBackendPort();
  const backendHttp = `http://127.0.0.1:${backendPort}`;
  const backendWs = `ws://127.0.0.1:${backendPort}`;

  // Shared by the dev server and the production preview.
  const apiProxy = {
    "/api": {
      target: backendHttp,
      changeOrigin: true,
      ws: true,
      timeout: 60000,
      proxyTimeout: 60000,
      // "/api" (no sub-path) is the SPA's API-keys page, not a backend call.
      bypass(req: { url?: string }) {
        if (req.url === "/api" || req.url.startsWith("/api?")) return "/index.html";
      },
    },
    "/api-docs": { target: backendHttp, changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
    "/v2": { target: backendHttp, changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
    "/v3": { target: backendHttp, changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
    "/ws": { target: backendWs, changeOrigin: true, ws: true },
    "/health": { target: backendHttp, timeout: 10000, proxyTimeout: 10000 },
    "/healthz": { target: backendHttp, timeout: 10000, proxyTimeout: 10000 },
    "/ready": { target: backendHttp, timeout: 10000, proxyTimeout: 10000 },
    "/readyz": { target: backendHttp, timeout: 10000, proxyTimeout: 10000 },
    "/metrics": { target: backendHttp, timeout: 10000, proxyTimeout: 10000 },
  };

  return {
  plugins: reactPlugin ? [reactPlugin()] : [],
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@globaltalk/shared-types": fileURLToPath(new URL("./src/types/shared-types.ts", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: apiProxy,
  },
  // The production bundle can be previewed against the same local backend —
  // that is the only faithful way to measure the shipped app (the dev server
  // serves unbundled modules and is not representative).
  preview: {
    port: 4173,
    proxy: apiProxy,
  },
  build: {
    sourcemap: process.env.GENERATE_SOURCEMAP === 'true',
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          livekit: ["livekit-client"],
          query: ["@tanstack/react-query"],
          icons: ["lucide-react"],
        },
      },
    },
  },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test-setup.ts"],
      // Playwright owns e2e/*.spec.ts under its own runner; keep vitest on
      // unit/component tests of src only.
      exclude: [
        "e2e/**",
        "node_modules/**",
        "dist/**",
      ],
    },
  } as any;
});
