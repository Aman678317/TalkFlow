/**
 * The PostCSS pipeline must not run Tailwind over VENDOR stylesheets.
 *
 * Tailwind's PostCSS plugin rejects any stylesheet that uses `@layer base`
 * without a matching `@tailwind base` directive. Vendor stylesheets do exactly
 * that (the CopilotKit runtime stylesheet is one of them), and the rejection
 * failed the production build — which is why the in-app agent assistant could
 * never be shipped. The fix: Tailwind runs on the app's own CSS only.
 *
 * These tests run the app's REAL PostCSS config, so they fail again if the
 * exclusion is ever dropped.
 */
import { describe, expect, it } from "vitest";
import postcss from "postcss";
// @ts-expect-error - postcss.config.js is plain JS without type declarations
import config from "../../../postcss.config";

async function process(css: string, from: string) {
  const plugins = (config as { plugins: unknown[] }).plugins;
  const result = await postcss(plugins as never[]).process(css, { from });
  return result.css;
}

describe("postcss configuration", () => {
  it("processes a vendor stylesheet that uses @layer base", async () => {
    const css = await process(
      "@layer base{ [data-vendor]{ box-sizing:border-box; color:red } }",
      "node_modules/some-vendor/dist/index.css",
    );
    expect(css).toContain("color:red");
  });

  it("still expands the app's own tailwind directives", async () => {
    const css = await process("@tailwind base;", "src/index.css");
    expect(css.length).toBeGreaterThan(200);
    expect(css).toContain("box-sizing");
  });
});
