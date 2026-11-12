// A parent's whole trip through Studio, clicked in a real (headless) browser: a word with a meaning and a
// recording, a photo, a starter room, then Download. The file the browser saved is carried to a headless
// Purple (scripts/e2e_pack.py), which checks each of those reached the kid.
//   just e2e-studio [--url https://preview.vercel.app/] [--out DIR] [--no-purple]
// Screenshots of each step: DIR/studio/, Purple's: DIR/purple/. DIR defaults to $TMPDIR/studio-e2e.
import { spawnSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { click, clickText, find, nextDownload, openStudio, shot, sleep, things, type, upload } from "./browser.mjs";
import { studioFiles } from "./fixtures";

const arg = (name: string) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : undefined; };
const OUT = resolve(arg("out") ?? join(process.env.TMPDIR ?? "/tmp", "studio-e2e"));
const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const WORD = "octopus", MEANING = "An octopus has eight arms and three hearts.";
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
await step(`the ${ROOM.name} room`, async () => {
  await go("#rooms");
  await clickText(page, ROOM.card);
  await sleep(2500);
  await clickText(page, /Add to my Purple Pack/);
});
let pack = "";
await step("download", async () => {
  await go("#pack");
  const since = Date.now();
  await clickText(page, /Download my Purple Pack/);
  pack = await nextDownload(join(OUT, "downloads"), since);
});
console.log(`studio: downloaded ${pack}`);
const late = errors();
await s.close();
if (late.length) console.log(`studio: browser errors along the way:\n  ${late.join("\n  ")}`);
if (process.argv.includes("--no-purple")) process.exit(0);

const expect = [`Play answers "${WORD}"`, `Play explains "${WORD}"`, `Purple says "${WORD}"`, "Art's Open has", `room ${ROOM.name} runs`];
const python = spawnSync("just", ["e2e-pack", pack, "--shots", join(OUT, "purple"), ...expect.flatMap((e) => ["--expect", e])], { cwd: ROOT, stdio: "inherit" });
process.exit(python.status ?? 1);
