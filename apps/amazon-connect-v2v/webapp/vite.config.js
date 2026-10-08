import { defineConfig } from "vite";
import mkcert from "vite-plugin-mkcert";
import { nodePolyfills } from "vite-plugin-node-polyfills";
import { viteStaticCopy } from "vite-plugin-static-copy";

export default defineConfig({
  base: "/connect/",
  server: {
    https: true,
    fs: {
      cachedChecks: false,
    },
  },
  plugins: [
    mkcert(),
    nodePolyfills(),
    viteStaticCopy({
      targets: [
        {
          src: "lib/*",
          dest: "./lib",
        },
        {
          src: "assets/*",
          dest: "./assets",
        },
      ],
    }),
  ],
  define: {
    global: {},
  },
});
