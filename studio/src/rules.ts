// A room made of rules, "when this happens, do these", and the Python Purple runs for it. The rules are
// saved beside the Python so the room reopens as rules. Text goes into the code only as JSON string
// literals, which are valid Python strings, so nothing typed can become code.
import { PURPLE } from "@sdk";

export const BACKGROUNDS: [string, string][] = [
  ["night purple", "#1e1033"], ["deep purple", "#2a1845"], ["plum", "#3a1d63"], ["midnight", "#141024"],
  ["forest", "#173a2a"], ["sea", "#12304a"], ["sunset", "#4a1f2e"], ["sand", "#4a3b1f"],
];
export const DRUMS: string[] = PURPLE.room.drums;

export type When = { kind: "start" } | { kind: "key"; key: string } | { kind: "other" } | { kind: "every"; seconds: number };
// Something to show: words or an emoji, the key just pressed, one of the pack's pictures, or one picked at random.
export type Thing = { kind: "text" | "key" | "picture" | "pick"; value: string };
export type Action =
  | { kind: "show"; thing: Thing }
  | { kind: "put"; thing: Thing; x: number; y: number }
  | { kind: "write" | "say"; text: string }
  | { kind: "play"; note: string; instrument: string }
  | { kind: "drum"; name: string }
  | { kind: "sound"; name: string }
  | { kind: "background"; color: string }
  | { kind: "clear" };
export interface Rule { when: When; actions: Action[] }

const text = (value: string): Thing => ({ kind: "text", value });

export const ACTIONS: Record<Action["kind"], { label: string; fresh: () => Action }> = {
  show: { label: "show big", fresh: () => ({ kind: "show", thing: text("⭐") }) },
  put: { label: "put on the grid", fresh: () => ({ kind: "put", thing: text("🌼"), x: 12, y: 6 }) },
  write: { label: "write a line", fresh: () => ({ kind: "write", text: "Hello!" }) },
  play: { label: "play a note", fresh: () => ({ kind: "play", note: "C4", instrument: "marimba" }) },
  drum: { label: "hit a drum", fresh: () => ({ kind: "drum", name: DRUMS[0] }) },
  sound: { label: "play my sound", fresh: () => ({ kind: "sound", name: "" }) },
  say: { label: "say", fresh: () => ({ kind: "say", text: "hello" }) },
  background: { label: "make the background", fresh: () => ({ kind: "background", color: BACKGROUNDS[0][1] }) },
  clear: { label: "clear the screen", fresh: () => ({ kind: "clear" }) },
};

export const WHENS: Record<When["kind"], { label: string; fresh: () => When }> = {
  start: { label: "the room opens", fresh: () => ({ kind: "start" }) },
  key: { label: "this key is pressed", fresh: () => ({ kind: "key", key: "c" }) },
  other: { label: "any other key is pressed", fresh: () => ({ kind: "other" }) },
  every: { label: "every few seconds", fresh: () => ({ kind: "every", seconds: 2 }) },
};

// A wave when the room opens, and every key shows itself.
export const blankRules = (): Rule[] => [
  { when: { kind: "start" }, actions: [{ kind: "show", thing: text("👋") }] },
  { when: { kind: "other" }, actions: [{ kind: "show", thing: { kind: "key", value: "" } }] },
];

const lit = (s: string) => JSON.stringify(s);
const INDENT = "    ";
const indent = (lines: string[]) => lines.map((l) => INDENT + l);
const list = (v: string) => v.split(",").map((s) => s.trim()).filter(Boolean);

function thing(t: Thing, inKey: boolean): string {
  if (t.kind === "key") return inKey ? "key" : '""';
  if (t.kind === "picture") return t.value ? `picture(${lit(t.value)})` : '""';
  if (t.kind === "pick") return `random.choice(${JSON.stringify(list(t.value).length ? list(t.value) : [""])})`;
  return lit(t.value);
}

function line(a: Action, inKey: boolean): string | null {
  switch (a.kind) {
    case "show": return `show(${thing(a.thing, inKey)})`;
    case "put": return `grid.set(${Math.trunc(a.x) || 0}, ${Math.trunc(a.y) || 0}, ${thing(a.thing, inKey)})`;
    case "write": case "say": return a.text.trim() ? `${a.kind}(${lit(a.text)})` : null;
    case "play": return `play(${lit(a.note.trim() || "C4")}, ${lit(a.instrument)})`;
    case "drum": return `drum(${lit(a.name)})`;
    case "sound": return a.name ? `sound(${lit(a.name)})` : null;
    case "background": return `background(${lit(a.color)})`;
    case "clear": return "clear()";
  }
}

const lines = (actions: Action[], inKey: boolean) => actions.map((a) => line(a, inKey)).filter((l): l is string => !!l);
const block = (actions: Action[], inKey = false) => indent(lines(actions, inKey).length ? lines(actions, inKey) : ["pass"]);

export function rulesSource(rules: Rule[]): string {
  const byKey = new Map<string, Action[]>();
  const other: Action[] = [];
  const start: Action[] = [];
  const timers: string[] = [];
  for (const r of rules) {
    if (r.when.kind === "key") byKey.set(r.when.key, [...(byKey.get(r.when.key) ?? []), ...r.actions]);
    else if (r.when.kind === "other") other.push(...r.actions);
    else if (r.when.kind === "start") start.push(...r.actions);
    else {
      const fn = `every_${timers.length + 1}`;
      timers.push([`def ${fn}():`, ...block(r.actions), "", "", `every(${Math.max(0.1, Number(r.when.seconds) || 1)}, ${fn})`].join("\n"));
    }
  }
  const branches = [...byKey].flatMap(([k, actions], i) => [`${i ? "elif" : "if"} key == ${lit(k)}:`, ...block(actions, true)]);
  const otherwise = !other.length ? [] : branches.length ? ["else:", ...block(other, true)] : lines(other, true);
  const onKey = branches.length || otherwise.length ? ["def on_key(key):", ...indent([...branches, ...otherwise])].join("\n") : "";
  const top = lines(start, false).join("\n");
  const source = [onKey, ...timers, top].filter(Boolean).join("\n\n\n");
  const imports = source.includes("random.") ? "from purple import *\nimport random" : "from purple import *";
  return `${imports}\n\n# Made with rules in Purple Studio.\n${source ? `\n${source}\n` : ""}`;
}
