import "./fonts";
import "./styles.css";
import logo from "../../assets/logo.svg";
import { features, hasWork, onChange, pieces, replaceDraft } from "./state";
import { recall, remember } from "./saved";
import { clearEverythingButton, clearSectionButton, openPackButton } from "./ui/packfile";
import { clear, h } from "./ui/dom";
import { colorsView } from "./ui/colors";
import { downloadView } from "./ui/download";
import { formatView, installView } from "./ui/install";
import { instrumentsView } from "./ui/instrument";
import { picturesView } from "./ui/pictures";
import { privacyView, staysHere } from "./ui/privacy";
import { pythonView } from "./ui/python";
import { EXAMPLES } from "./examples";
import { addRoom } from "./pybridge";
import { guideView } from "./ui/guide";
import { typingKeys } from "./keys";
import type { Room } from "./live/boot";
import { Laptop } from "./ui/laptop";
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
  // What "Clear all" names on this section's pages; colors has its own undo instead.
  clears?: string;
  view: (item: string | null) => View;
}

const SECTIONS: Section[] = [
  { id: "pictures", clears: "pictures", label: "Pictures", icon: "🖼️", blurb: "A photo or picture for for them to open and paint on top of", view: picturesView },
  { id: "voice", clears: "recordings", label: "Voice", icon: "🎙️", blurb: "Make any key say any sound or recorded voice", view: voiceView },
  { id: "words", clears: "emoji words", label: "Emoji", icon: "🐶", blurb: "Pick an emoji for any word", view: wordsView },
  { id: "instruments", clears: "instruments", label: "Instruments", icon: "🎹", blurb: "Custom instruments for them to play", view: instrumentsView },
  { id: "rooms", clears: "rooms", label: "Rooms", icon: "🧩", blurb: "A little game, story, or quiz", view: roomsView },
  { id: "colors", label: "Colors", icon: "🎨", blurb: "Make Purple green, or change the colors the letters type", view: colorsView },
].filter((s) => features.rooms || s.id !== "rooms");
type Page = [id: string, label: string, view: (item: string | null) => View];
const MORE = ([
  ["install", "Putting it on Purple", installView],
  ["guide", "Room guide", guideView],
  ["python", "Python console", pythonView],
  ["format", "What is in a Purple Pack", formatView],
  ["privacy", "Your privacy", privacyView],
] satisfies Page[]).filter(([id]) => features.rooms || id !== "guide");
const PAGES: Record<string, (item: string | null) => View> = { pack: downloadView, ...Object.fromEntries(MORE.map(([id, , view]) => [id, view])) };

function welcomeView(): View {
  return {
    title: "",
    editor: h(
      "section",
      {},
      h("h1", {}, "Make Purple your own"),
      h("p", { class: "serif" }, "A photo of your dog to draw on. A message from Grandma when you press G. Custom musical instruments."),
      h("div", { class: "cards" }, ...SECTIONS.map((s) =>
        h("a", { class: "pick", href: `#${s.id}` }, h("span", { class: "pick-icon" }, s.icon), h("b", {}, s.label), h("span", {}, s.blurb)))),
      h("p", { class: "dim" }, "When you're done, download your Purple Pack and put it on Purple with a USB drive."),
      h("p", { class: "dim" }, "Made one before? ", openPackButton("Open your Purple Pack"), " to keep going."),
      hasWork() ? h("p", { class: "dim" }, "Want a fresh start? ", clearEverythingButton(), ".") : null,
      staysHere("Everything happens in your web browser. Nothing you add is uploaded, and nothing is tracked."),
    ),
    live: { room: "art" },
    previewTitle: "This is Purple",
    caption: "The real Purple, running in your browser. Type any letter to paint, and the arrows move.",
  };
}

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
const stageTitle = h("h3");
const stageCaption = h("p", { class: "caption" });
// Purple's voice runs espeak-ng, which is GPL: its source goes wherever the voice does.
const voiceCredit = h("p", { class: "dim small" }, h("a", { href: "voice/espeak-ng/README.md", target: "_blank" }, "Voice license and source"));
const stageStays = staysHere("This Purple runs in your browser. What you type into it stays on your device.");
const stage = h("aside", { class: "stage" }, h("div", { class: "stage-inner" }, stageTitle, laptop.element, phoneBar, stageCaption, stageStays, voiceCredit));
const body = h("div", { class: "body" }, main, stage);
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
      h("span", { class: "icon" }, s.icon), h("span", { class: "label" }, s.label), added(s.id) ? h("span", { class: "n" }, String(added(s.id))) : null))),
    h("a", { class: "privacy-link", href: "#privacy", "aria-current": sec === "privacy" ? "page" : null }, "🔒", h("span", {}, " Privacy")),
    h("details", { class: "more-menu" }, h("summary", {}, "More"),
      h("div", { onclick: (e: Event) => (e.target as HTMLElement).closest("details")?.removeAttribute("open") },
        ...MORE.map(([id, label]) => h("a", { href: `#${id}`, "aria-current": sec === id ? "page" : null }, label)), clearEverythingButton("clear-all"))),
    h("a", { class: `btn download${sec === "pack" ? " here" : ""}`, href: "#pack" }, "Download", n ? h("span", { class: "n" }, String(n)) : null),
  );
}

function renderStage() {
  const v = current;
  body.classList.toggle("no-stage", !v?.live);
  live.element.hidden = !v?.live;
  stageTitle.textContent = v?.previewTitle ?? "What your kid sees";
  stageCaption.textContent = v?.caption ?? "";
  voiceCredit.hidden = !v?.live;
  if (v?.live) live.show(v.live);
  renderPhoneBar();
  tapTarget = v?.live ? (key) => live.key(key) : null;
}

function route() {
  current?.cleanup?.();
  const [sec, item] = parseHash();
  const section = SECTIONS.find((s) => s.id === sec);
  const view = section ? section.view(item) : PAGES[sec] ? PAGES[sec](item) : welcomeView();
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
recall().then((saved) => {
  if (saved) replaceDraft(saved);
  route();
});
