// Purple itself in the browser: Purple's own Python and pygame canvas UI, run by Pyodide on this
// page and drawn into a canvas. purple.zip is built by scripts/studio_bundle.py.
import type { ArtPicture } from "@sdk/purple/art";
import browserShim from "./browser.py?raw";
import controller from "./live.py?raw";
import { piperSay, startIfCached } from "./piper";

const ROOT = "/home/pyodide/purple";

interface Pyodide {
  loadPackage(names: string | string[]): Promise<void>;
  unpackArchive(buffer: ArrayBuffer, format: string, options: { extractDir: string }): void;
  runPythonAsync(code: string): Promise<unknown>;
  setStdout(o: { batched: (s: string) => void }): void;
  setStderr(o: { batched: (s: string) => void }): void;
  canvas: { setCanvas2D(canvas: HTMLCanvasElement): void };
  FS: { readFile(path: string): Uint8Array; writeFile(path: string, data: Uint8Array): void };
  globals: { get(name: string): unknown };
  toPy(value: unknown): { destroy(): void };
}

// An emoji run as RGBA pixels, height px, drawn in the Noto Color Emoji Purple itself uses.
function drawEmoji(text: string, px: number): ImageData {
  const probe = new OffscreenCanvas(1, 1).getContext("2d")!;
  const font = `${Math.round(px / 1.17)}px PurpleEmoji`;
  probe.font = font;
  const width = Math.max(1, Math.ceil(probe.measureText(text).width));
  const ctx = new OffscreenCanvas(width, px).getContext("2d")!;
  ctx.font = font;
  ctx.textBaseline = "middle";
  ctx.fillText(text, 0, px / 2);
  return ctx.getImageData(0, 0, width, px);
}

// Only voices on this machine: Chrome's "Google" voices send the text to Google.
function localVoice(): SpeechSynthesisVoice | undefined {
  const voices = speechSynthesis.getVoices().filter((v) => v.localService);
  return voices.find((v) => v.default) ?? voices.find((v) => v.lang.startsWith("en")) ?? voices[0];
}

// Resolves when the browser's voice finishes, so a spoken sequence keeps its gaps.
function say(text: string): Promise<void> {
  return new Promise((done) => {
    const voice = localVoice();
    if (!voice) return done();
    const u = new SpeechSynthesisUtterance(text);
    u.voice = voice;
    u.rate = 0.95;
    u.onend = u.onerror = () => done();
    speechSynthesis.speak(u);
  });
}

// The room a Studio page shows; see setup() in live.py.
export type Room = "art" | "music" | "play" | "blocks";
// at: the room's cursor, as fractions of the screen; writing: Art writes letters rather than paints (see place() in live.py).
export interface Place { room: Room; menu: boolean; at: [number, number] | null; writing: boolean }
// letters: Music in Say Letters, or Art writing letters.
// picture: painted on the Art canvas as Art's Open paints a pack picture.
// family: a family room opened over the room, as the Esc menu opens one.
export interface RoomSetup { room: Room; letters?: boolean; instrument?: string; picture?: ArtPicture; family?: { name: string; source: string } }

// A pack's files since the last one Purple got (all of them when fresh), as install() in live.py takes them.
export interface PackFiles { id: string; fresh: boolean; files: [path: string, data: Uint8Array][]; removed: string[] }

export interface LivePurple {
  // Installs the pack (null: none) into the running Purple, first calling restarting when Purple
  // has to start again to read it.
  load(pack: PackFiles | null, restarting?: () => void): Promise<void>;
  // Both resolve to where Purple is afterwards: Esc opens the room picker, picking one changes the
  // room, and keys move the cursor.
  setup(room: RoomSetup): Promise<Place>;
  key(char: string): Promise<Place>;
  // Where Purple is now, after keys it got straight from the browser.
  place(): Promise<Place>;
  // What's on the Art canvas now.
  picture(): Promise<ArtPicture>;
}

export async function bootPurple(canvas: HTMLCanvasElement, log: (line: string) => void): Promise<LivePurple> {
  const indexURL = new URL("pyodide/", document.baseURI).href;
  const { loadPyodide } = (await import(/* @vite-ignore */ `${indexURL}pyodide.mjs`)) as { loadPyodide: (o: { indexURL: string }) => Promise<Pyodide> };
  log("Loading Python…");
  const py = await loadPyodide({ indexURL });
  py.setStdout({ batched: log });
  py.setStderr({ batched: log });
  log("Loading pygame…");
  await py.loadPackage(["pygame-ce", "fonttools", "rich", "wcwidth"]);
  log("Loading Purple…");
  py.unpackArchive(await (await fetch(new URL("purple/purple.zip", document.baseURI))).arrayBuffer(), "zip", { extractDir: ROOT });
  py.canvas.setCanvas2D(canvas);
  const emoji = new FontFace("PurpleEmoji", py.FS.readFile(`${ROOT}/fonts/NotoColorEmoji.ttf`).slice());
  document.fonts.add(await emoji.load());
  Object.assign(globalThis, { purpleDrawEmoji: drawEmoji, purpleSay: say, purplePiper: piperSay, purpleHush: () => speechSynthesis.cancel() });
  void startIfCached();
  log("Starting Purple…");
  await py.runPythonAsync(`
import os, sys
os.environ.update(PURPLE_NO_EVDEV="1", PURPLE_DEV_MODE="1", PYGAME_HIDE_SUPPORT_PROMPT="1",
                  PURPLE_EMOJI_FONT="${ROOT}/fonts/NotoColorEmoji.ttf")
sys.path.insert(0, "${ROOT}")
`);
  await py.runPythonAsync(browserShim);
  await py.runPythonAsync(controller);
  const call = (code: string) => py.runPythonAsync(code);
  const install = py.globals.get("install") as (id: string | undefined, files: unknown, removed: string[], fresh: boolean) => boolean;
  const arg = (v: unknown) => `__import__("json").loads(${JSON.stringify(JSON.stringify(v))})`;
  const place = async (code: string): Promise<Place> => {
    const proxy = (await call(code)) as { toJs(): [Room, boolean, [number, number] | null, boolean]; destroy(): void };
    const [room, menu, at, writing] = proxy.toJs();
    proxy.destroy();
    return { room, menu, at, writing };
  };
  const live: LivePurple = {
    async load(pack, restarting) {
      // As Python objects first: Python reading a JS array copies it a byte at a time.
      const files = py.toPy(pack?.files ?? []);
      const restart = install(pack?.id, files, pack?.removed ?? [], pack?.fresh ?? true);
      files.destroy();
      if (restart) {
        restarting?.();
        await call("await restart()");
      } else await call("refresh()");
    },
    setup: (room) => place(`setup(**${arg(room)})`),
    key: (char) => place(`await key(${arg(char)})`),
    place: () => place("place()"),
    picture: async () => JSON.parse((await call("picture()")) as string) as ArtPicture,
  };
  await live.load(null);
  return live;
}
