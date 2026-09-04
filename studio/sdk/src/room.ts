// The room language, as purple_tui/room_program.py runs it. tests/room.test.ts holds this
// interpreter to the Python one through the trace in tests/room-golden.json, so a room a
// parent tries in Studio behaves the same on the laptop. Keep the two in step.
import exported from "./purple/export.json";

const room = exported.room;
export const ROOM_FORMAT: number = room.format;
export const EVENTS = room.events as readonly string[];
export const ACTIONS = room.actions as readonly string[];
export const MATH_OPS = room.math_ops as readonly string[];
export const COMPARE_OPS = room.compare_ops as readonly string[];
export const SPECIAL_KEYS = room.special_keys as readonly string[];
export const DRUMS = room.drums as readonly string[];
export const LIMITS = room.limits;

export type Value = number | string;
export type Expr = number | string | { var: string } | { key: true } | { pick: Expr[] } | { join: Expr[] } | { random: { from: Expr; to: Expr } } | { math: string; a: Expr; b: Expr };
export type Test = { compare: string; a: Expr; b: Expr } | { and: Test[] } | { or: Test[] } | { not: Test };
export type RoomEvent = { event: "start" } | { event: "key"; key: string } | { event: "any_key" } | { event: "every"; seconds: number };
export type Action =
  | { do: "show" | "add" | "say"; text: Expr }
  | { do: "play"; note: Expr; instrument?: string }
  | { do: "drum"; name: string }
  | { do: "clear" }
  | { do: "background"; color: string }
  | { do: "wait"; seconds: Expr }
  | { do: "set"; var: string; value: Expr }
  | { do: "change"; var: string; by: Expr }
  | { do: "if"; test: Test; then?: Action[]; else?: Action[] }
  | { do: "repeat"; times: Expr; body: Action[] };
export interface Rule { when: RoomEvent; do: Action[] }
export interface RoomProgram { name: string; title?: string; background?: string; format?: number; rules: Rule[] }

export interface Host {
  show(text: string): void;
  add(text: string): void;
  say(text: string): void;
  play(note: string, instrument: string): void;
  drum(name: string): void;
  clear(): void;
  background(color: string): void;
  wait(seconds: number): Promise<void>;
}

export class RoomError extends Error {}

const NOTE = /^([A-Ga-g])(#?)(\d)$/;
const HEX = /^#[0-9a-fA-F]{6}$/;
const NAME = /^[a-z0-9][a-z0-9-]{0,39}$/;

export function parseNote(text: string): [string, number] | null {
  const m = NOTE.exec(text.trim());
  return m ? [m[1].toUpperCase() + m[2], Number(m[3])] : null;
}

const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
function fail(msg: string): never {
  throw new RoomError(msg);
}

export function parse(data: unknown): RoomProgram {
  if (!isObject(data)) fail("a room is a JSON object");
  const d = data as Record<string, unknown>;
  if (typeof d.name !== "string" || !NAME.test(d.name)) fail("name must be lowercase letters, digits, and dashes");
  if ((d.format ?? ROOM_FORMAT) !== ROOM_FORMAT) fail(`format must be ${ROOM_FORMAT}`);
  const title = d.title ?? d.name;
  if (typeof title !== "string" || !title.trim() || title.length > 40) fail("title must be a short string");
  if (d.background != null && !(typeof d.background === "string" && HEX.test(d.background))) fail("background must be #rrggbb");
  if (!Array.isArray(d.rules) || d.rules.length > 200) fail("rules must be a list");
  d.rules.forEach((rule, i) => {
    const where = `rule ${i + 1}`;
    if (!isObject(rule) || !isObject(rule.when) || !Array.isArray(rule.do)) fail(`${where}: needs a when and a do list`);
    checkEvent(rule.when as Record<string, unknown>, where);
    checkActions(rule.do as unknown[], where, 0);
  });
  return d as unknown as RoomProgram;
}

function checkEvent(when: Record<string, unknown>, where: string) {
  if (!EVENTS.includes(when.event as string)) fail(`${where}: event must be one of ${EVENTS.join(", ")}`);
  if (when.event === "key") {
    const key = when.key;
    if (typeof key !== "string" || !([...key].length === 1 || SPECIAL_KEYS.includes(key))) fail(`${where}: key must be one character or one of ${SPECIAL_KEYS.join(", ")}`);
  }
  if (when.event === "every") {
    const s = when.seconds;
    if (!isNumber(s) || s < LIMITS.every_min_seconds || s > 60) fail(`${where}: every needs seconds between ${LIMITS.every_min_seconds} and 60`);
  }
}

function checkActions(actions: unknown[], where: string, depth: number) {
  if (depth > LIMITS.depth) fail(`${where}: nested too deep`);
  if (actions.length > LIMITS.steps) fail(`${where}: too many actions`);
  for (const a of actions) {
    if (!isObject(a) || !ACTIONS.includes(a.do as string)) fail(`${where}: each action needs a do that is one of ${ACTIONS.join(", ")}`);
    const kind = a.do as string;
    if (kind === "show" || kind === "add" || kind === "say") checkValue(a.text, where);
    else if (kind === "play") {
      checkValue(a.note, where);
      if (typeof a.note === "string" && !parseNote(a.note)) fail(`${where}: note must look like C4 or F#3`);
      if ("instrument" in a && typeof a.instrument !== "string") fail(`${where}: instrument must be a name`);
    } else if (kind === "drum") {
      if (typeof a.name !== "string") fail(`${where}: drum needs a name`);
    } else if (kind === "background") {
      if (!(typeof a.color === "string" && HEX.test(a.color))) fail(`${where}: background color must be #rrggbb`);
    } else if (kind === "wait") checkValue(a.seconds, where);
    else if (kind === "set" || kind === "change") {
      if (typeof a.var !== "string" || !a.var) fail(`${where}: ${kind} needs a var name`);
      checkValue(kind === "set" ? a.value : a.by, where);
    } else if (kind === "if") {
      checkTest(a.test, where);
      for (const branch of ["then", "else"] as const) {
        if (branch in a) {
          if (!Array.isArray(a[branch])) fail(`${where}: ${branch} must be a list`);
          checkActions(a[branch] as unknown[], where, depth + 1);
        }
      }
    } else if (kind === "repeat") {
      checkValue(a.times, where);
      if (!Array.isArray(a.body)) fail(`${where}: repeat needs a body list`);
      checkActions(a.body, where, depth + 1);
    }
  }
}

function checkValue(value: unknown, where: string) {
  if (isNumber(value) || typeof value === "string") return;
  if (!isObject(value) || Object.keys(value).length === 0) fail(`${where}: expected a number, text, or a value block`);
  if ("var" in value) {
    if (typeof value.var !== "string") fail(`${where}: var needs a name`);
  } else if ("key" in value) {
    return;
  } else if ("pick" in value || "join" in value) {
    const items = value.pick ?? value.join;
    if (!Array.isArray(items) || !items.length) fail(`${where}: pick and join need a non-empty list`);
    for (const item of items as unknown[]) checkValue(item, where);
  } else if ("random" in value) {
    const r = value.random;
    if (!isObject(r)) fail(`${where}: random needs from and to`);
    checkValue((r as Record<string, unknown>).from, where);
    checkValue((r as Record<string, unknown>).to, where);
  } else if ("math" in value) {
    if (!MATH_OPS.includes(value.math as string)) fail(`${where}: math must be one of ${MATH_OPS.join(" ")}`);
    checkValue(value.a, where);
    checkValue(value.b, where);
  } else fail(`${where}: unknown value block ${JSON.stringify(Object.keys(value).sort())}`);
}

function checkTest(test: unknown, where: string) {
  if (!isObject(test)) fail(`${where}: if needs a test`);
  const t = test as Record<string, unknown>;
  if ("compare" in t) {
    if (!COMPARE_OPS.includes(t.compare as string)) fail(`${where}: compare must be one of ${COMPARE_OPS.join(" ")}`);
    checkValue(t.a, where);
    checkValue(t.b, where);
  } else if ("and" in t || "or" in t) {
    const items = t.and ?? t.or;
    if (!Array.isArray(items)) fail(`${where}: and/or need a list`);
    for (const item of items as unknown[]) checkTest(item, where);
  } else if ("not" in t) checkTest(t.not, where);
  else fail(`${where}: unknown test ${JSON.stringify(Object.keys(t).sort())}`);
}

// Numbers read the way a kid would write them: 3, not 3.0; 2.5 stays 2.5.
export function formatValue(v: Value): string {
  if (typeof v === "string") return v;
  if (Number.isInteger(v) && Math.abs(v) < 1e15) return String(v);
  return v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

export function toNumber(v: Value): number {
  if (typeof v === "string") {
    const n = v.trim() === "" ? NaN : Number(v.trim());
    return Number.isFinite(n) ? n : 0;
  }
  return v;
}

const codePoints = (s: string, n: number) => Array.from(s).slice(0, n).join("");

export class Runner {
  vars: Record<string, Value> = {};
  private key = "";
  private steps = 0;

  constructor(public program: RoomProgram, public host: Host, public rng: () => number = Math.random) {}

  rulesFor(event: string, key = ""): Rule[] {
    key = key.toLowerCase();
    return this.program.rules.filter((r) => r.when.event === event && (event !== "key" || (r.when as { key: string }).key.toLowerCase() === key));
  }

  everyRules(): [number, Rule][] {
    return this.program.rules.filter((r) => r.when.event === "every").map((r) => [(r.when as { seconds: number }).seconds, r]);
  }

  async fire(event: string, key = ""): Promise<void> {
    this.key = key.toLowerCase();
    const rules = this.rulesFor(event, key);
    if (event === "key") rules.push(...this.rulesFor("any_key"));
    this.steps = 0;
    for (const rule of rules) await this.run(rule.do, 0);
  }

  async runRule(rule: Rule): Promise<void> {
    this.steps = 0;
    await this.run(rule.do, 0);
  }

  private async run(actions: Action[], depth: number): Promise<void> {
    if (depth > LIMITS.depth) return;
    for (const action of actions) {
      this.steps += 1;
      if (this.steps > LIMITS.steps) return;
      await this.doAction(action, depth);
    }
  }

  private async doAction(action: Action, depth: number): Promise<void> {
    switch (action.do) {
      case "show": case "add": case "say":
        this.host[action.do](this.text(action.text));
        return;
      case "play": {
        const note = this.text(action.note);
        if (parseNote(note)) this.host.play(note, action.instrument ?? "marimba");
        return;
      }
      case "drum": this.host.drum(action.name); return;
      case "clear": this.host.clear(); return;
      case "background": this.host.background(action.color); return;
      case "wait": await this.host.wait(Math.min(Math.max(0, toNumber(this.eval(action.seconds))), LIMITS.wait_seconds)); return;
      case "set": this.vars[action.var] = this.eval(action.value); return;
      case "change": this.vars[action.var] = toNumber(this.vars[action.var] ?? 0) + toNumber(this.eval(action.by)); return;
      case "if": await this.run((this.test(action.test) ? action.then : action.else) ?? [], depth + 1); return;
      case "repeat": {
        const times = Math.trunc(Math.min(Math.max(0, toNumber(this.eval(action.times))), LIMITS.repeat));
        for (let i = 0; i < times; i++) {
          if (this.steps > LIMITS.steps) return;
          await this.run(action.body, depth + 1);
        }
      }
    }
  }

  text(value: Expr): string {
    return codePoints(formatValue(this.eval(value)), LIMITS.text);
  }

  eval(value: Expr): Value {
    if (typeof value === "string") return value;
    if (typeof value === "number") return value;
    if ("var" in value) return this.vars[value.var] ?? 0;
    if ("key" in value) return this.key;
    if ("pick" in value) return this.eval(value.pick[Math.floor(this.rng() * value.pick.length) % value.pick.length]);
    if ("join" in value) return value.join.map((item) => formatValue(this.eval(item))).join("");
    if ("random" in value) {
      let lo = Math.floor(toNumber(this.eval(value.random.from)));
      let hi = Math.floor(toNumber(this.eval(value.random.to)));
      if (hi < lo) [lo, hi] = [hi, lo];
      return lo + (Math.floor(this.rng() * (hi - lo + 1)) % (hi - lo + 1));
    }
    const a = toNumber(this.eval(value.a));
    const b = toNumber(this.eval(value.b));
    switch (value.math) {
      case "+": return a + b;
      case "-": return a - b;
      case "*": return a * b;
      default: return b !== 0 ? a / b : 0;
    }
  }

  test(test: Test): boolean {
    if ("compare" in test) {
      let a = this.eval(test.a);
      let b = this.eval(test.b);
      if (typeof a === "string" || typeof b === "string") {
        a = formatValue(a);
        b = formatValue(b);
      }
      switch (test.compare) {
        case "=": return a === b;
        case "!=": return a !== b;
        case "<": return a < b;
        default: return a > b;
      }
    }
    if ("and" in test) return test.and.every((t) => this.test(t));
    if ("or" in test) return test.or.some((t) => this.test(t));
    return !this.test(test.not);
  }
}

// Records every host call, for tests and parity with Purple's TraceHost.
export class TraceHost implements Host {
  trace: unknown[][] = [];
  show(text: string) { this.trace.push(["show", text]); }
  add(text: string) { this.trace.push(["add", text]); }
  say(text: string) { this.trace.push(["say", text]); }
  play(note: string, instrument: string) { this.trace.push(["play", note, instrument]); }
  drum(name: string) { this.trace.push(["drum", name]); }
  clear() { this.trace.push(["clear"]); }
  background(color: string) { this.trace.push(["background", color]); }
  async wait(seconds: number) { this.trace.push(["wait", seconds]); }
}
