// The room on the right: a RoomHost drawn the way Purple's screen draws a family room, with the
// synth for notes, the core percussion clips, and the browser's voice for "say".
import { PURPLE, SYNTH_RATE, defaults, noteFrequency, parseNote, renderNote, type BaseName } from "@sdk";
import { roomTitle } from "@sdk/pack";
import { INSTRUMENTS } from "@sdk/purple/sounds";
import { audioContext, clipToBuffer, playBuffer } from "../audio";
import { GRID_H, GRID_W, RoomHost, type Problem, type Scene } from "../rooms/host";
import { draft } from "../state";
import { h } from "./dom";
import { DEFAULT_COLORS, MUTED, PRIMARY, WHITE } from "./facsimile";

const DRUM_URLS = import.meta.glob("../../../packs/core-sounds/content/[0-9].ogg", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const DRUM_KEYS: Record<string, string> = PURPLE.room.drum_keys;
const HEX = /^#[0-9a-fA-F]{6}$/;

// Logical size: a 24 by 12 grid of 40px squares, inside the frame, with a title and a hint strip.
const CELL = 40;
const PAD = 20;
const TOP = 44;
const BOTTOM = 40;
const FRAME = { x: PAD, y: TOP, w: GRID_W * CELL, h: GRID_H * CELL };
const WIDTH = FRAME.w + 2 * PAD;
const HEIGHT = TOP + FRAME.h + BOTTOM;
const FONT = "Figtree, Inter, system-ui, sans-serif";

export function browserKey(e: KeyboardEvent): string | null {
  const map: Record<string, string> = { " ": "space", Enter: "enter", Backspace: "backspace", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
  if (e.key in map) return map[e.key];
  return [...e.key].length === 1 ? e.key.toLowerCase() : null;
}

export interface StageHooks { problem(p: Problem | null): void; print(text: string): void }

export class RoomStage {
  readonly element: HTMLElement;
  private canvas = h("canvas", { width: WIDTH * 2, height: HEIGHT * 2 });
  private host: RoomHost;
  private failed = false;
  private notes = new Map<string, AudioBuffer>();
  private drums = new Map<string, Promise<AudioBuffer | null>>();
  private frame = 0;

  constructor(private name: string, hooks: StageHooks) {
    this.canvas.style.width = "100%";
    this.canvas.style.aspectRatio = `${WIDTH} / ${HEIGHT}`;
    this.element = h("div", { class: "roomstage", tabindex: 0, title: "Click here, then press keys" }, this.canvas);
    this.host = new RoomHost({
      redraw: () => this.redraw(),
      say: (t) => this.say(t),
      play: (n, i) => this.play(n, i),
      drum: (n) => this.drum(n),
      print: hooks.print,
      problem: (p) => { this.failed = !!p; hooks.problem(p); },
    }, DEFAULT_COLORS.surface);
    this.element.addEventListener("keydown", (e) => {
      const key = browserKey(e);
      if (!key || e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      if (!e.repeat || ["up", "down", "left", "right", "backspace"].includes(key)) this.host.key(key);
    });
    this.redraw();
  }

  run(source: string): void {
    speechSynthesis?.cancel();
    this.host.start(source);
  }

  dispose(): void {
    this.host.dispose();
    speechSynthesis?.cancel();
    cancelAnimationFrame(this.frame);
  }

  private redraw(): void {
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(() => draw(this.canvas, this.host.scene, roomTitle(this.name), this.failed));
  }

  private say(text: string): void {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95;
    speechSynthesis.speak(u);
  }

  private play(note: string, instrument: string): void {
    const parsed = parseNote(note);
    if (!parsed) return;
    const key = `${instrument}|${note}`;
    let buffer = this.notes.get(key);
    if (!buffer) {
      const inst = draft.instruments.find((i) => i.name === instrument);
      const base = inst?.base ?? ((INSTRUMENTS as readonly string[]).includes(instrument) ? (instrument as BaseName) : "marimba");
      if (this.notes.size > 200) this.notes.clear();
      buffer = clipToBuffer({ samples: renderNote(base, inst?.params ?? defaults(base), noteFrequency(parsed[0], parsed[1])), rate: SYNTH_RATE });
      this.notes.set(key, buffer);
    }
    playBuffer(buffer);
  }

  private drum(name: string): void {
    const digit = Object.entries(DRUM_KEYS).find(([, n]) => n === name.toLowerCase())?.[0];
    if (!digit) return;
    if (!this.drums.has(digit)) {
      const url = Object.entries(DRUM_URLS).find(([path]) => path.endsWith(`/${digit}.ogg`))?.[1];
      this.drums.set(digit, url ? fetch(url).then((r) => r.arrayBuffer()).then((b) => audioContext().decodeAudioData(b)).catch(() => null) : Promise.resolve(null));
    }
    this.drums.get(digit)!.then((buffer) => buffer && playBuffer(buffer));
  }
}

function fitText(ctx: CanvasRenderingContext2D, text: string, px: number, maxWidth: number, weight = 600): number {
  for (; px > 14; px -= 4) {
    ctx.font = `${weight} ${px}px ${FONT}`;
    if (ctx.measureText(text).width <= maxWidth) break;
  }
  return px;
}

function centered(ctx: CanvasRenderingContext2D, text: string, y: number, px: number, color: string, weight = 600): void {
  fitText(ctx, text, px, FRAME.w - 2 * CELL, weight);
  ctx.fillStyle = color;
  ctx.fillText(text, FRAME.x + FRAME.w / 2, y);
}

function draw(canvas: HTMLCanvasElement, s: Scene, title: string, failed: boolean): void {
  const ctx = canvas.getContext("2d")!;
  ctx.setTransform(2, 0, 0, 2, 0, 0);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = DEFAULT_COLORS.background;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  centered(ctx, title, TOP / 2, 20, PRIMARY);

  ctx.save();
  ctx.beginPath();
  ctx.roundRect(FRAME.x, FRAME.y, FRAME.w, FRAME.h, 14);
  ctx.fillStyle = failed ? DEFAULT_COLORS.surface : s.background;
  ctx.fill();
  ctx.clip();
  if (failed) {
    centered(ctx, "🔧", FRAME.y + FRAME.h * 0.4, 72, WHITE);
    centered(ctx, "This room needs fixing", FRAME.y + FRAME.h * 0.6, 28, WHITE);
  } else {
    drawScene(ctx, s);
  }
  ctx.restore();
  ctx.strokeStyle = PRIMARY;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.roundRect(FRAME.x, FRAME.y, FRAME.w, FRAME.h, 14);
  ctx.stroke();
  centered(ctx, "Esc leaves the room", HEIGHT - BOTTOM / 2, 15, MUTED, 500);
}

function drawScene(ctx: CanvasRenderingContext2D, s: Scene): void {
  if (s.cells.size) {
    for (const [at, thing] of s.cells) {
      const [x, y] = at.split(",").map(Number);
      const px = FRAME.x + x * CELL;
      const py = FRAME.y + y * CELL;
      if (HEX.test(thing)) {
        ctx.fillStyle = thing;
        ctx.beginPath();
        ctx.roundRect(px + 2, py + 2, CELL - 4, CELL - 4, 6);
        ctx.fill();
      } else {
        fitText(ctx, thing, 30, CELL - 4, 600);
        ctx.fillStyle = WHITE;
        ctx.fillText(thing, px + CELL / 2, py + CELL / 2 + 1);
      }
    }
  } else {
    const lines = s.lines.length;
    if (s.big) centered(ctx, s.big, FRAME.y + FRAME.h * (lines ? 0.32 : 0.45), 120, WHITE);
    s.lines.forEach((line, i) => centered(ctx, line, FRAME.y + FRAME.h * 0.58 + i * 30, 22, WHITE, 500));
  }
  if (s.ask) {
    const y = FRAME.y + FRAME.h - 70;
    if (s.ask.prompt) centered(ctx, s.ask.prompt, y - 28, 16, MUTED, 500);
    ctx.fillStyle = "rgba(255,255,255,0.08)";
    ctx.strokeStyle = PRIMARY;
    ctx.beginPath();
    ctx.roundRect(FRAME.x + FRAME.w / 2 - 220, y - 4, 440, 44, 10);
    ctx.fill();
    ctx.stroke();
    centered(ctx, `${s.ask.text}▏`, y + 18, 22, WHITE, 500);
  }
  if (s.over !== null) {
    ctx.fillStyle = "rgba(20, 10, 36, 0.72)";
    ctx.fillRect(FRAME.x, FRAME.y, FRAME.w, FRAME.h);
    centered(ctx, s.over, FRAME.y + FRAME.h / 2, 30, WHITE);
  }
}
