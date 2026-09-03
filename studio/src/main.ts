import "./styles.css";
import logo from "../../assets/logo.svg";
import { draft, onChange, pieces } from "./state";
import { clear, h } from "./ui/dom";
import { colorsView } from "./ui/colors";
import { downloadView } from "./ui/download";
import { formatView, installView } from "./ui/install";
import { instrumentView } from "./ui/instrument";
import { photosView } from "./ui/photos";
import { voiceView } from "./ui/voice";
import { wordsView } from "./ui/words";

interface Step { id: string; label: string; view: () => HTMLElement; filled?: () => boolean }

const STEPS: Step[] = [
  { id: "photos", label: "Photos", view: photosView, filled: () => draft.pictures.length > 0 },
  { id: "voice", label: "Voice", view: voiceView, filled: () => Object.keys(draft.letters).length + draft.phrases.length > 0 },
  { id: "words", label: "Words", view: wordsView, filled: () => draft.words.length + draft.synonyms.length + draft.ranked.length > 0 },
  { id: "instrument", label: "Instrument", view: instrumentView, filled: () => !!draft.instrument },
  { id: "colors", label: "Colors", view: colorsView, filled: () => !!draft.theme },
  { id: "pack", label: "Your pack", view: downloadView, filled: () => pieces().length > 0 },
];
const PAGES: Record<string, () => HTMLElement> = { install: installView, format: formatView };

function welcomeView(): HTMLElement {
  return h(
    "section",
    {},
    h("h1", {}, "Make it your family's."),
    h("p", { class: "serif" }, "The dog on the canvas. Grandma saying the letters."),
    h("p", { class: "lead" }, "Purple Computer ships almost empty on purpose. Studio lets you put a few of your own things in: photos to draw on, voices your kid knows, the words your family uses. It all goes into one file that rides along with Purple."),
    h("p", { class: "dim" }, "Everything here happens on this computer. No account, nothing uploaded, nothing kept after you close the tab."),
    h("p", { style: "margin-top:32px" }, h("a", { class: "btn", href: "#photos", style: "text-decoration:none" }, "Start with a photo")),
  );
}

const app = document.getElementById("app")!;
const nav = h("nav", { class: "steps" });

function renderNav() {
  clear(nav);
  const current = location.hash.slice(1);
  for (const s of STEPS) nav.append(h("a", { href: `#${s.id}`, "aria-current": s.id === current ? "page" : null }, s.label, s.filled?.() && h("span", { class: "dot" })));
}

function route() {
  const id = location.hash.slice(1);
  const step = STEPS.find((s) => s.id === id);
  const view = step?.view ?? PAGES[id] ?? welcomeView;
  const index = step ? STEPS.indexOf(step) : -1;
  const next = index >= 0 && index < STEPS.length - 1 ? STEPS[index + 1] : null;
  clear(app);
  app.append(
    h("header", { class: "topbar" }, h("img", { src: logo, alt: "" }), h("a", { class: "wordmark", href: "#", style: "text-decoration:none;color:inherit" }, "Purple ", h("span", {}, "Studio"))),
    nav,
    view(),
    h("div", { class: "foot" },
      id === "install" ? h("a", { href: "#format", class: "small dim" }, "What is in the pack") : h("a", { href: "#install", class: "small dim" }, "How a pack gets onto Purple"),
      next ? h("a", { href: `#${next.id}`, class: "btn secondary", style: "text-decoration:none" }, `Next: ${next.label}`) : step ? h("span") : null),
  );
  renderNav();
  window.scrollTo(0, 0);
}

onChange(renderNav);
window.addEventListener("hashchange", route);
window.addEventListener("beforeunload", (e) => pieces().length && e.preventDefault());
route();
