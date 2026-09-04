// Blockly blocks for the room language, the generator from a workspace to a room program,
// and the loader back from a program to a workspace. The program is what ships in the pack;
// the workspace is saved beside it so the room can be reopened.
import * as Blockly from "blockly";
import { COMPARE_OPS, DRUMS, MATH_OPS, SPECIAL_KEYS, type Action, type Expr, type RoomProgram, type Rule, type Test } from "@sdk/room";
import { INSTRUMENTS } from "@sdk/purple/sounds";
import { draft } from "./state";

export const BACKGROUNDS: [string, string][] = [
  ["night purple", "#1e1033"], ["deep purple", "#2a1845"], ["plum", "#3a1d63"], ["midnight", "#141024"],
  ["forest", "#173a2a"], ["sea", "#12304a"], ["sunset", "#4a1f2e"], ["sand", "#4a3b1f"],
];

const OP_LABELS: Record<string, string> = { "+": "+", "-": "−", "*": "×", "/": "÷", "=": "=", "!=": "≠", "<": "<", ">": ">" };

const keyValidator = (v: string) => {
  const s = v.trim().toLowerCase();
  if (SPECIAL_KEYS.includes(s)) return s;
  const chars = [...s];
  return chars.length ? chars[0] : null;
};

let defined = false;

export function defineBlocks(): void {
  if (defined) return;
  defined = true;
  Blockly.defineBlocksWithJsonArray([
    { type: "purple_when_start", message0: "when the room opens %1 %2", args0: [{ type: "input_dummy" }, { type: "input_statement", name: "DO" }], style: "event_blocks", hat: "cap", tooltip: "Runs once, when the kid opens the room." },
    { type: "purple_when_key", message0: "when %1 is pressed %2 %3", args0: [{ type: "field_input", name: "KEY", text: "c" }, { type: "input_dummy" }, { type: "input_statement", name: "DO" }], style: "event_blocks", hat: "cap", tooltip: "A letter, a number, or space, enter, up, down, left, right." },
    { type: "purple_when_any_key", message0: "when any key is pressed %1 %2", args0: [{ type: "input_dummy" }, { type: "input_statement", name: "DO" }], style: "event_blocks", hat: "cap" },
    { type: "purple_when_every", message0: "every %1 seconds %2 %3", args0: [{ type: "field_number", name: "SECONDS", value: 2, min: 0.5, max: 60, precision: 0.5 }, { type: "input_dummy" }, { type: "input_statement", name: "DO" }], style: "event_blocks", hat: "cap" },

    { type: "purple_show", message0: "show %1", args0: [{ type: "input_value", name: "TEXT" }], previousStatement: null, nextStatement: null, style: "screen_blocks", tooltip: "Big, in the middle of the screen. Replaces what was there." },
    { type: "purple_add", message0: "add %1 to the line", args0: [{ type: "input_value", name: "TEXT" }], previousStatement: null, nextStatement: null, style: "screen_blocks", tooltip: "Adds to a line that fills up as keys are pressed." },
    { type: "purple_clear", message0: "clear the screen", previousStatement: null, nextStatement: null, style: "screen_blocks" },
    { type: "purple_background", message0: "make the background %1", args0: [{ type: "field_dropdown", name: "COLOR", options: BACKGROUNDS }], previousStatement: null, nextStatement: null, style: "screen_blocks" },
    { type: "purple_say", message0: "say %1", args0: [{ type: "input_value", name: "TEXT" }], previousStatement: null, nextStatement: null, style: "sound_blocks", tooltip: "Purple speaks it, in its own voice or a recorded phrase." },
    { type: "purple_drum", message0: "hit the %1", args0: [{ type: "field_dropdown", name: "NAME", options: DRUMS.map((d) => [d, d]) }], previousStatement: null, nextStatement: null, style: "sound_blocks" },
    { type: "purple_wait", message0: "wait %1 seconds", args0: [{ type: "input_value", name: "SECONDS" }], previousStatement: null, nextStatement: null, style: "flow_blocks" },
    { type: "purple_set", message0: "set %1 to %2", args0: [{ type: "field_input", name: "VAR", text: "count" }, { type: "input_value", name: "VALUE" }], previousStatement: null, nextStatement: null, style: "number_blocks" },
    { type: "purple_change", message0: "change %1 by %2", args0: [{ type: "field_input", name: "VAR", text: "count" }, { type: "input_value", name: "BY" }], previousStatement: null, nextStatement: null, style: "number_blocks" },
    { type: "purple_if", message0: "if %1 then %2 %3 else %4 %5", args0: [{ type: "input_value", name: "TEST", check: "Boolean" }, { type: "input_dummy" }, { type: "input_statement", name: "DO" }, { type: "input_dummy" }, { type: "input_statement", name: "ELSE" }], previousStatement: null, nextStatement: null, style: "flow_blocks" },
    { type: "purple_repeat", message0: "repeat %1 times %2 %3", args0: [{ type: "input_value", name: "TIMES" }, { type: "input_dummy" }, { type: "input_statement", name: "DO" }], previousStatement: null, nextStatement: null, style: "flow_blocks" },

    { type: "purple_var", message0: "%1", args0: [{ type: "field_input", name: "VAR", text: "count" }], output: null, style: "number_blocks", tooltip: "A number or word the room remembers." },
    { type: "purple_key", message0: "the key pressed", output: null, style: "number_blocks" },
    { type: "purple_pick", message0: "pick one of %1", args0: [{ type: "field_input", name: "LIST", text: "cow, pig, sheep" }], output: null, style: "number_blocks", tooltip: "Separate choices with commas." },
    { type: "purple_join", message0: "join %1 %2", args0: [{ type: "input_value", name: "A" }, { type: "input_value", name: "B" }], output: null, inputsInline: true, style: "number_blocks" },
    { type: "purple_random", message0: "random number from %1 to %2", args0: [{ type: "input_value", name: "FROM" }, { type: "input_value", name: "TO" }], output: null, inputsInline: true, style: "number_blocks" },
    { type: "purple_math", message0: "%1 %2 %3", args0: [{ type: "input_value", name: "A" }, { type: "field_dropdown", name: "OP", options: MATH_OPS.map((op) => [OP_LABELS[op], op]) }, { type: "input_value", name: "B" }], output: null, inputsInline: true, style: "number_blocks" },
    { type: "purple_compare", message0: "%1 %2 %3", args0: [{ type: "input_value", name: "A" }, { type: "field_dropdown", name: "OP", options: COMPARE_OPS.map((op) => [OP_LABELS[op], op]) }, { type: "input_value", name: "B" }], output: "Boolean", inputsInline: true, style: "flow_blocks" },
    { type: "purple_logic", message0: "%1 %2 %3", args0: [{ type: "input_value", name: "A", check: "Boolean" }, { type: "field_dropdown", name: "OP", options: [["and", "and"], ["or", "or"]] }, { type: "input_value", name: "B", check: "Boolean" }], output: "Boolean", inputsInline: true, style: "flow_blocks" },
    { type: "purple_not", message0: "not %1", args0: [{ type: "input_value", name: "A", check: "Boolean" }], output: "Boolean", style: "flow_blocks" },
  ]);

  // The instrument list is live: Purple's four plus whatever the parent has made in this pack.
  Blockly.Blocks.purple_play = {
    init(this: Blockly.Block) {
      this.jsonInit({
        message0: "play note %1 on %2",
        args0: [{ type: "input_value", name: "NOTE" }, { type: "field_dropdown", name: "INSTRUMENT", options: () => [...INSTRUMENTS, ...draft.instruments.map((i) => i.name)].map((n) => [n, n]) }],
        previousStatement: null, nextStatement: null, inputsInline: true, style: "sound_blocks",
        tooltip: "A note name like C4 or F#3. The Music room's keys run from C1 to D7.",
      });
    },
  };

  const whenKey = Blockly.Blocks.purple_when_key;
  const init = whenKey.init;
  whenKey.init = function (this: Blockly.Block) {
    init.call(this);
    this.getField("KEY")?.setValidator(keyValidator);
  };

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
      { kind: "block", type: "purple_show", inputs: { TEXT: text("🐄") } }, { kind: "block", type: "purple_add", inputs: { TEXT: text("⭐") } },
      { kind: "block", type: "purple_clear" }, { kind: "block", type: "purple_background" },
    ] },
    { kind: "category", name: "Sound", categorystyle: "sound_category", contents: [
      { kind: "block", type: "purple_say", inputs: { TEXT: text("cow") } }, { kind: "block", type: "purple_play", inputs: { NOTE: text("C4") } },
      { kind: "block", type: "purple_drum" },
    ] },
    { kind: "category", name: "Then", categorystyle: "flow_category", contents: [
      { kind: "block", type: "purple_wait", inputs: { SECONDS: num(1) } }, { kind: "block", type: "purple_repeat", inputs: { TIMES: num(3) } },
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

// Workspace -> program -----------------------------------------------------------------

function expr(b: Blockly.Block | null): Expr {
  if (!b) return "";
  switch (b.type) {
    case "text": return String(b.getFieldValue("TEXT") ?? "");
    case "math_number": return Number(b.getFieldValue("NUM") ?? 0);
    case "purple_var": return { var: String(b.getFieldValue("VAR") || "count") };
    case "purple_key": return { key: true };
    case "purple_pick": {
      const items = String(b.getFieldValue("LIST") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
      return { pick: items.length ? items : [""] };
    }
    case "purple_join": return { join: [expr(b.getInputTargetBlock("A")), expr(b.getInputTargetBlock("B"))] };
    case "purple_random": return { random: { from: expr(b.getInputTargetBlock("FROM")), to: expr(b.getInputTargetBlock("TO")) } };
    case "purple_math": return { math: String(b.getFieldValue("OP")), a: expr(b.getInputTargetBlock("A")), b: expr(b.getInputTargetBlock("B")) };
    default: return "";
  }
}

function test(b: Blockly.Block | null): Test {
  if (!b) return { compare: "=", a: 1, b: 1 };
  switch (b.type) {
    case "purple_compare": return { compare: String(b.getFieldValue("OP")), a: expr(b.getInputTargetBlock("A")), b: expr(b.getInputTargetBlock("B")) };
    case "purple_logic": {
      const both = [test(b.getInputTargetBlock("A")), test(b.getInputTargetBlock("B"))];
      return b.getFieldValue("OP") === "or" ? { or: both } : { and: both };
    }
    case "purple_not": return { not: test(b.getInputTargetBlock("A")) };
    default: return { compare: "=", a: 1, b: 1 };
  }
}

function actions(first: Blockly.Block | null): Action[] {
  const out: Action[] = [];
  for (let b = first; b; b = b.getNextBlock()) {
    const a = action(b);
    if (a) out.push(a);
  }
  return out;
}

function action(b: Blockly.Block): Action | null {
  switch (b.type) {
    case "purple_show": case "purple_add": case "purple_say":
      return { do: b.type.slice(7) as "show" | "add" | "say", text: expr(b.getInputTargetBlock("TEXT")) };
    case "purple_play": return { do: "play", note: expr(b.getInputTargetBlock("NOTE")), instrument: String(b.getFieldValue("INSTRUMENT") || "marimba") };
    case "purple_drum": return { do: "drum", name: String(b.getFieldValue("NAME")) };
    case "purple_clear": return { do: "clear" };
    case "purple_background": return { do: "background", color: String(b.getFieldValue("COLOR")) };
    case "purple_wait": return { do: "wait", seconds: expr(b.getInputTargetBlock("SECONDS")) };
    case "purple_set": return { do: "set", var: String(b.getFieldValue("VAR") || "count"), value: expr(b.getInputTargetBlock("VALUE")) };
    case "purple_change": return { do: "change", var: String(b.getFieldValue("VAR") || "count"), by: expr(b.getInputTargetBlock("BY")) };
    case "purple_if": return { do: "if", test: test(b.getInputTargetBlock("TEST")), then: actions(b.getInputTargetBlock("DO")), else: actions(b.getInputTargetBlock("ELSE")) };
    case "purple_repeat": return { do: "repeat", times: expr(b.getInputTargetBlock("TIMES")), body: actions(b.getInputTargetBlock("DO")) };
    default: return null;
  }
}

function rule(b: Blockly.Block): Rule | null {
  const body = actions(b.getInputTargetBlock("DO"));
  switch (b.type) {
    case "purple_when_start": return { when: { event: "start" }, do: body };
    case "purple_when_key": return { when: { event: "key", key: String(b.getFieldValue("KEY") || "c") }, do: body };
    case "purple_when_any_key": return { when: { event: "any_key" }, do: body };
    case "purple_when_every": return { when: { event: "every", seconds: Number(b.getFieldValue("SECONDS") || 2) }, do: body };
    default: return null;
  }
}

export function toProgram(ws: Blockly.Workspace, name: string, title: string): RoomProgram {
  const rules = ws.getTopBlocks(true).map(rule).filter((r): r is Rule => r !== null);
  return { name, title, rules };
}

export { toState } from "./roomstate";
