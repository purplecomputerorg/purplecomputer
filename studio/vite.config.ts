/// <reference types="vitest/config" />
import { copyFileSync, mkdirSync, readdirSync, createReadStream, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const pyodideDir = resolve(here, "node_modules/pyodide");
const PYODIDE_FILES = ["pyodide.asm.js", "pyodide.asm.wasm", "pyodide-lock.json", "python_stdlib.zip", "pyodide.mjs"];

// Pyodide loads its runtime files by URL next to itself, so serve node_modules/pyodide
// at /pyodide/ in dev and copy the same files into dist/pyodide/ on build.
function pyodideAssets(): Plugin {
  return {
    name: "pyodide-assets",
    configureServer(server) {
      server.middlewares.use("/pyodide", (req, res, next) => {
        const name = (req.url ?? "/").slice(1).split("?")[0];
        const file = join(pyodideDir, name);
        if (!name || !existsSync(file) || !readdirSync(pyodideDir).includes(name)) return next();
        res.setHeader("Content-Type", name.endsWith(".wasm") ? "application/wasm" : name.endsWith(".json") ? "application/json" : name.endsWith(".zip") ? "application/zip" : "text/javascript");
        createReadStream(file).pipe(res);
      });
    },
    closeBundle() {
      const out = resolve(here, "dist/pyodide");
      mkdirSync(out, { recursive: true });
      for (const f of PYODIDE_FILES) if (existsSync(join(pyodideDir, f))) copyFileSync(join(pyodideDir, f), join(out, f));
    },
  };
}

// Core pack data is imported straight from ../packs so Studio and Purple share one source of truth.
export default defineConfig({
  base: "./",
  plugins: [pyodideAssets()],
  resolve: { alias: { "@sdk": resolve(here, "sdk/src") } },
  // host: true listens on the LAN so the dev server can be opened from another machine (the Mac hits "simba").
  server: { host: true, allowedHosts: ["simba"], fs: { allow: [".."] } },
  build: { target: "es2022" },
  optimizeDeps: { exclude: ["pyodide"] },
  test: { environment: "node" },
});
