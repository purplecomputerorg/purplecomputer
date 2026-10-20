import * as Blockly from "blockly";
import { ROOM_NAME, roomTitle } from "@sdk/pack";
import { BLANK_BLOCKS, TOOLBOX, defineBlocks, sourceFromBlocks, toPython } from "../blocks";
import { BLANK_ROOM, EXAMPLES, TEMPLATES, templateSource, type TemplateDraft } from "../examples";
import type { RoomSetup } from "../live/boot";
import { addRoom } from "../pybridge";
import { changed, draft, freeName, type RoomDraft } from "../state";
import { field, go, h } from "./dom";
import { liveScreen, type RoomProblem } from "./live";
import { openPackButton } from "./packfile";
import { roomFilesBox } from "./roomfiles";
import { tryBar, tryChip } from "./trybar";
import { templateForm } from "./templateform";
import type { View } from "./view";

function drop(room: RoomDraft) {
  if (!confirm(`Throw away ${roomTitle(room.name)}?`)) return;
  draft.rooms = draft.rooms.filter((r) => r !== room);
  changed();
  go("#rooms");
}

function list(): View {
  const nameIn = h("input", { type: "text", placeholder: "Farm" });
  const status = h("div", { class: "status" });
  const open = (base: string, source: string, made: Pick<RoomDraft, "blocks" | "template">) => {
    const name = freeName(nameIn.value || base, (n) => draft.rooms.some((r) => r.name === n));
    if (!ROOM_NAME.test(name)) {
      status.textContent = "Use letters, numbers, and dashes for the name (Purple is taken).";
      return;
    }
    addRoom(name, source, made);
    location.hash = `#rooms/${encodeURIComponent(name)}`;
  };
  return {
    title: "Rooms",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A room of your own: a little game, a story, a quiz. Your kid finds it next to Purple's rooms."),
      h("div", { class: "name-field" }, field("Its name on Purple (optional)", nameIn), status),
      h("h3", {}, "Pick a way to start"),
      h("div", { class: "cards" },
        ...(Object.entries(TEMPLATES) as [TemplateDraft["kind"], (typeof TEMPLATES)[TemplateDraft["kind"]]][]).map(([kind, t]) => {
          const template = { kind, data: t.defaults() } as TemplateDraft;
          return choice(kind === "trivia" ? "❓" : "🔊", t.label, t.about, () => open(kind, templateSource(template), { blocks: null, template }));
        }),
        choice("🧱", "Blocks", "Snap blocks together to make anything. No typing code.", () => open("my-room", sourceFromBlocks(BLANK_BLOCKS), { blocks: BLANK_BLOCKS, template: null })),
        choice("✏️", "Python from nothing", "An empty room to write yourself, or to paste in what an AI helper wrote.", () => open("my-room", BLANK_ROOM, { blocks: null, template: null }))),
      h("h3", {}, "Or change one of these"),
      h("div", { class: "cards" }, ...EXAMPLES.map((e) => choice(e.icon, e.label, e.about, () => open(e.name, e.source, { blocks: null, template: null })))),
      h("p", { class: "dim" }, "Made a Purple Pack with an AI helper, or by hand? ", openPackButton("Open it here"), " to try its rooms and change them."),
      roomFilesBox(),
      ...([true, false] as const).map((kept) => {
        const rooms = draft.rooms.filter((r) => !!r.kept === kept);
        return rooms.length ? h("div", {}, h("h3", {}, kept ? "In your Purple Pack" : "Trying"), h("div", { class: "row" }, ...rooms.map((r) => {
          const link = h("a", { class: "btn secondary small", href: `#rooms/${encodeURIComponent(r.name)}` }, roomTitle(r.name));
          return kept ? link : tryChip(link, roomTitle(r.name), () => drop(r));
        }))) : null;
      }),
    ),
  };
}

const choice = (icon: string, label: string, about: string, go: () => void) =>
  h("button", { class: "pick", onclick: go }, h("span", { class: "pick-icon" }, icon), h("b", {}, label), h("span", {}, about));

function problemBox(): { element: HTMLElement; show(p: RoomProblem | null): void } {
  const element = h("div", { class: "problem", hidden: true });
  return {
    element,
    show(p) {
      element.hidden = !p;
      if (!p) return;
      const where = p.line ? `Line ${p.line}` : "The room stopped";
      const copy = `${where}: ${p.text}`;
      element.replaceChildren(
        h("div", { class: "row between" }, h("strong", { class: "where" }, where), h("button", { class: "linkbtn dim small", onclick: () => navigator.clipboard?.writeText(copy) }, "Copy the error")),
        h("div", { class: "mono" }, p.text),
      );
    },
  };
}

function editor(room: RoomDraft): View {
  defineBlocks();
  const problems = problemBox();
  const out = h("pre", { class: "console" });
  const live = liveScreen();
  // The room opens over Play on the real Purple, as the Esc menu opens it on a laptop.
  const family = () => ({ name: room.name, source: room.source, pack: draft.id });
  const setup: RoomSetup = { room: "play", family: family() };
  const restart = () => {
    out.textContent = "";
    problems.show(null);
    setup.family = family();
    live.show(setup);
  };
  let timer = 0;
  const later = (ms: number) => { clearTimeout(timer); timer = window.setTimeout(restart, ms); };

  const code = h("textarea", { class: "code", rows: 24, spellcheck: false }, room.source);
  const workspaceDiv = h("div", { class: "blockly" });
  const detached = h("div", { class: "note" }, "This room is Python now, so blocks and forms can't show it. ",
    h("button", { class: "linkbtn", onclick: () => {
      if (!confirm("Start this room over from blocks? The Python you wrote will be replaced.")) return;
      room.blocks = BLANK_BLOCKS;
      room.template = null;
      room.source = sourceFromBlocks(BLANK_BLOCKS);
      code.value = room.source;
      changed();
      showTab("blocks");
      restart();
    } }, "Start over with blocks"));
  let ws: Blockly.WorkspaceSvg | null = null;

  const fromBlocks = () => {
    if (!ws || !room.blocks) return;
    room.blocks = Blockly.serialization.workspaces.save(ws);
    room.source = toPython(ws);
    code.value = room.source;
    changed();
    later(400);
  };

  const fromForm = () => {
    if (!room.template) return;
    room.source = templateSource(room.template);
    code.value = room.source;
    changed();
    later(500);
  };

  code.addEventListener("input", () => {
    const madeFrom = room.blocks ? "the blocks" : room.template ? "the form" : "";
    if (madeFrom && !confirm(`Editing the Python by hand leaves ${madeFrom} behind; from here on this room is Python. Keep going?`)) {
      code.value = room.source;
      return;
    }
    if (madeFrom) {
      room.blocks = null;
      room.template = null;
      ws?.dispose();
      ws = null;
      tabs.blocks.textContent = "Blocks";
    }
    room.source = code.value;
    changed();
    later(700);
  });
  code.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      code.setRangeText("    ", code.selectionStart, code.selectionEnd, "end");
      code.dispatchEvent(new Event("input"));
    }
  });

  const panes = { blocks: h("div", {}), python: h("div", {}, code) };
  const tabs = { blocks: h("button", { class: "tab" }, room.template ? "Form" : "Blocks"), python: h("button", { class: "tab" }, "Python") };
  const showTab = (which: "blocks" | "python") => {
    for (const k of ["blocks", "python"] as const) {
      panes[k].hidden = k !== which;
      tabs[k].setAttribute("aria-selected", String(k === which));
    }
    if (which !== "blocks") return;
    if (room.template) return void panes.blocks.replaceChildren(templateForm(room.template, fromForm));
    panes.blocks.replaceChildren(room.blocks ? workspaceDiv : detached);
    if (room.blocks && !ws) {
      ws = Blockly.inject(workspaceDiv, { media: "blockly/", toolbox: TOOLBOX, renderer: "zelos", zoom: { controls: true, wheel: false, startScale: 0.85 }, trashcan: true, move: { scrollbars: true, drag: true, wheel: true } });
      ws.setTheme(Blockly.registry.getObject(Blockly.registry.Type.THEME, "purple") as Blockly.Theme);
      Blockly.serialization.workspaces.load(room.blocks as object, ws);
      ws.addChangeListener((e: Blockly.Events.Abstract) => { if (!e.isUiEvent) fromBlocks(); });
    } else ws && Blockly.svgResize(ws);
  };
  tabs.blocks.onclick = () => showTab("blocks");
  tabs.python.onclick = () => showTab("python");

  return {
    title: roomTitle(room.name),
    back: ["#rooms", "All rooms"],
    editor: h(
      "section",
      {},
      tryBar(room, () => drop(room)),
      h("div", { class: "row between" }, h("div", { class: "tabs", role: "tablist" }, tabs.blocks, tabs.python),
        h("button", { class: "btn small", onclick: () => { restart(); live.focus(); } }, "▶ Play from the start")),
      panes.blocks,
      panes.python,
      problems.element,
      out,
      roomFilesBox(),
      h("p", { class: "dim small" }, "What a room can call is on the ", h("a", { href: "#guide" }, "Room guide"), "."),
    ),
    live: setup,
    caption: "Your room, running on the real Purple. Esc leaves it, as on Purple; ▶ starts it again.",
    mounted: () => {
      showTab(room.blocks || room.template ? "blocks" : "python");
      live.onPrint = (t) => { out.textContent = (out.textContent + t + "\n").split("\n").slice(-40).join("\n"); };
      live.onProblem = (p) => problems.show(p);
      live.focus();
    },
    cleanup: () => {
      clearTimeout(timer);
      ws?.dispose();
      ws = null;
      live.onPrint = live.onProblem = () => {};
    },
  };
}

export function roomsView(item: string | null): View {
  const room = item ? draft.rooms.find((r) => r.name === item) : null;
  return room ? editor(room) : list();
}
