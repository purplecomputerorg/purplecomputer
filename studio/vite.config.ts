/// <reference types="vitest/config" />
import { copyFileSync, cpSync, mkdirSync, readdirSync, createReadStream, existsSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import basicSsl from "@vitejs/plugin-basic-ssl";
import { defineConfig, type Connect, type Plugin } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const pyodideDir = resolve(here, "node_modules/pyodide");
// The ONNX runtime for Purple's voice (src/live/piper.worker.ts), loaded by URL rather than bundled: its
// threads start from the file the runtime is in.
const ortDir = resolve(here, "node_modules/onnxruntime-web/dist");
const ORT_FILES = ["ort.wasm.min.mjs", "ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"];
// espeak-ng's source offer, served beside the voice (see vendor/espeak-ng/README.md).
const espeakDir = resolve(here, "vendor/espeak-ng");
const ESPEAK_SOURCE = ["README.md", "espeak_bridge.c", "build.sh"];
// Files fetched or built for the in-browser Purple by scripts/studio_bundle.py: Pyodide's pygame-ce
// wheel, purple.zip, Purple's voice (voice/), and the room checker the Room guide links to.
const cacheDir = resolve(here, ".cache");
const PYODIDE_FILES = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.mjs", "pyodide.asm.wasm", "pyodide-lock.json", "python_stdlib.zip", "pyodide.mjs"];

// pygame's WebAssembly build evaluates JavaScript, so the live Purple page alone allows eval.
const liveCsp: Connect.NextHandleFunction = (req, res, next) => {
  if (req.url?.startsWith("/purple.html")) {
    const set = res.setHeader.bind(res);
    res.setHeader = (k: string, v: number | string | readonly string[]) => set(k, k.toLowerCase() === "content-security-policy" ? LIVE_CSP : v);
  }
  next();
};

// Pyodide loads its runtime files by URL next to itself, so serve node_modules/pyodide
// at /pyodide/ in dev and copy the same files into dist/pyodide/ on build.
function pyodideAssets(): Plugin {
  return {
    name: "pyodide-assets",
    configureServer(server) {
      const serve = (prefix: string, dirs: string[], keep: (f: string) => boolean = () => true) => server.middlewares.use(prefix, (req, res, next) => {
        const name = decodeURIComponent((req.url ?? "/").slice(1).split("?")[0]);
        const file = name && keep(name) ? dirs.map((d) => resolve(d, name)).find((f) => dirs.some((d) => f.startsWith(d + sep)) && existsSync(f) && statSync(f).isFile()) : null;
        if (!file) return next();
        res.setHeader("Content-Type", TYPES[name.split(".").pop()!] ?? "application/octet-stream");
        for (const [k, v] of Object.entries(HEADERS)) res.setHeader(k, v);
        createReadStream(file).pipe(res);
      });
      server.middlewares.use(liveCsp);
      serve("/pyodide", [pyodideDir, join(cacheDir, "pyodide")]);
      serve("/purple", [cacheDir]);
      serve("/ort", [ortDir], (f) => ORT_FILES.includes(f));
      serve("/voice/espeak-ng", [espeakDir], (f) => ESPEAK_SOURCE.includes(f));
      serve("/voice", [join(cacheDir, "voice")]);
    },
    configurePreviewServer(server) {
      server.middlewares.use(liveCsp);
    },
    closeBundle() {
      const copyAll = (from: string, to: string, keep: (f: string) => boolean) => {
        mkdirSync(to, { recursive: true });
        if (existsSync(from)) for (const f of readdirSync(from).filter(keep)) copyFileSync(join(from, f), join(to, f));
      };
      copyAll(pyodideDir, resolve(here, "dist/pyodide"), (f) => PYODIDE_FILES.includes(f));
      copyAll(join(cacheDir, "pyodide"), resolve(here, "dist/pyodide"), (f) => f.endsWith(".whl"));
      copyAll(cacheDir, resolve(here, "dist/purple"), (f) => f === "purple.zip" || f === "purple-room-check.pyz");
      copyAll(ortDir, resolve(here, "dist/ort"), (f) => ORT_FILES.includes(f));
      if (existsSync(join(cacheDir, "voice"))) cpSync(join(cacheDir, "voice"), resolve(here, "dist/voice"), { recursive: true });
      copyAll(espeakDir, resolve(here, "dist/voice/espeak-ng"), (f) => ESPEAK_SOURCE.includes(f));
      // Vercel's Build Output API config, so `just studio-deploy` sends the same headers as vite.
      const routes = [
        { src: "/(.*)", headers: HEADERS, continue: true },
        { src: "/purple\\.html", headers: { "Content-Security-Policy": LIVE_CSP }, continue: true },
      ];
      mkdirSync(resolve(here, ".vercel/output"), { recursive: true });
      writeFileSync(resolve(here, ".vercel/output/config.json"), JSON.stringify({ version: 3, routes }, null, 2));
    },
  };
}

// Cross-origin isolation lets a room's worker block on shared memory (purple.ask), and the CSP keeps
// everything in Studio, room workers included, off the network: connect-src is this site only.
// A static host must send the same headers; see README.md.
export const CSP = [
  "default-src 'self'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "img-src 'self' data: blob:",
  "media-src 'self' data: blob:",
  "connect-src 'self'",
  "worker-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'none'",
].join("; ");
const LIVE_CSP = CSP.replace("'wasm-unsafe-eval'", "'wasm-unsafe-eval' 'unsafe-eval'");
const TYPES: Record<string, string> = { svg: "image/svg+xml", mp3: "audio/mpeg", gif: "image/gif", png: "image/png", cur: "image/x-icon", wasm: "application/wasm", json: "application/json", zip: "application/zip", whl: "application/zip", js: "text/javascript", mjs: "text/javascript", md: "text/plain; charset=utf-8", c: "text/plain; charset=utf-8", sh: "text/plain; charset=utf-8" };
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
