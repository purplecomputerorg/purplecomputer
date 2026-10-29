import "./fonts";
import "./styles.css";
import logo from "../../assets/logo.svg";
import { features, hasWork, onChange, pieces, replaceDraft } from "./state";
import { recall, remember } from "./saved";
import { loadShelf, shelveDraft } from "./shelf";
import { clearEverythingButton, clearSectionButton } from "./ui/packfile";
import { clear, h } from "./ui/dom";
import { colorsView } from "./ui/colors";
import { downloadView } from "./ui/download";
import { formatView, installView } from "./ui/install";
import { instrumentsView } from "./ui/instrument";
import { picturesView } from "./ui/pictures";
import { licensesView } from "./ui/licenses";
import { privacyView, staysHere } from "./ui/privacy";
import { pythonView } from "./ui/python";
import { EXAMPLES } from "./examples";
import { addRoom } from "./pybridge";
import { guideView } from "./ui/guide";
import { homeView, rainbow, type HomeSection } from "./ui/home";
import { purpleEmoji } from "./ui/icons";
import { typingKeys } from "./keys";
import type { Room } from "./live/boot";
import { Laptop } from "./ui/laptop";
import { liveScreen } from "./ui/live";
import { roomsView } from "./ui/rooms";
import { keysView } from "./ui/keys";
import { wordsView } from "./ui/words";
import type { View } from "./ui/view";

interface Section extends HomeSection {
  // What "Clear all" names on this section's pages; colors has its own undo instead.
  clears?: string;
  view: (item: string | null) => View;
}

const SECTIONS: Section[] = [
  { id: "pictures", clears: "pictures", label: "Pictures", icon: "🖼️", blurb: "The dog, ready to paint on", view: picturesView },
  { id: "words", clears: "words", label: "Words", icon: "🗨️", blurb: "The dog's name, with a picture", voice: true, view: wordsView },
  { id: "keys", clears: "letters", label: "Letters", icon: "z", blurb: "Grandma, every time they press G", voice: true, view: keysView },
  { id: "instruments", clears: "instruments", label: "Instruments", icon: "🎹", blurb: "Like a kazoo or a harp", view: instrumentsView },
  { id: "colors", label: "Colors", icon: "🎨", blurb: () => ["Purple, but green, or ", rainbow("any color")], view: colorsView },
  { id: "rooms", clears: "rooms", label: "Rooms", icon: "🧩", blurb: "Like a world for them to walk around", voice: true, view: roomsView },
].filter((s) => features.rooms || s.id !== "rooms");
// Old links to pages that moved.
const MOVED: Record<string, string> = { voice: "keys", "voice/phrases": "words", "words/phrases": "words" };

type Page = [id: string, label: string, view: (item: string | null) => View];
const MORE = ([
  ["install", "Putting it on Purple", installView],
  ["guide", "Room guide", guideView],
  ["python", "Python console", pythonView],
  ["format", "What is in a Purple Pack", formatView],
  ["privacy", "Your privacy", privacyView],
  ["licenses", "Open source licenses", licensesView],
] satisfies Page[]).filter(([id]) => features.rooms || id !== "guide");
const PAGES: Record<string, (item: string | null) => View> = { pack: downloadView, ...Object.fromEntries(MORE.map(([id, , view]) => [id, view])) };

const app = document.getElementById("app")!;
const top = h("header", { class: "topbar" });
const main = h("main", { class: "main" });
const live = liveScreen();
// The laptop and the live Purple inside it stay put for the whole visit (moving an iframe reloads it).
let tapTarget: ((key: string) => void) | null = null;
const engage = () => current?.live && live.engage();
const laptop = new Laptop((key) => { tapTarget?.(key); engage(); });
laptop.screen.append(live.element);

// On a phone, under the laptop: Purple's rooms to switch between, and a few keys for the room it's in.
const ROOMS: [Room, string][] = [["art", "🎨 Art"], ["music", "🎵 Music"], ["play", "💬 Play"], ["blocks", "🧊 Blocks"]];
const TRAY: Record<Room, string[]> = { play: typingKeys("cat"), music: [..."asdfg"], art: ["q", "a", "z", "space"], blocks: ["q", "a", "z", "enter"] };
const ARROWS = ["left", "up", "down", "right"];
const roomButtons = h("div", { class: "room-buttons" });
const phoneBar = h("div", { class: "phone-bar" }, roomButtons, laptop.tray, h("p", { class: "phone-hint" }, "Or tap the laptop to type with your phone's keyboard."));
function renderPhoneBar() {
  const v = current;
  const page = v?.live;
  roomButtons.hidden = !page;
  roomButtons.replaceChildren(...ROOMS.map(([room, label]) => h("button", {
    type: "button", "aria-pressed": String(live.place.room === room),
    onclick: () => { live.show(room === page?.room ? page : { room }); engage(); },
  }, label)));
  const { room, menu } = live.place;
  const keys = !page ? [] : menu ? [...ARROWS, "enter"] : (room === page.room && v?.keys?.()) || TRAY[room];
  laptop.paint(page ? [...keys, "escape"] : keys);
}
live.onMove = renderPhoneBar;
const stageTitle = h("h3", {}, "This little computer is a real Purple Computer for you to try");
const stageCaption = h("p", { class: "caption" });
const stageStays = staysHere("This Purple runs in your browser. What you type into it stays on your device.");
const stage = h("aside", { class: "stage" }, h("div", { class: "stage-inner" }, stageTitle, laptop.element, phoneBar, stageCaption, stageStays));
// Which side the live Purple sits on, and how wide, are per-browser choices kept until changed back.
const pref = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const keep = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* private window: it lasts this visit */ } };
const SWAPPED = "studio-swapped";
const WIDTH = "studio-live-width";
// The live Purple's width over the editor's: dragging moves the line only somewhat either way of the usual 1.3.
const [NARROWEST, USUAL, WIDEST] = [0.8, 1.3, 2.1];
let liveWidth = USUAL;
const widen = (r: number) => {
  liveWidth = Math.min(WIDEST, Math.max(NARROWEST, r));
  body.style.setProperty("--live", `${liveWidth}fr`);
  body.classList.toggle("resized", liveWidth !== USUAL);
};
// Stacked on a phone, the page scrolls so the divider stays where it was under the finger.
const flip = () => {
  const was = split.getBoundingClientRect().top;
  const on = body.classList.toggle("swapped");
  window.scrollBy(0, split.getBoundingClientRect().top - was);
  keep(SWAPPED, on ? "1" : "0");
};
// The two sides slide past each other where the browser can; elsewhere they just trade places.
const swap = () => document.startViewTransition?.(flip) ?? flip();
const side = window.matchMedia("(min-width: 961px)");
// The line drags at once; the swap button drags once moved a few pixels, and a press that never moved is a click that swaps.
const NUDGE = 4;
let dragged = false;
function drag(e: PointerEvent) {
  if (!side.matches || e.button !== 0) return;
  e.preventDefault();
  // Captured by what was pressed, so a press on the button still ends in a click on it.
  const grip = e.target as HTMLElement;
  grip.setPointerCapture(e.pointerId);
  let moving = grip === split;
  body.classList.toggle("dragging", moving);
  grip.onpointermove = (m) => {
    if (!moving && Math.abs(m.clientX - e.clientX) < NUDGE) return;
    moving = true;
    body.classList.add("dragging");
    const { left, width } = body.getBoundingClientRect();
    const x = m.clientX - left;
    const [live, rest] = body.classList.contains("swapped") ? [x, width - x] : [width - x, x];
    widen(live / Math.max(rest, 1));
  };
  const end = () => {
    grip.onpointermove = grip.onpointerup = grip.onpointercancel = null;
    body.classList.remove("dragging");
    if (moving) keep(WIDTH, String(liveWidth));
  };
  grip.onpointercancel = end;
  grip.onpointerup = () => { dragged = moving && grip !== split; end(); };
}
const split = h("div", { class: "split", onpointerdown: drag, ondblclick: (e: Event) => { if (e.target === split) { widen(USUAL); keep(WIDTH, String(USUAL)); } } },
  h("button", { type: "button", class: "swap", title: "Swap sides", "aria-label": "Swap sides", onclick: () => { if (!dragged) swap(); dragged = false; } }));
const body = h("div", { class: `body${pref(SWAPPED) === "1" ? " swapped" : ""}` }, main, split, stage);
widen(Number(pref(WIDTH)) || USUAL);
app.append(top, body);

let current: View | null = null;
const clearBar = h("p", { class: "clear-section" });

function renderClear() {
  const section = SECTIONS.find((s) => s.id === parseHash()[0]);
  clearBar.replaceChildren(section?.clears && hasWork(section.id) ? clearSectionButton(section.id, section.clears) : "");
}

function parseHash(): [section: string, item: string | null] {
  const [section, ...rest] = location.hash.slice(1).split("/");
  return [section, rest.length ? decodeURIComponent(rest.join("/")) : null];
}

// How many things on each Studio page are added to the family's Purple.
const added = (section: string) => pieces().filter((p) => p.section === section).reduce((sum, p) => sum + p.count, 0);

function renderTop() {
  const [sec] = parseHash();
  const n = pieces().reduce((sum, p) => sum + p.count, 0);
  top.replaceChildren(
    h("a", { class: "brand", href: "#" }, h("img", { src: logo, alt: "" }), h("b", {}, "Purple ", h("span", {}, "Studio"))),
    h("nav", { class: "tabs-nav" }, ...SECTIONS.map((s) => h("a", { href: `#${s.id}`, "aria-current": sec === s.id ? "page" : null },
      purpleEmoji(s.icon, "icon"), h("span", { class: "label" }, s.label), added(s.id) ? h("span", { class: "n" }, String(added(s.id))) : null))),
    h("a", { class: "privacy-link", href: "#privacy", "aria-current": sec === "privacy" ? "page" : null }, "🔒", h("span", {}, " Privacy")),
    h("details", { class: "more-menu" }, h("summary", {}, "More"),
      h("div", { onclick: (e: Event) => (e.target as HTMLElement).closest("details")?.removeAttribute("open") },
        ...MORE.map(([id, label]) => h("a", { href: `#${id}`, "aria-current": sec === id ? "page" : null }, label)),
        clearEverythingButton("clear-all"))),
    h("a", { class: `btn download${sec === "pack" ? " here" : ""}`, href: "#pack", onclick: (e: Event) => { if (current?.download) { e.preventDefault(); current.download(); } } }, "Download", n ? h("span", { class: "n" }, String(n)) : null),
  );
}

function renderStage() {
  const v = current;
  body.classList.toggle("no-stage", !v?.live);
  body.classList.toggle("at-home", !parseHash()[0]);
  live.element.hidden = !v?.live;
  stageCaption.textContent = v?.caption ?? "";
  if (v?.live) live.show(v.live);
  renderPhoneBar();
  tapTarget = v?.live ? (key) => live.key(key) : null;
}

function route() {
  const moved = MOVED[location.hash.slice(1)];
  if (moved) return location.replace(`#${moved}`);
  current?.cleanup?.();
  const [sec, item] = parseHash();
  const section = SECTIONS.find((s) => s.id === sec);
  const view = section ? section.view(item) : PAGES[sec] ? PAGES[sec](item) : homeView(SECTIONS);
  current = view;
  clear(main);
  if (view.back) main.append(h("a", { class: "back", href: view.back[0] }, `← ${view.back[1]}`));
  if (view.title) main.append(h("div", { class: "editor-head" }, h("h2", {}, view.title)));
  main.append(view.editor, clearBar);
  renderClear();
  renderTop();
  renderStage();
  window.scrollTo(0, 0);
  view.mounted?.();
}

// ?sample seeds a room so a screenshot or a demo lands on a filled editor.
if (features.rooms && new URLSearchParams(location.search).has("sample")) addRoom(EXAMPLES[0].name, EXAMPLES[0].source);

onChange(() => { renderTop(); renderClear(); renderPhoneBar(); live.changed(); remember(); });
window.addEventListener("hashchange", route);
Promise.all([recall(), loadShelf()]).then(([saved]) => {
  if (saved) {
    shelveDraft(saved);
    replaceDraft(saved);
  }
  route();
});
