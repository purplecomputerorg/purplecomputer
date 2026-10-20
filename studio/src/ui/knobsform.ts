// A room's knobs as a form: words and emoji as text, colors as swatches, numbers, and lists and dicts as
// rows that can grow and shrink. Each edit changes the knob in place and calls onEdit.
import { roomTitle } from "@sdk/pack";
import type { Knob, Lit } from "../knobs";
import { h } from "./dom";
import { textIn } from "./rulesform";

const COLOR = /^#[0-9a-f]{6}$/i;
const isEmoji = (s: string) => /^\p{Extended_Pictographic}/u.test(s) && !/[\p{L}\p{N}]/u.test(s);
const nested = (v: Lit) => v.t === "list" || v.t === "tuple" || v.t === "dict";
// Short plain values fit on one line; long words (a map row, a sentence) get a line each.
const inline = (items: Lit[]) => items.length <= 8 && items.every((x) => !nested(x) && !(x.t === "str" && x.v.length > 12));
// The item just added: it gets focus once drawn, so the family can type over the copy.
let fresh: Lit | null = null;

function scalar(v: Lit, onEdit: () => void): HTMLElement {
  if (v.t === "str" && COLOR.test(v.v)) {
    const el = h("input", { type: "color", value: v.v });
    el.addEventListener("input", () => { v.v = el.value; onEdit(); });
    return el;
  }
  if (v.t === "str") {
    const look = isEmoji(v.v) ? " emoji-in" : v.v.length > 12 ? " mono-in" : "";
    return textIn(v.v, (s) => { v.v = s; onEdit(); }, { size: Math.min(40, Math.max(4, [...v.v].length + 2)), class: `inline${look}` });
  }
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
  const el = nested(v) ? group(v, onEdit, redraw) : scalar(v, onEdit);
  if (v === fresh) {
    fresh = null;
    queueMicrotask(() => {
      const input = (el.matches("input") ? el : el.querySelector("input")) as HTMLInputElement | null;
      input?.focus();
      if (input?.type === "text") input.select();
    });
  }
  return el;
}

// An inline group's items each take a grid column, so every row's columns line up.
const cells = (row: (HTMLElement | null)[]) => row.reduce((n, c) => n + (!c ? 0 : c.classList.contains("knob-inline") ? c.children.length : 1), 0);

function group(v: Lit, onEdit: () => void, redraw: () => void): HTMLElement {
  const changed = () => { redraw(); onEdit(); };
  const remove = (fn: () => void) => h("button", { class: "x", title: "Remove", "aria-label": "Remove", onclick: () => { fn(); changed(); } }, "×");
  const addSlot = (push: () => Lit) => h("button", { class: "add-slot", title: "Add another", "aria-label": "Add another", onclick: () => { fresh = push(); changed(); } }, "+");
  const rows = (cellRows: (HTMLElement | null)[][], add: HTMLElement | null) => {
    const el = h("div", { class: "knob-rows" }, ...cellRows.map((c) => h("div", { class: "form-row" }, ...c)), add);
    el.style.setProperty("--cols", String(Math.max(1, ...cellRows.map(cells))));
    return el;
  };
  if (v.t === "dict") {
    const add = () => { const key: Lit = { t: "str", v: "" }; v.entries.push([key, structuredClone(v.entries.at(-1)![1])]); return key; };
    return rows(v.entries.map((e, i) => [editor(e[0], onEdit, redraw), h("span", { class: "dim" }, "→"), editor(e[1], onEdit, redraw),
      v.entries.length > 1 ? remove(() => v.entries.splice(i, 1)) : null]), v.entries.length ? addSlot(add) : null);
  }
  const items = (v as { items: Lit[] }).items;
  const growable = v.t === "list" && items.length > 0;
  const removable = growable && items.length > 1;
  const add = () => { items.push(structuredClone(items.at(-1)!)); return items.at(-1)!; };
  if (inline(items)) {
    return h("span", { class: "knob-inline" },
      ...items.map((x, i) => removable ? h("span", { class: "tile" }, editor(x, onEdit, redraw), remove(() => items.splice(i, 1))) : editor(x, onEdit, redraw)),
      growable ? addSlot(add) : null);
  }
  return rows(items.map((x, i) => [editor(x, onEdit, redraw), removable ? remove(() => items.splice(i, 1)) : null]), growable ? addSlot(add) : null);
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
