// Studio in headless Chromium for an AI tester (scripts/e2e_ai.py): one JSON request per line on stdin,
// one "@@" + JSON reply per line on stdout. vite-node scripts/browser-bridge.ts <out dir> [url]
//   {"op": "look"}                        -> {url, things, shot (base64 PNG)}
//   {"op": "click"|"type"|"upload"|"key"|"scroll"|"wait", ...} -> {url, things}
//   {"op": "downloads"}                   -> {files}
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { click, openStudio, sleep, things, type, upload } from "./browser.mjs";
import { studioFiles } from "./fixtures";

const [out, url] = process.argv.slice(2);
const files = studioFiles(join(out, "files"));
const downloads = join(out, "downloads");
const s = await openStudio({ url, downloads, mic: files.mic });
const { page } = s;
const reply = (body: object) => process.stdout.write(`@@${JSON.stringify(body)}\n`);
const now = async () => ({ url: page.url().replace(s.url, "/"), things: await things(page), errors: s.errors.splice(0) });

type Request = { op: string; n?: number; text?: string; enter?: boolean; file?: keyof typeof files; key?: string; dy?: number; seconds?: number };
const ops: Record<string, (r: Request) => Promise<object>> = {
  look: async () => ({ ...(await now()), shot: await page.screenshot({ encoding: "base64" }) }),
  click: async ({ n }) => (await click(page, n!), now()),
  type: async ({ n, text, enter }) => (await type(page, n!, text ?? "", { enter }), now()),
  upload: async ({ n, file }) => (await upload(page, n!, files[file ?? "photo"]), now()),
  key: async ({ key }) => (await page.keyboard.press(key as never), await sleep(300), now()),
  scroll: async ({ dy }) => (await page.mouse.wheel({ deltaY: dy ?? 600 }), await sleep(300), now()),
  wait: async ({ seconds }) => (await sleep(Math.min(10, seconds ?? 2) * 1000), now()),
  downloads: async () => ({ files: readdirSync(downloads).filter((f) => !f.endsWith(".crdownload")).map((f) => join(downloads, f)) }),
};

reply({ ready: true, files: Object.keys(files) });
for await (const line of createInterface({ input: process.stdin })) {
  const req = JSON.parse(line) as Request;
  try {
    reply({ ok: true, ...(await (ops[req.op] ?? (() => Promise.reject(new Error(`no such op ${req.op}`))))(req)) });
  } catch (e) {
    reply({ ok: false, error: e instanceof Error ? e.message.split("\n")[0] : String(e), ...(await now()) });
  }
}
await s.close();
