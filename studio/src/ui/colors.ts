import { ASDF_ROW, QWERTY_ROW, ZXCV_ROW, generateRowGradient } from "../purple/art";
import { DEFAULT_THEME, changed, draft } from "../state";
import { clear, h } from "./dom";
import { artFrame } from "./facsimile";

const ROWS = [
  ["qwerty", "Top letter row", QWERTY_ROW],
  ["asdf", "Home row", ASDF_ROW],
  ["zxcv", "Bottom row", ZXCV_ROW],
] as const;

export function colorsView(): HTMLElement {
  const preview = h("div");
  const controls = h("div", { class: "card" });

  function render() {
    const theme = draft.theme ?? DEFAULT_THEME;
    clear(preview);
    preview.append(artFrame(null, theme));
    clear(controls);
    const set = (patch: () => void) => {
      draft.theme ??= structuredClone(DEFAULT_THEME);
      patch();
      changed();
      render();
    };
    const color = (label: string, key: "background" | "surface") =>
      h("div", { class: "row" }, h("input", { type: "color", value: theme[key], oninput: (e: Event) => set(() => (draft.theme![key] = (e.target as HTMLInputElement).value)) }), h("span", {}, label), h("span", { class: "mono" }, theme[key]));
    controls.append(h("div", { class: "stack" }, color("Around the rooms", "background"), color("The canvas and the grid", "surface")));
    for (const [key, label, keys] of ROWS) {
      const grad = generateRowGradient(theme.hues[key], keys);
      controls.append(
        h("h3", {}, label),
        h("div", { class: "swatches" }, ...keys.map((k) => h("span", { style: `background:${grad[k]}`, title: k }))),
        h("input", { type: "range", min: 0, max: 359, value: theme.hues[key], oninput: (e: Event) => set(() => (draft.theme!.hues[key] = Number((e.target as HTMLInputElement).value))) }),
      );
    }
    if (draft.theme) controls.append(h("p", { style: "margin-top:20px" }, h("button", { class: "linkbtn dim", onclick: () => { draft.theme = null; changed(); render(); } }, "Back to Purple's colors")));
  }
  render();

  return h(
    "section",
    {},
    h("h2", {}, "Your own colors"),
    h("p", { class: "lead" }, "The purple behind everything, and the colors each keyboard row paints with. The number row stays gray so the stickers on the keys still match."),
    preview,
    controls,
    h("div", { class: "note" }, h("strong", {}, "What Purple does with this today: "), "nothing. These colors are written into Purple's code, not read from a file. The pack carries your choices as a small theme file so there is something concrete to point a future change at. The keyboard stickers that come with a Purple Key match Purple's own rows, not these."),
  );
}
