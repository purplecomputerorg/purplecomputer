import "./styles.css";
import logo from "../../assets/logo.svg";
import { draft, onChange, pieces } from "./state";
import { clear, h } from "./ui/dom";
import { colorsView } from "./ui/colors";
import { downloadView } from "./ui/download";
import { helperView } from "./ui/helper";
import { formatView, installView } from "./ui/install";
import { instrumentsView } from "./ui/instrument";
import { photosView } from "./ui/photos";
import { pythonView } from "./ui/python";
import { addRoom } from "./pybridge";
import { sampleRoom } from "./roomstate";
import { roomsView } from "./ui/rooms";
import { voiceView } from "./ui/voice";
import { wordsView } from "./ui/words";
import type { View } from "./ui/view";

interface Section {
  id: string;
  label: string;
  view: (item: string | null) => View;
  count: () => number;
  children?: () => { id: string; label: string }[];
}

const SECTIONS: Section[] = [
  { id: "photos", label: "Photos", view: photosView, count: () => draft.pictures.length, children: () => draft.pictures.map((p) => ({ id: p.name, label: p.name })) },
  { id: "voice", label: "Voice", view: voiceView, count: () => Object.keys(draft.letters).length + draft.phrases.length },
  { id: "words", label: "Words", view: wordsView, count: () => draft.words.length + draft.synonyms.length + draft.ranked.length },
  { id: "instruments", label: "Instruments", view: instrumentsView, count: () => draft.instruments.length, children: () => draft.instruments.map((i) => ({ id: i.name, label: i.name })) },
  { id: "rooms", label: "Rooms", view: roomsView, count: () => draft.rooms.length, children: () => draft.rooms.map((r) => ({ id: r.program.name, label: r.program.name })) },
  { id: "colors", label: "Colors", view: colorsView, count: () => (draft.theme ? 1 : 0) },
];
const PAGES: Record<string, (item: string | null) => View> = { pack: downloadView, install: installView, format: formatView, helper: helperView, python: pythonView };

function welcomeView(): View {
  return {
    title: "",
    editor: h(
      "section",
      {},
      h("h1", {}, "Make it your family's."),
      h("p", { class: "serif" }, "The dog on the canvas. Grandma saying the letters. A marimba that sounds like your kitchen. A room where C is for cow."),
      h("p", { class: "lead" }, "Purple Computer ships almost empty on purpose. Studio is where a parent puts a few of their own things in. The left side is your pack, one file that rides along with Purple. The right side is what your kid will see."),
      h("p", { class: "dim" }, "Everything happens on this computer. No account, nothing uploaded, nothing kept after you close the tab."),
      h("p", { style: "margin-top:28px" }, h("a", { class: "btn", href: "#photos", style: "text-decoration:none" }, "Start with a photo"), " ", h("a", { class: "btn secondary", href: "#rooms", style: "text-decoration:none;margin-left:8px" }, "Or build a room")),
    ),
    stage: () => null,
  };
}

const app = document.getElementById("app")!;
const side = h("aside", { class: "side" });
const main = h("main", { class: "main" });
const stage = h("aside", { class: "stage" });
app.append(h("div", { class: "ide" }, side, main, stage));

let current: View | null = null;

function parseHash(): [section: string, item: string | null] {
  const [section, ...rest] = location.hash.slice(1).split("/");
  return [section, rest.length ? decodeURIComponent(rest.join("/")) : null];
}

function renderSide() {
  const [sec, item] = parseHash();
  clear(side);
  const tree = h("ul", { class: "tree" });
  const link = (href: string, label: string, icon: string, active: boolean, extra?: Node | null) =>
    h("li", {}, h("a", { href, "aria-current": active ? "page" : null }, h("span", { class: "icon" }, icon), label, extra ?? null));
  tree.append(link("#pack", draft.familyName ? `${draft.familyName}` : "Our pack", "▣", sec === "pack"));
  for (const s of SECTIONS) {
    const li = link(`#${s.id}`, s.label, "▸", sec === s.id && !item, s.count() ? h("span", { class: "n" }, String(s.count())) : null);
    const kids = s.children?.() ?? [];
    if (kids.length) li.append(h("ul", {}, ...kids.map((k) => h("li", {}, h("a", { href: `#${s.id}/${encodeURIComponent(k.id)}`, "aria-current": sec === s.id && item === k.id ? "page" : null }, h("span", { class: "path" }, k.label))))));
    tree.append(li);
  }
  tree.append(
    h("li", { class: "sep" }),
    h("li", {}, h("a", { href: "#pack", class: "action" }, h("span", { class: "icon" }, "↓"), "Download the pack", pieces().length ? h("span", { class: "n" }, String(pieces().length)) : null)),
    link("#install", "Getting it onto Purple", "?", sec === "install"),
    link("#format", "What is in the pack", "{}", sec === "format"),
    h("li", { class: "sep" }),
    link("#python", "Python", ">_", sec === "python"),
    link("#helper", "Helper", "✦", sec === "helper"),
  );
  side.append(
    h("a", { class: "brand", href: "#" }, h("img", { src: logo, alt: "" }), h("b", {}, "Purple ", h("span", {}, "Studio"))),
    tree,
    h("div", { class: "foot" }, "Nothing here leaves this computer. Close the tab and the draft is gone; the pack file you download is yours."),
  );
}

function renderStage() {
  clear(stage);
  const node = current?.stage();
  if (!node) return;
  stage.append(h("div", {}, h("h3", {}, current?.stageTitle ?? "What your kid sees"), node, current?.caption ? h("p", { class: "caption" }, current.caption) : null));
}

function route() {
  current?.cleanup?.();
  const [sec, item] = parseHash();
  const section = SECTIONS.find((s) => s.id === sec);
  const view = section ? section.view(item) : PAGES[sec] ? PAGES[sec](item) : welcomeView();
  current = view;
  clear(main);
  if (view.title) {
    main.append(h("div", { class: "editor-head" }, h("h2", {}, view.title), view.tag ? h("span", { class: `tag ${view.tag}` }, view.tag === "real" ? "Read by Purple today" : "Proposed") : null));
    if (view.path) main.append(h("div", { class: "editor-path" }, view.path));
  }
  main.append(view.editor);
  renderSide();
  renderStage();
  window.scrollTo(0, 0);
  view.mounted?.();
}

// ?sample seeds a room so a screenshot or a demo lands on a filled editor.
if (new URLSearchParams(location.search).has("sample")) addRoom(sampleRoom());

onChange(() => { renderSide(); renderStage(); });
window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", (e) => pieces().length && e.preventDefault());
route();
