// Purple itself in the browser: Purple's own Python and pygame canvas UI, run by Pyodide on this
// page and drawn into a canvas. purple.zip is built by scripts/studio_bundle.py.
import browserShim from "./browser.py?raw";
import controller from "./live.py?raw";

const ROOT = "/home/pyodide/purple";

interface Pyodide {
  loadPackage(names: string | string[]): Promise<void>;
  unpackArchive(buffer: ArrayBuffer, format: string, options: { extractDir: string }): void;
  runPythonAsync(code: string): Promise<unknown>;
  setStdout(o: { batched: (s: string) => void }): void;
  setStderr(o: { batched: (s: string) => void }): void;
  canvas: { setCanvas2D(canvas: HTMLCanvasElement): void };
  FS: { readFile(path: string): Uint8Array; writeFile(path: string, data: Uint8Array): void };
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

// Resolves when the browser's voice finishes, so a spoken sequence keeps its gaps.
function say(text: string): Promise<void> {
  return new Promise((done) => {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95;
    u.onend = u.onerror = () => done();
    speechSynthesis.speak(u);
  });
}

// The room a Studio page shows; see setup() in live.py.
export type Room = "play" | "music" | "art" | "blocks";
// at: the room's cursor, as fractions of the screen (see place() in live.py).
export interface Place { room: Room; menu: boolean; at: [number, number] | null }
export interface RoomSetup { room: Room; letters?: boolean; instrument?: string; picture?: string }

export interface LivePurple {
  // Installs a .purplepack (null: none) and starts Purple again so it reads it.
  load(pack: Uint8Array | null): Promise<void>;
  // Both resolve to where Purple is afterwards: Esc opens the room picker, picking one changes the
  // room, and keys move the cursor.
  setup(room: RoomSetup): Promise<Place>;
  key(char: string): Promise<Place>;
  // Where Purple is now, after keys it got straight from the browser.
  place(): Promise<Place>;
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
  Object.assign(globalThis, { purpleDrawEmoji: drawEmoji, purpleSay: say, purpleHush: () => speechSynthesis.cancel() });
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
  const arg = (v: unknown) => `__import__("json").loads(${JSON.stringify(JSON.stringify(v))})`;
  const place = async (code: string): Promise<Place> => {
    const proxy = (await call(code)) as { toJs(): [Room, boolean, [number, number] | null]; destroy(): void };
    const [room, menu, at] = proxy.toJs();
    proxy.destroy();
    return { room, menu, at };
  };
  const live: LivePurple = {
    async load(pack) {
      if (pack) py.FS.writeFile("/tmp/studio.purplepack", pack);
      await call(`install(${pack ? `"/tmp/studio.purplepack"` : "None"})`);
      await call("await restart()");
    },
    setup: (room) => place(`setup(**${arg(room)})`),
    key: (char) => place(`await key(${arg(char)})`),
    place: () => place("place()"),
  };
  await live.load(null);
  return live;
}
