import { purpleEmoji } from "./icons";
import { ROOM_NAME, roomTitle } from "@sdk/pack";
import { BLANK_ROOMS, EXAMPLES, IDEA, roomIcon, TEMPLATES, templateSource, type TemplateDraft } from "../examples";
import { readKnobs, writeKnobs } from "../knobs";
import type { RoomSetup } from "../live/boot";
import { rulesSource } from "../rules";
import { changed, draft, freeName, mine, withSample, type Made, type RoomDraft } from "../state";
import { ask, go, h } from "./dom";
import { emojiCell } from "./emojipicker";
import { knobsForm } from "./knobsform";
import { liveScreen, type RoomProblem } from "./live";
import { codeHints } from "./codehints";
import { copyGuideRow, LIBRARY_NAMES } from "./guide";
import { openPackButton } from "./packfile";
import { roomFilesBox } from "./roomfiles";
import { rulesForm } from "./rulesform";
import { tryBar, yoursList } from "./trybar";
import { templateForm } from "./templateform";
import type { View } from "./view";

type FormMade = Exclude<Made, { kind: "blocks" }>;
const sourceOf = (made: FormMade) => (made.kind === "rules" ? rulesSource(made.rules) : templateSource(made));
// Blockly comes in only when a room made of blocks opens.
const blocks = () => import("./blocksform");
const href = (name: string) => `#rooms/${encodeURIComponent(name)}`;
// A room name nothing else uses; a try being replaced doesn't count.
const roomName = (text: string, except?: RoomDraft) =>
  freeName(text, (n) => n === "purple" || draft.rooms.some((r) => r !== except && (!r.sample || r.kept) && r.name === n), "my-room");

// The names `from purple import *` brings in, and the ones Purple calls when the room defines them.
const CALLED = ["on_key", "on_key_up"];

// Says why the name can't be used, or renames the room and says nothing.
function rename(room: RoomDraft, text: string): string | null {
  const name = roomName(text, room);
  if (!ROOM_NAME.test(name)) return "Use letters, numbers, and spaces.";
  room.name = name;
  mine(room);
  changed();
  return null;
}

function drop(gone: RoomDraft[]) {
  draft.rooms = draft.rooms.filter((r) => !gone.includes(r));
  changed();
  go("#rooms");
}

// Opening a way to start only tries it: it becomes the family's room, in their Purple Pack, when they change something.
function tryRoom(base: string, made: Made | null, source = made && made.kind !== "blocks" ? sourceOf(made) : BLANK_ROOMS[0].source) {
  const name = roomName(base);
  draft.rooms = withSample(draft.rooms, { name, source, made });
  changed();
  location.hash = href(name);
}

function list(): View {
  const template = (kind: TemplateDraft["kind"]) => ({ kind, data: TEMPLATES[kind].defaults() }) as TemplateDraft;
  return {
    title: "New Rooms",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "A room of your own: a little game, a story, a quiz. Your kid finds it next to Purple's rooms."),
      yoursList(draft.rooms, (r) => ({ href: href(r.name), title: roomTitle(r.name), face: purpleEmoji(roomIcon(r), "pick-icon"), rename: (t) => rename(r, t) }), drop),
      h("div", { class: "pick featured write-own" }, purpleEmoji(IDEA, "pick-icon"),
        h("div", {},
          h("b", {}, "Make any room you can imagine"),
          h("p", {}, "Any game or toy. Purple comes with the pieces every room needs, so a whole room can be a few lines of Python, written by you or with an AI helper, or a few blocks snapped together."),
          h("ul", {}, ...["Key presses and timers", "Emoji, pictures, text", "Notes, drums, sounds", "Talking out loud", "Remembering for next time"].map((t) => h("li", {}, t))),
          h("div", { class: "row" },
            h("button", { class: "btn", onclick: startPython }, "Start with Python"),
            h("button", { class: "btn", onclick: startBlocks }, "Start with blocks"))),
        wholeRoom()),
      h("h3", {}, "Or start from one of these"),
      h("div", { class: "cards" },
        ...[
          ...(Object.keys(TEMPLATES) as TemplateDraft["kind"][]).map((kind) => ({ ...TEMPLATES[kind], go: () => tryRoom(TEMPLATES[kind].name, template(kind)) })),
          ...EXAMPLES.map((e) => ({ ...e, go: () => tryRoom(e.name, null, e.source) })),
        ].sort((a, b) => ORDER.indexOf(a.name) - ORDER.indexOf(b.name)).map((s) => choice(s, s.go))),
      h("p", { class: "dim" }, "Made a Purple Pack already? ", openPackButton("Open it here"), " to try its rooms and change them."),
      roomFilesBox(),
    ),
  };
}

const call = (name: string) => h("span", { class: "call" }, name);
const WHOLE_ROOM = [
  "from purple import *\n\n",
  "def on_key(key):\n",
  "    ", call("grid.set"), "(", call("grid.random_empty"), "(), \"🐶\")\n",
  "    ", call("drum"), "(\"bongo\")\n",
  "    ", call("say"), "(key)",
];

const startPython = () => tryRoom("my-room", null);
const startBlocks = () => void blocks().then((m) => {
  const workspace = m.BLOCK_STARTERS[0].workspace();
  tryRoom("my-room", { kind: "blocks", workspace }, m.blocksSource(workspace));
});

// A whole room, as Python and as the same room in blocks, which draw once Blockly has loaded. Each starts a room that way.
function wholeRoom(): HTMLElement {
  const picture = h("div", { class: "blocks-picture" });
  void blocks().then((m) => picture.replaceChildren(m.blocksPicture(m.WHOLE_ROOM_BLOCKS())));
  return h("figure", {}, h("figcaption", {}, "A whole room: every key puts a dog on the screen"),
    h("div", { class: "whole-room" }, ...([["Python", h("pre", {}, ...WHOLE_ROOM), startPython], ["Blocks", picture, startBlocks]] as const).map(([label, pane, go]) =>
      h("button", { type: "button", title: `Start with ${label.toLowerCase()}`, onclick: go }, pane, h("span", {}, label)))));
}

// The starters' order on the Rooms page: the liveliest first.
const ORDER = ["story", "explore", "memory", "beats", "garden", "picture-quiz", "picture-keyboard", "snake"];

const choice = (s: { icon: string; label: string; about: string }, go: () => void, cls = "pick") =>
  h("button", { class: cls, onclick: go }, purpleEmoji(s.icon, "pick-icon"),
    h("b", {}, s.label), h("span", {}, s.about));

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

// The Python as it stands can't run yet, likely mid-word or mid-line: said gently, while Purple keeps the last version that ran.
function typingNote(): { element: HTMLElement; show(p: RoomProblem | null): void } {
  const element = h("p", { class: "typing-note small", hidden: true });
  return {
    element,
    show(p) {
      element.hidden = !p;
      if (p) element.replaceChildren(h("strong", {}, "Still writing? "), `${p.line ? `Line ${p.line}: ` : ""}${p.text}${/[.?!]$/.test(p.text) ? "" : "."} Purple keeps playing the last version that worked.`);
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
      ...LIBRARY_NAMES.filter(uses).map((n) => h("a", { class: "lib-name", href: `#guide/${n}` }, n))));
}

// A new line lined up with the one before, one step further in after a ":".
function newLine(before: string): string {
  const line = before.slice(before.lastIndexOf("\n") + 1);
  return `\n${/^ */.exec(line)![0]}${/:\s*$/.test(line) ? "    " : ""}`;
}

type Tab = "made" | "knobs" | "python";
const IN_PLACE = " The copy goes in your Purple Pack in place of this one.";

function editor(room: RoomDraft): View {
  const problems = problemBox();
  const typing = typingNote();
  const out = h("pre", { class: "console" });
  const live = liveScreen();
  // The room opens over Play on the real Purple, as the Esc menu opens it on a laptop.
  const family = () => ({ name: room.name, source: room.source, icon: roomIcon(room), pack: draft.id });
  const setup: RoomSetup = { room: "play", family: family() };
  // The Python Purple is playing now.
  let playing = room.source;
  const restart = () => {
    playing = room.source;
    out.textContent = "";
    problems.show(null);
    typing.show(null);
    setup.family = family();
    live.show(setup);
  };
  // Typed Python restarts the room once it reads as whole; forms and knobs always write whole Python.
  const settle = async () => {
    const source = room.source;
    const problem = await live.check(source, [...LIBRARY_NAMES, ...CALLED]);
    if (source !== room.source) return;
    typing.show(problem);
    if (!problem && source !== playing) restart();
  };
  let timer = 0;
  const later = (ms: number, typed: boolean) => { clearTimeout(timer); timer = window.setTimeout(typed ? settle : restart, ms); };

  const nameIn = h("input", { type: "text", class: "room-name", value: roomTitle(room.name), "aria-label": "Room name", maxLength: 40 });
  const nameNote = h("span", { class: "dim small" });
  nameIn.onchange = () => {
    const why = rename(room, nameIn.value);
    if (why) nameNote.textContent = why;
    else location.replace(href(room.name));
  };

  // Every change goes through here: the first one makes a try the family's. Focus stays put, so the
  // page doesn't jump away from what they just changed.
  const own = () => {
    if (room.sample) {
      mine(room);
      nameNote.textContent = "It's yours now. Click its name to change it.";
      nameIn.classList.add("just-yours");
    }
    changed();
  };
  const edited = (source: string, ms: number, typed = false) => {
    room.source = source;
    peekCode.textContent = source;
    own();
    later(ms, typed);
  };
  const iconCell = h("span", { class: "emoji-wrap" }, emojiCell(roomIcon(room), () => "", (e) => {
    room.icon = e;
    own();
    restart();
  }, { title: "The room's emoji in Purple's room picker" }));

  const code = h("textarea", { class: "code", rows: 24, spellcheck: false });
  const hints = codeHints(code);
  code.addEventListener("input", () => edited(code.value, 700, true));
  code.addEventListener("keydown", (e) => {
    if (hints.key(e) || !(e.key === "Tab" || e.key === "Enter") || e.shiftKey) return;
    e.preventDefault();
    code.setRangeText(e.key === "Tab" ? "    " : newLine(code.value.slice(0, code.selectionStart)), code.selectionStart, code.selectionEnd, "end");
    code.dispatchEvent(new Event("input"));
  });
  const insert = (text: string) => {
    if (tab !== "python") return false;
    code.setRangeText(text, code.selectionStart, code.selectionEnd, "end");
    code.focus();
    code.dispatchEvent(new Event("input"));
    return true;
  };
  // The copy takes the form room's place in the Purple Pack, so the Esc menu doesn't show the same room twice.
  const pythonCopy = () => {
    const name = roomName(`${room.name}-python`);
    room.kept = false;
    draft.rooms = [...draft.rooms.filter((r) => r !== room || !r.sample), { name, source: room.source, made: null, kept: true }];
    changed();
    location.hash = href(name);
  };

  const tray = roomFilesBox((call) => insert(call), () => showTab(tab));
  const made = room.made;
  const hasKnobs = readKnobs(room.source).length > 0;
  // A made room's Python is looked at under its form, not edited: a tab for it would read as a way to switch.
  const tabs: Tab[] = made ? ["made"] : [...(hasKnobs ? ["knobs" as const] : []), "python"];
  const LABELS: Record<Tab, string> = { made: made?.kind === "rules" ? "Rules" : made?.kind === "blocks" ? "Blocks" : "Form", knobs: "Knobs", python: "Python" };
  let tab: Tab = tabs[0];
  const pane = h("div", {});
  const peekCode = h("pre", {});
  const peek = h("details", { class: "peek" }, h("summary", {}, "See the Python it writes"), peekCode);
  const tabButtons = tabs.map((t) => h("button", { class: "tab", role: "tab", onclick: () => showTab(t) }, LABELS[t]));
  // Forms and knobs cover only part of a room; the way to the rest stays in view above them.
  const seePython = () => {
    peek.open = true;
    peek.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  const toPython = (text: string) => h("p", { class: "to-python small" }, text,
    ...(made && tab === "made" ? [h("button", { class: "linkbtn", onclick: seePython }, "See the Python"), ". "] : []),
    made ? h("button", { class: "linkbtn", onclick: pythonCopy }, "Make a Python copy") : h("button", { class: "linkbtn", onclick: () => showTab("python") }, "Open the Python"),
    made ? ` to write the rest yourself.${IN_PLACE}` : " to change anything else.");
  // A room opened as a blank room, or as blocks, can start over from any of its starters for as long as it stays open.
  const startedAsTry = room.sample;
  const startFrom = async <T extends { icon: string; label: string }>(starters: T[], pick: T, sourceOf: (s: T) => string, use: (s: T) => void) => {
    const untouched = starters.some((s) => sourceOf(s) === room.source);
    if (!untouched && !(await ask("Start over from this one? Your changes go away.", "Start over"))) return;
    use(pick);
    room.source = sourceOf(pick);
    changed();
    restart();
    showTab(tab);
  };
  const startPicker = <T extends { icon: string; label: string }>(starters: T[], sourceOf: (s: T) => string, use: (s: T) => void = () => {}) =>
    startedAsTry && starters.some((s) => sourceOf(s) === room.source) ? h("p", { class: "row small" }, h("span", { class: "dim" }, "Start from:"),
      h("span", { class: "seg" }, ...starters.map((s) =>
        h("button", { "aria-pressed": String(sourceOf(s) === room.source), onclick: () => startFrom(starters, s, sourceOf, use) }, `${s.icon} ${s.label}`)))) : "";
  const formPane = (made: FormMade) => {
    const onEdit = () => edited(sourceOf(made), 500);
    return [toPython("This form writes the room's Python for you. "),
      made.kind === "rules" ? rulesForm(made.rules, onEdit) : templateForm(made, onEdit, tray.refresh), peek];
  };
  const blocksPane = (made: { workspace: object }) => {
    const holder = h("div", {});
    void blocks().then((m) => holder.replaceChildren(
      startPicker(m.BLOCK_STARTERS, (s) => m.blocksSource(s.workspace()), (s) => (made.workspace = s.workspace())),
      m.blocksForm(made, (source) => edited(source, 500))));
    return [toPython("These blocks write the room's Python for you. "), holder, peek];
  };
  const showTab = (which: Tab) => {
    tab = which;
    tabButtons.forEach((b, i) => b.setAttribute("aria-selected", String(tabs[i] === which)));
    peekCode.textContent = room.source;
    if (which === "made" && made) {
      pane.replaceChildren(...(made.kind === "blocks" ? blocksPane(made) : formPane(made)));
    } else if (which === "knobs") {
      const knobs = readKnobs(room.source);
      pane.replaceChildren(toPython("Knobs are the settings at the top of this room's Python, and the Python changes to match. "),
        knobs.length ? knobsForm(knobs, () => edited(writeKnobs(room.source, knobs), 500))
        : h("p", { class: "note" }, "The settings at the top of the Python can't be read as knobs right now. Everything still works in Python."));
    } else {
      code.value = room.source;
      pane.replaceChildren(startPicker(BLANK_ROOMS, (b) => b.source), pythonHelp(room.source), hints.element, typing.element);
    }
  };

  return {
    title: "",
    back: ["#rooms", "All rooms"],
    editor: h(
      "section",
      {},
      h("div", { class: "editor-head" }, iconCell, nameIn, h("button", { class: "linkbtn dim small", onclick: () => nameIn.select() }, "✏️ Rename"), nameNote),
      tryBar(room),
      copyGuideRow(h("span", { class: "small" }, "Using an AI helper? The ", h("a", { href: "#guide" }, "Room guide"), " is everything it needs:")),
      h("div", { class: "row between tab-row" }, h("div", { class: "tabs", role: "tablist", hidden: tabs.length < 2 }, ...tabButtons),
        h("button", { class: "btn small", onclick: () => { restart(); live.focus(); } }, "▶ Play from the start")),
      pane,
      problems.element,
      out,
      tray,
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
