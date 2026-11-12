// Studio in headless Chromium for an AI tester (scripts/e2e_ai.py): one JSON request per line on stdin,
// one "@@" + JSON reply per line on stdout. vite-node scripts/browser-bridge.ts <out dir> [url]
//   {"op": "look"}                        -> {url, things, shot (base64 PNG)}
//   {"op": "click"|"type"|"upload"|"key"|"scroll"|"wait", ...} -> {url, things}
//   {"op": "downloads"}                   -> {files}
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { click, openStudio, sleep, things, type, upload } from "./browser.mjs";
import { studioFiles } from "./fixtures";

const [out, url] = process.argv.slice(2);
const files = studioFiles(join(out, "files"));
const downloads = join(out, "downloads");
const [width, height] = (process.env.E2E_VIEWPORT || "1280x900").split("x").map(Number);
const s = await openStudio({ url, downloads, mic: files.mic, width, height });
const { page } = s;
const reply = (body: object) => process.stdout.write(`@@${JSON.stringify(body)}\n`);
const now = async () => ({ url: page.url().replace(s.url, "/"), things: await things(page), errors: s.errors.splice(0) });

const saved = () => readdirSync(downloads).filter((f) => !f.endsWith(".crdownload")).map((f) => join(downloads, f));
// "pack": the Purple Pack this parent downloaded last, to open in Studio again.
const fileFor = (file: string) => {
  if (file !== "pack") return files[(file in files ? file : "photo") as keyof typeof files];
  const packs = saved().filter((f) => f.endsWith(".purplepack")).sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  if (!packs.length) throw new Error("you haven't downloaded a Purple Pack yet");
  return packs[0];
};

type Request = { op: string; n?: number; text?: string; enter?: boolean; file?: string; key?: string; dy?: number; seconds?: number };
const ops: Record<string, (r: Request) => Promise<object>> = {
  look: async () => ({ ...(await now()), shot: await page.screenshot({ encoding: "base64" }) }),
  click: async ({ n }) => (await click(page, n!), now()),
  type: async ({ n, text, enter }) => (await type(page, n!, text ?? "", { enter }), now()),
  upload: async ({ n, file }) => (await upload(page, n!, fileFor(file ?? "photo")), now()),
  key: async ({ key }) => (await page.keyboard.press(key as never), await sleep(300), now()),
  scroll: async ({ dy }) => (await page.mouse.wheel({ deltaY: dy ?? 600 }), await sleep(300), now()),
  wait: async ({ seconds }) => (await sleep(Math.min(10, seconds ?? 2) * 1000), now()),
  reload: async () => (await page.reload({ waitUntil: "networkidle2" }), now()),
  back: async () => (await page.goBack({ waitUntil: "networkidle2" }), await sleep(300), now()),
  downloads: async () => ({ files: saved() }),
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
