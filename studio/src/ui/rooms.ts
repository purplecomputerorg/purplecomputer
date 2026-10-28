import { purpleEmoji } from "./icons";
import { ROOM_NAME, roomTitle } from "@sdk/pack";
import { BLANK_ROOM, EXAMPLES, TEMPLATES, templateSource, type TemplateDraft } from "../examples";
import { readKnobs, writeKnobs } from "../knobs";
import type { RoomSetup } from "../live/boot";
import { rulesSource } from "../rules";
import { changed, draft, freeName, mine, withSample, type Made, type RoomDraft } from "../state";
import { go, h } from "./dom";
import { knobsForm } from "./knobsform";
import { liveScreen, type RoomProblem } from "./live";
import { copyGuideRow, LIBRARY_NAMES } from "./guide";
import { openPackButton } from "./packfile";
import { roomFilesBox } from "./roomfiles";
import { rulesForm } from "./rulesform";
import { tryBar, yoursList } from "./trybar";
import { templateForm } from "./templateform";
import type { View } from "./view";

// Rules aren't offered any more, but a room made from them still opens in them.
export const ICONS: Record<Made["kind"], string> = { rules: "🧱", quiz: TEMPLATES.quiz.icon, soundboard: TEMPLATES.soundboard.icon };
const sourceOf = (made: Made) => (made.kind === "rules" ? rulesSource(made.rules) : templateSource(made));
const href = (name: string) => `#rooms/${encodeURIComponent(name)}`;
// A room name nothing else uses; a try being replaced doesn't count.
const roomName = (text: string, except?: RoomDraft) =>
  freeName(text, (n) => n === "purple" || draft.rooms.some((r) => r !== except && (!r.sample || r.kept) && r.name === n), "my-room");

// The names `from purple import *` brings in, and the ones Purple calls when the room defines them.
const CALLED = ["on_key", "on_key_up"];

// A starter's own icon follows it, as garden-3 came from garden; Python with no starter is a lightbulb, like its card.
const IDEA = "💡";
const iconOf = (room: RoomDraft) =>
  room.made ? ICONS[room.made.kind] : (EXAMPLES.find((e) => e.name === room.name.replace(/-\d+$/, ""))?.icon ?? IDEA);

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
      yoursList(draft.rooms, (r) => ({ href: href(r.name), title: roomTitle(r.name), face: purpleEmoji(iconOf(r), "pick-icon"), rename: (t) => rename(r, t) }), drop),
      h("button", { class: "pick featured write-own", onclick: () => tryRoom("my-room", null) }, purpleEmoji(IDEA, "pick-icon"),
        h("div", {},
          h("b", {}, "Make any room you can imagine"),
          h("p", {}, "Any game or toy. Purple comes with the pieces every room needs, so a whole room can be a few lines of Python, written by you or with an AI helper."),
          h("ul", {}, ...["Key presses and timers", "Emoji, pictures, text", "Notes, drums, sounds", "Talking out loud", "Remembering for next time"].map((t) => h("li", {}, t))),
          h("span", { class: "btn small" }, "Start a blank room")),
        h("figure", {}, h("figcaption", {}, "A whole room: every key puts a dog on the screen"), h("pre", {}, ...WHOLE_ROOM))),
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

type Tab = "made" | "knobs" | "python";
const IN_PLACE = " The copy goes in your Purple Pack in place of this one.";

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
    const why = rename(room, nameIn.value);
    if (why) nameNote.textContent = why;
    else location.replace(href(room.name));
  };

  // Every change goes through here: the first one makes a try the family's. Focus stays put, so the
  // page doesn't jump away from what they just changed.
  const edited = (source: string, ms: number) => {
    room.source = source;
    if (room.sample) {
      mine(room);
      nameNote.textContent = "It's yours now. Click its name to change it.";
      nameIn.classList.add("just-yours");
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
  const tabs: Tab[] = [...(made ? ["made" as const] : readKnobs(room.source).length ? ["knobs" as const] : []), "python"];
  const LABELS: Record<Tab, string> = { made: made?.kind === "rules" ? "Rules" : "Form", knobs: "Knobs", python: "Python" };
  let tab: Tab = tabs[0];
  const pane = h("div", {});
  const tabButtons = tabs.map((t) => h("button", { class: "tab", role: "tab", onclick: () => showTab(t) }, LABELS[t]));
  // Forms and knobs cover only part of a room; the way to the rest stays in view above them.
  const toPython = (text: string) => h("p", { class: "to-python small" }, text,
    made ? h("button", { class: "linkbtn", onclick: pythonCopy }, "Make a Python copy") : h("button", { class: "linkbtn", onclick: () => showTab("python") }, "Open the Python"),
    made ? ` to write the rest yourself.${IN_PLACE}` : " to change anything else.");
  const showTab = (which: Tab) => {
    tab = which;
    tabButtons.forEach((b, i) => b.setAttribute("aria-selected", String(tabs[i] === which)));
    if (which === "made" && made) {
      const onEdit = () => edited(sourceOf(made), 500);
      pane.replaceChildren(toPython("This form writes the room's Python for you. "),
        made.kind === "rules" ? rulesForm(made.rules, onEdit) : templateForm(made, onEdit, tray.refresh));
    } else if (which === "knobs") {
      const knobs = readKnobs(room.source);
      pane.replaceChildren(toPython("Knobs are the settings at the top of this room's Python, and the Python changes to match. "),
        knobs.length ? knobsForm(knobs, () => edited(writeKnobs(room.source, knobs), 500))
        : h("p", { class: "note" }, "The settings at the top of the Python can't be read as knobs right now. Everything still works in Python."));
    } else {
      code.value = room.source;
      pane.replaceChildren(pythonHelp(room.source),
        made ? h("p", { class: "note" }, `Made from ${LABELS.made.toLowerCase()}, so its Python changes when they do. `, h("button", { class: "linkbtn", onclick: pythonCopy }, "Make a Python copy"), ` to write it yourself.${IN_PLACE}`) : "",
        code);
    }
  };

  return {
    title: "",
    back: ["#rooms", "All rooms"],
    editor: h(
      "section",
      {},
      h("div", { class: "editor-head" }, nameIn, h("button", { class: "linkbtn dim small", onclick: () => nameIn.select() }, "✏️ Rename"), nameNote),
      tryBar(room),
      copyGuideRow(h("span", { class: "small" }, "Using an AI helper? The ", h("a", { href: "#guide" }, "Room guide"), " is everything it needs:")),
      h("div", { class: "row between" }, h("div", { class: "tabs", role: "tablist" }, ...tabButtons),
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
