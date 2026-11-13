// The page inside Studio's live preview iframe: boots Purple and does what Studio asks over
// postMessage. Kept in its own page because pygame's WebAssembly build needs eval, which
// Studio's own pages forbid.
import { browserKey, MODIFIERS } from "../keys";
import { roomGuests } from "../rooms/guests";
import { bootPurple, type LivePurple, type PackFiles, type Place, type RoomSetup } from "./boot";
import { onVoiceNote } from "./piper";
import { trace } from "./trace";

export type ToFrame =
  | { type: "load"; pack: PackFiles | null; setup: RoomSetup | null }
  | { type: "setup"; setup: RoomSetup }
  | { type: "key"; char: string }
  | { type: "code"; on: boolean }
  | { type: "demo" }
  | { type: "focus" }
  | { type: "hush" }
  | { type: "filter"; id: number; text: string }
  | { type: "check"; id: number; source: string; names: string[] }
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
  | { type: "modifier"; key: string }
  | { type: "click" }
  | { type: "place"; place: Place }
  | { type: "print"; text: string }
  | { type: "answer"; id: number; value: unknown }
  | { type: "problem"; text: string; line: number | null };

// SDL draws into #canvas, kept off screen; #screen is what people see, at its own pixel size.
const sdl = document.getElementById("canvas") as HTMLCanvasElement;
const canvas = document.getElementById("screen") as HTMLCanvasElement;
const post = (m: FromFrame) => (m.type !== "status" && trace("[frame] sends", m.type), parent.postMessage(m, location.origin));
// For Purple's FamilyRoom (browser.py): rooms run in workers from this page.
const guests = roomGuests((text) => post({ type: "print", text }));
Object.assign(globalThis, {
  purpleRoomGuest: guests,
  purpleRoomProblem: (text: string, line: number | null) => post({ type: "problem", text, line: line ?? null }),
});
onVoiceNote((text) => post({ type: "voice", text }));
canvas.addEventListener("focus", () => post({ type: "focus", on: true }));
canvas.addEventListener("blur", () => post({ type: "focus", on: false }));
addEventListener("pointerdown", (e) => e.pointerType === "mouse" && post({ type: "click" }));
addEventListener("keydown", (e) => {
  const key = browserKey(e);
  if (key) post({ type: "keydown", key });
  else if (e.key in MODIFIERS && !e.repeat) post({ type: "modifier", key: MODIFIERS[e.key] });
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
// Purple says where it is after each frame that leaves it somewhere new (browser.py).
const moved = (json: string) => post({ type: "place", place: JSON.parse(json) as Place });
Object.assign(globalThis, { purplePresented: copyFrame, purpleMoved: moved });
new ResizeObserver(copyFrame).observe(canvas);

const handle = (live: LivePurple, m: ToFrame): Promise<void> => {
  if (m.type === "load") return live.load(m.pack, () => post({ type: "restarting" })).then(() => m.setup && live.setup(m.setup)).then(() => post({ type: "loaded" }));
  if (m.type === "setup") return live.setup(m.setup);
  if (m.type === "key") return live.key(m.char);
  if (m.type === "code") return live.code(m.on);
  if (m.type === "demo") return live.demo();
  if (m.type === "hush") return live.hush();
  if (m.type === "filter") return live.filter(m.text).then((value) => post({ type: "answer", id: m.id, value }));
  if (m.type === "check") return live.check(m.source, m.names).then((value) => post({ type: "answer", id: m.id, value }));
  canvas.focus();
  return Promise.resolve();
};

// Messages queue up while Purple boots, then run in order, one at a time.
// Straight to the console too, to see how far Purple got in a browser where it never shows.
const booted = bootPurple(sdl, (text) => (console.info("[purple]", text), post({ type: "status", text })));
let queue: Promise<unknown> = booted;
const run = (task: (live: LivePurple) => Promise<void>) => {
  queue = queue.then(async () => task(await booted)).catch((err) => post({ type: "failed", text: String(err?.message ?? err) }));
};
addEventListener("message", (e: MessageEvent<ToFrame>) => {
  // Not e.source: Safari gives this page's own window for Studio's messages. Pyodide's own have no type.
  if (e.origin !== location.origin || !e.data?.type) return;
  trace("[frame] got", e.data.type);
  // A view doesn't wait for Purple: it's only how the frames are copied.
  if (e.data.type === "view") {
    target = e.data.view;
    if (!gliding) glide();
    return;
  }
  run((live) => handle(live, e.data));
});
// The spare room waits for Purple, so the two don't download Pyodide side by side on a first visit.
booted.then(() => guests.warm(), (err) => post({ type: "failed", text: String(err?.message ?? err) }));
post({ type: "hello" });
