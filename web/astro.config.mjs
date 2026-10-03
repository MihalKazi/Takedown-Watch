// @ts-check
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

const dataDir = process.env.TW_DATA_DIR ?? fileURLToPath(new URL("../data", import.meta.url));

/**
 * @returns {import("astro").AstroIntegration}
 * The dataset the site is built from ships beside it, unchanged, at /data/v1/*.json:
 * one pipeline serves the page and the open data release.
 */
function publishDataset() {
  return {
    name: "takedown-watch:publish-dataset",
    hooks: {
      "astro:build:done": ({ dir }) => {
        const src = `${dataDir}/v1`;
        if (!existsSync(src)) throw new Error(`[data contract] no dataset at ${src}`);
        const out = new URL("data/v1/", dir);
        mkdirSync(out, { recursive: true });
        cpSync(src, fileURLToPath(out), { recursive: true, filter: (f) => !f.endsWith(".tmp") });
      },
    },
  };
}

export default defineConfig({
  // Mirrors served under a sub-path set SITE_BASE, e.g. SITE_BASE=/takedown-watch/
  base: process.env.SITE_BASE ?? "/",
  ...(process.env.SITE_URL ? { site: process.env.SITE_URL } : {}),
  output: "static",
  trailingSlash: "always",
  build: { format: "directory", inlineStylesheets: "always" },
  i18n: {
    defaultLocale: "bn",
    locales: ["bn", "en"],
    routing: { prefixDefaultLocale: true, redirectToDefaultLocale: true },
  },
  integrations: [publishDataset()],
  vite: { plugins: [tailwindcss()] },
});
