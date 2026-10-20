// A room's knobs as a form: words and emoji as text, colors as swatches, numbers, and lists and dicts as
// rows that can grow and shrink. Each edit changes the knob in place and calls onEdit.
import { roomTitle } from "@sdk/pack";
import type { Knob, Lit } from "../knobs";
import { h } from "./dom";
import { textIn } from "./rulesform";

const COLOR = /^#[0-9a-f]{6}$/i;
const nested = (v: Lit) => v.t === "list" || v.t === "tuple" || v.t === "dict";
// Short plain values fit on one line; long words (a map row, a sentence) get a line each.
const inline = (items: Lit[]) => items.length <= 8 && items.every((x) => !nested(x) && !(x.t === "str" && x.v.length > 12));

function scalar(v: Lit, onEdit: () => void): HTMLElement {
  if (v.t === "str" && COLOR.test(v.v)) {
    const el = h("input", { type: "color", value: v.v });
    el.addEventListener("input", () => { v.v = el.value; onEdit(); });
    return el;
  }
  if (v.t === "str") return textIn(v.v, (s) => { v.v = s; onEdit(); }, { size: Math.min(40, Math.max(4, [...v.v].length + 2)), class: `inline${v.v.length > 12 ? " mono-in" : ""}` });
  if (v.t === "num") {
    const el = h("input", { type: "number", class: "inline num", value: String(v.v) });
    el.addEventListener("input", () => { if (Number.isFinite(el.valueAsNumber)) { v.v = el.valueAsNumber; onEdit(); } });
    return el;
  }
  if (v.t === "bool") {
    const el = h("input", { type: "checkbox", checked: v.v });
    el.addEventListener("change", () => { v.v = el.checked; onEdit(); });
    return el;
  }
  return h("span", { class: "dim small" }, "nothing");
}

function editor(v: Lit, onEdit: () => void, redraw: () => void): HTMLElement {
  if (!nested(v)) return scalar(v, onEdit);
  const changed = () => { redraw(); onEdit(); };
  const remove = (fn: () => void) => h("button", { class: "linkbtn dim small", title: "Remove", onclick: () => { fn(); changed(); } }, "✕");
  if (v.t === "dict") {
    const add = () => { const last = v.entries.at(-1)!; v.entries.push([{ t: "str", v: "" }, structuredClone(last[1])]); changed(); };
    return h("div", { class: "knob-rows" },
      ...v.entries.map((e, i) => h("div", { class: "form-row" }, editor(e[0], onEdit, redraw), "→", editor(e[1], onEdit, redraw), remove(() => v.entries.splice(i, 1)))),
      v.entries.length ? h("button", { class: "linkbtn small", onclick: add }, "+ add one") : null);
  }
  const items = (v as { items: Lit[] }).items;
  const growable = v.t === "list" && items.length > 0;
  const add = () => { items.push(structuredClone(items.at(-1)!)); changed(); };
  if (inline(items)) {
    return h("span", { class: "knob-inline" }, ...items.flatMap((x, i) => [editor(x, onEdit, redraw), growable && items.length > 1 ? remove(() => items.splice(i, 1)) : null]),
      growable ? h("button", { class: "linkbtn small", title: "Add one", onclick: add }, "+") : null);
  }
  return h("div", { class: "knob-rows" },
    ...items.map((x, i) => h("div", { class: "form-row" }, editor(x, onEdit, redraw), growable ? remove(() => items.splice(i, 1)) : null)),
    growable ? h("button", { class: "linkbtn small", onclick: add }, "+ add one") : null);
}

export function knobsForm(knobs: Knob[], onEdit: () => void): HTMLElement {
  return h("div", {}, h("p", { class: "dim small" }, "The settings at the top of this room's Python. Change them here, and the Python changes to match."),
    ...knobs.map((k) => {
      const card = h("div", { class: "card knob" });
      const redraw = () => card.replaceChildren(h("div", { class: "card-head" }, h("h2", {}, k.about || roomTitle(k.name.toLowerCase().replace(/_/g, "-"))), h("code", {}, k.name)),
        editor(k.value, onEdit, redraw));
      redraw();
      return card;
    }));
}
