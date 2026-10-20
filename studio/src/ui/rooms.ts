import { ROOM_NAME, roomTitle } from "@sdk/pack";
import roomLibrary from "../../../purple_tui/roomkit/purple.py?raw";
import { BLANK_ROOM, EXAMPLES, TEMPLATES, templateSource, type TemplateDraft } from "../examples";
import { readKnobs, writeKnobs } from "../knobs";
import type { RoomSetup } from "../live/boot";
import { blankRules, rulesSource } from "../rules";
import { changed, draft, freeName, withSample, type Made, type RoomDraft } from "../state";
import { go, h } from "./dom";
import { knobsForm } from "./knobsform";
import { liveScreen, type RoomProblem } from "./live";
import { openPackButton } from "./packfile";
import { roomFilesBox } from "./roomfiles";
import { rulesForm } from "./rulesform";
import { tryBar, yoursList } from "./trybar";
import { templateForm } from "./templateform";
import type { View } from "./view";

export const ICONS: Record<Made["kind"], string> = { rules: "🧱", trivia: "❓", soundboard: "🔊" };
const sourceOf = (made: Made) => (made.kind === "rules" ? rulesSource(made.rules) : templateSource(made));
const href = (name: string) => `#rooms/${encodeURIComponent(name)}`;
// A room name nothing else uses; a try being replaced doesn't count.
const roomName = (text: string, except?: RoomDraft) =>
  freeName(text, (n) => n === "purple" || draft.rooms.some((r) => r !== except && (!r.sample || r.kept) && r.name === n), "my-room");

// The names `from purple import *` brings in, and the ones Purple calls when the room defines them.
export const LIBRARY_NAMES: string[] = JSON.parse(/__all__ = (\[[^\]]*\])/.exec(roomLibrary)![1].replace(/'/g, '"'));
const CALLED = ["on_key", "on_key_up"];

// A starter's own icon follows it, as garden-3 came from garden; Python with no starter is a pencil, like its card.
const iconOf = (room: RoomDraft) =>
  room.made ? ICONS[room.made.kind] : (EXAMPLES.find((e) => e.name === room.name.replace(/-\d+$/, ""))?.icon ?? "✏️");

function drop(gone: RoomDraft[]) {
  draft.rooms = draft.rooms.filter((r) => !gone.includes(r));
  changed();
  go("#rooms");
}

// Opening a way to start only tries it: it becomes the family's room when they change something.
function tryRoom(base: string, made: Made | null, source = made ? sourceOf(made) : BLANK_ROOM) {
  const name = roomName(base);
  draft.rooms = withSample(draft.rooms, { name, source, made });
  changed();
  location.hash = href(name);
}

function list(): View {
  const template = (kind: TemplateDraft["kind"]) => ({ kind, data: TEMPLATES[kind].defaults() }) as TemplateDraft;
  return {
    title: "Rooms",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A room of your own: a little game, a story, a quiz. Your kid finds it next to Purple's rooms."),
      yoursList(draft.rooms, (r) => ({ href: href(r.name), title: roomTitle(r.name), face: h("span", { class: "pick-icon" }, iconOf(r)) }), drop),
      h("h3", {}, "Pick a way to start"),
      h("div", { class: "cards" },
        choice("🧱", "Rules", "When a key is pressed, show, play, or say something. Built from menus, no typing code.", () => tryRoom("my-room", { kind: "rules", rules: blankRules() })),
        ...(Object.keys(TEMPLATES) as TemplateDraft["kind"][]).map((kind) =>
          choice(ICONS[kind], TEMPLATES[kind].label, TEMPLATES[kind].about, () => tryRoom(kind, template(kind)))),
        choice("✏️", "Python from nothing", "An empty room to write yourself, or to paste in what an AI helper wrote.", () => tryRoom("my-room", null))),
      h("h3", {}, "Or change one of these"),
      h("div", { class: "cards" }, ...EXAMPLES.map((e) => choice(e.icon, e.label, e.about, () => tryRoom(e.name, null, e.source)))),
      h("p", { class: "dim" }, "Made a Purple Pack with an AI helper, or by hand? ", openPackButton("Open it here"), " to try its rooms and change them."),
      roomFilesBox(),
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

// Above the Python: it's the whole room, what Purple calls, and which names come from Purple.
function pythonHelp(source: string): HTMLElement {
  const code = source.replace(/#.*$/gm, "").replace(/"[^"\n]*"|'[^'\n]*'/g, '""');
  const uses = (n: string) => new RegExp(`\\b${n}\\b`).test(code);
  const called = CALLED.filter(uses);
  return h("div", { class: "py-help" },
    h("p", {}, "This is the whole room. Purple runs it from the top when your kid comes in",
      ...(called.length ? [", then calls ", ...called.flatMap((n, i) => [i ? " and " : "", h("code", {}, `${n}(key)`)]), " for each key"] : []),
      ". Everything not from Purple is the room's own."),
    h("p", { class: "row small" }, h("span", { class: "dim" }, "From Purple:"),
      ...LIBRARY_NAMES.filter(uses).map((n) => h("a", { class: "lib-name", href: `#guide/${n}` }, n)),
      h("a", { class: "push", href: "#library" }, "See Purple's room library")));
}

type Tab = "made" | "knobs" | "python";

function editor(room: RoomDraft): View {
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

  const nameIn = h("input", { type: "text", class: "room-name", value: roomTitle(room.name), "aria-label": "Room name", maxLength: 40 });
  const nameNote = h("span", { class: "dim small" });
  nameIn.onchange = () => {
    const name = roomName(nameIn.value, room);
    if (!ROOM_NAME.test(name)) return void (nameNote.textContent = "Use letters, numbers, and spaces.");
    room.name = name;
    room.sample = false;
    changed();
    location.replace(href(name));
  };

  // Every change goes through here: the first one makes a try the family's, so it's time to name it.
  const edited = (source: string, ms: number) => {
    room.source = source;
    if (room.sample) {
      room.sample = false;
      nameNote.textContent = "It's yours now. Give it a name.";
      nameIn.focus();
      nameIn.select();
    }
    changed();
    later(ms);
  };

  const code = h("textarea", { class: "code", rows: 24, spellcheck: false, readOnly: !!room.made });
  code.addEventListener("input", () => edited(code.value, 700));
  code.addEventListener("keydown", (e) => {
    if (e.key !== "Tab" || code.readOnly) return;
    e.preventDefault();
    code.setRangeText("    ", code.selectionStart, code.selectionEnd, "end");
    code.dispatchEvent(new Event("input"));
  });
  const insert = (text: string) => {
    if (code.readOnly || tab !== "python") return false;
    code.setRangeText(text, code.selectionStart, code.selectionEnd, "end");
    code.focus();
    code.dispatchEvent(new Event("input"));
    return true;
  };
  const pythonCopy = () => {
    const name = roomName(`${room.name}-python`);
    draft.rooms = [...draft.rooms, { name, source: room.source, made: null }];
    changed();
    location.hash = href(name);
  };

  const made = room.made;
  const tabs: Tab[] = [...(made ? ["made" as const] : readKnobs(room.source).length ? ["knobs" as const] : []), "python"];
  const LABELS: Record<Tab, string> = { made: made?.kind === "rules" ? "Rules" : "Form", knobs: "Knobs", python: "Python" };
  let tab: Tab = tabs[0];
  const pane = h("div", {});
  const tabButtons = tabs.map((t) => h("button", { class: "tab", role: "tab", onclick: () => showTab(t) }, LABELS[t]));
  const showTab = (which: Tab) => {
    tab = which;
    tabButtons.forEach((b, i) => b.setAttribute("aria-selected", String(tabs[i] === which)));
    if (which === "made" && made) {
      const onEdit = () => edited(sourceOf(made), 500);
      pane.replaceChildren(made.kind === "rules" ? rulesForm(made.rules, onEdit) : templateForm(made, onEdit));
    } else if (which === "knobs") {
      const knobs = readKnobs(room.source);
      pane.replaceChildren(knobs.length ? knobsForm(knobs, () => edited(writeKnobs(room.source, knobs), 500))
        : h("p", { class: "note" }, "The settings at the top of the Python can't be read as knobs right now. Everything still works in Python."));
    } else {
      code.value = room.source;
      pane.replaceChildren(pythonHelp(room.source),
        made ? h("p", { class: "note" }, `Made from ${LABELS.made.toLowerCase()}, so its Python changes when they do. `, h("button", { class: "linkbtn", onclick: pythonCopy }, "Make a Python copy"), " to write it yourself.") : "",
        code);
    }
  };

  return {
    title: "",
    back: ["#rooms", "All rooms"],
    editor: h(
      "section",
      {},
      h("div", { class: "editor-head" }, nameIn, nameNote),
      tryBar(room, () => confirm(`Throw away ${roomTitle(room.name)}?`) && drop([room])),
      roomFilesBox((call) => insert(call)),
      h("div", { class: "row between" }, h("div", { class: "tabs", role: "tablist" }, ...tabButtons),
        h("button", { class: "btn small", onclick: () => { restart(); live.focus(); } }, "▶ Play from the start")),
      pane,
      problems.element,
      out,
      h("p", { class: "dim small" }, "What a room can call is on the ", h("a", { href: "#guide" }, "Room guide"), "."),
    ),
    live: setup,
    caption: "Your room, running on the real Purple. Esc leaves it; it waits in the Esc menu, where it shows up on Purple once you turn it on in the Parent Menu.",
    mounted: () => {
      showTab(tab);
      live.onPrint = (t) => { out.textContent = (out.textContent + t + "\n").split("\n").slice(-40).join("\n"); };
      live.onProblem = (p) => problems.show(p);
      live.focus();
    },
    cleanup: () => {
      clearTimeout(timer);
      live.onPrint = live.onProblem = () => {};
    },
  };
}

export function roomsView(item: string | null): View {
  const room = item ? draft.rooms.find((r) => r.name === item) : null;
  return room ? editor(room) : list();
}
