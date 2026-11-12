// A parent's whole trip through Studio, clicked in a real (headless) browser: a word with a meaning and a
// recording, a photo renamed, a starter room, then Download; then Clear everything, open the downloaded file, and
// download again, which must give the same pack. That file is carried to a headless Purple
// (scripts/e2e_pack.py), which checks each part reached the kid. A browser error fails the run.
//   just e2e-studio [--url https://preview.vercel.app/] [--out DIR] [--no-purple]
// Screenshots of each step: DIR/studio/, Purple's: DIR/purple/. DIR defaults to $TMPDIR/studio-e2e.
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzip, untar } from "@sdk/tar";
import { click, clickText, find, nextDownload, openStudio, shot, sleep, things, type, upload } from "./browser.mjs";
import { studioFiles } from "./fixtures";

const arg = (name: string) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : undefined; };
const OUT = resolve(arg("out") ?? join(process.env.TMPDIR ?? "/tmp", "studio-e2e"));
const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const WORD = "octopus", MEANING = "An octopus has eight arms and three hearts.", PHOTO = "Biscuit's Yard";
const ROOM = { card: /button: .*spelling snake/i, name: "snake" };

rmSync(OUT, { recursive: true, force: true });
mkdirSync(join(OUT, "studio"), { recursive: true });
const files = studioFiles(join(OUT, "files"));
const s = await openStudio({ url: arg("url"), downloads: join(OUT, "downloads"), mic: files.mic });
const { page } = s;
const go = async (hash: string) => { await page.goto(new URL(hash, s.url).href); await sleep(1200); };
// The live Purple preview's Python and voice are fetched separately (just studio-bundle); the download needs neither.
const errors = () => s.errors.filter((e) => !/favicon|pyodide|\.whl|voice|kokoro|onnx/i.test(e));
let n = 0;
async function step(name: string, act: () => Promise<void>) {
  process.stdout.write(`studio: ${name}... `);
  try {
    await act();
    await shot(page, join(OUT, "studio", `${++n}-${name.replace(/\W+/g, "-")}.png`));
    console.log("ok");
  } catch (e) {
    await shot(page, join(OUT, "studio", `${++n}-FAILED.png`));
    console.log(`FAILED\n${e instanceof Error ? e.message : e}\nOn the page:\n${(await things(page)).join("\n")}\nBrowser errors: ${errors().join("\n") || "none"}`);
    await s.close();
    process.exit(1);
  }
}

await step("a word with a meaning", async () => {
  await go("#words");
  await type(page, await find(page, /input text: (New word|Type a new word)/), WORD, { enter: true });
  await type(page, await find(page, /Meaning|What Purple answers/), MEANING);
  await page.keyboard.press("Tab");
});
await step("a recording of the word", async () => {
  await clickText(page, /Your voice/);
  await clickText(page, /Record a sound/);
  await sleep(1500);
  await clickText(page, /Record a sound|■/);
  await sleep(1500);
});
await step("a photo", async () => {
  await go("#pictures");
  await upload(page, await find(page, /input file/), files.photo);
  await page.waitForFunction(() => /#pictures\/./.test(location.hash), { timeout: 20000 });
  const add = (await things(page)).find((t) => /Add to my Purple Pack/.test(t));
  if (add) await click(page, Number(add.match(/\d+/)![0]));
});
await step("rename the photo", async () => {
  await type(page, await find(page, /input text: Picture name/), PHOTO);
  await page.keyboard.press("Tab");
  await page.waitForFunction((t) => document.querySelector(".editor-head h2")?.textContent === t, { timeout: 5000 }, PHOTO);
  await find(page, new RegExp(`Choose ${PHOTO}`));
});
await step(`the ${ROOM.name} room`, async () => {
  await go("#rooms");
  await clickText(page, ROOM.card);
  await sleep(2500);
  await clickText(page, /Add to my Purple Pack/);
});
async function download(): Promise<string> {
  await go("#pack");
  const since = Date.now();
  await clickText(page, /Download my Purple Pack/);
  return nextDownload(join(OUT, "downloads"), since);
}
let pack = "", reopened = "";
await step("download", async () => { pack = await download(); });
// A family changes their pack weeks later by opening the file they downloaded: everything must come back.
await step("clear everything", async () => {
  await go("#pack");
  await clickText(page, /button: Clear everything/, { last: true });  // the page's own; the More menu's copy is folded away
  await page.waitForSelector("dialog[open]", { timeout: 5000 });
  await page.$$eval("dialog[open] button", (bs) => bs.find((b) => b.textContent === "Clear everything")?.click());
  await page.waitForFunction(() => !document.querySelector("dialog[open]"), { timeout: 5000 });
  await go("#pack");
  if ((await things(page)).some((t) => /a: 1 word/.test(t))) throw new Error("the words are still there after Clear everything");
});
await step("open the Purple Pack again", async () => {
  await upload(page, await find(page, /open your Purple Pack/i), pack);
  await sleep(1500);
});
await step("download it again", async () => { reopened = await download(); });

// What Purple reads must come back byte for byte; the photo kept for re-cropping (studio/) is re-encoded, so only its presence counts.
const entries = async (file: string) => new Map<string, Uint8Array>(untar(await gunzip(readFileSync(file))).map((e) => [e.path, e.data]));
const [before, after] = await Promise.all([entries(pack), entries(reopened)]);
const same = (a?: Uint8Array, b?: Uint8Array) => !!a && !!b && a.length === b.length && a.every((v, i) => v === b[i]);
const lost = [...new Set([...before.keys(), ...after.keys()])].filter((p) =>
  p.startsWith("studio/pictures/") ? before.has(p) !== after.has(p) : !same(before.get(p), after.get(p)));
console.log(lost.length ? `studio: reopening changed ${lost.join(", ")}` : "studio: reopened and downloaded again, the same pack");
const late = errors();
await s.close();
if (late.length) console.log(`studio: browser errors along the way:\n  ${late.join("\n  ")}`);
const studioOk = !lost.length && !late.length;
if (process.argv.includes("--no-purple")) process.exit(studioOk ? 0 : 1);

const expect = [`Play answers "${WORD}"`, `Play explains "${WORD}"`, `Purple says "${WORD}"`, "Art's Open has", `room ${ROOM.name} runs`];
const python = spawnSync("just", ["e2e-pack", reopened, "--shots", join(OUT, "purple"), ...expect.flatMap((e) => ["--expect", e])], { cwd: ROOT, stdio: "inherit" });
process.exit(studioOk && python.status === 0 ? 0 : 1);
