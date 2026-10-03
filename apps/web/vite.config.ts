import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

let reactPlugin: any = null;
try {
  const reactMod = await import("@vitejs/plugin-react");
  reactPlugin = reactMod.default ?? reactMod;
} catch {
  console.warn("\x1b[33m[@globaltalk/web] Notice: @vitejs/plugin-react not found in node_modules. Falling back to built-in esbuild JSX. Run 'npm install' in apps/web for full Fast-Refresh.\x1b[0m");
}

export default defineConfig({
  plugins: reactPlugin ? [reactPlugin()] : [],
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@globaltalk/shared-types": fileURLToPath(new URL("../../packages/shared-types/src/index.ts", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8088", changeOrigin: true, ws: true, timeout: 60000, proxyTimeout: 60000 },
      "/api-docs": { target: "http://127.0.0.1:8088", changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
      "/v2": { target: "http://127.0.0.1:8088", changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
      "/v3": { target: "http://127.0.0.1:8088", changeOrigin: true, timeout: 60000, proxyTimeout: 60000 },
      "/ws": { target: "ws://127.0.0.1:8088", ws: true },
      "/health": { target: "http://127.0.0.1:8088", timeout: 10000, proxyTimeout: 10000 },
      "/healthz": { target: "http://127.0.0.1:8088", timeout: 10000, proxyTimeout: 10000 },
      "/ready": { target: "http://127.0.0.1:8088", timeout: 10000, proxyTimeout: 10000 },
      "/readyz": { target: "http://127.0.0.1:8088", timeout: 10000, proxyTimeout: 10000 },
      "/metrics": { target: "http://127.0.0.1:8088", timeout: 10000, proxyTimeout: 10000 },
    },
  },
  build: {
    sourcemap: true,
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
  },
} as any);
