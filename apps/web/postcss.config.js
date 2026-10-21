import tailwindcss from "tailwindcss";
import autoprefixer from "autoprefixer";

const tw = tailwindcss({});

/**
 * Tailwind refuses any stylesheet that uses `@layer base` without a matching
 * `@tailwind base` directive. Vendor stylesheets do exactly that — the
 * CopilotKit runtime stylesheet is one of them — and the rejection failed the
 * production build, which is why the in-app assistant could never be shipped.
 *
 * So Tailwind now runs on the app's own CSS only; vendor CSS passes through
 * untouched (its rules are scoped to its own `[data-copilotkit]` attributes,
 * so it does not need the Tailwind layers).
 */
const tailwindAppOnly = {
  postcssPlugin: "tailwind-app-only",
  plugins: [
    async (root, result) => {
      const from = String(result.opts.from || "");
      if (from.includes("node_modules")) return;
      for (const plugin of tw.plugins) {
        if (typeof plugin === "function") await plugin(root, result);
      }
    },
  ],
};

export default {
  plugins: [tailwindAppOnly, autoprefixer()],
};
