// Blocks made from the room library's own ideas (keys on the keyboard, squares, things, a player, settings) and
// the Python they write. The Python is what ships in the pack; the workspace is saved beside it so the room
// reopens as blocks. Typed text goes into the code only as JSON string literals, so nothing typed can become code.
import * as Blockly from "blockly";
import { Order, pythonGenerator as py } from "blockly/python";
import { PURPLE } from "@sdk";
import { INSTRUMENTS } from "@sdk/purple/sounds";
import type { Knob, Lit } from "./knobs";
import { draft } from "./state";

const lit = (s: string) => JSON.stringify(s);
const DRUMS: string[] = PURPLE.room.drums;
const WAYS = ["up", "down", "left", "right"];
// A picture field's value: one of the pack's pictures, by name, rather than an emoji.
export const PIC = "picture:";
const NOTES = [3, 4, 5].flatMap((o) => [..."CDEFGAB"].map((n) => `${n}${o}`)).concat("C6");

// Colors with names a kid knows, then the theme's own, which follow the family's theme.
export const COLORS: [name: string, color: string][] = [
  ["grass", "#4a8a50"], ["leaves", "#2f9e44"], ["water", "#4677b0"], ["sky", "#8ec5ff"], ["sand", "#e2c27a"],
  ["dirt", "#7a5230"], ["stone", "#8a8a8a"], ["snow", "#ffffff"], ["night", "#1e1033"], ["red", "#e44444"],
  ["orange", "#ec7a1c"], ["yellow", "#e0c020"], ["green", "#2e9e4f"], ["blue", "#2e6ae1"], ["purple", "#9b4dca"],
  ["pink", "#e0457b"], ["tile", "tile"], ["picked", "primary"], ["bright", "accent"],
];
// What the theme's colors look like in Studio, which has no family theme to paint them in.
const THEME_LOOKS: Record<string, string> = { tile: "#d9cdea", primary: "#7a2fb8", accent: "#e3b8ff", surface: "#2a1845" };
export const colorLooks = (c: string) => THEME_LOOKS[c] ?? c;

// A field that opens a picker: an emoji or picture, a square on the grid, a key, a color, or one of the room's settings.
export type PickerKind = "emoji" | "square" | "key" | "color" | "setting";
// Studio's page fills these in; with none (tests, building a pack), the field just keeps its value.
export const pickers: Partial<Record<PickerKind, (field: PickerField) => void>> = {};
const CAPS: Record<string, string> = { space: "Space", enter: "Enter", backspace: "Backspace", up: "↑", down: "↓", left: "←", right: "→" };
const SHOWN: Record<PickerKind, (v: string) => string> = {
  emoji: (v) => (v.startsWith(PIC) ? `🖼️ ${v.slice(PIC.length)}` : v || "?"),
  square: (v) => `▦ ${v.replace(",", ", ")}`,
  key: (v) => CAPS[v] ?? v.toUpperCase(),
  color: () => "⬤",
  setting: (v) => v || "?",
};

export class PickerField extends Blockly.Field<string> {
  override SERIALIZABLE = true;

  constructor(readonly kind: PickerKind, value: string) {
    super(value);
  }

  static override fromJson(o: Blockly.FieldConfig & { kind?: PickerKind; value?: string }) {
    return new PickerField(o.kind ?? "emoji", o.value ?? "");
  }

  protected override getText_() {
    return SHOWN[this.kind](this.getValue() ?? "");
  }

  protected override showEditor_() {
    pickers[this.kind]?.(this);
  }

  protected override render_() {
    super.render_();
    if (this.kind === "color" && this.textElement_) this.textElement_.style.fill = colorLooks(this.getValue() ?? "");
  }
}

type Arg = Record<string, unknown>;
const pick = (name: string, kind: PickerKind, value: string): Arg => ({ type: "field_picker", name, kind, value });
const input = (name: string, check?: string | string[]): Arg => ({ type: "input_value", name, ...(check ? { check } : {}) });
const menu = (name: string, options: [string, string][] | (() => [string, string][])): Arg => ({ type: "field_dropdown", name, options });
const size = menu("SIZE", ["1", "2", "3", "4", "6", "8"].map((n) => [n, n]));
const DO: Arg[] = [{ type: "input_dummy" }, { type: "input_statement", name: "DO" }];
const THING = ["Thing", "Color", "String", "Number"];
const message = (text: string, args: Arg[]) => ({ message0: text, args0: args, inputsInline: true });
const statement = (type: string, text: string, args: Arg[], style: string, tooltip = "") =>
  ({ type, ...message(text, args), previousStatement: null, nextStatement: null, style, tooltip });
const hat = (type: string, text: string, args: Arg[], tooltip = "") =>
  ({ type, ...message(`${text} %${args.length + 1} %${args.length + 2}`, [...args, ...DO]), style: "event_blocks", tooltip, inputsInline: false });
const value = (type: string, text: string, args: Arg[], output: string | string[] | null, style: string, extensions?: string[]) =>
  ({ type, ...message(text, args), output, style, ...(extensions ? { extensions } : {}) });
const wrap = (type: string, text: string, args: Arg[], style: string) =>
  ({ ...statement(type, `${text} %${args.length + 1} %${args.length + 2}`, [...args, ...DO], style), inputsInline: false });

const instruments = (): [string, string][] => [...INSTRUMENTS, ...draft.instruments.map((i) => i.name)].map((n) => [n, n]);
const drums = (): [string, string][] => [...DRUMS.map((d): [string, string] => [`🥁 ${d}`, d]),
  ...draft.roomFiles.filter((f) => f.kind === "sounds").map((f): [string, string] => [`🎤 ${f.name}`, f.name])];

const BLOCKS = [
  hat("purple_on_start", "when the room opens", [], "Runs once, when your kid comes in."),
  hat("purple_on_key", "when %1 is pressed", [menu("WHICH", [["any key", "any"], ["an arrow", "arrow"], ["a keyboard key", "keyboard"], ["a number key", "number"], ["a key that isn't an arrow", "not_arrow"], ["Space", "space"], ["Enter", "enter"]])]),
  hat("purple_on_this_key", "when key %1 is pressed", [pick("KEY", "key", "q")]),
  hat("purple_every", "every %1 seconds", [input("SECONDS", "Number")], "Over and over, at least a tenth of a second apart."),
  hat("purple_on_meet", "when the player meets %1", [input("THING", THING)], "When the player walks onto it, or it moves onto the player. It goes away."),

  statement("purple_player_put", "put the player %1 at %2", [input("THING", THING), input("SQUARE", "Square")], "player_blocks"),
  { ...statement("purple_player_move", "move the player %1", [menu("WAY", [["the arrow's way", "key"], ...WAYS.map((w): [string, string] => [w, w])])], "player_blocks",
    "A square that way, unless a wall is there. Off one edge comes back on the other."), extensions: ["key_only"] },
  statement("purple_wall", "%1 is a wall", [input("THING", THING)], "player_blocks", "The player can't walk through it."),
  value("purple_player_square", "the player's square", [], "Square", "player_blocks"),

  statement("purple_put", "put %1 at %2 size %3", [input("THING", THING), input("SQUARE", "Square"), size], "grid_blocks"),
  statement("purple_floor", "paint the floor %1 at %2 size %3", [input("COLOR", "Color"), input("SQUARE", "Square"), size], "grid_blocks", "The floor stays under whatever is on the square."),
  statement("purple_erase", "erase %1", [input("SQUARE", "Square")], "grid_blocks"),
  statement("purple_move_all", "move every %1 one square %2", [input("THING", THING), menu("WAY", WAYS.map((w) => [w, w]))], "grid_blocks",
    "Off the edge, it's gone. Onto the player, they meet."),
  value("purple_square", "square %1", [pick("SQUARE", "square", "13,6")], "Square", "grid_blocks"),
  value("purple_random_square", "a random square %1", [menu("WHERE", [["that's empty", "empty"], ["along the top", "top"], ["along the bottom", "bottom"], ["along the left", "left"], ["along the right", "right"]])], "Square", "grid_blocks"),
  value("purple_what_at", "what's at %1", [input("SQUARE", "Square")], "Thing", "grid_blocks"),
  value("purple_is_empty", "%1 is empty", [input("SQUARE", "Square")], "Boolean", "grid_blocks"),
  statement("purple_ring_put", "put the ring at %1", [input("SQUARE", "Square")], "grid_blocks", "A ring around one square, to show what's picked."),
  { ...statement("purple_ring_move", "move the ring %1", [menu("WAY", [["the arrow's way", "key"], ...WAYS.map((w): [string, string] => [w, w])])], "grid_blocks",
    "A square that way. Off one edge comes back on the other."), extensions: ["key_only"] },
  value("purple_ring_square", "the ring's square", [], "Square", "grid_blocks"),

  value("purple_key_pressed", "the key pressed", [], "Key", "key_blocks", ["key_only"]),
  value("purple_key", "key %1", [pick("KEY", "key", "q")], "Key", "key_blocks"),
  wrap("purple_each_key", "for every key on the keyboard", [], "key_blocks"),
  value("purple_that_key", "that key", [], "Key", "key_blocks"),
  value("purple_key_spot", "where %1 is", [input("KEY", "Key")], "Square", "key_blocks"),
  value("purple_key_letter", "%1 as a letter", [input("KEY", "Key")], "String", "key_blocks"),
  value("purple_key_color", "%1's sticker color", [input("KEY", "Key")], "Color", "key_blocks"),
  value("purple_key_note", "%1's note", [input("KEY", "Key")], "Note", "key_blocks", ),

  value("purple_thing", "%1", [pick("THING", "emoji", "⭐")], ["Thing", "Literal"], "thing_blocks"),
  value("purple_color", "%1", [pick("COLOR", "color", "#4a8a50")], ["Color", "Literal"], "thing_blocks"),
  value("purple_things", "[ %1 ]", [{ type: "field_input", name: "THINGS", text: "🍎 🍌 🍇" }], ["List", "Literal"], "thing_blocks"),
  value("purple_one_of", "one of %1", [input("LIST", "List")], "Thing", "thing_blocks"),
  value("purple_text", "“%1”", [{ type: "field_input", name: "TEXT", text: "Hello!" }], ["String", "Literal"], "thing_blocks"),
  value("purple_number", "%1", [{ type: "field_number", name: "NUM", value: 1 }], ["Number", "Literal"], "thing_blocks"),
  value("purple_join", "%1 %2", [input("A"), input("B")], "String", "thing_blocks"),
  value("purple_any_picture", "one of your pictures", [], "Thing", "thing_blocks"),
  statement("purple_pot_add", "mix %1 into the pot", [input("COLOR", "Color")], "thing_blocks", "The last six colors in the pot mix like paint."),
  statement("purple_pot_empty", "empty the pot", [], "thing_blocks"),
  value("purple_pot_color", "the pot's color", [], "Color", "thing_blocks"),
  value("purple_note", "note %1", [menu("NOTE", NOTES.map((n) => [n, n]))], "Note", "sound_blocks"),

  statement("purple_show", "show %1 big", [input("TEXT")], "screen_blocks"),
  statement("purple_write", "write %1", [input("TEXT")], "screen_blocks", "A line under the middle. The last five stay."),
  statement("purple_status", "put %1 at the top", [input("TEXT")], "screen_blocks", "For a score, or what to do next."),
  statement("purple_clear", "clear the screen", [], "screen_blocks"),
  statement("purple_background", "make the background %1", [input("COLOR", "Color")], "screen_blocks"),
  statement("purple_say", "say %1", [input("TEXT")], "sound_blocks"),
  statement("purple_play", "play %1 on %2", [input("NOTE", "Note"), menu("INSTRUMENT", instruments)], "sound_blocks"),
  statement("purple_drum", "hit the %1", [menu("DRUM", drums)], "sound_blocks"),

  statement("purple_set", "set %1 to %2", [{ type: "field_variable", name: "VAR", variable: "score" }, input("VALUE")], "game_blocks"),
  statement("purple_change", "change %1 by %2", [{ type: "field_variable", name: "VAR", variable: "score" }, input("BY", "Number")], "game_blocks"),
  value("purple_get", "%1", [{ type: "field_variable", name: "VAR", variable: "score" }], null, "game_blocks"),
  wrap("purple_after", "after %1 seconds", [input("SECONDS", "Number")], "game_blocks"),
  statement("purple_game_over", "game over: %1", [input("TEXT")], "game_blocks", "Stops the timers. A key starts the room again from the top."),
  { type: "purple_setting", message0: "setting %1 is %2", args0: [{ type: "field_input", name: "NAME", text: "FRUIT" }, input("VALUE", "Literal")],
    message1: "for %1", args1: [{ type: "field_input", name: "ABOUT", text: "what it's for" }], style: "setting_blocks",
    tooltip: "A setting your family can change on the Knobs tab." },
  value("purple_setting_get", "%1", [pick("NAME", "setting", "FRUIT")], null, "setting_blocks"),
];

const usesKey = (block: Blockly.Block) => !block.getField("WAY") || block.getFieldValue("WAY") === "key";
const underKey = (block: Blockly.Block) => ["purple_on_key", "purple_on_this_key"].includes(block.getRootBlock().type);

// Each kind of block's color: its blocks and its toolbox category.
const BLOCK_COLORS = {
  event: "#9b59d0", player: "#d0577f", grid: "#5c2d91", key: "#c9a227", thing: "#7f6a9e",
  screen: "#4a6fb5", sound: "#3f9fbf", game: "#d08a3a", setting: "#4c9a6a",
};

let defined = false;

export function defineBlocks(): void {
  if (defined) return;
  defined = true;
  Blockly.fieldRegistry.register("field_picker", PickerField);
  Blockly.Extensions.register("key_only", function (this: Blockly.Block) {
    this.setOnChange(() => {
      this.setWarningText(usesKey(this) && !underKey(this) ? "The key pressed only means something under \"when a key is pressed\"." : null);
    });
  });
  Blockly.defineBlocksWithJsonArray(BLOCKS);
  Blockly.Blocks.purple_setting.init = ((init) => function (this: Blockly.Block) {
    init.call(this);
    this.getField("NAME")!.setValidator((v: string) => v.toUpperCase().replace(/[^A-Z0-9_]/g, "_").replace(/^[^A-Z]+/, "") || null);
  })(Blockly.Blocks.purple_setting.init);
  defineGenerators();
  const style = (c: string) => ({ colourPrimary: c, colourSecondary: c, colourTertiary: c });
  Blockly.Theme.defineTheme("purple", {
    name: "purple",
    base: Blockly.Themes.Zelos,
    blockStyles: {
      ...Object.fromEntries(Object.entries(BLOCK_COLORS).map(([kind, c]) => [`${kind}_blocks`, style(c)])),
      logic_blocks: style(BLOCK_COLORS.game), loop_blocks: style(BLOCK_COLORS.game), math_blocks: style(BLOCK_COLORS.thing),
    },
    categoryStyles: Object.fromEntries(CATEGORIES.map(([name, colour]) => [`${name}_category`, { colour }])),
    componentStyles: {
      workspaceBackgroundColour: "#faf8f5", flyoutBackgroundColour: "#ffffff", flyoutForegroundColour: "#857698",
      flyoutOpacity: 1, scrollbarColour: "#c4aee0",
      insertionMarkerColour: "#5c2d91", insertionMarkerOpacity: 0.3, cursorColour: "#5c2d91",
    },
    fontStyle: { family: "Figtree, Inter, system-ui, sans-serif", weight: "500", size: 11 },
  });
}

// Toolbox -------------------------------------------------------------------------------

type BJ = { type: string; fields?: Record<string, unknown>; inputs?: Record<string, { block?: BJ; shadow?: BJ }>; next?: { block: BJ }; x?: number; y?: number };
// A plain value in a slot is a shadow: it's edited where it sits, and dropping another block on it replaces it.
const LITERALS = new Set(["purple_thing", "purple_color", "purple_things", "purple_text", "purple_number", "purple_square", "purple_key", "purple_note"]);
const slot = (v: BJ) => (LITERALS.has(v.type) ? { shadow: v } : { block: v });
const b = (type: string, fields: Record<string, unknown> = {}, inputs: Record<string, BJ> = {}): BJ =>
  ({ type, fields, inputs: Object.fromEntries(Object.entries(inputs).map(([k, v]) => [k, slot(v)])) });
const stack = (...bs: BJ[]): BJ => bs.reduceRight((next, cur) => ({ ...cur, next: { block: next } }));
const on = (type: string, fields: Record<string, unknown>, inputs: Record<string, BJ>, ...body: BJ[]) =>
  b(type, fields, { ...inputs, ...(body.length ? { DO: stack(...body) } : {}) });
const thing = (t: string) => b("purple_thing", { THING: t });
const text = (t: string) => b("purple_text", { TEXT: t });
const num = (n: number) => b("purple_number", { NUM: n });
const square = (x: number, y: number) => b("purple_square", { SQUARE: `${x},${y}` });
const color = (c: string) => b("purple_color", { COLOR: c });
const key = (k: string) => b("purple_key", { KEY: k });
const pressed = () => b("purple_key_pressed");
const that = () => b("purple_that_key");
const score = (name: string) => b("purple_get", { VAR: { name } });
const setting = (name: string) => b("purple_setting_get", { NAME: name });

// [category, color, its blocks], each block as it comes out of the toolbox.
export const CATEGORIES: [string, string, BJ[]][] = [
  ["When", BLOCK_COLORS.event, [on("purple_on_key", {}, {}), on("purple_on_start", {}, {}), on("purple_on_this_key", {}, {}),
    on("purple_every", {}, { SECONDS: num(1) }), on("purple_on_meet", {}, { THING: thing("⭐") })]],
  ["Show and say", BLOCK_COLORS.screen, [b("purple_say", {}, { TEXT: text("Hello!") }), b("purple_show", {}, { TEXT: thing("🎉") }),
    b("purple_play", {}, { NOTE: b("purple_note", { NOTE: "C4" }) }), b("purple_drum"), b("purple_write", {}, { TEXT: text("Hello!") }),
    b("purple_status", {}, { TEXT: text("Find the stars!") }), b("purple_background", {}, { COLOR: color("#1e1033") }), b("purple_clear")]],
  ["Grid", BLOCK_COLORS.grid, [b("purple_put", {}, { THING: thing("⭐"), SQUARE: square(13, 6) }), b("purple_erase", {}, { SQUARE: square(13, 6) }),
    b("purple_random_square"), square(13, 6), b("purple_floor", {}, { COLOR: color("#4a8a50"), SQUARE: square(13, 6) }),
    b("purple_ring_put", {}, { SQUARE: square(13, 6) }), b("purple_ring_move"), b("purple_ring_square"),
    b("purple_move_all", { WAY: "down" }, { THING: thing("🍎") }), b("purple_what_at", {}, { SQUARE: square(13, 6) }), b("purple_is_empty", {}, { SQUARE: square(13, 6) })]],
  ["Things", BLOCK_COLORS.thing, [thing("⭐"), text("Hello!"), num(1), color("#4a8a50"), b("purple_one_of", {}, { LIST: b("purple_things") }), b("purple_things"),
    b("purple_any_picture"), b("purple_join", {}, { A: text("⭐ "), B: score("score") }),
    b("purple_pot_add", {}, { COLOR: color("#e0c020") }), b("purple_pot_empty"), b("purple_pot_color")]],
  ["Keys", BLOCK_COLORS.key, [pressed(), b("purple_key_letter", {}, { KEY: pressed() }), b("purple_key_color", {}, { KEY: pressed() }),
    b("purple_key_note", {}, { KEY: pressed() }), b("purple_key_spot", {}, { KEY: pressed() }), b("purple_each_key"), that(), key("q")]],
  ["Player", BLOCK_COLORS.player, [b("purple_player_put", {}, { THING: thing("🧒"), SQUARE: square(13, 6) }), b("purple_player_move"),
    b("purple_wall", {}, { THING: thing("🌳") }), b("purple_player_square")]],
  ["Game", BLOCK_COLORS.game, [b("purple_set", {}, { VALUE: num(0) }), b("purple_change", {}, { BY: num(1) }), score("score"),
    b("controls_if"), b("logic_compare", {}, { A: score("score"), B: num(10) }), b("purple_after", {}, { SECONDS: num(1) }),
    b("controls_repeat_ext", {}, { TIMES: num(5) }), b("purple_game_over", {}, { TEXT: text("You did it! Press a key to play again.") }),
    b("math_random_int", {}, { FROM: num(1), TO: num(6) }), b("math_arithmetic", {}, { A: num(1), B: num(1) }), b("logic_operation"), b("logic_negate")]],
  ["Settings", BLOCK_COLORS.setting, [b("purple_setting", {}, { VALUE: thing("🍎") }), setting("FRUIT")]],
];

export const TOOLBOX = {
  kind: "categoryToolbox",
  contents: CATEGORIES.map(([name, , blocks]) => ({ kind: "category", name, categorystyle: `${name}_category`,
    contents: [{ kind: "label", text: name, "web-class": "drawer-title" }, { kind: "label", text: "Click to add, or drag out", "web-class": "drawer-hint" },
      ...blocks.map((x) => ({ kind: "block", ...x }))] })),
};

// Workspace -> Python ---------------------------------------------------------------------

const INDENT = "    ";
// What the blocks in use need from the top of the file; set while toPython runs.
type Need = "keyboard" | "player" | "move_all" | "pot";
let needs = new Set<Need>();
let laterCount = 0;

const indent = (code: string) => code.split("\n").map((l) => (l ? INDENT + l : l)).join("\n");
const dedent = (code: string) => code.split("\n").map((l) => (l.startsWith(INDENT) ? l.slice(INDENT.length) : l)).join("\n");
const body = (block: Blockly.Block, name = "DO") => py.statementToCode(block, name) || `${INDENT}pass\n`;
const val = (block: Blockly.Block, name: string, fallback = '""') => py.valueToCode(block, name, Order.NONE) || fallback;
const atom = (code: string): [string, Order] => [code, Order.ATOMIC];
const need = (n: Need, code: string) => { needs.add(n); return code; };
// A Python name for a game value: "high score" is game.high_score.
const pyName = (text: string) => {
  const name = text.toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "") || "value";
  return /^\d/.test(name) ? `n${name}` : name;
};
const varName = (block: Blockly.Block) => pyName(block.getField("VAR")!.getText());
const isLiteral = (code: string) => /^"([^"\\]|\\.)*"$/.test(code);
const asText = (code: string) => (isLiteral(code) ? code : `str(${code})`);
const sized = (block: Blockly.Block) => (block.getFieldValue("SIZE") === "1" ? "" : `, size=${block.getFieldValue("SIZE")}`);
const RANDOM_SQUARE: Record<string, string> = {
  empty: "grid.random_empty()", top: "(random.randrange(grid.w), 0)", bottom: "(random.randrange(grid.w), grid.h - 1)",
  left: "(0, random.randrange(grid.h))", right: "(grid.w - 1, random.randrange(grid.h))",
};
const KEY_TESTS: Record<string, string> = {
  arrow: "key in ARROWS", not_arrow: "key not in ARROWS", keyboard: "key in spots", number: "key.isdigit()", space: 'key == "space"', enter: 'key == "enter"',
};

// The arrow's way, or a fixed one. Out from under a key block, the arrow's way is no way, rather than a room that stops.
const move = (b: Blockly.Block, call: string) => (usesKey(b) && !underKey(b) ? "" : `${call}(${usesKey(b) ? "key" : lit(b.getFieldValue("WAY"))})\n`);

function defineGenerators(): void {
  const f = py.forBlock;
  f.purple_player_put = (b) => need("player", `player.look, player.at = ${val(b, "THING")}, ${val(b, "SQUARE", "(13, 6)")}\ngrid.set(player.at, player.look)\n`);
  f.purple_player_move = (b) => {
    const code = move(b, "move_player");
    return code && need("player", code);
  };
  f.purple_wall = (b) => need("player", `walls.add(${asText(val(b, "THING"))})\n`);
  f.purple_player_square = () => atom(need("player", "player.at"));

  f.purple_put = (b) => `grid.set(${val(b, "SQUARE", "(13, 6)")}, ${val(b, "THING")}${sized(b)})\n`;
  f.purple_floor = (b) => `grid.floor.set(${val(b, "SQUARE", "(13, 6)")}, ${val(b, "COLOR", '"tile"')}${sized(b)})\n`;
  f.purple_erase = (b) => `grid.erase(${val(b, "SQUARE", "(13, 6)")})\n`;
  f.purple_move_all = (b) => need("move_all", `move_all(${val(b, "THING")}, ${lit(b.getFieldValue("WAY"))})\n`);
  f.purple_square = (b) => atom(`(${b.getFieldValue("SQUARE").replace(",", ", ")})`);
  f.purple_random_square = (b) => atom(RANDOM_SQUARE[b.getFieldValue("WHERE")]);
  f.purple_what_at = (b) => atom(`grid.get(${val(b, "SQUARE", "(13, 6)")})`);
  f.purple_is_empty = (b) => [`grid.get(${val(b, "SQUARE", "(13, 6)")}) is None`, Order.RELATIONAL];
  f.purple_ring_put = (b) => `grid.cursor(${val(b, "SQUARE", "(13, 6)")})\n`;
  f.purple_ring_move = (b) => move(b, "grid.move");
  f.purple_ring_square = () => atom("grid.here");

  f.purple_key_pressed = () => atom("key");
  f.purple_key = (b) => atom(lit(b.getFieldValue("KEY")));
  f.purple_each_key = (b) => need("keyboard", `for that_key in spots:\n${body(b)}`);
  f.purple_that_key = () => atom("that_key");
  f.purple_key_spot = (b) => atom(need("keyboard", `spots[${val(b, "KEY", "key")}]`));
  f.purple_key_letter = (b) => atom(`${val(b, "KEY", "key")}.upper()`);
  f.purple_key_color = (b) => atom(`KEY_COLORS.get(${val(b, "KEY", "key")}, "tile")`);
  f.purple_key_note = (b) => atom(`KEY_NOTES.get(${val(b, "KEY", "key")}, "C4")`);

  f.purple_thing = (b) => {
    const v: string = b.getFieldValue("THING");
    return atom(v.startsWith(PIC) ? `picture(${lit(v.slice(PIC.length))})` : lit(v));
  };
  f.purple_color = (b) => atom(lit(b.getFieldValue("COLOR")));
  f.purple_things = (b) => atom(`[${String(b.getFieldValue("THINGS")).split(/\s+/).filter(Boolean).map(lit).join(", ")}]`);
  f.purple_one_of = (b) => atom(`random.choice(${val(b, "LIST", "[]")})`);
  f.purple_text = (b) => atom(lit(b.getFieldValue("TEXT")));
  f.purple_number = (b) => atom(String(Number(b.getFieldValue("NUM"))));
  f.purple_join = (b) => [`${asText(val(b, "A"))} + ${asText(val(b, "B"))}`, Order.ADDITIVE];
  f.purple_any_picture = () => atom("picture()");
  f.purple_pot_add = (b) => need("pot", `pot.append(${val(b, "COLOR", '"#ffffff"')})\ndel pot[:-6]\n`);
  f.purple_pot_empty = () => need("pot", "pot.clear()\n");
  f.purple_pot_color = () => [need("pot", 'mix(*pot) if pot else "tile"'), Order.CONDITIONAL];
  f.purple_note = (b) => atom(lit(b.getFieldValue("NOTE")));

  f.purple_show = (b) => `show(${val(b, "TEXT")})\n`;
  f.purple_write = (b) => `write(${val(b, "TEXT")})\n`;
  f.purple_status = (b) => `status(${val(b, "TEXT")})\n`;
  f.purple_clear = () => "clear()\n";
  f.purple_background = (b) => `background(${val(b, "COLOR", '"surface"')})\n`;
  f.purple_say = (b) => `say(${val(b, "TEXT")})\n`;
  f.purple_play = (b) => `play(${val(b, "NOTE", '"C4"')}, ${lit(b.getFieldValue("INSTRUMENT") || "marimba")})\n`;
  f.purple_drum = (b) => `drum(${lit(b.getFieldValue("DRUM") || DRUMS[0])})\n`;

  f.purple_set = (b) => `game.${varName(b)} = ${val(b, "VALUE", "0")}\n`;
  f.purple_change = (b) => `game.${varName(b)} += ${val(b, "BY", "1")}\n`;
  f.purple_get = (b) => atom(`game.${varName(b)}`);
  f.purple_after = (b) => {
    const fn = `later_${++laterCount}`;
    return `def ${fn}():\n${body(b)}after(${val(b, "SECONDS", "1")}, ${fn})\n`;
  };
  f.purple_game_over = (b) => `game_over(${val(b, "TEXT", '"Press a key to play again"')})\n`;
  f.purple_setting_get = (b) => atom(b.getFieldValue("NAME"));
  // Hats and settings are written by toPython, never inside a stack.
  for (const t of ["purple_on_start", "purple_on_key", "purple_on_this_key", "purple_every", "purple_on_meet", "purple_setting"]) f[t] = () => "";
}

// What each need adds to the top of the file: plain lines, then its function.
const HELPERS: Record<Need, (meets: boolean) => [lines: string, def: string]> = {
  keyboard: () => ["spots = grid.keyboard()\n", ""],
  pot: () => ["pot = []\n", ""],
  player: (meets) => ['player = state(at=(13, 6), look="🧒")\nwalls = set()\n', `def move_player(way):
    if way not in ARROWS:
        return
    dx, dy = ARROWS[way]
    x, y = player.at
    there = grid.get(x + dx, y + dy)
    if str(there) in walls:
        return
    grid.erase(player.at)
    player.at = ((x + dx) % grid.w, (y + dy) % grid.h)
    grid.set(player.at, player.look)${meets ? "\n    if there is not None:\n        meet(there)" : ""}
`],
  move_all: (meets) => ["", `def move_all(thing, way):
    dx, dy = ARROWS[way]
    moving = [(x, y) for x in range(grid.w) for y in range(grid.h) if str(grid.get(x, y)) == str(thing)]
    for spot in moving:
        grid.erase(spot)
    for x, y in moving:
        to = (x + dx, y + dy)${meets ? "\n        if to == player.at:\n            meet(thing)" : ""}
        ${meets ? "elif" : "if"} 0 <= to[0] < grid.w and 0 <= to[1] < grid.h:
            grid.set(to, thing)
`],
};

const literalSetting = (block: Blockly.Block) => {
  const about = String(block.getFieldValue("ABOUT")).trim();
  return `${about && about !== "what it's for" ? `# ${about.replace(/\n/g, " ")}\n` : ""}${block.getFieldValue("NAME")} = ${val(block, "VALUE", "None")}\n`;
};

export function toPython(ws: Blockly.Workspace): string {
  py.INDENT = INDENT;
  py.init(ws);
  needs = new Set();
  laterCount = 0;
  const tops = ws.getTopBlocks(true);
  const of = (type: string) => tops.filter((t) => t.type === type);
  const settings = of("purple_setting").map(literalSetting);
  const start = of("purple_on_start").map((t) => dedent(py.statementToCode(t, "DO")));
  const keys = [...of("purple_on_key"), ...of("purple_on_this_key")].map((t) => {
    const code = py.statementToCode(t, "DO");
    const test = t.type === "purple_on_this_key" ? `key == ${lit(t.getFieldValue("KEY"))}` : KEY_TESTS[t.getFieldValue("WHICH")];
    if (test === "key in spots") needs.add("keyboard");
    return !code ? "" : test ? `${INDENT}if ${test}:\n${indent(code)}` : code;
  }).filter(Boolean);
  const meets = of("purple_on_meet").map((t) => `${INDENT}if str(thing) == ${asText(val(t, "THING"))}:\n${indent(body(t))}`);
  const timers = of("purple_every").map((t, i) => [`def every_${i + 1}():\n${body(t)}`, `every(${val(t, "SECONDS", "1")}, every_${i + 1})\n`]);
  // Moving things meet the player, so they need one.
  if (meets.length && needs.has("move_all")) needs.add("player");
  const vars = [...new Set(ws.getVariableMap().getAllVariables().map((v) => pyName(v.getName())))];
  const helpers = (["keyboard", "pot", "player", "move_all"] as Need[]).filter((n) => needs.has(n)).map((n) => HELPERS[n](meets.length > 0));
  const lines = [vars.length ? `game = state(${vars.map((v) => `${v}=0`).join(", ")})\n` : "", ...helpers.map(([l]) => l)].join("");
  const defs = [...helpers.map(([, d]) => d), keys.length ? `def on_key(key):\n${keys.join("")}` : "",
    meets.length ? `def meet(thing):\n${meets.join("")}` : "", ...timers.map(([def]) => def)];
  const top = ["from purple import *\n", settings.join(""), lines].filter(Boolean).join("\n");
  const source = [top, ...defs, start.join("") + timers.map(([, go]) => go).join("")].filter((p) => p.trim()).join("\n\n").trimEnd() + "\n";
  return /\brandom\./.test(source) ? `import random\n\n${source}` : source;
}

// The Python for a saved workspace, without drawing it.
export function blocksSource(state: object): string {
  defineBlocks();
  const ws = new Blockly.Workspace();
  try {
    Blockly.serialization.workspaces.load(state, ws);
    return toPython(ws);
  } finally {
    ws.dispose();
  }
}

// Knobs -> blocks ---------------------------------------------------------------------------

type Saved = { blocks?: { blocks?: BJ[] } };

// The literal block for a value a knob holds, or null for one blocks can't show.
function literalBlock(v: Lit): BJ | null {
  if (v.t === "num") return num(v.v);
  if (v.t === "picture") return thing(PIC + v.v);
  if (v.t === "str") return /^#[0-9a-f]{6}$/i.test(v.v) || COLORS.some(([, c]) => c === v.v) ? color(v.v) : /[a-z0-9]/i.test(v.v) ? text(v.v) : thing(v.v);
  if (v.t === "list" && v.items.every((x) => x.t === "str" && !/\s/.test(x.v))) return b("purple_things", { THINGS: v.items.map((x) => (x as { v: string }).v).join(" ") });
  return null;
}

// Each knob's value written into its setting block, so the Knobs tab and the blocks stay one room.
export function applyKnobs(state: object, knobs: Knob[]): void {
  for (const top of (state as Saved).blocks?.blocks ?? []) {
    const knob = top.type === "purple_setting" && knobs.find((k) => k.name === top.fields?.NAME);
    const block = knob && literalBlock(knob.value);
    if (block) top.inputs = { ...top.inputs, VALUE: slot(block) };
  }
}

// Starters ---------------------------------------------------------------------------------

// A workspace of top blocks, with no places yet: the editor lays them out down the page when it opens.
const workspace = (vars: string[], ...tops: BJ[]): object =>
  ({ blocks: { languageVersion: 0, blocks: tops }, variables: vars.map((name) => ({ name, id: name })) });

const settingOf = (name: string, about: string, v: BJ) => b("purple_setting", { NAME: name, ABOUT: about }, { VALUE: v });

// The Rooms page's whole room, in blocks: every key puts a dog on the screen.
export const WHOLE_ROOM_BLOCKS = () => workspace([], on("purple_on_key", { WHICH: "any" }, {},
  b("purple_put", { SIZE: "1" }, { THING: thing("🐶"), SQUARE: b("purple_random_square", { WHERE: "empty" }) }),
  b("purple_drum", { DRUM: "bongo" }),
  b("purple_say", {}, { TEXT: pressed() })));

// The same starters as a Python room's, in the same order: Flowers first, where "Start with blocks" opens.
const keySquare = (key: BJ) => b("purple_key_spot", {}, { KEY: key });
const potAt = () => b("purple_put", { SIZE: "8" }, { THING: b("purple_pot_color"), SQUARE: square(9, 2) });
export const BLOCK_STARTERS: { icon: string; label: string; workspace: () => object }[] = [
  { icon: "🌸", label: "Flowers", workspace: () => workspace([],
    on("purple_on_start", {}, {},
      b("purple_put", { SIZE: "1" }, { THING: thing("👋"), SQUARE: square(10, 5) }),
      b("purple_put", { SIZE: "1" }, { THING: thing("🌟"), SQUARE: square(15, 5) }),
      b("purple_ring_put", {}, { SQUARE: square(12, 7) })),
    on("purple_on_key", { WHICH: "arrow" }, {}, b("purple_ring_move", { WAY: "key" })),
    on("purple_on_key", { WHICH: "not_arrow" }, {}, b("purple_put", { SIZE: "1" }, { THING: thing("🌸"), SQUARE: b("purple_ring_square") }))) },
  { icon: "🎨", label: "Paint", workspace: () => workspace([],
    on("purple_on_start", {}, {},
      b("purple_status", {}, { TEXT: text("Press a letter or number key to mix its color into the pot, Space empties it") }),
      potAt()),
    on("purple_on_key", { WHICH: "keyboard" }, {},
      b("purple_pot_add", {}, { COLOR: b("purple_key_color", {}, { KEY: pressed() }) }),
      b("purple_put", { SIZE: "2" }, { THING: b("purple_key_color", {}, { KEY: pressed() }), SQUARE: square(5, 5) }),
      potAt()),
    on("purple_on_key", { WHICH: "space" }, {}, b("purple_pot_empty"), b("purple_erase", {}, { SQUARE: square(5, 5) }), potAt())) },
  { icon: "📷", label: "Photo", workspace: () => workspace([],
    on("purple_on_start", {}, {}, b("purple_show", {}, { TEXT: thing("📷") })),
    on("purple_on_key", { WHICH: "any" }, {}, b("purple_show", {}, { TEXT: b("purple_any_picture") }))) },
  { icon: "🎹", label: "Light the keys", workspace: () => workspace([],
    on("purple_on_start", {}, {},
      b("purple_each_key", {}, { DO: b("purple_put", { SIZE: "1" }, { THING: b("purple_key_letter", {}, { KEY: that() }), SQUARE: keySquare(that()) }) })),
    on("purple_on_key", { WHICH: "keyboard" }, {},
      b("purple_floor", { SIZE: "1" }, { COLOR: b("purple_key_color", {}, { KEY: pressed() }), SQUARE: keySquare(pressed()) }),
      b("purple_play", { INSTRUMENT: "marimba" }, { NOTE: b("purple_key_note", {}, { KEY: pressed() }) }))) },
];

// For tests that build their own small rooms.
export const build = { b, on, thing, text, num, square, score, workspace, settingOf };
