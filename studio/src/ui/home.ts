// The home page: a card per section, each showing on a small Purple screen an idea for what to make
// there. Purple only ever appears inside a screen; the paper around it is Studio.
import { CELL_ASPECT, KEY_COLORS } from "@sdk/purple/art";
import { EXAMPLES, examplePicture } from "../photo";
import { countOf, hasWork, notInPieces, onChange, pieces, type Count } from "../state";
import { h } from "./dom";
import { clearEverythingButton, openPackButton } from "./packfile";
import { staysHere } from "./privacy";
import { purpleEmoji } from "./icons";
import { MIC } from "./record";
import { sticker } from "./stickers";
import type { View } from "./view";

// voice: takes the family's recorded voice, so its card says so.
export interface HomeSection { id: string; label: string; icon: string; blurb: string | (() => (string | Node)[]); voice?: boolean }

const RAINBOW = ["#5c2d91", "#c0392b", "#2f5bb5", "#a86f00", "#9b59d0", "#2e7d32"];
export const rainbow = (text: string) => h("span", {}, ...[...text].map((c, i) => h("span", { style: `color:${RAINBOW[i % RAINBOW.length]}` }, c)));

const svg = (viewBox: string, inner: string, cls: string) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  el.setAttribute("viewBox", viewBox);
  el.setAttribute("class", cls);
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = inner;
  return el;
};

// Glasses a kid painted on the dog with Art's red and blue keys, ringing its eyes.
const GLASSES = [
  "",
  "...........rrr......bbb",
  "........rrr...r....b...bbb",
  "..........r...rrrbbb...b",
  "..........r...r....b...b",
  "...........rrr......bbb",
];
const INK: Record<string, string> = { r: KEY_COLORS.y, b: KEY_COLORS.b };

// The dog from Pictures, in Purple's own cells, after a kid has painted on it.
function dogCells(): HTMLCanvasElement {
  const canvas = h("canvas");
  void examplePicture(EXAMPLES[0]).then(({ cells }) => {
    const [rows, cols] = [cells.length, cells[0].length];
    Object.assign(canvas, { width: cols, height: rows });
    canvas.style.aspectRatio = String(cols / (rows * CELL_ASPECT));
    const ctx = canvas.getContext("2d")!;
    cells.forEach((row, y) => row.forEach((color, x) => { ctx.fillStyle = INK[GLASSES[y]?.[x]] ?? color; ctx.fillRect(x, y, 1, 1); }));
  });
  return canvas;
}

// A recording of "bzzz bzz bzzzz": three buzzes, each swelling and fading, with quiet between.
const BUZZES = [[4, 46], [62, 90], [106, 156]];
const loudness = (x: number) => Math.max(0, ...BUZZES.map(([a, b]) => Math.sin((Math.PI * (x - a)) / (b - a)) * (x > a && x < b ? 1 : 0)));
const WAVE = `<path d="M${Array.from({ length: 321 }, (_, i) => `${i / 2} ${(15 - 13 * loudness(i / 2) * Math.sin(i * 1.3)).toFixed(1)}`).join(" L")}" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>`;

// A corner of the Explore starter room's world.
const WORLD = ["TTTTTTTTTTTT", "T.*..T..~~.T", "T....T.~~~*T", "T.f.....~~.T", "T....@.....T", "T.d...h..*.T", "TTTTTTTTTTTT"];
const TILES: Record<string, string> = { T: "🌳", "*": "⭐", f: "🦊", "@": "🧒", h: "🏠", d: "🚪" };

const SCREENS: Record<string, () => Node[]> = {
  pictures: () => [dogCells()],
  keys: () => [h("span", { class: "bubble" }, "“Hi sweetie, it's Grandma!”"), sticker("g")],
  words: () => [h("span", { class: "prompt" }, h("i", {}, "Type →"), h("span", { class: "field" }, "biscuit", h("span", { class: "caret" }))), h("span", { class: "big" }, "🐶"), h("i", {}, "Biscuit is our dog!")],
  instruments: () => [svg("0 0 160 30", WAVE, "wave"), h("span", {}, "bzzz bzz bzzzz")],
  colors: () => [h("span", {}, "My Purple Computer"), h("b", {})],
  rooms: () => [h("div", { class: "map" }, ...WORLD.flatMap((row, y) => [...row].map((c, x) =>
    h("span", { class: c === "~" ? "water" : (x + y) % 2 ? "grass dark" : "grass" }, TILES[c] ?? ""))))],
};

const micIcon = () => { const el = h("span", { class: "mic", "aria-hidden": "true" }); el.innerHTML = MIC; return el; };

const card = (s: HomeSection) =>
  h("a", { class: "home-card", href: `#${s.id}` },
    h("div", { class: "bezel" }, h("div", { class: `mini ${s.id}` }, ...SCREENS[s.id]())),
    h("b", {}, purpleEmoji(s.icon), s.label,
      s.voice ? h("span", { class: "voice-badge", title: "Takes your recorded voice" }, micIcon(), "Your voice") : null),
    h("span", {}, ...(typeof s.blurb === "string" ? [s.blurb] : s.blurb())));

// What's in the family's Purple Pack, and what isn't, as the download page counts them.
const packLine = h("div");
const listed = (list: Count[]) => list.map(countOf).join(", ");
function renderPack() {
  const [list, trying] = [pieces(), notInPieces()];
  packLine.replaceChildren(...[
    h("div", { class: "pack-line" },
      h("div", {},
        h("p", {}, h("b", {}, "In your Purple Pack: "), list.length ? `${listed(list)}.` : "nothing yet."),
        trying.length ? h("p", { class: "dim" }, h("b", {}, "Not in your Purple Pack: "), `${listed(trying)}.`) : null),
      list.length || trying.length ? h("a", { class: "btn small", href: "#pack" }, "Download") : null),
    h("p", { class: "dim" }, "When you're done, download your Purple Pack and put it on Purple with a USB drive."),
    h("p", { class: "dim" }, "Made one before? ", openPackButton("Open a Purple Pack"), " to keep going."),
    hasWork() ? h("p", { class: "dim" }, "Want a fresh start? ", clearEverythingButton(), ".") : null,
    staysHere("Everything happens in your web browser. Nothing you add is uploaded, and nothing is tracked."),
  ].filter((c) => c !== null));
}
onChange(renderPack);

export function homeView(sections: HomeSection[]): View {
  renderPack();
  return {
    title: "",
    editor: h("section", { class: "home" },
      h("h1", {}, "Make Purple ", h("span", { class: "stroke" }, "your own.")),
      h("p", { class: "serif" }, "A photo of your dog to draw on. A message from Grandma when you press G. Custom musical instruments."),
      h("p", { class: "home-note" }, h("b", {}, "For Purple Computer customers: "), "Purple Studio lets you customize it for your family. Make changes here and transfer them to your Purple Computer with a USB drive."),
      h("div", { class: "home-cards" }, ...sections.map(card)),
      packLine,
    ),
    live: { room: "art" },
    previewTitle: "This little computer is a real Purple Computer for you to try",
  };
}
