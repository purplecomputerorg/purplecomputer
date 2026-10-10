// The room on the right: a RoomHost drawn the way Purple's screen draws a family room
// (purple_tui/canvas/rooms/family_room.py), with the synth for notes, the core percussion clips,
// and the browser's voice for "say".
import { PURPLE, SYNTH_RATE, defaults, noteFrequency, parseNote, renderNote, type BaseName } from "@sdk";
import { roomTitle } from "@sdk/pack";
import { INSTRUMENTS } from "@sdk/purple/sounds";
import { audioContext, clipToBuffer, playBuffer } from "../audio";
import { GRID_H, GRID_W, RoomHost, type Problem, type Scene } from "../rooms/host";
import { draft } from "../state";
import { h } from "./dom";
import { MONO, P, SANS, ScreenCanvas, drawScreen, fit, rounded, text } from "./screen";

const DRUM_URLS = import.meta.glob("../../../packs/core-sounds/content/[0-9].ogg", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const DRUM_KEYS: Record<string, string> = PURPLE.room.drum_keys;
const HEX = /^#[0-9a-fA-F]{6}$/;
// The room area inside the stage, as the laptop sizes it: 48 by 24 units of 24px.
const VP = { x: 107, y: 80, w: 1152, h: 576 };
const CELL = Math.min(VP.w / GRID_W, VP.h / GRID_H);

export function browserKey(e: KeyboardEvent): string | null {
  const map: Record<string, string> = { " ": "space", Enter: "enter", Backspace: "backspace", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
  if (e.key in map) return map[e.key];
  return [...e.key].length === 1 ? e.key.toLowerCase() : null;
}

export interface StageHooks { problem(p: Problem | null): void; print(text: string): void }

export class RoomStage {
  readonly element: HTMLElement;
  private screen: ScreenCanvas;
  private host: RoomHost;
  private problem: Problem | null = null;
  private notes = new Map<string, AudioBuffer>();
  private drums = new Map<string, Promise<AudioBuffer | null>>();

  constructor(private name: string, hooks: StageHooks) {
    this.screen = new ScreenCanvas((ctx) => draw(ctx, this.host.scene, roomTitle(this.name), this.problem), true);
    this.element = this.screen.element;
    this.element.classList.add("roomstage");
    this.element.tabIndex = 0;
    // The hint covers the room whenever it isn't getting keys; CSS hides it on focus.
    this.element.append(h("div", { class: "roomstage-hint" }, h("strong", {}, "Click to play"), h("span", {}, "then use the keyboard, like on Purple")));
    this.host = new RoomHost({
      redraw: () => this.screen.redraw(),
      say: (t) => this.say(t),
      play: (n, i) => this.play(n, i),
      drum: (n) => this.drum(n),
      print: hooks.print,
      problem: (p) => { this.problem = p; hooks.problem(p); },
    }, P.surface);
    this.element.addEventListener("keydown", (e) => {
      const key = browserKey(e);
      if (!key || e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      if (!e.repeat || ["up", "down", "left", "right", "backspace"].includes(key)) this.host.key(key);
    });
  }

  run(source: string): void {
    speechSynthesis?.cancel();
    this.host.start(source);
  }

  focus(): void {
    this.element.focus({ preventScroll: true });
  }

  dispose(): void {
    this.host.dispose();
    this.screen.dispose();
    speechSynthesis?.cancel();
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

const mid = VP.x + VP.w / 2;

function draw(ctx: CanvasRenderingContext2D, s: Scene, title: string, problem: Problem | null): void {
  drawScreen(ctx, { title: `⌂ ${title}`, right: "Esc leaves", stage: problem ? P.surface : s.background }, () => {
    if (problem?.setup) return card(ctx, "Can't preview here", problem.text);
    if (problem) return card(ctx, "This room needs fixing", "A grown-up can fix it in Purple Studio.  Esc goes back.",
      `(Technical: ${problem.text}${problem.line ? ` (line ${problem.line})` : ""})`);
    if (s.cells.size) drawGrid(ctx, s);
    else drawWords(ctx, s);
    drawFooter(ctx, s);
  });
}

function drawGrid(ctx: CanvasRenderingContext2D, s: Scene): void {
  for (const [at, thing] of s.cells) {
    const [x, y] = at.split(",").map(Number);
    const px = VP.x + x * CELL;
    const py = VP.y + y * CELL;
    if (HEX.test(thing)) rounded(ctx, px + 1, py + 1, CELL - 2, CELL - 2, CELL / 8, thing);
    else text(ctx, thing, px + CELL / 2, py + CELL / 2, CELL * 0.78, P.text, "center", SANS);
  }
}

function drawWords(ctx: CanvasRenderingContext2D, s: Scene): void {
  if (s.big) text(ctx, s.big, mid, VP.y + VP.h * 0.36, fit(ctx, s.big, Math.round(VP.h * 0.24), VP.w * 0.9), P.text, "center", SANS, 600);
  const px = VP.h * 0.055;
  s.lines.forEach((line, i) => text(ctx, line, mid, VP.y + VP.h * 0.6 + i * px * 1.35 + px / 2, px, P.text, "center", SANS));
}

function drawFooter(ctx: CanvasRenderingContext2D, s: Scene): void {
  const px = VP.h * 0.05;
  const y = VP.y + VP.h - px * 2.2 + px / 2;
  if (s.ask) {
    if (s.ask.prompt) text(ctx, s.ask.prompt, VP.x + px, y - px * 1.5, px, P.muted, "left", SANS);
    const w = text(ctx, "Answer →", VP.x + px, y, px, P.accent, "left", MONO, 700);
    const tw = text(ctx, s.ask.text, VP.x + px + w + px / 2, y, px, P.text, "left", MONO);
    ctx.fillStyle = P.caret;
    ctx.fillRect(VP.x + px + w + px / 2 + tw, y - px * 0.5, px * 0.55, px * 1.05);
  } else if (s.over !== null) {
    text(ctx, s.over, mid, y, px, P.accent, "center", MONO, 700);
  }
}

function card(ctx: CanvasRenderingContext2D, title: string, line: string, technical = ""): void {
  const px = VP.h * 0.06;
  const cy = VP.y + VP.h / 2;
  text(ctx, title, mid, cy - px * 2, fit(ctx, title, px * 1.4, VP.w * 0.9, MONO, 700), P.text, "center", MONO, 700);
  text(ctx, line, mid, cy, fit(ctx, line, px, VP.w * 0.92, SANS, 400), P.muted, "center", SANS);
  if (technical) text(ctx, technical, mid, cy + px * 1.8, fit(ctx, technical, px * 0.7, VP.w * 0.92, MONO, 400), P.dim, "center", MONO);
}
