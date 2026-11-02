// Opens every Studio page and room at editor widths from the floor (380px, styles.css --pane) up, plus phone widths,
// and lists anything that sticks out of its card or the pane. Exits 1 if anything does.
// node scripts/layout-check.mjs [--only=<scene>] [--shots=pane380,win360]  (screenshots go to $TMPDIR/studio-layout)
import { execSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";
import { createServer } from "vite";

const arg = (name) => (process.argv.find((a) => a.startsWith(`--${name}=`)) ?? "").split("=")[1] ?? "";
const ONLY = arg("only");
const SHOTS = arg("shots").split(",").filter(Boolean);
const SHOT_DIR = join(process.env.TMPDIR ?? "/tmp", "studio-layout");
const PANES = [380, 400, 440, 480, 560, 680];
const PHONES = [360, 700];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const firefox = process.env.FIREFOX ?? execSync("command -v firefox-esr || command -v firefox", { shell: "/bin/sh" }).toString().trim();

const server = await createServer({ root: fileURLToPath(new URL("..", import.meta.url)), server: { port: 5199, strictPort: true }, logLevel: "error" });
await server.listen();
const BASE = "https://localhost:5199/";
// Headless Firefox can't start its content sandbox in a container; it only ever loads this local server.
const browser = await puppeteer.launch({ browser: "firefox", executablePath: firefox, headless: true, acceptInsecureCerts: true,
  env: { ...process.env, MOZ_DISABLE_CONTENT_SANDBOX: "1", MOZ_DISABLE_GMP_SANDBOX: "1", MOZ_DISABLE_RDD_SANDBOX: "1", MOZ_DISABLE_SOCKET_PROCESS_SANDBOX: "1" } });
await sleep(1500);
const p = (await browser.pages())[0] ?? await browser.newPage();
// The live Purple runs Pyodide in every room, which layout doesn't need and which crashes headless Firefox over a long run.
await p.setRequestInterception(true);
p.on("request", (r) => (/purple\.html|pyodide/.test(r.url()) ? r.abort() : r.continue()));
await p.setViewport({ width: 1440, height: 900 });

// Rooms being tried aren't kept, so each is reached by clicking its starter every time.
const go = async (hash) => { await p.goto(BASE + "#"); await sleep(300); await p.goto(BASE + hash); await sleep(1200); };
const click = (sel, i) => p.$$eval(sel, (els, i) => (typeof i === "number" ? els[i] : els.find((e) => e.textContent === i))?.click(), i);
const scenes = ["#pictures", "#words", "#keys", "#instruments", "#colors", "#rooms"].map((h) => ({ name: h, open: () => go(h) }));
await go("#rooms");
const starters = await p.$$eval(".cards .pick", (els) => els.length);
for (let i = 0; i < starters; i++) scenes.push({ name: `starter${i}`, open: async () => { await go("#rooms"); await click(".cards .pick", i); await sleep(1500); } });
for (const label of ["Start with Python", "Start with blocks"]) scenes.push({ name: label, open: async () => { await go("#rooms"); await click(".write-own .btn", label); await sleep(2500); } });

// Runs in the page: elements past their card's or the pane's edge, and boxes that cut off what's inside them.
function audit() {
  const main = document.querySelector(".main");
  const mr = main.getBoundingClientRect(), ms = getComputedStyle(main);
  const L = mr.left + parseFloat(ms.paddingLeft) - 1, R = mr.right - parseFloat(ms.paddingRight) + 1;
  const BOX = ".card, .rule, .knob-entry, .q-block, .story-page, .word-row, .your-card, .pick, .thing-detail, .blocks-editor, .trybar, .pack-line";
  const name = (el) => el.tagName.toLowerCase() + (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).join(".") : "");
  const path = (el) => { const parts = []; for (let a = el; a && a !== main && parts.length < 4; a = a.parentElement) parts.unshift(name(a)); return parts.join(" > "); };
  const bad = new Map(), clips = [];
  for (const el of main.querySelectorAll("*")) {
    if (el instanceof SVGElement || el.closest(".blockly, [hidden], .emoji-pop, dialog")) continue;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width < 1 || r.height < 1 || s.visibility === "hidden" || s.position === "fixed") continue;
    // Ellipsis text, fields, and a map square cropping its emoji cut off on purpose.
    const cuts = (s.overflowX === "hidden" || s.overflowX === "clip") && s.textOverflow !== "ellipsis" && s.webkitLineClamp === "none";
    if (cuts && !el.matches(".map-cell, textarea, input, select") && el.scrollWidth > el.clientWidth + 2) clips.push(`${path(el)} cuts off ${el.scrollWidth - el.clientWidth}px`);
    let box = null, a = el.parentElement;
    for (; a && a !== main && getComputedStyle(a).overflowX === "visible"; a = a.parentElement) box ??= a.matches(BOX) ? a : null;
    if (a !== main) continue;
    const br = box ? Math.min(R, box.getBoundingClientRect().right) : R, bl = box ? Math.max(L, box.getBoundingClientRect().left) : L;
    // The room's name hangs left of the column on purpose.
    const over = Math.max(r.right - br, el.matches("input.room-name") ? 0 : bl - r.left);
    if (over > 1.5) bad.set(el, `${path(el)} +${Math.round(over)}px ${box ? "past " + name(box) : "past the pane"}`);
  }
  const outermost = [...bad].filter(([el]) => { for (let a = el.parentElement; a; a = a.parentElement) if (bad.has(a)) return false; return true; }).map(([, v]) => v);
  const sideways = document.documentElement.scrollWidth - innerWidth;
  return [...(sideways > 1 ? [`page scrolls sideways ${sideways}px`] : []), ...outermost, ...clips];
}

const found = {};
const record = (where, issues) => { for (const i of issues) (found[i] ??= []).push(where); };
async function check(scene, tag) {
  const tabs = await p.$$eval(".tab[role=tab]", (els) => els.map((e) => e.textContent));
  for (const [t, tab] of (tabs.length ? tabs : [""]).entries()) {
    if (tab) { await click(".tab[role=tab]", t); await sleep(400); }
    await p.waitForSelector(".main");
    await p.$$eval(".main details:not(.more-menu)", (els) => els.forEach((d) => (d.open = true)));
    await sleep(150);
    const where = `${scene}${tab ? ` [${tab}]` : ""} @${tag}`;
    record(where, await p.evaluate(audit));
    if (SHOTS.includes(tag)) await (await p.$(".main")).screenshot({ path: join(SHOT_DIR, `${where.replace(/[^a-z0-9]+/gi, "_")}.png`) });
  }
}
const setBody = (prop, value) => p.evaluate((prop, value) => document.querySelector(".body").style.setProperty(prop, value), prop, value);
if (SHOTS.length) mkdirSync(SHOT_DIR, { recursive: true });
for (const s of scenes) {
  if (ONLY && !s.name.includes(ONLY)) continue;
  await p.setViewport({ width: 1440, height: 900 });
  await s.open();
  const scene = s.name.startsWith("#") ? s.name : `${await p.evaluate(() => location.hash)} (${s.name})`;
  console.error(scene);
  const staged = await p.evaluate(() => !document.querySelector(".body").classList.contains("no-stage"));
  if (staged) {
    for (const w of PANES) { await setBody("--pane", `${w}px`); await sleep(250); await check(scene, `pane${w}`); }
    await setBody("--pane", "");
    // The narrowest a window can be with the panes side by side, dragged as far as it goes: the floor must hold.
    await p.setViewport({ width: 961, height: 900 });
    await setBody("--live", "2.1fr");
    const w = await p.evaluate(() => document.querySelector(".main").getBoundingClientRect().width);
    if (w < 379) record(`the editor got narrower than its floor: ${Math.round(w)}px`, [scene]);
    await check(scene, "win961-dragged");
    await setBody("--live", "");
  }
  for (const w of PHONES) { await p.setViewport({ width: w, height: 900 }); await sleep(300); await check(scene, `win${w}`); }
}
await browser.close();
await server.close();
const issues = Object.entries(found);
for (const [issue, where] of issues) console.log(`${issue}\n    ${where.length}x: ${where.slice(0, 4).join(", ")}${where.length > 4 ? ", ..." : ""}`);
console.log(issues.length ? `\n${issues.length} layout problems` : "No layout problems.");
process.exit(issues.length ? 1 : 0);
