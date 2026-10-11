// The page inside Studio's live preview iframe: boots Purple and does what Studio asks over
// postMessage. Kept in its own page because pygame's WebAssembly build needs eval, which
// Studio's own pages forbid.
import { bootPurple, type LivePurple, type RoomSetup } from "./boot";

export type ToFrame =
  | { type: "load"; pack: Uint8Array | null; setup: RoomSetup }
  | { type: "setup"; setup: RoomSetup }
  | { type: "key"; char: string }
  | { type: "focus" };
export type FromFrame =
  | { type: "hello" }
  | { type: "status"; text: string }
  | { type: "loaded" }
  | { type: "failed"; text: string }
  | { type: "focus"; on: boolean };

// SDL draws into #canvas, kept off screen; #screen is what people see, at its own pixel size.
const sdl = document.getElementById("canvas") as HTMLCanvasElement;
const canvas = document.getElementById("screen") as HTMLCanvasElement;
const post = (m: FromFrame) => parent.postMessage(m, location.origin);
canvas.addEventListener("focus", () => post({ type: "focus", on: true }));
canvas.addEventListener("blur", () => post({ type: "focus", on: false }));

function copyFrame(): void {
  const w = Math.max(1, Math.round(canvas.clientWidth * devicePixelRatio));
  const h = Math.round((w * sdl.height) / sdl.width);
  if (canvas.width !== w) Object.assign(canvas, { width: w, height: h });
  const ctx = canvas.getContext("2d")!;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(sdl, 0, 0, w, h);
}
Object.assign(globalThis, { purplePresented: copyFrame });
new ResizeObserver(copyFrame).observe(canvas);

const handle = (live: LivePurple, m: ToFrame): Promise<void> => {
  if (m.type === "load") return live.load(m.pack).then(() => live.setup(m.setup)).then(() => post({ type: "loaded" }));
  if (m.type === "setup") return live.setup(m.setup);
  if (m.type === "key") return live.key(m.char);
  canvas.focus();
  return Promise.resolve();
};

// Messages queue up while Purple boots, then run in order, one at a time.
const booted = bootPurple(sdl, (text) => post({ type: "status", text }));
let queue: Promise<unknown> = booted;
addEventListener("message", (e: MessageEvent<ToFrame>) => {
  if (e.origin !== location.origin || e.source !== parent) return;
  queue = queue.then(async () => handle(await booted, e.data)).catch((err) => post({ type: "failed", text: String(err?.message ?? err) }));
});
booted.catch((err) => post({ type: "failed", text: String(err?.message ?? err) }));
post({ type: "hello" });
