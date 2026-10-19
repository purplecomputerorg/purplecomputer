// The page inside Studio's live preview iframe: boots Purple and does what Studio asks over
// postMessage. Kept in its own page because pygame's WebAssembly build needs eval, which
// Studio's own pages forbid.
import { browserKey } from "../keys";
import { roomGuests } from "../rooms/guests";
import { bootPurple, type LivePurple, type PackFiles, type Place, type RoomSetup } from "./boot";
import { onVoiceNote } from "./piper";

export type ToFrame =
  | { type: "load"; pack: PackFiles | null; setup: RoomSetup }
  | { type: "setup"; setup: RoomSetup }
  | { type: "key"; char: string }
  | { type: "focus" }
  | { type: "view"; view: View };
// The part of Purple's screen to show, as fractions of it: x, y, width, height.
export type View = [number, number, number, number];
export type FromFrame =
  | { type: "hello" }
  | { type: "status"; text: string }
  | { type: "voice"; text: string | null }
  | { type: "restarting" }
  | { type: "loaded" }
  | { type: "failed"; text: string }
  | { type: "focus"; on: boolean }
  | { type: "keydown"; key: string }
  | { type: "place"; place: Place }
  | { type: "print"; text: string }
  | { type: "problem"; text: string; line: number | null };

// SDL draws into #canvas, kept off screen; #screen is what people see, at its own pixel size.
const sdl = document.getElementById("canvas") as HTMLCanvasElement;
const canvas = document.getElementById("screen") as HTMLCanvasElement;
const post = (m: FromFrame) => parent.postMessage(m, location.origin);
// For Purple's FamilyRoom (browser.py): rooms run in workers from this page.
Object.assign(globalThis, {
  purpleRoomGuest: roomGuests((text) => post({ type: "print", text })),
  purpleRoomProblem: (text: string, line: number | null) => post({ type: "problem", text, line: line ?? null }),
});
onVoiceNote((text) => post({ type: "voice", text }));
canvas.addEventListener("focus", () => post({ type: "focus", on: true }));
canvas.addEventListener("blur", () => post({ type: "focus", on: false }));
addEventListener("keydown", (e) => {
  const key = browserKey(e);
  if (key) post({ type: "keydown", key });
});
// Purple reads these keys itself, on its next frame, so ask it a moment later where they left it
// (Esc opens the room picker on release, hence keyup).
const SETTLE_MS = 120;
let asking = 0;
addEventListener("keyup", () => {
  clearTimeout(asking);
  asking = window.setTimeout(() => run((live) => live.place().then(placed)), SETTLE_MS);
});

let view: View = [0, 0, 1, 1];
let target: View = view;
let gliding = false;

function copyFrame(): void {
  const w = Math.max(1, Math.round(canvas.clientWidth * devicePixelRatio));
  const h = Math.round((w * sdl.height) / sdl.width);
  if (canvas.width !== w) Object.assign(canvas, { width: w, height: h });
  const ctx = canvas.getContext("2d")!;
  ctx.imageSmoothingQuality = "high";
  const [x, y, vw, vh] = view;
  ctx.drawImage(sdl, x * sdl.width, y * sdl.height, vw * sdl.width, vh * sdl.height, 0, 0, w, h);
}

// Eases toward the view Studio asked for, a frame at a time, and stops once there.
function glide(): void {
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  view = view.map((v, i) => (still || Math.abs(target[i] - v) < 0.002 ? target[i] : v + (target[i] - v) * 0.22)) as View;
  copyFrame();
  gliding = view.some((v, i) => v !== target[i]);
  if (gliding) requestAnimationFrame(glide);
}
Object.assign(globalThis, { purplePresented: copyFrame });
new ResizeObserver(copyFrame).observe(canvas);

const placed = (place: Place) => post({ type: "place", place });
const handle = (live: LivePurple, m: ToFrame): Promise<void> => {
  if (m.type === "load") return live.load(m.pack, () => post({ type: "restarting" })).then(() => live.setup(m.setup)).then(placed).then(() => post({ type: "loaded" }));
  if (m.type === "setup") return live.setup(m.setup).then(placed);
  if (m.type === "key") return live.key(m.char).then(placed);
  canvas.focus();
  return Promise.resolve();
};

// Messages queue up while Purple boots, then run in order, one at a time.
const booted = bootPurple(sdl, (text) => post({ type: "status", text }));
let queue: Promise<unknown> = booted;
const run = (task: (live: LivePurple) => Promise<void>) => {
  queue = queue.then(async () => task(await booted)).catch((err) => post({ type: "failed", text: String(err?.message ?? err) }));
};
addEventListener("message", (e: MessageEvent<ToFrame>) => {
  if (e.origin !== location.origin || e.source !== parent) return;
  // A view doesn't wait for Purple: it's only how the frames are copied.
  if (e.data.type === "view") {
    target = e.data.view;
    if (!gliding) glide();
    return;
  }
  run((live) => handle(live, e.data));
});
booted.catch((err) => post({ type: "failed", text: String(err?.message ?? err) }));
post({ type: "hello" });
