import { defineConfig } from "vitest/config";

// Core pack data is imported straight from ../packs so Studio and Purple share one source of truth.
export default defineConfig({
  base: "./",
  server: { fs: { allow: [".."] } },
  build: { target: "es2022" },
  test: { environment: "node" },
});
