// The block editor: Blockly with Purple's blocks, and the pickers its fields open. Loaded only when a room
// made of blocks opens, so the rest of Studio never waits for Blockly.
import * as Blockly from "blockly";
import { BLOCK_COLORS, CATEGORIES, COLORS, colorLooks, defineBlocks, PIC, pickers, toPython, TOOLBOX, type PickerField } from "../blocks";
import { ask, askText, h, tell } from "./dom";
import { isEmoji, openEmojiPicker } from "./emojipicker";
import { sticker } from "./stickers";
import { WIDER } from "./view";

export { applyKnobs, BLOCK_STARTERS, blocksSource, WHOLE_ROOM_BLOCKS } from "../blocks";

const KEY_ROWS = ["1234567890", "qwertyuiop", "asdfghjkl;", "zxcvbnm,./"];
const MORE_KEYS: [string, string][] = [["space", "Space"], ["enter", "Enter"], ["up", "↑"], ["down", "↓"], ["left", "←"], ["right", "→"]];

function dropDown(field: PickerField, content: HTMLElement) {
  Blockly.DropDownDiv.getContentDiv().replaceChildren(content);
  Blockly.DropDownDiv.setColour("#ffffff", "#c4aee0");
  Blockly.DropDownDiv.showPositionedByField(field);
}

const choose = (field: PickerField, v: string) => () => {
  field.setValue(v);
  Blockly.DropDownDiv.hideIfOwner(field);
};

// Blockly's confirms, alerts, and prompts (deleting every block, renaming a score) in Studio's own dialogs.
const yesFor = (message: string) => /^(Delete|Rename)\b/.exec(message)?.[1] ?? "OK";
function setUpDialogs() {
  Blockly.dialog.setConfirm((message, done) => void ask(message, yesFor(message)).then(done));
  Blockly.dialog.setAlert((message, done) => void tell(message).then(() => done?.()));
  Blockly.dialog.setPrompt((message, value, done) => void askText(message, value, yesFor(message)).then(done));
}

function setUpPickers() {
  pickers.square = (field) => {
    const at = field.getValue();
    dropDown(field, h("div", { class: "square-pick" }, ...Array.from({ length: 26 * 12 }, (_, i) => {
      const v = `${i % 26},${Math.floor(i / 26)}`;
      return h("button", { type: "button", title: `${i % 26} across, ${Math.floor(i / 26)} down`, "aria-pressed": String(v === at), onclick: choose(field, v) });
    })));
  };
  pickers.key = (field) => dropDown(field, h("div", { class: "key-pick" },
    ...KEY_ROWS.map((row) => h("div", {}, ...[...row].map((k) => h("button", { type: "button", onclick: choose(field, k) }, sticker(k))))),
    h("div", {}, ...MORE_KEYS.map(([k, label]) => h("button", { type: "button", class: "word", onclick: choose(field, k) }, label)))));
  pickers.color = (field) => {
    const own = h("input", { type: "color", value: /^#/.test(field.getValue() ?? "") ? field.getValue()! : "#4a8a50", title: "Any color" });
    own.onchange = choose(field, own.value);
    dropDown(field, h("div", { class: "color-pick" },
      ...COLORS.map(([name, c]) => h("button", { type: "button", title: name, style: `background:${colorLooks(c)}`, onclick: choose(field, c) })), own));
  };
  pickers.setting = (field) => {
    const names = field.getSourceBlock()!.workspace.getTopBlocks(false).filter((t) => t.type === "purple_setting").map((t) => t.getFieldValue("NAME") as string);
    dropDown(field, h("div", { class: "setting-pick" }, ...(names.length
      ? names.map((n) => h("button", { type: "button", onclick: choose(field, n) }, n))
      : [h("p", { class: "dim small" }, "Make a knob first: it's in Knobs.")])));
  };
  // Studio's own emoji picker, which offers the family's pictures too, opened where the field is.
  pickers.emoji = (field) => {
    const box = field.getSvgRoot()!.getBoundingClientRect();
    const anchor = h("button", { type: "button", class: "block-anchor" });
    const wrap = h("div", { class: "emoji-wrap block-emoji", style: `left:${box.left}px;top:${box.bottom - 48}px` }, anchor);
    document.body.append(wrap);
    openEmojiPicker(anchor, "", (e) => {
      wrap.remove();
      if (e) field.setValue(isEmoji(e) ? e : PIC + e);
    }, { pictures: true, title: "Pick an emoji or one of your pictures", onClose: () => wrap.remove() });
  };
}

// A block clicked in the palette goes where the family is working: right after the picked block, inside a
// "when" block's empty space, or into the picked block's first slot that takes it. Otherwise it waits below the rest.
function attach(ws: Blockly.WorkspaceSvg, block: Blockly.BlockSvg, picked: Blockly.BlockSvg | null) {
  let at = picked && !picked.isDeadOrDying() ? picked : null;
  if (block.outputConnection) {
    const slot = at?.inputList.map((i) => i.connection).find((c) => c?.type === Blockly.ConnectionType.INPUT_VALUE
      && (!c.targetBlock() || c.targetBlock()!.isShadow()) && ws.connectionChecker.canConnect(c, block.outputConnection, false));
    if (slot) return slot.connect(block.outputConnection);
  } else if (block.previousConnection) {
    while (at?.outputConnection && at.getParent()) at = at.getParent();
    const inside = at?.getInput("DO")?.connection;
    const to = inside ? (inside.targetBlock()?.lastConnectionInStack(true) ?? inside) : at?.nextConnection;
    if (to && ws.connectionChecker.canConnect(to, block.previousConnection, false)) return to.connect(block.previousConnection);
  }
  const below = ws.getBlocksBoundingBox();
  block.moveTo(new Blockly.utils.Coordinate(below.left, below.bottom + 32));
}

// How much of the canvas's left the open drawer covers; on a phone it opens along the bottom instead.
const drawerWidth = (ws: Blockly.WorkspaceSvg) => {
  const fly = ws.getToolbox()?.getFlyout();
  return fly?.isVisible() && !ws.horizontalLayout ? fly.getWidth() : 0;
};

// The blocks start at the canvas's top left, or just right of the open drawer, so they never hide under it.
function home(ws: Blockly.WorkspaceSvg, top = false) {
  const box = ws.getBlocksBoundingBox();
  ws.scroll(drawerWidth(ws) + 24 - box.left * ws.scale, top ? 24 - box.top * ws.scale : ws.scrollY);
}

// A faint white pattern on some kinds of block, so they tell apart by more than color: squares on grid blocks,
// dots on keys, stripes on scores. Matched by the fill Blockly gives each block, so it reaches flyouts and pictures too.
const PATTERNS: Partial<Record<keyof typeof BLOCK_COLORS, string>> = {
  grid: '<path d="M12 0V12H0" fill="none" stroke="#fff" stroke-opacity=".12"/>',
  key: '<circle cx="6" cy="6" r="1.4" fill="#fff" fill-opacity=".16"/>',
  score: '<path d="M-3 3 3-3M0 12 12 0M9 15 15 9" stroke="#fff" stroke-opacity=".12" stroke-width="2.5"/>',
};
function addPatterns() {
  if (document.getElementById("block-patterns")) return;
  const kinds = Object.entries(PATTERNS) as [keyof typeof BLOCK_COLORS, string][];
  const box = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  box.id = "block-patterns";
  box.setAttribute("style", "position:absolute;width:0;height:0");
  box.innerHTML = `<defs>${kinds.map(([k, art]) => `<pattern id="pattern-${k}" width="12" height="12" patternUnits="userSpaceOnUse">` +
    `<rect width="12" height="12" fill="${BLOCK_COLORS[k]}"/>${art}</pattern>`).join("")}</defs>` +
    `<style>${kinds.map(([k]) => `:not(.blocklyDisabledPattern) > .blocklyPath[fill="${BLOCK_COLORS[k]}"] { fill: url(#pattern-${k}); }`).join("")}</style>`;
  document.body.append(box);
}

// Under the blocks: what the picked one does, and where the Room guide says more.
const HINT = "Open a drawer above, then click a block to add it or drag it out. Click a block here to see what it does.";
function helpLine(): [HTMLElement, (block: Blockly.Block | null) => void] {
  const line = h("p", { class: "block-help" }, HINT);
  return [line, (block) => {
    const about = block && Blockly.Tooltip.getTooltipOfObject(block);
    const url = block && (typeof block.helpUrl === "function" ? block.helpUrl() : block.helpUrl);
    line.replaceChildren(...(about ? [about, url ? h("a", { href: url, target: "_blank" }, "More in the Room guide") : ""] : [HINT]));
  }];
}

let current: Blockly.WorkspaceSvg | null = null;
let shown: Blockly.WorkspaceSvg | null = null;

const purpleTheme = () => Blockly.registry.getObject(Blockly.registry.Type.THEME, "purple") as Blockly.Theme;

// Blocks to look at, not change: as tall as their box, cut off on the right like the Python beside them.
export function blocksPicture(workspace: object): HTMLElement {
  defineBlocks();
  addPatterns();
  const div = h("div", {});
  requestAnimationFrame(() => {
    shown?.dispose();
    shown = Blockly.inject(div, { renderer: "zelos", theme: purpleTheme(), media: "blockly/", sounds: false,
      move: { scrollbars: false, drag: false, wheel: false }, zoom: { controls: false, wheel: false, maxScale: 0.8, minScale: 0.2 } });
    Blockly.serialization.workspaces.load(workspace, shown);
    const ws = shown;
    void Blockly.renderManagement.finishQueuedRenders().then(() => {
      const box = ws.getBlocksBoundingBox();
      ws.setScale(Math.min(0.8, (div.clientHeight - 16) / (box.bottom - box.top)));
      ws.translate(8 - box.left * ws.scale, 8 - box.top * ws.scale);
    });
  });
  return div;
}

// The editor for made.workspace, saving each change into it and handing back the Python.
export function blocksForm(made: { workspace: object }, onEdit: (source: string) => void): HTMLElement {
  defineBlocks();
  setUpPickers();
  setUpDialogs();
  addPatterns();
  Blockly.config.snapRadius = 48;
  Blockly.config.connectingSnapRadius = 64;
  const div = h("div", { class: "blockly" });
  const [help, explain] = helpLine();
  // The categories are tabs above the blocks; Blockly's own toolbox stays hidden and opens the drawer for them.
  let editor: Blockly.WorkspaceSvg | null = null;
  const toolbox = () => editor!.getToolbox() as Blockly.Toolbox;
  const showing = () => (toolbox().getFlyout()?.isVisible() ? (toolbox().getSelectedItem() as Blockly.ToolboxCategory | null)?.getName() : undefined);
  const tabs = CATEGORIES.map(([name, color]) => h("button", { type: "button", style: `--c:${color}`, "aria-pressed": "false",
    onclick: () => editor && openDrawer(showing() === name ? null : name) }, name));
  const close = h("button", { type: "button", class: "drawer-close", title: "Close", "aria-label": "Close", hidden: true, onclick: () => openDrawer(null) }, "×");
  // The tabs show which drawer is open, and the drawer's close button sits in its top right corner.
  const sync = () => {
    tabs.forEach((t) => t.setAttribute("aria-pressed", String(t.textContent === showing())));
    undo.disabled = !editor!.getUndoStack().length;
    redo.disabled = !editor!.getRedoStack().length;
    const fly = toolbox().getFlyout()!;
    close.hidden = !fly.isVisible();
    if (fly.isVisible()) Object.assign(close.style, editor!.horizontalLayout
      ? { left: `${div.clientWidth - 44}px`, top: `${div.clientHeight - fly.getHeight() + 8}px` } : { left: `${fly.getWidth() - 48}px`, top: "8px" });
  };
  // The drawer's width the blocks were last moved for: they move again when it opens or closes, but not mid-drag.
  let homedFor = 0;
  const settle = () => {
    if (editor!.isDragging() || drawerWidth(editor!) === homedFor) return;
    homedFor = drawerWidth(editor!);
    home(editor!);
  };
  const openDrawer = (name: string | null) => {
    toolbox().clearSelection();
    const item = toolbox().getToolboxItems().find((i) => (i as Blockly.ToolboxCategory).getName?.() === name);
    if (item) toolbox().setSelectedItem(item as Blockly.ISelectableToolboxItem);
    settle();
    sync();
  };
  const tool = (label: string, title: string, go: (ws: Blockly.WorkspaceSvg) => void, cls = "") =>
    h("button", { type: "button", class: cls, title, "aria-label": title, onclick: () => editor && go(editor) }, label);
  // These move the blocks, which then go back to the top left.
  const settled = (go: (ws: Blockly.WorkspaceSvg) => void) => (ws: Blockly.WorkspaceSvg) => { go(ws); home(ws, true); };
  // Deleted blocks come back with Undo, rather than from a look inside the trash.
  const undo = tool("", "Undo", (ws) => ws.undo(false), "icon undo");
  const redo = tool("", "Redo", (ws) => ws.undo(true), "icon redo");
  undo.disabled = redo.disabled = true;
  const tools = h("span", { class: "block-tools" }, undo, redo,
    tool("−", "Smaller", settled((ws) => ws.zoomCenter(-1))), tool("+", "Bigger", settled((ws) => ws.zoomCenter(1))),
    tool("Tidy up", "Line the blocks up", settled((ws) => ws.cleanUp())),
    tool("", "More room for the blocks, or back", () => document.dispatchEvent(new Event(WIDER)), "icon wider"));
  requestAnimationFrame(() => {
    current?.dispose();
    const phone = matchMedia("(max-width: 700px)").matches;
    const ws = editor = current = Blockly.inject(div, {
      toolbox: TOOLBOX, renderer: "zelos", media: "blockly/", sounds: false, trashcan: true, maxTrashcanContents: 0,
      theme: purpleTheme(), horizontalLayout: phone, toolboxPosition: phone ? "end" : "start",
      zoom: { controls: false, wheel: false, startScale: 0.7, minScale: 0.4, maxScale: 1.2 }, move: { scrollbars: true, drag: true, wheel: true },
      grid: { spacing: 24, length: 3, colour: "#e3dcec", snap: false },
    });
    // Opening the room isn't a change to it. A starter's blocks have no places yet, so they're laid out here.
    Blockly.Events.disable();
    Blockly.serialization.workspaces.load(made.workspace, ws);
    if (!("x" in ((made.workspace as { blocks?: { blocks?: object[] } }).blocks?.blocks?.[0] ?? { x: 0 }))) ws.cleanUp();
    Blockly.Events.enable();
    div.append(close);
    // Blockly sizes itself to the window, not its box, so a wider editor pane needs telling.
    new ResizeObserver(() => Blockly.svgResize(ws)).observe(div);
    void Blockly.renderManagement.finishQueuedRenders().then(() => home(ws, true));
    // The drawer stays open while blocks are added from it; a click on the canvas, Esc, or its close button closes it.
    toolbox().getFlyout()!.autoClose = false;
    let picked: Blockly.BlockSvg | null = ws.getTopBlocks(true)[0] ?? null;
    if (picked) Blockly.common.setSelected(picked);
    ws.addChangeListener((e: Blockly.Events.Abstract) => {
      sync();
      settle();
      if (e.type === Blockly.Events.CLICK && (e as Blockly.Events.Click).targetType === "workspace") openDrawer(null);
      if (e.type === Blockly.Events.SELECTED) {
        const block = ws.getBlockById((e as Blockly.Events.Selected).newElementId ?? "");
        picked = block ?? picked;
        explain(block);
      }
      // A block made by a click in the palette, not a drag out of it.
      if (e.type === Blockly.Events.BLOCK_CREATE) {
        setTimeout(() => {
          const block = ws.getBlockById((e as Blockly.Events.BlockCreate).blockId ?? "");
          if (!block || ws.isDragging() || block.getParent() || block.nextConnection?.isConnected()) return;
          attach(ws, block, picked);
          // Keeps the stacks in a column, so a longer one never runs into the next.
          ws.cleanUp();
          Blockly.common.setSelected(block);
          ws.scrollBoundsIntoView(block.getBoundingRectangle(), 40);
          home(ws);
        });
      }
      if (e.isUiEvent || ws.isDragging()) return;
      made.workspace = Blockly.serialization.workspaces.save(ws);
      onEdit(toPython(ws));
    });
  });
  return h("div", { class: "blocks-editor", onkeydown: (e: KeyboardEvent) => e.key === "Escape" && editor && openDrawer(null) },
    h("div", { class: "block-bar" }, h("div", { class: "block-tabs" }, ...tabs), tools), div, help);
}
