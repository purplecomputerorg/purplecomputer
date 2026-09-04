// Program -> Blockly workspace state, and the sample room. Pure: no Blockly, no DOM, so the
// Python bridge and tests can use it in Node.
import type { Action, Expr, RoomProgram, Rule, Test } from "@sdk/room";

type State = Record<string, unknown>;
const block = (type: string, fields: Record<string, unknown> = {}, inputs: Record<string, State> = {}): State => ({ type, fields, inputs });
const value = (s: State) => ({ block: s });

function exprState(e: Expr): State {
  if (typeof e === "string") return block("text", { TEXT: e });
  if (typeof e === "number") return block("math_number", { NUM: e });
  if ("var" in e) return block("purple_var", { VAR: e.var });
  if ("key" in e) return block("purple_key");
  if ("pick" in e) return block("purple_pick", { LIST: e.pick.map((i) => (typeof i === "string" ? i : JSON.stringify(i))).join(", ") });
  if ("join" in e) {
    const [a, ...rest] = e.join;
    const b: Expr = rest.length > 1 ? { join: rest } : (rest[0] ?? "");
    return block("purple_join", {}, { A: value(exprState(a ?? "")), B: value(exprState(b)) });
  }
  if ("random" in e) return block("purple_random", {}, { FROM: value(exprState(e.random.from)), TO: value(exprState(e.random.to)) });
  return block("purple_math", { OP: e.math }, { A: value(exprState(e.a)), B: value(exprState(e.b)) });
}

const TRUE: Test = { compare: "=", a: 1, b: 1 };

function testState(t: Test): State {
  if ("compare" in t) return block("purple_compare", { OP: t.compare }, { A: value(exprState(t.a)), B: value(exprState(t.b)) });
  if ("not" in t) return block("purple_not", {}, { A: value(testState(t.not)) });
  const op = "and" in t ? "and" : "or";
  const [a, ...rest] = "and" in t ? t.and : t.or;
  const b: Test = rest.length > 1 ? ({ [op]: rest } as Test) : (rest[0] ?? TRUE);
  return block("purple_logic", { OP: op }, { A: value(testState(a ?? TRUE)), B: value(testState(b)) });
}

function chain(items: Action[]): State | undefined {
  let next: State | undefined;
  for (let i = items.length - 1; i >= 0; i--) {
    const s = actionState(items[i]);
    if (next) s.next = { block: next };
    next = s;
  }
  return next;
}

const withBody = (s: State, name: string, body: Action[]): State => {
  const first = chain(body);
  if (first) (s.inputs as Record<string, State>)[name] = { block: first };
  return s;
};

function actionState(a: Action): State {
  switch (a.do) {
    case "show": case "add": case "say": return block(`purple_${a.do}`, {}, { TEXT: value(exprState(a.text)) });
    case "play": return block("purple_play", { INSTRUMENT: a.instrument ?? "marimba" }, { NOTE: value(exprState(a.note)) });
    case "drum": return block("purple_drum", { NAME: a.name });
    case "clear": return block("purple_clear");
    case "background": return block("purple_background", { COLOR: a.color });
    case "wait": return block("purple_wait", {}, { SECONDS: value(exprState(a.seconds)) });
    case "set": return block("purple_set", { VAR: a.var }, { VALUE: value(exprState(a.value)) });
    case "change": return block("purple_change", { VAR: a.var }, { BY: value(exprState(a.by)) });
    case "if": return withBody(withBody(block("purple_if", {}, { TEST: value(testState(a.test)) }), "DO", a.then ?? []), "ELSE", a.else ?? []);
    case "repeat": return withBody(block("purple_repeat", {}, { TIMES: value(exprState(a.times)) }), "DO", a.body);
  }
}

function ruleState(r: Rule): State {
  const w = r.when;
  const s = w.event === "start" ? block("purple_when_start")
    : w.event === "key" ? block("purple_when_key", { KEY: w.key })
    : w.event === "any_key" ? block("purple_when_any_key")
    : block("purple_when_every", { SECONDS: w.seconds });
  return withBody(s, "DO", r.do);
}

export function toState(program: RoomProgram): unknown {
  return { blocks: { languageVersion: 0, blocks: program.rules.map((r, i) => ({ ...ruleState(r), x: 24 + (i % 2) * 320, y: 24 + Math.floor(i / 2) * 220 })) } };
}

// A small farm: three animal keys, a counter, and a line that fills up. The starting point for a new room.
export function sampleRoom(name = "farm", title = "Farm"): RoomProgram {
  const animal = (key: string, emoji: string, word: string, note: string): Rule =>
    ({ when: { event: "key", key }, do: [{ do: "show", text: emoji }, { do: "say", text: word }, { do: "play", note, instrument: "marimba" }] });
  return {
    name, title, background: "#1e1033",
    rules: [
      { when: { event: "start" }, do: [{ do: "set", var: "count", value: 0 }, { do: "show", text: "🐄 🐖 🐑" }, { do: "say", text: "farm" }] },
      animal("c", "🐄", "cow", "C4"), animal("p", "🐖", "pig", "E4"), animal("s", "🐑", "sheep", "G4"),
      { when: { event: "any_key" }, do: [
        { do: "change", var: "count", by: 1 }, { do: "add", text: { pick: ["🌾", "🌻", "🐝"] } }, { do: "drum", name: "woodblock" },
        { do: "if", test: { compare: ">", a: { var: "count" }, b: 9 }, then: [{ do: "clear" }, { do: "set", var: "count", value: 0 }] },
      ] },
    ],
  };
}
