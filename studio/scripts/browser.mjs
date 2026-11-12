// Studio in a headless Chromium, the way a parent's browser sees it: a real download lands in a real
// folder, the microphone hears a fixture WAV, and what's on the page can be listed as numbered things
// to click. e2e-studio.mjs (scripted) and browser-bridge.mjs (an AI tester) both drive it.
import { execSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = () => process.env.CHROME ?? execSync("command -v chromium || command -v chromium-browser || command -v google-chrome", { shell: "/bin/sh" }).toString().trim();

// url: a deployed Studio (a Vercel preview, say); without one, this checkout's Studio on a local Vite server.
// mic: a WAV the fake microphone plays when Studio records.
/** @param {{ url?: string, downloads: string, mic?: string, width?: number, height?: number }} options */
export async function openStudio({ url, downloads, mic, width = 1280, height = 900 }) {
  let server = null;
  if (!url) {
    const { createServer } = await import("vite");
    server = await createServer({ root: fileURLToPath(new URL("..", import.meta.url)), server: { port: 5198, strictPort: true }, logLevel: "error" });
    await server.listen();
    url = "https://localhost:5198/";
  }
  mkdirSync(downloads, { recursive: true });
  // A fresh profile each time: a parent's first visit, with nothing saved from the last run.
  const profile = mkdtempSync(join(process.env.TMPDIR ?? tmpdir(), "studio-profile-"));
  const browser = await puppeteer.launch({
    executablePath: chrome(), headless: true, acceptInsecureCerts: true, userDataDir: profile, pipe: true,
    args: ["--no-sandbox", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
      ...(mic ? [`--use-file-for-fake-audio-capture=${mic}`] : []), "--autoplay-policy=no-user-gesture-required"],
  });
  const page = (await browser.pages())[0] ?? (await browser.newPage());
  await page.setViewport({ width, height });
  const cdp = await page.createCDPSession();
  await cdp.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads, eventsEnabled: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(url, { waitUntil: "networkidle2" });
  return { browser, page, url, downloads, errors, close: async () => { await browser.close(); await server?.close(); rmSync(profile, { recursive: true, force: true }); } };
}

// The newest file in downloads that finished, waiting up to timeout for one newer than since.
export async function nextDownload(downloads, since, timeout = 120000) {
  for (const end = Date.now() + timeout; Date.now() < end; await sleep(250)) {
    const done = readdirSync(downloads).filter((f) => !f.endsWith(".crdownload")).map((f) => join(downloads, f)).filter((f) => statSync(f).mtimeMs > since);
    if (done.length && !readdirSync(downloads).some((f) => f.endsWith(".crdownload"))) return done.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)[0];
  }
  throw new Error(`no download within ${timeout / 1000}s`);
}

// Runs in the page: every visible thing a person could click or type in, numbered, as a person would name it.
function listThings() {
  const cut = (s, n) => [...s].slice(0, n).join("");  // whole characters: half an emoji is invalid JSON downstream
  const els = [...document.querySelectorAll("a[href], button, input, textarea, select, summary, [role=button], [role=tab], [contenteditable=true], .pick")];
  const seen = els.filter((el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    // A file input is often hidden inside its visible label ("Choose a picture"); the preview's on-screen keys are its own.
    const box = el.type === "file" ? el.closest("label")?.getBoundingClientRect() ?? r : r;
    return box.width > 0 && box.height > 0 && s.visibility !== "hidden" && !el.closest("[hidden], .laptop-keys") && !el.disabled;
  });
  document.querySelectorAll("[data-e2e]").forEach((el) => el.removeAttribute("data-e2e"));
  return seen.map((el, i) => {
    el.setAttribute("data-e2e", String(i));
    const kind = el.tagName === "INPUT" ? `input ${el.type}` : el.tagName.toLowerCase();
    const label = el.type === "file" ? el.closest("label")?.textContent : "";
    const name = (el.getAttribute("aria-label") || label || el.textContent || el.placeholder || el.title || el.value || "").replace(/\s+/g, " ").trim();
    return `[${i}] ${kind}${name ? `: ${cut(name, 80)}` : ""}${el.value && el.tagName !== "BUTTON" ? ` (now: ${cut(String(el.value), 40)})` : ""}`;
  });
}

export const things = (page) => page.evaluate(listThings);
const at = (n) => `[data-e2e="${n}"]`;
export async function click(page, n) { await page.click(at(n)); await sleep(400); }
export async function type(page, n, text, { enter = false } = {}) {
  await page.click(at(n), { clickCount: 3 });
  await page.keyboard.type(text);
  if (enter) await page.keyboard.press("Enter");
  await sleep(300);
}
export async function upload(page, n, file) {
  const el = await page.$(at(n));
  const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }).catch(() => null), el.evaluate((e) => e.tagName === "INPUT" || e.click())]);
  await (chooser ? chooser.accept([file]) : el.uploadFile(file));
  await sleep(800);
}

// The numbered thing whose label matches re, listing the page again first.
export async function find(page, re) {
  const list = await things(page);
  const hit = list.find((t) => re.test(t));
  if (!hit) throw new Error(`nothing on the page matches ${re}`);
  return Number(hit.match(/^\[(\d+)\]/)[1]);
}
export const clickText = async (page, re) => click(page, await find(page, re));
export const shot = (page, path) => page.screenshot({ path });
export { sleep };
