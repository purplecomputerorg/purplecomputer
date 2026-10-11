import "./styles.css";
import logo from "../../assets/logo.svg";
import { draft, onChange, pieces } from "./state";
import { clear, h } from "./ui/dom";
import { colorsView } from "./ui/colors";
import { downloadView } from "./ui/download";
import { formatView, installView } from "./ui/install";
import { instrumentsView } from "./ui/instrument";
import { photosView } from "./ui/photos";
import { pythonView } from "./ui/python";
import { EXAMPLES } from "./examples";
import { addRoom } from "./pybridge";
import { roomTitle } from "@sdk/pack";
import { guideView } from "./ui/guide";
import { liveScreen } from "./ui/live";
import { roomsView } from "./ui/rooms";
import { voiceView } from "./ui/voice";
import { wordsView } from "./ui/words";
import type { View } from "./ui/view";

interface Section {
  id: string;
  label: string;
  icon: string;
  blurb: string;
  view: (item: string | null) => View;
  count: () => number;
  children?: () => { id: string; label: string }[];
}

const SECTIONS: Section[] = [
  { id: "photos", label: "Photos", icon: "🖼️", blurb: "A family photo, painted in the Art room", view: photosView, count: () => draft.pictures.length, children: () => draft.pictures.map((p) => ({ id: p.name, label: p.name })) },
  { id: "voice", label: "Voice", icon: "🎙️", blurb: "Your voice saying the letters", view: voiceView, count: () => Object.keys(draft.letters).length + draft.phrases.length },
  { id: "words", label: "Words", icon: "🐶", blurb: "Your words, each with its own emoji", view: wordsView, count: () => draft.words.length },
  { id: "instruments", label: "Instruments", icon: "🎹", blurb: "A sound of your own for the Music room", view: instrumentsView, count: () => draft.instruments.length, children: () => draft.instruments.map((i) => ({ id: i.name, label: i.name })) },
  { id: "rooms", label: "Rooms", icon: "🧩", blurb: "A little game, story, or quiz", view: roomsView, count: () => draft.rooms.length, children: () => draft.rooms.map((r) => ({ id: r.name, label: roomTitle(r.name) })) },
  { id: "colors", label: "Colors", icon: "🎨", blurb: "The colors the letters paint with", view: colorsView, count: () => (draft.theme ? 1 : 0) },
];
const MORE: [id: string, label: string, view: (item: string | null) => View][] = [
  ["install", "Putting it on Purple", installView],
  ["guide", "Room guide", guideView],
  ["python", "Python console", pythonView],
  ["format", "What is in the file", formatView],
];
const PAGES: Record<string, (item: string | null) => View> = { pack: downloadView, ...Object.fromEntries(MORE.map(([id, , view]) => [id, view])) };

function welcomeView(): View {
  return {
    title: "",
    editor: h(
      "section",
      {},
      h("h1", {}, "Make it your family's."),
      h("p", { class: "serif" }, "The dog on the canvas. Grandma saying the letters. A room where C is for cow."),
      h("div", { class: "cards" }, ...SECTIONS.map((s) =>
        h("a", { class: "pick", href: `#${s.id}` }, h("span", { class: "pick-icon" }, s.icon), h("b", {}, s.label), h("span", {}, s.blurb)))),
      h("p", { class: "dim" }, "Pick any one. When you're done, download one file and put it on Purple with a USB stick. Nothing here leaves this computer."),
    ),
    live: { room: "play" },
    previewTitle: "This is Purple",
    caption: "The real Purple, running in your browser. Try cat, red sun, or 3 dogs.",
  };
}

const app = document.getElementById("app")!;
const side = h("aside", { class: "side" });
const main = h("main", { class: "main" });
const stage = h("aside", { class: "stage" });
const live = liveScreen();
const liveTitle = h("h3");
const liveCaption = h("p", { class: "caption" });
const liveBox = h("div", {}, liveTitle, live.element, liveCaption);
const previewBox = h("div");
stage.append(liveBox, previewBox);
const ide = h("div", { class: "ide" }, side, main, stage);
app.append(ide);

let current: View | null = null;

function parseHash(): [section: string, item: string | null] {
  const [section, ...rest] = location.hash.slice(1).split("/");
  return [section, rest.length ? decodeURIComponent(rest.join("/")) : null];
}

function renderSide() {
  const [sec, item] = parseHash();
  clear(side);
  const link = (href: string, label: string, active: boolean, ...extra: (Node | null)[]) =>
    h("li", {}, h("a", { href, "aria-current": active ? "page" : null }, label, ...extra));
  const tree = h("ul", { class: "tree" });
  for (const s of SECTIONS) {
    const li = link(`#${s.id}`, s.label, sec === s.id && !item, s.count() ? h("span", { class: "n" }, String(s.count())) : null);
    li.firstElementChild!.prepend(h("span", { class: "icon" }, s.icon));
    const kids = s.children?.() ?? [];
    if (kids.length) li.append(h("ul", {}, ...kids.map((k) => link(`#${s.id}/${encodeURIComponent(k.id)}`, k.label, sec === s.id && item === k.id))));
    tree.append(li);
  }
  const n = pieces().reduce((sum, p) => sum + p.count, 0);
  side.append(
    h("a", { class: "brand", href: "#" }, h("img", { src: logo, alt: "" }), h("b", {}, "Purple ", h("span", {}, "Studio"))),
    tree,
    h("a", { class: `btn download${sec === "pack" ? " here" : ""}`, href: "#pack" }, "Download", n ? h("span", { class: "n" }, String(n)) : null),
    h("div", { class: "more" }, h("span", {}, "More"), h("ul", { class: "tree" }, ...MORE.map(([id, label]) => link(`#${id}`, label, sec === id)))),
  );
}

// The live Purple keeps its place in the stage for the whole visit (moving an iframe reloads it);
// other previews come and go below it.
function renderStage() {
  const v = current;
  ide.classList.toggle("no-stage", !v?.live && !v?.preview);
  liveBox.hidden = !v?.live;
  clear(previewBox);
  const title = v?.previewTitle ?? "What your kid sees";
  if (v?.live) {
    live.show(v.live);
    liveTitle.textContent = title;
    liveCaption.textContent = v.caption ?? "";
  } else if (v?.preview) {
    previewBox.append(h("h3", {}, title), v.preview.element, h("p", { class: "caption" }, v.caption ?? ""));
  }
}

function route() {
  current?.cleanup?.();
  current?.preview?.dispose();
  const [sec, item] = parseHash();
  const section = SECTIONS.find((s) => s.id === sec);
  const view = section ? section.view(item) : PAGES[sec] ? PAGES[sec](item) : welcomeView();
  current = view;
  clear(main);
  if (view.title) main.append(h("div", { class: "editor-head" }, h("h2", {}, view.title)));
  main.append(view.editor);
  renderSide();
  renderStage();
  window.scrollTo(0, 0);
  view.mounted?.();
}

// ?sample seeds a room so a screenshot or a demo lands on a filled editor.
if (new URLSearchParams(location.search).has("sample")) addRoom(EXAMPLES[0].name, EXAMPLES[0].source);

onChange(() => { renderSide(); current?.preview?.redraw?.(); live.changed(); });
window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", (e) => pieces().length && e.preventDefault());
route();
