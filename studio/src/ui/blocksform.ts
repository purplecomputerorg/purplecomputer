// The block editor: Blockly with Purple's blocks, and the pickers its fields open. Loaded only when a room
// made of blocks opens, so the rest of Studio never waits for Blockly.
import * as Blockly from "blockly";
import { COLORS, colorLooks, defineBlocks, PIC, pickers, toPython, TOOLBOX, type PickerField } from "../blocks";
import { h } from "./dom";
import { isEmoji, openEmojiPicker } from "./emojipicker";
import { sticker } from "./stickers";

export { applyKnobs, BLOCK_STARTERS, blocksSource } from "../blocks";

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
      : [h("p", { class: "dim small" }, "Make a setting first: it's in Settings.")])));
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

let current: Blockly.WorkspaceSvg | null = null;

// The editor for made.workspace, saving each change into it and handing back the Python.
export function blocksForm(made: { workspace: object }, onEdit: (source: string) => void): HTMLElement {
  defineBlocks();
  setUpPickers();
  Blockly.config.snapRadius = 48;
  Blockly.config.connectingSnapRadius = 64;
  const div = h("div", { class: "blockly" });
  requestAnimationFrame(() => {
    current?.dispose();
    const ws = current = Blockly.inject(div, {
      toolbox: TOOLBOX, renderer: "zelos", media: "blockly/", sounds: false, trashcan: true,
      theme: Blockly.registry.getObject(Blockly.registry.Type.THEME, "purple") as Blockly.Theme,
      zoom: { controls: true, wheel: false, startScale: 0.8 }, move: { scrollbars: true, drag: true, wheel: true },
      grid: { spacing: 24, length: 3, colour: "#e3dcec", snap: false },
    });
    // Opening the room isn't a change to it. A starter's blocks have no places yet, so they're laid out here.
    Blockly.Events.disable();
    Blockly.serialization.workspaces.load(made.workspace, ws);
    if (!("x" in ((made.workspace as { blocks?: { blocks?: object[] } }).blocks?.blocks?.[0] ?? { x: 0 }))) ws.cleanUp();
    Blockly.Events.enable();
    let picked: Blockly.BlockSvg | null = ws.getTopBlocks(true)[0] ?? null;
    if (picked) Blockly.common.setSelected(picked);
    ws.addChangeListener((e: Blockly.Events.Abstract) => {
      if (e.type === Blockly.Events.SELECTED) picked = ws.getBlockById((e as Blockly.Events.Selected).newElementId ?? "") ?? picked;
      // A block made by a click in the palette, not a drag out of it.
      if (e.type === Blockly.Events.BLOCK_CREATE) setTimeout(() => {
        const block = ws.getBlockById((e as Blockly.Events.BlockCreate).blockId ?? "");
        if (!block || ws.isDragging() || block.getParent() || block.nextConnection?.isConnected()) return;
        attach(ws, block, picked);
        // Keeps the stacks in a column, so a longer one never runs into the next.
        ws.cleanUp();
        Blockly.common.setSelected(block);
        ws.scrollBoundsIntoView(block.getBoundingRectangle(), 40);
      });
      if (e.isUiEvent || ws.isDragging()) return;
      made.workspace = Blockly.serialization.workspaces.save(ws);
      onEdit(toPython(ws));
    });
  });
  return div;
}
