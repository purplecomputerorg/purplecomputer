import * as Blockly from "blockly";
import { parse, RoomError } from "@sdk/room";
import { TOOLBOX, defineBlocks, toProgram } from "../blocks";
import { addRoom } from "../pybridge";
import { sampleRoom, toState } from "../roomstate";
import { changed, draft, slug, type RoomDraft } from "../state";
import { field, h } from "./dom";
import { RoomStage, roomFrame } from "./roomstage";
import type { View } from "./view";

function list(): View {
  const titleIn = h("input", { type: "text", placeholder: "Farm" });
  const status = h("div", { class: "status" });
  const start = () => {
    const title = titleIn.value.trim() || "My room";
    const name = slug(title) || "room";
    if (draft.rooms.some((r) => r.program.name === name)) {
      status.textContent = `There is already a room called ${name}. Pick another name.`;
      return;
    }
    addRoom(sampleRoom(name, title));
    location.hash = `#rooms/${encodeURIComponent(name)}`;
  };
  return {
    title: "Rooms",
    path: "content/rooms/<name>.json",
    tag: "real",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A room of your own: what each key shows, says, and plays. Snap blocks together, try it on the right, and it runs the same way on Purple."),
      h("div", { class: "card" }, field("What to call it", titleIn), status, h("p", { style: "margin-top:14px" }, h("button", { class: "btn", onclick: start }, "Start a room"), h("span", { class: "dim small", style: "margin-left:12px" }, "It starts as a small farm you can take apart."))),
      draft.rooms.length ? h("p", { class: "dim small" }, "Yours so far: ", ...draft.rooms.flatMap((r, n) => [n ? ", " : "", h("a", { href: `#rooms/${encodeURIComponent(r.program.name)}` }, r.program.title ?? r.program.name)])) : null,
      h("div", { class: "note" }, h("strong", {}, "What Purple does with this: "), "the room picker (a tap of Esc) grows a row of your rooms under Play, Music, and Art, on the keys 4 to 7. Inside, every key runs your blocks: text and emoji on the screen, Purple's voice or a recorded phrase, notes on any instrument in this pack, the percussion. Esc leaves. A room is a small data file, not a program; Purple reads it and refuses anything it does not understand, so there is nothing a room can do that Purple itself cannot."),
    ),
    stage: () => roomFrame({ background: "#1e1033", shown: "🐄", line: ["c", "o", "w"], title: "Farm" }),
    caption: "A room, as the kid sees it: whatever the blocks show in the middle, and a line that fills up with keys.",
  };
}

function editor(room: RoomDraft): View {
  defineBlocks();
  const titleIn = h("input", { type: "text", value: room.program.title ?? room.program.name });
  const workspaceDiv = h("div", { class: "blockly" });
  const problems = h("div", { class: "status" });
  const json = h("pre", { class: "small" });
  const stage = new RoomStage(room.program);
  let ws: Blockly.WorkspaceSvg | null = null;
  let timer = 0;

  const sync = () => {
    if (!ws) return;
    const program = toProgram(ws, room.program.name, titleIn.value.trim() || room.program.name);
    program.background = room.program.background;
    try {
      parse(program);
      problems.textContent = "";
    } catch (e) {
      problems.textContent = e instanceof RoomError ? e.message : String(e);
      return;
    }
    room.program = program;
    room.blocks = Blockly.serialization.workspaces.save(ws);
    json.textContent = JSON.stringify(program, null, 2);
    stage.setProgram(program);
    changed();
  };

  titleIn.onchange = sync;
  json.textContent = JSON.stringify(room.program, null, 2);

  const remove = () => {
    draft.rooms = draft.rooms.filter((r) => r !== room);
    changed();
    location.hash = "#rooms";
  };

  return {
    title: room.program.title ?? room.program.name,
    path: `content/rooms/${room.program.name}.json  ·  content/rooms/${room.program.name}.blocks.json`,
    tag: "real",
    editor: h(
      "section",
      {},
      h("div", { class: "card" }, h("div", { class: "row between" }, h("div", { style: "flex:1;min-width:200px" }, field("Title", titleIn)), h("span", { class: "dim small" }, "Drag blocks from the left. Every top block is one rule."))),
      workspaceDiv,
      problems,
      h("div", { class: "row between", style: "margin-top:14px" },
        h("div", { class: "row" }, h("button", { class: "btn small", onclick: () => { stage.start(); stage.element.focus(); } }, "Try it"), h("span", { class: "dim small" }, "then press keys with the room on the right focused")),
        h("button", { class: "linkbtn dim", onclick: remove }, "Remove this room")),
      h("details", { style: "margin-top:18px" }, h("summary", { class: "dim small" }, "The file Purple reads"), json),
    ),
    stage: () => stage.element,
    stageTitle: "What your kid sees",
    caption: "Click the room, then press keys. Sound comes from the same synth Purple uses; the voice is your browser's.",
    mounted: () => {
      ws = Blockly.inject(workspaceDiv, { toolbox: TOOLBOX, renderer: "zelos", theme: Blockly.Theme.defineTheme("purple-live", { name: "purple-live", base: Blockly.Themes.Zelos }), zoom: { controls: true, wheel: false, startScale: 0.85 }, trashcan: true, move: { scrollbars: true, drag: true, wheel: true } });
      ws.setTheme(Blockly.registry.getObject(Blockly.registry.Type.THEME, "purple") as Blockly.Theme);
      if (room.blocks) Blockly.serialization.workspaces.load(room.blocks as object, ws);
      else Blockly.serialization.workspaces.load(toState(room.program) as object, ws);
      ws.addChangeListener((e: Blockly.Events.Abstract) => {
        if (e.isUiEvent) return;
        clearTimeout(timer);
        timer = window.setTimeout(sync, 250);
      });
      stage.start();
    },
    cleanup: () => { clearTimeout(timer); stage.stop(); ws?.dispose(); ws = null; },
  };
}

export function roomsView(item: string | null): View {
  const room = item ? draft.rooms.find((r) => r.program.name === item) : null;
  return room ? editor(room) : list();
}
