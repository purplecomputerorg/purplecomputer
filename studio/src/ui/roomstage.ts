// The room on the right: a RoomHost drawn the way Purple's screen draws a family room
// (purple_tui/canvas/rooms/family_room.py), with the synth for notes, the core percussion clips,
// and the browser's voice for "say".
import { parseNote } from "@sdk";
import { roomTitle } from "@sdk/pack";
import { GRID_H, GRID_W, RoomHost, type Problem, type Scene } from "../rooms/host";
import { hush, playDrum, playNote, say } from "../sounds";
import { Playable } from "./playable";
import { MONO, P, SANS, drawScreen, fit, rounded, text } from "./screen";

const HEX = /^#[0-9a-fA-F]{6}$/;
// The room area inside the stage, as the laptop sizes it: 48 by 24 units of 24px.
const VP = { x: 107, y: 80, w: 1152, h: 576 };
const CELL = Math.min(VP.w / GRID_W, VP.h / GRID_H);

export interface StageHooks { problem(p: Problem | null): void; print(text: string): void }

export class RoomStage {
  readonly element: HTMLElement;
  private screen: Playable;
  private host: RoomHost;
  private problem: Problem | null = null;

  constructor(private name: string, hooks: StageHooks) {
    this.screen = new Playable((ctx) => draw(ctx, this.host.scene, roomTitle(this.name), this.problem), (key) => this.host.key(key), "then use the keyboard, like on Purple");
    this.element = this.screen.element;
    this.host = new RoomHost({
      redraw: () => this.screen.redraw(),
      say,
      play: (note, instrument) => {
        const parsed = parseNote(note);
        if (parsed) playNote(instrument, ...parsed);
      },
      drum: playDrum,
      print: hooks.print,
      problem: (p) => { this.problem = p; hooks.problem(p); },
    }, P.surface);
  }

  run(source: string): void {
    hush();
    this.host.start(source);
  }

  focus(): void {
    this.screen.focus();
  }

  // Esc and Tab never reach a room on Purple either.
  press(key: string): void {
    if (key !== "escape" && key !== "tab") this.host.key(key);
  }

  dispose(): void {
    this.host.dispose();
    this.screen.dispose();
    hush();
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
