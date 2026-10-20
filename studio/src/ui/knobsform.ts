// A room's knobs as a form: words and emoji as text, colors as swatches, numbers, and lists and dicts as
// rows that can grow and shrink. Each edit changes the knob in place and calls onEdit.
import { roomTitle } from "@sdk/pack";
import type { Knob, Lit } from "../knobs";
import { field, h } from "./dom";
import { isEmoji } from "./emojipicker";
import { select, textIn } from "./rulesform";

type Dict = Extract<Lit, { t: "dict" }>;
type Str = Extract<Lit, { t: "str" }>;
// pages: the knob's own keys when its entries point at each other by name (a story's pages); links: the
// dicts holding those names, shown as dropdowns.
interface Ctx { onEdit: () => void; redraw: () => void; pages: string[]; links: Set<Dict>; relink: (from: string, to: string) => void }

const COLOR = /^#[0-9a-f]{6}$/i;
const LONG = 40;
const nested = (v: Lit) => v.t === "list" || v.t === "tuple" || v.t === "dict";
// Short plain values fit on one line; long words (a map row, a sentence) get a line each.
const inline = (items: Lit[]) => items.length <= 8 && items.every((x) => !nested(x) && !(x.t === "str" && x.v.length > 12));
const keyText = (k: Lit) => (k.t === "str" ? k.v : k.t === "num" ? String(k.v) : "");
const fit = (s: string) => Math.min(LONG, Math.max(2, [...s].length + 1));
const labelled = (label: string | undefined, el: HTMLElement) => (label ? field(label, el) : el);
// The item just added: it gets focus once drawn, so the family can type over the copy.
let fresh: Lit | null = null;
const dictsIn = (v: Lit): Dict[] =>
  v.t === "dict" ? [v, ...v.entries.flatMap(([, x]) => dictsIn(x))] : v.t === "list" || v.t === "tuple" ? v.items.flatMap(dictsIn) : [];

function text(v: Str, onEdit: () => void): HTMLElement {
  if (v.v.length > LONG) {
    const el = h("textarea", { class: "words-in", rows: 2, value: v.v });
    el.addEventListener("input", () => { v.v = el.value; onEdit(); });
    return el;
  }
  const emoji = isEmoji(v.v);
  return textIn(v.v, (s) => { v.v = s; onEdit(); }, { size: emoji ? 2 : fit(v.v), class: `inline${emoji ? " emoji-in" : v.v.length > 12 ? " mono-in" : ""}` });
}

function scalar(v: Lit, onEdit: () => void): HTMLElement {
  if (v.t === "str" && COLOR.test(v.v)) {
    const el = h("input", { type: "color", value: v.v });
    el.addEventListener("input", () => { v.v = el.value; onEdit(); });
    return el;
  }
  if (v.t === "str") return text(v, onEdit);
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

// peers: the values beside this one in the same spot of the other entries, so an empty dict knows what to add.
function editor(v: Lit, ctx: Ctx, peers: Lit[] = [], labels: string[] = []): HTMLElement {
  if (v.t === "dict") return focusIfFresh(v, dict(v, ctx, peers, labels));
  if (v.t === "list" || v.t === "tuple") return focusIfFresh(v, list(v.items, v.t === "list", ctx, labels));
  return focusIfFresh(v, scalar(v, ctx.onEdit));
}

function focusIfFresh(v: Lit, el: HTMLElement): HTMLElement {
  if (v !== fresh) return el;
  fresh = null;
  queueMicrotask(() => {
    const input = (el.matches("input, textarea") ? el : el.querySelector("input, textarea")) as HTMLInputElement | null;
    input?.focus();
    if (input?.type === "text" || input?.type === "textarea") input.select();
  });
  return el;
}

const changed = (ctx: Ctx) => { ctx.redraw(); ctx.onEdit(); };
const remove = (ctx: Ctx, fn: () => void, label?: string) => {
  const onclick = () => { fn(); changed(ctx); };
  return label ? h("button", { class: "linkbtn dim small", onclick }, label) : h("button", { class: "x", title: "Remove", "aria-label": "Remove", onclick }, "×");
};
const addSlot = (ctx: Ctx, push: () => Lit) =>
  h("button", { class: "add-slot", title: "Add another", "aria-label": "Add another", onclick: () => { fresh = push(); changed(ctx); } }, "+");

const row = (...cells: (HTMLElement | null)[]) => h("div", { class: "form-row knob-item" }, ...cells);
// An inline group's items each take a grid column, so every row's columns line up.
const width = (r: Element) => [...r.children].reduce((n, c) => n + (c.classList.contains("knob-inline") ? c.children.length : 1), 0);
function rows(items: HTMLElement[], add: HTMLElement | null): HTMLElement {
  const el = h("div", { class: "knob-rows" }, ...items, add);
  el.style.setProperty("--cols", String(Math.max(1, ...items.filter((r) => r.classList.contains("form-row")).map(width))));
  return el;
}

function list(items: Lit[], growable: boolean, ctx: Ctx, labels: string[]): HTMLElement {
  growable &&= items.length > 0;
  const add = () => (growable ? addSlot(ctx, () => { items.push(structuredClone(items.at(-1)!)); return items.at(-1)!; }) : null);
  const drop = (i: number) => (growable && items.length > 1 ? remove(ctx, () => items.splice(i, 1)) : null);
  const item = (x: Lit) => editor(x, ctx, [], nested(x) ? labels : []);
  if (inline(items)) {
    return h("span", { class: "knob-inline" },
      ...items.map((x, i) => h("span", { class: "knob-item tile" }, labelled(labels[i], item(x)), drop(i))), add());
  }
  return rows(items.map((x, i) => row(item(x), drop(i))), add());
}

// A new entry's key: the next free number when keys are numbers, else the first label and a number.
function nextKey(d: Dict, like: Lit, noun = "new"): Lit {
  const taken = new Set(d.entries.map(([k]) => keyText(k)));
  const numbered = /^\d+$/.test(keyText(like));
  for (let n = 1; ; n++) {
    const s = numbered ? String(n) : `${noun.replace(/\W+/g, "_")}${n}`;
    if (!taken.has(s)) return like.t === "num" ? { t: "num", v: n } : { t: "str", v: s };
  }
}

function keyIn(d: Dict, k: Lit, ctx: Ctx): HTMLElement {
  if (k.t !== "str") return scalar(k, ctx.onEdit);
  let was = k.v;
  const el = textIn(k.v, (s) => {
    k.v = s;
    el.classList.toggle("bad", d.entries.filter(([o]) => keyText(o) === s).length > 1);
    ctx.onEdit();
  }, { size: fit(k.v), class: "inline key-in" });
  if (ctx.pages.length && !ctx.links.has(d)) el.addEventListener("change", () => { ctx.relink(was, k.v); was = k.v; changed(ctx); });
  return el;
}

function link(v: Str, ctx: Ctx): HTMLElement {
  const missing = !ctx.pages.includes(v.v);
  const el = select([...(missing ? [[v.v, `${v.v || "nothing"} (missing)`] as [string, string]] : []), ...ctx.pages.map((p): [string, string] => [p, p])],
    v.v, (s) => { v.v = s; changed(ctx); });
  el.classList.toggle("bad", missing);
  return el;
}

function dict(d: Dict, ctx: Ctx, peers: Lit[], labels: string[]): HTMLElement {
  const values = d.entries.map(([, x]) => x);
  const template = d.entries.at(-1) ?? peers.flatMap((p) => (p.t === "dict" ? p.entries : [])).at(0);
  const add = () => { const [k, x] = structuredClone(template!); const key = nextKey(d, k, labels[0]); d.entries.push([key, x]); return key; };
  const drop = (i: number) => () => d.entries.splice(i, 1);
  const key = (k: Lit) => labelled(labels[0], focusIfFresh(k, keyIn(d, k, ctx)));
  const value = (x: Lit) => (ctx.links.has(d) && x.t === "str" ? link(x, ctx) : editor(x, ctx, values));
  const fields = (x: Lit) => x.t === "tuple"
    ? x.items.map((y, j) => labelled(labels[j + 1], editor(y, ctx, values.map((p) => (p.t === "tuple" ? p.items[j] : p)).filter(Boolean))))
    : [labelled(labels[1], value(x))];
  const entry = ([k, x]: [Lit, Lit], i: number) => d.entries.some(([, y]) => nested(y))
    ? h("div", { class: "knob-entry" },
      h("div", { class: "entry-head" }, key(k), remove(ctx, drop(i), "✕ remove")),
      h("div", { class: "entry-fields" }, ...fields(x)))
    : row(key(k), h("span", { class: "dim" }, "→"), labelled(labels[1], value(x)), remove(ctx, drop(i)));
  return rows(d.entries.map(entry), template ? addSlot(ctx, add) : null);
}

function linksOf(v: Lit): Pick<Ctx, "pages" | "links" | "relink"> {
  const keys = v.t === "dict" ? v.entries.map(([k]) => keyText(k)) : [];
  const dicts = v.t === "dict" ? v.entries.flatMap(([, x]) => dictsIn(x)).filter((d) => d.entries.every(([, y]) => y.t === "str")) : [];
  const linked = dicts.some((d) => d.entries.some(([, y]) => keys.includes(keyText(y))));
  const relink = (from: string, to: string) => {
    if (v.t !== "dict" || v.entries.filter(([k]) => keyText(k) === to).length !== 1) return;
    for (const d of dicts) for (const [, y] of d.entries) if (y.t === "str" && y.v === from) y.v = to;
  };
  return linked ? { pages: keys, links: new Set(dicts), relink } : { pages: [], links: new Set(), relink };
}

export function knobsForm(knobs: Knob[], onEdit: () => void): HTMLElement {
  return h("div", {}, h("p", { class: "dim small" }, "The settings at the top of this room's Python. Change them here, and the Python changes to match."),
    ...knobs.map((k) => {
      const card = h("div", { class: "card knob" });
      const redraw = () => card.replaceChildren(h("div", { class: "card-head" }, h("h2", {}, k.about || roomTitle(k.name.toLowerCase().replace(/_/g, "-"))), h("code", {}, k.name)),
        editor(k.value, { onEdit, redraw, ...linksOf(k.value) }, [], k.labels));
      redraw();
      return card;
    }));
}
