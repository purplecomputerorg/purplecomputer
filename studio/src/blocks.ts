// Blockly blocks for rooms and the generator from a workspace to the room's Python. The Python
// is what ships in the pack; the workspace is saved beside it so the room can be reopened.
import * as Blockly from "blockly";
import { Order, pythonGenerator as py } from "blockly/python";
import { PURPLE } from "@sdk";
import { INSTRUMENTS } from "@sdk/purple/sounds";
import { normalizeKey } from "./examples";
import { draft } from "./state";

export const BACKGROUNDS: [string, string][] = [
  ["night purple", "#1e1033"], ["deep purple", "#2a1845"], ["plum", "#3a1d63"], ["midnight", "#141024"],
  ["forest", "#173a2a"], ["sea", "#12304a"], ["sunset", "#4a1f2e"], ["sand", "#4a3b1f"],
];
const DRUMS: string[] = PURPLE.room.drums;
const OP_LABELS: Record<string, string> = { "+": "+", "-": "−", "*": "×", "/": "÷", "==": "=", "!=": "≠", "<": "<", ">": ">" };


const statement = (type: string, message0: string, args0: object[], style: string, tooltip = "") =>
  ({ type, message0, args0, previousStatement: null, nextStatement: null, inputsInline: true, style, tooltip });
const event = (type: string, message0: string, args0: object[], tooltip = "") =>
  ({ type, message0: `${message0} %${args0.length + 1} %${args0.length + 2}`, args0: [...args0, { type: "input_dummy" }, { type: "input_statement", name: "DO" }], style: "event_blocks", hat: "cap", tooltip });
const value = (type: string, message0: string, args0: object[], output: string | null = null) =>
  ({ type, message0, args0, output, inputsInline: true, style: output === "Boolean" ? "flow_blocks" : "number_blocks" });
const input = (name: string, check?: string) => ({ type: "input_value", name, ...(check ? { check } : {}) });

let defined = false;

export function defineBlocks(): void {
  if (defined) return;
  defined = true;
  Blockly.defineBlocksWithJsonArray([
    event("purple_when_start", "when the room opens", [], "Runs once, when the kid opens the room."),
    event("purple_when_key", "when %1 is pressed", [{ type: "field_input", name: "KEY", text: "c" }], "A letter, a number, or space, enter, backspace, up, down, left, right."),
    event("purple_when_any_key", "when any key is pressed", []),
    event("purple_when_every", "every %1 seconds", [{ type: "field_number", name: "SECONDS", value: 1, min: 0.1, max: 60, precision: 0.1 }]),

    statement("purple_show", "show %1", [input("TEXT")], "screen_blocks", "Big, in the middle of the screen. Replaces what was there."),
    statement("purple_write", "write %1", [input("TEXT")], "screen_blocks", "A line of text under the middle."),
    statement("purple_clear", "clear the screen", [], "screen_blocks"),
    statement("purple_background", "make the background %1", [{ type: "field_dropdown", name: "COLOR", options: BACKGROUNDS }], "screen_blocks"),
    statement("purple_grid_set", "put %1 at column %2 row %3", [input("THING"), input("X"), input("Y")], "screen_blocks", "The grid is 24 columns by 12 rows, starting at 0 in the top left."),
    statement("purple_grid_erase", "erase column %1 row %2", [input("X"), input("Y")], "screen_blocks"),
    statement("purple_say", "say %1", [input("TEXT")], "sound_blocks", "Purple speaks it."),
    statement("purple_drum", "hit the %1", [{ type: "field_dropdown", name: "NAME", options: DRUMS.map((d) => [d, d]) }], "sound_blocks"),
    statement("purple_set", "set %1 to %2", [{ type: "field_input", name: "VAR", text: "count" }, input("VALUE")], "number_blocks"),
    statement("purple_change", "change %1 by %2", [{ type: "field_input", name: "VAR", text: "count" }, input("BY")], "number_blocks"),
    { ...statement("purple_if", "if %1 then %2 %3 else %4 %5", [input("TEST", "Boolean"), { type: "input_dummy" }, { type: "input_statement", name: "DO" }, { type: "input_dummy" }, { type: "input_statement", name: "ELSE" }], "flow_blocks"), inputsInline: false },
    { ...statement("purple_repeat", "repeat %1 times %2 %3", [input("TIMES"), { type: "input_dummy" }, { type: "input_statement", name: "DO" }], "flow_blocks"), inputsInline: false },

    value("purple_var", "%1", [{ type: "field_input", name: "VAR", text: "count" }]),
    value("purple_key", "the key pressed", []),
    value("purple_pick", "pick one of %1", [{ type: "field_input", name: "LIST", text: "cow, pig, sheep" }]),
    value("purple_join", "join %1 %2", [input("A"), input("B")]),
    value("purple_random", "random number from %1 to %2", [input("FROM"), input("TO")]),
    value("purple_math", "%1 %2 %3", [input("A"), { type: "field_dropdown", name: "OP", options: ["+", "-", "*", "/"].map((op) => [OP_LABELS[op], op]) }, input("B")]),
    value("purple_compare", "%1 %2 %3", [input("A"), { type: "field_dropdown", name: "OP", options: ["==", "!=", "<", ">"].map((op) => [OP_LABELS[op], op]) }, input("B")], "Boolean"),
    value("purple_logic", "%1 %2 %3", [input("A", "Boolean"), { type: "field_dropdown", name: "OP", options: [["and", "and"], ["or", "or"]] }, input("B", "Boolean")], "Boolean"),
    value("purple_not", "not %1", [input("A", "Boolean")], "Boolean"),
  ]);

  // The instrument list is live: Purple's four plus whatever the parent has made in this pack.
  Blockly.Blocks.purple_play = {
    init(this: Blockly.Block) {
      this.jsonInit({
        ...statement("purple_play", "play note %1 on %2", [input("NOTE"), { type: "field_dropdown", name: "INSTRUMENT", options: () => [...INSTRUMENTS, ...draft.instruments.map((i) => i.name)].map((n) => [n, n]) }], "sound_blocks", "A note name like C4 or F#3."),
      });
    },
  };

  const whenKey = Blockly.Blocks.purple_when_key;
  const init = whenKey.init;
  whenKey.init = function (this: Blockly.Block) {
    init.call(this);
    this.getField("KEY")?.setValidator(normalizeKey);
  };

  defineGenerators();

  Blockly.Theme.defineTheme("purple", {
    name: "purple",
    base: Blockly.Themes.Zelos,
    blockStyles: {
      event_blocks: { colourPrimary: "#9b59d0", colourSecondary: "#8a4cbf", colourTertiary: "#7a3fae" },
      screen_blocks: { colourPrimary: "#5c2d91", colourSecondary: "#4a2473", colourTertiary: "#3d1d60" },
      sound_blocks: { colourPrimary: "#3f7fbf", colourSecondary: "#356da6", colourTertiary: "#2c5b8c" },
      flow_blocks: { colourPrimary: "#d08a3a", colourSecondary: "#b97a32", colourTertiary: "#a1692a" },
      number_blocks: { colourPrimary: "#4c9a6a", colourSecondary: "#42875c", colourTertiary: "#38734e" },
      text_blocks: { colourPrimary: "#7f6a9e", colourSecondary: "#6f5b8c", colourTertiary: "#5f4c7a" },
      math_blocks: { colourPrimary: "#7f6a9e", colourSecondary: "#6f5b8c", colourTertiary: "#5f4c7a" },
    },
    categoryStyles: {
      event_category: { colour: "#9b59d0" }, screen_category: { colour: "#5c2d91" }, sound_category: { colour: "#3f7fbf" },
      flow_category: { colour: "#d08a3a" }, number_category: { colour: "#4c9a6a" },
    },
    componentStyles: {
      workspaceBackgroundColour: "#fbfaf8", toolboxBackgroundColour: "#f3f0f6", toolboxForegroundColour: "#352a4a",
      flyoutBackgroundColour: "#f3f0f6", flyoutForegroundColour: "#352a4a", flyoutOpacity: 1, scrollbarColour: "#c4aee0",
      insertionMarkerColour: "#5c2d91", insertionMarkerOpacity: 0.3, cursorColour: "#5c2d91",
    },
    fontStyle: { family: "Figtree, Inter, system-ui, sans-serif", weight: "500", size: 11 },
  });
}

const text = (t: string) => ({ shadow: { type: "text", fields: { TEXT: t } } });
const num = (n: number) => ({ shadow: { type: "math_number", fields: { NUM: n } } });

export const TOOLBOX = {
  kind: "categoryToolbox",
  contents: [
    { kind: "category", name: "When", categorystyle: "event_category", contents: [
      { kind: "block", type: "purple_when_key" }, { kind: "block", type: "purple_when_any_key" },
      { kind: "block", type: "purple_when_start" }, { kind: "block", type: "purple_when_every" },
    ] },
    { kind: "category", name: "Screen", categorystyle: "screen_category", contents: [
      { kind: "block", type: "purple_show", inputs: { TEXT: text("🐄") } }, { kind: "block", type: "purple_write", inputs: { TEXT: text("Moo!") } },
      { kind: "block", type: "purple_clear" }, { kind: "block", type: "purple_background" },
      { kind: "block", type: "purple_grid_set", inputs: { THING: text("⭐"), X: num(0), Y: num(0) } }, { kind: "block", type: "purple_grid_erase", inputs: { X: num(0), Y: num(0) } },
    ] },
    { kind: "category", name: "Sound", categorystyle: "sound_category", contents: [
      { kind: "block", type: "purple_say", inputs: { TEXT: text("cow") } }, { kind: "block", type: "purple_play", inputs: { NOTE: text("C4") } },
      { kind: "block", type: "purple_drum" },
    ] },
    { kind: "category", name: "Then", categorystyle: "flow_category", contents: [
      { kind: "block", type: "purple_repeat", inputs: { TIMES: num(3) } },
      { kind: "block", type: "purple_if", inputs: { TEST: { block: { type: "purple_compare", inputs: { A: { block: { type: "purple_var" } }, B: num(3) } } } } },
      { kind: "block", type: "purple_compare", inputs: { A: num(1), B: num(2) } }, { kind: "block", type: "purple_logic" }, { kind: "block", type: "purple_not" },
    ] },
    { kind: "category", name: "Numbers and words", categorystyle: "number_category", contents: [
      { kind: "block", type: "text" }, { kind: "block", type: "math_number" },
      { kind: "block", type: "purple_set", inputs: { VALUE: num(0) } }, { kind: "block", type: "purple_change", inputs: { BY: num(1) } }, { kind: "block", type: "purple_var" },
      { kind: "block", type: "purple_key" }, { kind: "block", type: "purple_pick" }, { kind: "block", type: "purple_join", inputs: { A: text("cow number "), B: { block: { type: "purple_var" } } } },
      { kind: "block", type: "purple_random", inputs: { FROM: num(1), TO: num(6) } }, { kind: "block", type: "purple_math", inputs: { A: num(1), B: num(2) } },
    ] },
  ],
};

// Workspace -> Python ------------------------------------------------------------------

const INDENT = "    ";
const RESERVED = new Set(["key", "grid", "show", "write", "clear", "background", "say", "play", "drum", "ask", "every", "after", "game_over", "random", "on_key", "and", "or", "not", "if", "else", "for", "in", "is", "def", "return", "global", "pass", "True", "False", "None"]);

// A block's variable name as a Python name that cannot clash with the room's own calls.
function varName(b: Blockly.Block): string {
  const base = String(b.getFieldValue("VAR") || "count").trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "count";
  return /^[0-9]/.test(base) || RESERVED.has(base) ? `my_${base}` : base;
}

const indent = (code: string) => code.split("\n").map((l) => (l ? INDENT + l : l)).join("\n");
const dedent = (code: string) => code.split("\n").map((l) => (l.startsWith(INDENT) ? l.slice(INDENT.length) : l)).join("\n");
const body = (b: Blockly.Block, name: string) => py.statementToCode(b, name) || `${INDENT}pass\n`;
const val = (b: Blockly.Block, name: string, fallback = '""') => py.valueToCode(b, name, Order.NONE) || fallback;
const atom = (code: string): [string, Order] => [code, Order.ATOMIC];

function defineGenerators(): void {
  const f = py.forBlock;
  f.purple_show = (b) => `show(${val(b, "TEXT")})\n`;
  f.purple_write = (b) => `write(${val(b, "TEXT")})\n`;
  f.purple_say = (b) => `say(${val(b, "TEXT")})\n`;
  f.purple_clear = () => "clear()\n";
  f.purple_background = (b) => `background(${JSON.stringify(b.getFieldValue("COLOR"))})\n`;
  f.purple_grid_set = (b) => `grid.set(${val(b, "X", "0")}, ${val(b, "Y", "0")}, ${val(b, "THING")})\n`;
  f.purple_grid_erase = (b) => `grid.erase(${val(b, "X", "0")}, ${val(b, "Y", "0")})\n`;
  f.purple_play = (b) => `play(${val(b, "NOTE", '"C4"')}, ${JSON.stringify(b.getFieldValue("INSTRUMENT") || "marimba")})\n`;
  f.purple_drum = (b) => `drum(${JSON.stringify(b.getFieldValue("NAME"))})\n`;
  f.purple_set = (b) => `${varName(b)} = ${val(b, "VALUE", "0")}\n`;
  f.purple_change = (b) => `${varName(b)} = ${varName(b)} + ${val(b, "BY", "1")}\n`;
  f.purple_if = (b) => {
    const otherwise = py.statementToCode(b, "ELSE");
    return `if ${val(b, "TEST", "False")}:\n${body(b, "DO")}${otherwise ? `else:\n${otherwise}` : ""}`;
  };
  f.purple_repeat = (b) => `for _ in range(int(${val(b, "TIMES", "1")})):\n${body(b, "DO")}`;
  f.purple_var = (b) => atom(varName(b));
  f.purple_key = () => atom("key");
  f.purple_pick = (b) => atom(`random.choice(${JSON.stringify(String(b.getFieldValue("LIST")).split(",").map((s) => s.trim()).filter(Boolean))})`);
  f.purple_join = (b) => atom(`(str(${val(b, "A")}) + str(${val(b, "B")}))`);
  f.purple_random = (b) => atom(`random.randint(int(${val(b, "FROM", "1")}), int(${val(b, "TO", "6")}))`);
  f.purple_math = (b) => atom(`(${val(b, "A", "0")} ${b.getFieldValue("OP")} ${val(b, "B", "0")})`);
  f.purple_compare = (b) => atom(`(${val(b, "A", "0")} ${b.getFieldValue("OP")} ${val(b, "B", "0")})`);
  f.purple_logic = (b) => atom(`(${val(b, "A", "False")} ${b.getFieldValue("OP")} ${val(b, "B", "False")})`);
  f.purple_not = (b) => atom(`(not ${val(b, "A", "False")})`);
}

export function toPython(ws: Blockly.Workspace): string {
  py.INDENT = INDENT;
  py.init(ws);
  const vars = [...new Set(ws.getAllBlocks(false).filter((b) => b.getField("VAR")).map(varName))];
  const glob = vars.length ? `${INDENT}global ${vars.join(", ")}\n` : "";
  const start: string[] = [];
  const keys: string[] = [];
  const timers: string[] = [];
  for (const b of ws.getTopBlocks(true)) {
    const code = py.statementToCode(b, "DO");
    if (!code) continue;
    if (b.type === "purple_when_start") start.push(dedent(code));
    else if (b.type === "purple_when_key") keys.push(`${INDENT}if key == ${JSON.stringify(b.getFieldValue("KEY") || "c")}:\n${indent(code)}`);
    else if (b.type === "purple_when_any_key") keys.push(code);
    else if (b.type === "purple_when_every") {
      const fn = `every_${timers.length + 1}`;
      timers.push(`def ${fn}():\n${glob}${code}\n\nevery(${Number(b.getFieldValue("SECONDS")) || 1}, ${fn})\n`);
    }
  }
  const parts = ["from purple import *\n"];
  if (vars.length) parts.push(vars.map((v) => `${v} = 0`).join("\n") + "\n");
  if (keys.length) parts.push(`def on_key(key):\n${glob}${keys.join("")}`);
  parts.push(...timers);
  if (start.length) parts.push(start.join(""));
  const source = parts.join("\n\n").replace(/\n{4,}/g, "\n\n\n").trimEnd() + "\n";
  return source.includes("random.") ? source.replace("from purple import *\n", "from purple import *\nimport random\n") : source;
}

// The starting point for "Start a room": a wave when the room opens, and every key shows itself.
export const BLANK_BLOCKS = {
  blocks: { languageVersion: 0, blocks: [
    { type: "purple_when_start", x: 24, y: 24, inputs: { DO: { block: { type: "purple_show", inputs: { TEXT: text("👋") } } } } },
    { type: "purple_when_any_key", x: 24, y: 150, inputs: { DO: { block: { type: "purple_show", inputs: { TEXT: { ...text(""), block: { type: "purple_key" } } } } } } },
  ] },
};

// The Python for a saved workspace, without drawing it.
export function sourceFromBlocks(state: object): string {
  defineBlocks();
  const ws = new Blockly.Workspace();
  try {
    Blockly.serialization.workspaces.load(state, ws);
    return toPython(ws);
  } finally {
    ws.dispose();
  }
}
