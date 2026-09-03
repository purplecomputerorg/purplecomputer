import { defineConfig } from "vitest/config";

// Core pack data is imported straight from ../packs so Studio and Purple share one source of truth.
export default defineConfig({
  base: "./",
  // host: true listens on the LAN so the dev server can be opened from another machine (the Mac hits "simba").
  server: { host: true, allowedHosts: ["simba"], fs: { allow: [".."] } },
  build: { target: "es2022" },
  test: { environment: "node" },
});
