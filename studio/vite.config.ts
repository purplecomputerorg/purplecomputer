/// <reference types="vitest/config" />
import { copyFileSync, mkdirSync, readdirSync, createReadStream, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import basicSsl from "@vitejs/plugin-basic-ssl";
import { defineConfig, type Plugin } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const pyodideDir = resolve(here, "node_modules/pyodide");
// Files fetched or built for the in-browser Purple: Pyodide's pygame-ce wheel, and purple.zip
// from scripts/studio_bundle.py.
const cacheDir = resolve(here, ".cache");
const PYODIDE_FILES = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.mjs", "pyodide.asm.wasm", "pyodide-lock.json", "python_stdlib.zip", "pyodide.mjs"];

// Pyodide loads its runtime files by URL next to itself, so serve node_modules/pyodide
// at /pyodide/ in dev and copy the same files into dist/pyodide/ on build.
function pyodideAssets(): Plugin {
  return {
    name: "pyodide-assets",
    configureServer(server) {
      const serve = (prefix: string, dirs: string[]) => server.middlewares.use(prefix, (req, res, next) => {
        const name = (req.url ?? "/").slice(1).split("?")[0];
        const dir = dirs.find((d) => existsSync(d) && readdirSync(d).includes(name));
        if (!name || !dir) return next();
        const file = join(dir, name);
        res.setHeader("Content-Type", name.endsWith(".wasm") ? "application/wasm" : name.endsWith(".json") ? "application/json" : /\.(zip|whl)$/.test(name) ? "application/zip" : "text/javascript");
        for (const [k, v] of Object.entries(HEADERS)) res.setHeader(k, v);
        createReadStream(file).pipe(res);
      });
      // pygame's WebAssembly build evaluates JavaScript, so the live Purple page alone allows eval.
      server.middlewares.use((req, res, next) => {
        if (req.url?.startsWith("/purple.html")) {
          const set = res.setHeader.bind(res);
          res.setHeader = (k: string, v: number | string | readonly string[]) => set(k, k.toLowerCase() === "content-security-policy" ? LIVE_CSP : v);
        }
        next();
      });
      serve("/pyodide", [pyodideDir, join(cacheDir, "pyodide")]);
      serve("/purple", [cacheDir]);
    },
    closeBundle() {
      const copyAll = (from: string, to: string, keep: (f: string) => boolean) => {
        mkdirSync(to, { recursive: true });
        if (existsSync(from)) for (const f of readdirSync(from).filter(keep)) copyFileSync(join(from, f), join(to, f));
      };
      copyAll(pyodideDir, resolve(here, "dist/pyodide"), (f) => PYODIDE_FILES.includes(f));
      copyAll(join(cacheDir, "pyodide"), resolve(here, "dist/pyodide"), (f) => f.endsWith(".whl"));
      copyAll(cacheDir, resolve(here, "dist/purple"), (f) => /^(purple\.zip|poster-.*\.png)$/.test(f));
    },
  };
}

// Cross-origin isolation lets a room's worker block on shared memory (purple.ask), and the CSP keeps
// everything in Studio, room workers included, off the network: connect-src is this site only.
// A static host must send the same headers; see README.md.
export const CSP = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: blob:",
  "media-src 'self' data: blob:",
  "connect-src 'self'",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
].join("; ");
const LIVE_CSP = CSP.replace("'wasm-unsafe-eval'", "'wasm-unsafe-eval' 'unsafe-eval'");
const HEADERS = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
  "Content-Security-Policy": CSP,
};

// Core pack data is imported straight from ../packs so Studio and Purple share one source of truth.
export default defineConfig({
  base: "./",
  // https: cross-origin isolation (and so the room preview) needs a secure context, and the Mac
  // opens the dev server as https://simba:5173, which plain http on a LAN name is not.
  plugins: [basicSsl(), pyodideAssets(), { name: "csp-meta", transformIndexHtml: (html, ctx) => html.replace("<head>", `<head>\n    <meta http-equiv="Content-Security-Policy" content="${ctx.path.endsWith("purple.html") ? LIVE_CSP : CSP}" />`) }],
  resolve: { alias: { "@sdk": resolve(here, "sdk/src") } },
  // host: true listens on the LAN so the dev server can be opened from another machine (the Mac hits "simba").
  server: { host: true, allowedHosts: ["simba"], fs: { allow: [".."] }, headers: HEADERS },
  preview: { headers: HEADERS },
  worker: { format: "es" },
  // Drum clips stay files: a data: URL fetch would fall outside connect-src.
  build: { target: "es2022", rollupOptions: { input: { main: resolve(here, "index.html"), purple: resolve(here, "purple.html") } }, assetsInlineLimit: (file) => (file.endsWith(".ogg") ? false : undefined) },
  optimizeDeps: { exclude: ["pyodide"] },
  test: { environment: "node" },
});
