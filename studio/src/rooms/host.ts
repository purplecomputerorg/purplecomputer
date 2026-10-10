// Runs a room the way Purple does on the laptop (guides/family-rooms.md): the room is a guest in
// its own worker and only asks for things; this side checks every message, keeps the time, and
// ends a room that hangs, floods, or sends something it should not.
import { PURPLE } from "@sdk";
import { newChannel, put } from "./channel";

export const [GRID_W, GRID_H] = PURPLE.room.grid as [number, number];
const STUCK_MS = 3000;
const MAX_MESSAGES_PER_EVENT = 2000;
const MAX_BACKGROUNDS_PER_SECOND = 4;
const MAX_QUEUED = 10;
const LINES_KEPT = 5;
const TEXT_MAX = 200;
const HEX = /^#[0-9a-fA-F]{6}$/;

export interface Scene {
  background: string;
  big: string;
  lines: string[];
  cells: Map<string, string>;
  ask: { prompt: string; text: string } | null;
  over: string | null;
}

// setup: the preview can't run here at all, as opposed to a problem in the room.
export interface Problem { text: string; line: number | null; setup?: boolean }

// Rooms block on shared memory (purple.ask), which browsers only allow on a cross-origin isolated
// page, and that needs a secure context: https, or http on localhost.
export const NOT_ISOLATED: Problem = {
  text: "The preview needs a secure page. Open Studio at its https:// address, or at http://localhost on the computer running it.",
  line: null,
  setup: true,
};

export interface Effects {
  redraw(): void;
  say(text: string): void;
  play(note: string, instrument: string): void;
  drum(name: string): void;
  print(text: string): void;
  problem(p: Problem | null): void;
}

type Msg = Record<string, unknown>;
const str = (v: unknown) => String(v ?? "").slice(0, TEXT_MAX);
const int = (v: unknown, max: number) => Number.isInteger(v) && (v as number) >= 0 && (v as number) < max;

interface Guest { worker: Worker; channel: SharedArrayBuffer }

function spawn(): Guest {
  const worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
  const channel = newChannel();
  worker.postMessage({ type: "init", indexURL: new URL("pyodide/", document.baseURI).href, channel });
  return { worker, channel };
}

export const emptyScene = (background: string): Scene => ({ background, big: "", lines: [], cells: new Map(), ask: null, over: null });

export class RoomHost {
  scene: Scene;
  private guest: Guest | null = null;
  private spare: Guest | null = null;
  private source = "";
  private queue: string[] = [];
  private outstanding = 0;
  private messages = 0;
  private stuck = 0;
  private pump = 0;
  private timers = new Map<number, number>();
  private backgrounds: number[] = [];

  constructor(private fx: Effects, private defaultBackground: string) {
    this.scene = emptyScene(defaultBackground);
  }

  start(source: string): void {
    this.stop();
    this.source = source;
    this.scene = emptyScene(this.defaultBackground);
    this.fx.problem(globalThis.crossOriginIsolated ? null : NOT_ISOLATED);
    this.fx.redraw();
    if (!globalThis.crossOriginIsolated) return;
    this.guest = this.spare ?? spawn();
    this.spare = spawn();
    this.guest.worker.onmessage = (e: MessageEvent<string>) => this.receive(e.data);
    this.guest.worker.postMessage({ type: "run", source });
  }

  stop(): void {
    this.guest?.worker.terminate();
    this.guest = null;
    this.timers.forEach((t) => clearInterval(t));
    this.timers.clear();
    this.queue = [];
    this.outstanding = 0;
    clearTimeout(this.stuck);
    clearTimeout(this.pump);
  }

  dispose(): void {
    this.stop();
    this.spare?.worker.terminate();
    this.spare = null;
  }

  key(key: string): void {
    if (!this.guest) return;
    if (this.scene.over !== null) return this.start(this.source);
    const ask = this.scene.ask;
    if (ask) return this.typeAnswer(ask, key);
    if (this.outstanding >= MAX_QUEUED) return;
    this.send({ ev: "key", key });
  }

  private typeAnswer(ask: { text: string }, key: string): void {
    if (key === "enter") {
      this.scene.ask = null;
      this.send({ ev: "answer", text: ask.text }, false);
      this.outstanding++;
      this.arm();
    } else if (key === "backspace") ask.text = ask.text.slice(0, -1);
    else if (key === "space") ask.text += " ";
    else if ([...key].length === 1) ask.text = (ask.text + key).slice(0, TEXT_MAX);
    this.fx.redraw();
  }

  private send(msg: Msg, counts = true): void {
    if (counts) {
      this.outstanding++;
      this.arm();
    }
    this.queue.push(JSON.stringify(msg));
    this.flush();
  }

  private flush(): void {
    clearTimeout(this.pump);
    while (this.guest && this.queue.length && put(this.guest.channel, this.queue[0])) this.queue.shift();
    if (this.queue.length) this.pump = window.setTimeout(() => this.flush(), 5);
  }

  private arm(): void {
    clearTimeout(this.stuck);
    this.stuck = window.setTimeout(() => this.fail({ text: "This room got stuck: it was still busy after 3 seconds. Is there a loop that never ends?", line: null }), STUCK_MS);
  }

  private fail(p: Problem): void {
    this.stop();
    this.fx.problem(p);
    this.fx.redraw();
  }

  private receive(raw: string): void {
    let msg: Msg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return this.fail({ text: "The room sent something Purple does not understand.", line: null });
    }
    if (++this.messages > MAX_MESSAGES_PER_EVENT) return this.fail({ text: "The room asked for too many things at once.", line: null });
    if (!this.apply(msg)) return this.fail({ text: `The room sent something Purple does not understand: ${str(msg.cmd)}`, line: null });
    this.flush();
    this.fx.redraw();
  }

  // False for anything outside the protocol; the room is ended for it.
  private apply(m: Msg): boolean {
    const s = this.scene;
    switch (m.cmd) {
      case "ended": return true;
      case "started": this.outstanding = 1; this.messages = 0; this.arm(); return true;
      case "done":
        this.messages = 0;
        this.outstanding = Math.max(0, this.outstanding - 1);
        if (this.outstanding) this.arm(); else clearTimeout(this.stuck);
        return true;
      case "print": this.fx.print(str(m.text)); return true;
      case "error": this.fail({ text: str(m.text), line: Number.isInteger(m.line) ? (m.line as number) : null }); return true;
      case "show": s.big = str(m.text); return true;
      case "write": s.lines = [...s.lines, str(m.text)].slice(-LINES_KEPT); return true;
      case "clear": s.big = ""; s.lines = []; s.cells.clear(); return true;
      case "grid_clear": s.cells.clear(); return true;
      case "background": {
        if (typeof m.color !== "string" || !HEX.test(m.color)) return false;
        const now = performance.now();
        this.backgrounds = this.backgrounds.filter((t) => now - t < 1000);
        if (this.backgrounds.length < MAX_BACKGROUNDS_PER_SECOND) {
          this.backgrounds.push(now);
          s.background = m.color;
        }
        return true;
      }
      case "cell": {
        if (!int(m.x, GRID_W) || !int(m.y, GRID_H)) return false;
        const at = `${m.x},${m.y}`;
        if (m.thing === null) s.cells.delete(at); else s.cells.set(at, str(m.thing));
        return true;
      }
      case "say": this.fx.say(str(m.text)); return true;
      case "play": this.fx.play(str(m.note), str(m.instrument)); return true;
      case "drum": this.fx.drum(str(m.name)); return true;
      case "every": case "after": {
        if (!Number.isInteger(m.id) || typeof m.seconds !== "number") return false;
        const id = m.id as number;
        const ms = Math.max(100, m.seconds * 1000);
        clearInterval(this.timers.get(id));
        this.timers.set(id, m.cmd === "every"
          ? window.setInterval(() => this.tick(id), ms)
          : window.setTimeout(() => { this.timers.delete(id); this.tick(id); }, ms));
        return true;
      }
      case "stop": clearInterval(this.timers.get(m.id as number)); this.timers.delete(m.id as number); return true;
      case "ask":
        clearTimeout(this.stuck);
        this.messages = 0;
        this.outstanding = Math.max(0, this.outstanding - 1);
        s.ask = { prompt: str(m.prompt), text: "" };
        return true;
      case "game_over":
        this.timers.forEach((t) => clearInterval(t));
        this.timers.clear();
        s.over = str(m.text);
        return true;
      default: return false;
    }
  }

  // A tick only goes in when the room is idle, so a slow room skips beats instead of piling them up.
  private tick(id: number): void {
    if (this.guest && !this.outstanding && !this.scene.ask && this.scene.over === null) this.send({ ev: "tick", id });
  }
}
