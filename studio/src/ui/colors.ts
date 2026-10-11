import { ASDF_ROW, QWERTY_ROW, ZXCV_ROW, DEFAULT_THEME, hslToHex, themePalette, type Role, type Theme } from "@sdk";
import { changed, draft } from "../state";
import { clear, h } from "./dom";
import { PURPLE_STICKERS, sticker } from "./stickers";
import type { View } from "./view";

// Screen colors: one base each; Purple's text and panels follow it.
const SCREENS: [name: string, base: string][] = [
  ["Purple", DEFAULT_THEME.base], ["Ocean", "#0d2233"], ["Forest", "#10241a"], ["Sunset", "#2a1420"], ["Night", "#0c1024"], ["Cocoa", "#24170f"], ["Daylight", "#efe9f7"],
];
const ROWS = [["qwerty", "Top row", QWERTY_ROW], ["asdf", "Middle row", ASDF_ROW], ["zxcv", "Bottom row", ZXCV_ROW]] as const;
// Spread around the wheel, and including the hues Purple's own rows use (0, 50, 220).
const HUES = [0, 25, 50, 90, 130, 165, 190, 220, 260, 285, 310, 335];
const TEXT_ROLES: [Role, string][] = [["text", "Text"], ["accent", "Titles"], ["muted", "Hints"], ["dim", "Quiet hints"]];
const SCREEN_ROLES: [Role, string][] = [
  ["bg", "Around everything"], ["surface", "Room panel"], ["canvas", "Art canvas"], ["tile", "Keys and cards"], ["field", "Typing box"],
  ["hair", "Thin borders"], ["line", "Outlines"], ["primary", "Highlight"], ["on_primary", "Text on highlight"],
];
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

// A small picture of a screen in a palette: the ground, the panel with a canvas, a line of text.
function miniScreen(theme: Theme): HTMLElement {
  const p = themePalette(theme);
  return h("span", { class: "mini-screen", style: `background:${p.bg}` },
    h("span", { style: `background:${p.surface};border-color:${p.line}` }, h("i", { style: `background:${p.canvas}` }), h("em", { style: `color:${p.text}` }, "Hi!")));
}

export function colorsView(): View {
  const body = h("div");
  const theme = () => draft.theme ?? DEFAULT_THEME;
  // Keeps the draft null while it matches Purple's own colors, so an untouched pack has no theme.
  const set = (next: Theme, rerender = true) => {
    draft.theme = same(next, DEFAULT_THEME) ? null : next;
    changed();
    if (rerender) render();
  };
  const edit = (patch: (t: Theme) => void, rerender = true) => {
    const next = structuredClone(theme());
    patch(next);
    set(next, rerender);
  };

  // A color well for one role. Dragging in the picker updates Purple; letting go redraws the page.
  const well = ([role, label]: [Role, string]) => h("label", { class: "swatch-pick" },
    h("input", {
      type: "color", value: themePalette(theme())[role],
      oninput: (e: Event) => edit((t) => (t.colors[role] = (e.target as HTMLInputElement).value), false),
      onchange: () => render(),
    }),
    h("span", {}, label, role in theme().colors ? h("button", { class: "linkbtn dim small", onclick: (e: Event) => { e.preventDefault(); edit((t) => delete t.colors[role]); } }, " auto") : null));

  function render() {
    const t = theme();
    const custom = !SCREENS.some(([, base]) => base === t.base);
    clear(body);
    body.append(h("div", {},
      h("h3", {}, "Screen"),
      h("div", { class: "presets" },
        ...SCREENS.map(([name, base]) => h("button", { class: "preset", "aria-pressed": String(t.base === base), onclick: () => edit((n) => { n.base = base; n.colors = {}; }) },
          miniScreen({ ...t, base, colors: {} }), name)),
        h("label", { class: "preset", "aria-pressed": String(custom) },
          h("span", { class: "mini-screen wheel" }, h("input", {
            type: "color", value: t.base, "aria-label": "Any color",
            oninput: (e: Event) => edit((n) => { n.base = (e.target as HTMLInputElement).value; n.colors = {}; }, false),
            onchange: () => render(),
          })),
          "Any color")),
      h("details", { class: "more-options" }, h("summary", {}, "Text colors"),
        h("p", { class: "dim small" }, "Purple picks text that's easy to read on your screen color. Change any of it here."),
        h("div", { class: "wells" }, ...TEXT_ROLES.map(well))),

      h("h3", {}, "Paint colors and stickers"),
      h("p", { class: "dim small" }, "Each letter row paints its own color, the same color as its sticker."),
      ...ROWS.map(([key, label, keys]) => h("div", { class: "card row-pick" },
        h("div", { class: "row between" }, h("strong", {}, label), h("div", { class: "sticker-row" }, ...keys.map((k) => sticker(k)))),
        h("div", { class: "hues" }, ...HUES.map((hue) => h("button", {
          class: "hue", title: `${hue}°`, "aria-pressed": String(hue === t.hues[key]), style: `background:${hslToHex(hue, 0.75, 0.55)}`,
          onclick: () => edit((n) => (n.hues[key] = hue)),
        }))))),
      same(t.hues, DEFAULT_THEME.hues) ? null : h("div", { class: "note sticker-note" },
        h("span", {}, "The stickers on your real keyboard stay Purple's colors:"),
        h("span", { class: "sticker-row tiny" }, ...["1", "q", "a", "z"].map((k) => sticker(k, PURPLE_STICKERS))),
        h("button", { class: "linkbtn small", onclick: () => edit((n) => (n.hues = { ...DEFAULT_THEME.hues })) }, "Match them again")),

      h("details", { class: "more-options" }, h("summary", {}, "Every screen color"),
        h("div", { class: "wells" }, ...SCREEN_ROLES.map(well))),
      draft.theme ? h("p", {}, h("button", { class: "linkbtn dim", onclick: () => set(structuredClone(DEFAULT_THEME)) }, "Back to Purple's colors")) : null,
    ));
  }
  render();

  return {
    title: "Colors",
    editor: h("section", {}, h("p", { class: "lead" }, "Pick a color for Purple's screen. The words on it change to stay easy to read."), body),
    live: { room: "art" },
    caption: "Type on the keyboard to paint: every key paints its sticker's color.",
  };
}
