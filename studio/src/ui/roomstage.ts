// Runs a room program in the browser the way Purple runs it on the laptop: a facsimile of the
// screen, the synth for notes, the core percussion clips, and the browser's voice for "say".
import { audioContext, clipToBuffer, playBuffer } from "../audio";
import { PURPLE, SYNTH_RATE, defaults, noteFrequency, parseNote, renderNote, Runner, type BaseName, type Host, type RoomProgram, type Rule } from "@sdk";
import { INSTRUMENTS } from "@sdk/purple/sounds";
import { draft } from "../state";
import { h } from "./dom";
import { frame, MUTED, PRIMARY, WHITE, type FrameColors, DEFAULT_COLORS, VIEWPORT_HEIGHT, VIEWPORT_WIDTH } from "./facsimile";

const DRUM_URLS = import.meta.glob("../../../packs/core-sounds/content/[0-9].ogg", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const DRUM_KEYS: Record<string, string> = PURPLE.room.drum_keys;
const DRUM_ALIASES: Record<string, string> = { hat: "hi-hat", hihat: "hi-hat", bell: "cowbell", wood: "woodblock", tri: "triangle", tamb: "tambourine" };

class Cancelled extends Error {}

export interface RoomScreen { background: string; shown: string; line: string[]; title: string }

export function roomFrame(screen: RoomScreen): HTMLCanvasElement {
  const colors: FrameColors = { background: DEFAULT_COLORS.background, surface: screen.background };
  return frame(colors, ({ cell, text, ctx, cw, ch }) => {
    cell(0, 0, screen.background, VIEWPORT_WIDTH, VIEWPORT_HEIGHT);
    text(`  ${screen.title}`, 0, 0, MUTED);
    if (screen.shown) {
      ctx.font = `600 ${cw * 6}px ui-monospace, Menlo, monospace`;
      ctx.fillStyle = WHITE;
      ctx.textAlign = "center";
      ctx.fillText(screen.shown, ((VIEWPORT_WIDTH + 2) / 2) * cw, (VIEWPORT_HEIGHT / 2 - 1) * ch);
      ctx.textAlign = "left";
    }
    const line = screen.line.join("  ");
    if (line) {
      ctx.font = `${cw * 2.2}px ui-monospace, Menlo, monospace`;
      ctx.fillStyle = WHITE;
      const maxWidth = (VIEWPORT_WIDTH - 6) * cw;
      const rows: string[] = [];
      let current = "";
      for (const word of line.split("  ")) {
        const next = current ? `${current}  ${word}` : word;
        if (ctx.measureText(next).width > maxWidth && current) { rows.push(current); current = word; } else current = next;
      }
      rows.push(current);
      rows.slice(-6).forEach((row, i) => { ctx.textAlign = "center"; ctx.fillText(row, ((VIEWPORT_WIDTH + 2) / 2) * cw, (VIEWPORT_HEIGHT - 8 + i * 1.2 + 1) * ch); });
      ctx.textAlign = "left";
    }
    const hint = "Press keys!   Esc to leave";
    text(hint, Math.floor((VIEWPORT_WIDTH - hint.length) / 2), VIEWPORT_HEIGHT - 1, PRIMARY);
  });
}

export class RoomStage implements Host {
  readonly element: HTMLElement;
  screen: RoomScreen;
  private runner: Runner;
  private generation = 0;
  private timers: number[] = [];
  private notes = new Map<string, AudioBuffer>();
  private drums = new Map<string, Promise<AudioBuffer | null>>();
  private canvasBox = h("div");

  constructor(program: RoomProgram) {
    this.screen = { background: program.background ?? "#1e1033", shown: "", line: [], title: program.title ?? program.name };
    this.runner = new Runner(program, this);
    this.element = h("div", { class: "roomstage", tabindex: 0, title: "Click here, then press keys" }, this.canvasBox);
    this.element.addEventListener("keydown", (e) => {
      const key = browserKey(e);
      if (!key) return;
      e.preventDefault();
      if (!e.repeat) this.press(key);
    });
    this.draw();
  }

  get program(): RoomProgram { return this.runner.program; }

  setProgram(program: RoomProgram): void {
    const vars = this.runner.vars;
    this.runner = new Runner(program, this);
    this.runner.vars = vars;
    this.screen.title = program.title ?? program.name;
    this.draw();
    this.startTimers();
  }

  start(): void {
    this.generation++;
    this.screen = { ...this.screen, shown: "", line: [], background: this.program.background ?? "#1e1033" };
    this.runner = new Runner(this.program, this);
    this.run(() => this.runner.fire("start"));
    this.startTimers();
  }

  stop(): void {
    this.generation++;
    this.timers.forEach((t) => clearInterval(t));
    this.timers = [];
    speechSynthesis?.cancel();
  }

  press(key: string): void {
    this.run(() => this.runner.fire("key", key));
  }

  private startTimers(): void {
    this.timers.forEach((t) => clearInterval(t));
    this.timers = this.runner.everyRules().map(([seconds, rule]: [number, Rule]) => window.setInterval(() => this.runner.runRule(rule).catch(() => {}), seconds * 1000));
  }

  // One run at a time, like Purple: a new key cancels a run still waiting.
  private run(go: () => Promise<void>): void {
    const mine = ++this.generation;
    go().catch((e) => { if (!(e instanceof Cancelled)) console.warn(e); });
    void mine;
  }

  private draw(): void {
    this.canvasBox.replaceChildren(roomFrame(this.screen));
  }

  show(text: string): void { this.screen.shown = text; this.draw(); }
  add(text: string): void { this.screen.line = [...this.screen.line, text].slice(-PURPLE.room.limits.line); this.draw(); }
  clear(): void { this.screen.shown = ""; this.screen.line = []; this.draw(); }
  background(color: string): void { this.screen.background = color; this.draw(); }

  say(text: string): void {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95;
    speechSynthesis.speak(u);
  }

  play(note: string, instrument: string): void {
    const parsed = parseNote(note);
    if (!parsed) return;
    const key = `${instrument}|${note}`;
    let buffer = this.notes.get(key);
    if (!buffer) {
      const inst = draft.instruments.find((i) => i.name === instrument);
      const base = inst?.base ?? ((INSTRUMENTS as readonly string[]).includes(instrument) ? (instrument as BaseName) : "marimba");
      const params = inst?.params ?? defaults(base);
      if (this.notes.size > 200) this.notes.clear();
      buffer = clipToBuffer({ samples: renderNote(base, params, noteFrequency(parsed[0], parsed[1])), rate: SYNTH_RATE });
      this.notes.set(key, buffer);
    }
    playBuffer(buffer);
  }

  drum(name: string): void {
    const canonical = DRUM_ALIASES[name.toLowerCase()] ?? name.toLowerCase();
    const digit = Object.entries(DRUM_KEYS).find(([, n]) => n === canonical)?.[0];
    if (!digit) return;
    if (!this.drums.has(digit)) {
      const url = Object.entries(DRUM_URLS).find(([path]) => path.endsWith(`/${digit}.ogg`))?.[1];
      this.drums.set(digit, url ? fetch(url).then((r) => r.arrayBuffer()).then((b) => audioContext().decodeAudioData(b)).catch(() => null) : Promise.resolve(null));
    }
    this.drums.get(digit)!.then((buffer) => buffer && playBuffer(buffer));
  }

  wait(seconds: number): Promise<void> {
    const mine = this.generation;
    return new Promise((resolve, reject) => setTimeout(() => (mine === this.generation ? resolve() : reject(new Cancelled())), seconds * 1000));
  }
}

export function browserKey(e: KeyboardEvent): string | null {
  const map: Record<string, string> = { " ": "space", Enter: "enter", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
  if (e.key in map) return map[e.key];
  return [...e.key].length === 1 ? e.key.toLowerCase() : null;
}
