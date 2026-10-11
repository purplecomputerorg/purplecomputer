import { generateRowGradient, hslToHex } from "@sdk/purple/art";
import { DEFAULT_THEME, changed, draft, type Theme } from "../state";
import { clear, h } from "./dom";
import { LETTER_ROWS, artPreview } from "./facsimile";
import type { View } from "./view";

const PRESETS: [name: string, theme: Theme][] = [
  ["Purple", DEFAULT_THEME],
  ["Ocean", { background: "#0d2233", surface: "#112c40", hues: { qwerty: 190, asdf: 220, zxcv: 260 } }],
  ["Forest", { background: "#10241a", surface: "#153022", hues: { qwerty: 90, asdf: 130, zxcv: 25 } }],
  ["Sunset", { background: "#2a1420", surface: "#341a29", hues: { qwerty: 0, asdf: 25, zxcv: 310 } }],
  ["Night", { background: "#0c1024", surface: "#121834", hues: { qwerty: 220, asdf: 260, zxcv: 50 } }],
  ["Candy", { background: "#2b1238", surface: "#361745", hues: { qwerty: 335, asdf: 285, zxcv: 190 } }],
];
// Spread around the wheel, and including the hues Purple's own rows use (0, 50, 220).
const HUES = [0, 25, 50, 90, 130, 165, 190, 220, 260, 285, 310, 335];
const same = (a: Theme, b: Theme) => JSON.stringify(a) === JSON.stringify(b);

function keycaps(hue: number, keys: readonly string[]): HTMLElement {
  const grad = generateRowGradient(hue, [...keys]);
  return h("div", { class: "keycaps" }, ...keys.map((k, i) => h("span", { class: i < keys.length / 2 ? "" : "dark", style: `background:${grad[k]}` }, k)));
}

export function colorsView(): View {
  const body = h("div");
  const preview = artPreview(() => draft.pictures[0]?.cells ?? null);

  function render() {
    const theme = draft.theme ?? DEFAULT_THEME;
    const set = (next: Theme | null) => {
      draft.theme = next && !same(next, DEFAULT_THEME) ? next : null;
      changed();
      render();
    };
    const edit = (patch: (t: Theme) => void) => {
      const next = structuredClone(theme);
      patch(next);
      set(next);
    };
    const color = (label: string, key: "background" | "surface") =>
      h("label", { class: "swatch-pick" }, h("input", { type: "color", value: theme[key], onchange: (e: Event) => edit((t) => (t[key] = (e.target as HTMLInputElement).value)) }), h("span", {}, label));
    clear(body);
    body.append(
      h("div", { class: "presets" }, ...PRESETS.map(([name, t]) =>
        h("button", { class: "preset", "aria-pressed": String(same(t, theme)), onclick: () => set(structuredClone(t)) },
          h("span", { class: "preset-art", style: `background:${t.background}` }, ...LETTER_ROWS.map(([key]) => h("i", { style: `background:${hslToHex(t.hues[key], 0.75, 0.55)}` }))),
          name))),
      h("h3", {}, "Each letter row"),
      ...LETTER_ROWS.map(([key, label, keys]) => h("div", { class: "card row-pick" },
        h("div", { class: "row between" }, h("strong", {}, label), keycaps(theme.hues[key], keys)),
        h("div", { class: "hues" }, ...HUES.map((hue) => h("button", {
          class: "hue", title: `${hue}°`, "aria-pressed": String(hue === theme.hues[key]), style: `background:${hslToHex(hue, 0.75, 0.55)}`,
          onclick: () => edit((t) => (t.hues[key] = hue)),
        }))))),
      h("details", { class: "more-options" }, h("summary", {}, "Background and canvas"),
        h("div", { class: "row", style: "gap:24px" }, color("Around every room", "background"), color("The Art canvas", "surface"))),
    );
  }
  render();

  return {
    title: "Colors",
    soon: true,
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Pick the colors your kid paints with. Click the preview and type to try them."),
      body,
      h("p", { class: "dim small" }, "Purple doesn't use these colors yet. They go in the pack so they're ready when it does. The number row stays gray to match the key stickers."),
    ),
    preview,
    caption: "Art: every letter paints its row's color. Arrows move, Space puts the pen down.",
  };
}
