import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // tsconfig.json sets jsx: "preserve" since Next.js's own SWC compiler
  // does the real transform — Vite/esbuild doesn't know what to do with
  // that on its own, so tests need this plugin to transform JSX too.
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    // jsdom (not "node") so component tests can render into a real DOM —
    // the original pure-logic tests (api.ts, format.ts, charts.ts) run
    // fine under it too, just with a little more setup overhead per file.
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
  },
});
