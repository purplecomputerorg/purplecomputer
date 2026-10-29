// A room's knobs as a form: words and emoji as text, colors as swatches, numbers, and lists and dicts as
// rows that can grow and shrink. Each edit changes the knob in place and calls onEdit.
import { roomTitle } from "@sdk/pack";
import { play } from "../audio";
import { isLoud, type Knob, type Lit } from "../knobs";
import { roomLine } from "../roomvoice";
import { isQuiet, phraseFor, putPhrase, QUIET } from "../state";
import { addRowButton, ask, field, h, removeButton } from "./dom";
import { emojiCell, isEmoji, searchEmoji } from "./emojipicker";
import { isMap, isWorld, legendFor, legendNames, lettersIn, mapPainter } from "./mappainter";
import { recordButton } from "./record";
import { drumIn, isDrum, pressKeyIn, select, textIn } from "./rulesform";

type Dict = Extract<Lit, { t: "dict" }>;
type Str = Extract<Lit, { t: "str" }>;
// An emoji, or one of the pack's pictures: the same picker sets either.
type Face = Extract<Lit, { t: "str" | "picture" }>;
// pages: the knob's own keys when its entries point at each other by name (a story's pages); links: the
// dicts holding those names, shown as dropdowns. taken: the emoji in the list being edited, so none repeats.
// drums: its comment or labels say drums, so a drum's name, or one of the pack's sounds, is picked from a list.
// stickers: its comment says sticker, so a color can be "stickers" instead: each key's sticker color.
// loud: its comment says out loud, so each of its words is read by Purple or recorded in the family's voice.
interface Ctx {
  onEdit: () => void; redraw: () => void; pages: string[]; links: Set<Dict>;
  relink: (from: string, to: string) => void; taken?: () => string[]; drums?: boolean; stickers?: boolean; loud?: boolean;
  // range: the lowest and highest a number may be, from its comment ("1 to 6"); without one, any number.
  range?: [number, number];
  // A map's legend, and the map it names the letters of; keyedBy: the legend a dict's keys are letters of (who says what).
  legend?: { dict: Dict; map: Lit }; keyedBy?: { dict: Dict; legend: Dict };
  // The knob's own list, which can be cleared to start over; lists nested in rows can't.
  top?: Lit[];
}
type Edit = Pick<Ctx, "onEdit" | "taken" | "drums" | "stickers" | "loud" | "range">;

const COLOR = /^#[0-9a-f]{6}$/i;
const DRUMS = /\bdrums?\b/i;
const STICKERS = "stickers";
const RANGE = /\b(\d+(?:\.\d+)?) to (\d+(?:\.\d+)?)\b/;
const LONG = 40;
// Letters a legend's new thing can take, plainest first.
const FREE_LETTERS = "ABCDEFGIJKLMNOPQSUVWXZabcdefghijklmnopqrstuvwxyz@%&+=?";
const unusedEmoji = (taken: string[]): Lit | undefined => searchEmoji("", 1, taken).map(({ emoji }): Lit => ({ t: "str", v: emoji }))[0];
const COLORS = ["#e44444", "#2e6ae1", "#2e9e4f", "#e0a020", "#9b4dca", "#e0457b", "#1fa5a5", "#8a5a2b"];
const faceText = (x: Lit) => (x.t === "str" || x.t === "picture" ? x.v : "");

// A new row for a list: a copy of the last, but with an emoji and a color none of the others have, so no two match.
function nextRow(items: Lit[]): Lit {
  const x = structuredClone(items.at(-1)!);
  if (x.t !== "tuple") return x;
  const column = (j: number) => items.map((r) => (r.t === "tuple" ? faceText(r.items[j]).toLowerCase() : ""));
  x.items = x.items.map((y, j) => y.t !== "str" ? y
    : COLOR.test(y.v) ? { t: "str", v: COLORS.find((c) => !column(j).includes(c)) ?? y.v }
    : isEmoji(y.v) ? unusedEmoji(column(j)) ?? y : y);
  return x;
}
const nested = (v: Lit) => v.t === "list" || v.t === "tuple" || v.t === "dict";
const isFace = (v: Lit) => v.t === "picture" || (v.t === "str" && isEmoji(v.v));
const emojiOnly = (items: Lit[]) => items.every(isFace);
// Short plain values fit on one line; long words (a map row, a sentence) get a line each, but a sound's name is a dropdown. Emoji wrap however many.
const long = (x: Lit) => x.t === "str" && x.v.length > 12 && !isDrum(x.v);
const inline = (items: Lit[]) => emojiOnly(items) || (items.length <= 8 && items.every((x) => !nested(x) && !long(x)));
const keyText = (k: Lit) => (k.t === "str" ? k.v : k.t === "num" ? String(k.v) : "");
const fit = (s: string) => Math.min(LONG, Math.max(2, [...s].length + 1));
// Labels come from the room's `# Labels:` comment as written; the form shows them capitalized, like its other headings.
const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const labelled = (label: string | undefined, el: HTMLElement) => (label ? field(sentence(label), el) : el);
// The item just added: it gets focus once drawn, so the family can type over the copy.
let fresh: Lit | null = null;
const dictsIn = (v: Lit): Dict[] =>
  v.t === "dict" ? [v, ...v.entries.flatMap(([, x]) => dictsIn(x))] : v.t === "list" || v.t === "tuple" ? v.items.flatMap(dictsIn) : [];

function faceIn(v: Face, { onEdit, taken }: Edit): HTMLElement {
  return h("span", { class: "emoji-wrap" }, emojiCell(v.v, () => "", (e) => {
    Object.assign(v, { t: isEmoji(e) ? "str" : "picture", v: e });
    onEdit();
  }, { taken, pictures: true }));
}

function text(v: Str, { onEdit, drums, loud }: Edit): HTMLElement {
  if (drums && isDrum(v.v)) return drumIn(v.v, (s) => { v.v = s; onEdit(); });
  if (v.v.length > LONG) {
    const el = h("textarea", { class: "words-in", rows: 2, value: v.v });
    el.addEventListener("input", () => { v.v = el.value; onEdit(); });
    return loud ? spoken(el, v) : el;
  }
  const el = textIn(v.v, (s) => { v.v = s; onEdit(); }, { size: fit(v.v), class: `inline${v.v.length > 12 && !/\s/.test(v.v) ? " mono-in" : ""}` });
  return loud ? spoken(el, v) : el;
}

// Words the room says out loud, read by Purple's room voice or recorded by the family, which Purple then plays instead.
function spoken(el: HTMLInputElement | HTMLTextAreaElement, v: Str): HTMLElement {
  const row = h("div", { class: "voice-row" });
  const note = h("span", { class: "dim small" });
  const say = (text: string) => void (note.textContent = text);
  type Voice = "purple" | "mine" | "quiet";
  const now = (): Voice | undefined => { const p = phraseFor(v.v); return p && (isQuiet(p.clip) ? "quiet" : "mine"); };
  let voice: Voice = now() ?? "purple";
  let said = v.v;
  let shown = "";
  const hearPurple = async () => {
    say("Getting Purple's voice ready…");
    const c = await roomLine(v.v);
    say(c ? "" : "Purple's voice didn't load. Try again in a moment.");
    if (c) play(c);
  };
  const record = () => recordButton((clip) => (v.v.trim() ? (putPhrase(v.v, clip, true), draw()) : say("Type the words first, then record them.")), say, true);
  const pick = (to: Voice) => async () => {
    if (now() === "mine" && to !== "mine" && !(await ask("Throw away your recording of these words?", "Throw it away"))) return;
    if (to !== "mine" || now() === "quiet") putPhrase(v.v, to === "quiet" ? QUIET : null, true);
    voice = to;
    draw();
  };
  const option = (to: Voice, label: string) => h("button", { type: "button", "aria-pressed": String(voice === to), onclick: pick(to) }, label);
  const draw = () => {
    const recorded = voice === "mine" ? phraseFor(v.v) : undefined;
    if (`${voice}${!!recorded}` === shown) return;
    shown = `${voice}${!!recorded}`;
    row.replaceChildren(
      h("span", { class: "seg" }, option("purple", "🔊 Purple reads it"), option("mine", "🎤 Your voice"), option("quiet", "🔇 No sound")),
      ...(voice === "purple" ? [h("button", { class: "rec-mini", title: "Hear Purple read it", "aria-label": "Hear Purple read it", onclick: hearPurple }, "▶")]
        : recorded ? [h("button", { class: "rec-mini", title: "Hear your recording", "aria-label": "Hear your recording", onclick: () => play(recorded.clip) }, "▶"), record()]
        : voice === "mine" ? [record()] : []),
      note);
    say(voice === "quiet" ? "The words show on the screen, and nothing is said." : voice === "purple" ? ""
      : recorded ? "Press the microphone to record it again." : "Press the microphone, read the words, and press it again.");
  };
  // No sound follows the words as they're edited; a recording is of the words it was made for, so it doesn't.
  el.addEventListener("input", () => {
    if (voice === "quiet") { putPhrase(said, null); putPhrase(v.v, QUIET, true); }
    said = v.v;
    draw();
  });
  draw();
  return h("div", { class: "spoken" }, el, row);
}

function scalar(v: Lit, edit: Edit): HTMLElement {
  const { onEdit } = edit;
  if (v.t === "str" && (COLOR.test(v.v) || (edit.stickers && v.v === STICKERS))) return colorIn(v, edit);
  if (isFace(v)) return faceIn(v as Face, edit);
  if (v.t === "str") return text(v, edit);
  if (v.t === "num") {
    const [min, max] = edit.range ?? [-Infinity, Infinity];
    const whole = Number.isInteger(v.v) && (!edit.range || Number.isInteger(min));
    const el = h("input", { type: "number", class: "inline num", value: String(v.v), step: whole ? 1 : "any", ...(edit.range && { min, max }) });
    const fit = () => Math.min(max, Math.max(min, whole ? Math.round(el.valueAsNumber) : el.valueAsNumber));
    el.addEventListener("input", () => { if (Number.isFinite(el.valueAsNumber)) { v.v = fit(); onEdit(); } });
    el.addEventListener("change", () => { el.value = String(v.v); });
    return el;
  }
  if (v.t === "bool") {
    const el = h("input", { type: "checkbox", checked: v.v });
    el.addEventListener("change", () => { v.v = el.checked; onEdit(); });
    return el;
  }
  return h("span", { class: "dim small" }, "nothing");
}

function colorIn(v: Str, { onEdit, stickers }: Edit): HTMLElement {
  const el = h("input", { type: "color", value: COLOR.test(v.v) ? v.v : "#f2c94c", disabled: v.v === STICKERS });
  el.addEventListener("input", () => { v.v = el.value; onEdit(); });
  if (!stickers) return el;
  const box = h("input", { type: "checkbox", checked: v.v === STICKERS });
  box.addEventListener("change", () => { v.v = box.checked ? STICKERS : el.value; el.disabled = box.checked; onEdit(); });
  return h("span", { class: "sticker-pick" }, el, h("label", { class: "row" }, box, "Sticker colors"));
}

// peers: the values beside this one in the same spot of the other entries, so an empty dict knows what to add.
function editor(v: Lit, ctx: Ctx, peers: Lit[] = [], labels: string[] = []): HTMLElement {
  if (v.t === "dict") return focusIfFresh(v, dict(v, ctx, peers, labels));
  if (v.t === "list" || v.t === "tuple") return focusIfFresh(v, list(v.items, v.t === "list", ctx, labels));
  return focusIfFresh(v, scalar(v, ctx));
}

function focusIfFresh(v: Lit, el: HTMLElement): HTMLElement {
  if (v !== fresh) return el;
  fresh = null;
  queueMicrotask(() => {
    // A new emoji opens the picker straight away, since its copy is never what the family wants.
    const cell = el.querySelector<HTMLButtonElement>(".emoji-cell");
    if (cell) return cell.click();
    const input = (el.matches("input, textarea") ? el : el.querySelector("input, textarea")) as HTMLInputElement | null;
    input?.focus();
    if (input?.type === "text" || input?.type === "textarea") input.select();
  });
  return el;
}

const changed = (ctx: Ctx) => { ctx.redraw(); ctx.onEdit(); };
const remove = (ctx: Ctx, fn: () => void) => removeButton(() => { fn(); changed(ctx); });
// A tile's "+" sits among the tiles it adds to; rows get a small button under them.
const addSlot = (ctx: Ctx, push: () => Lit, tile = false) => {
  const onclick = () => { fresh = push(); changed(ctx); };
  return tile ? h("button", { class: "add-slot", title: "Add another", "aria-label": "Add another", onclick }, "+") : addRowButton("Add another", onclick);
};

const row = (...cells: (HTMLElement | null)[]) => h("div", { class: "form-row knob-item" }, ...cells);
// An inline group's items each take a grid column, so every row's columns line up.
const width = (r: Element) => [...r.children].reduce((n, c) => n + (c.classList.contains("knob-inline") ? c.children.length : 1), 0);
// heads: the columns' names, shown once above the rows instead of beside every field.
function rows(items: HTMLElement[], add: HTMLElement | null, heads: string[] = []): HTMLElement {
  const head = heads.some(Boolean) ? h("div", { class: "form-row col-heads" }, ...heads.map((t) => h("span", {}, sentence(t ?? "")))) : null;
  const el = h("div", { class: "knob-rows" }, head, ...items, add);
  el.style.setProperty("--cols", String(Math.max(1, ...items.filter((r) => r.classList.contains("form-row")).map(width))));
  return el;
}

function list(items: Lit[], growable: boolean, ctx: Ctx, labels: string[]): HTMLElement {
  growable &&= items.length > 0;
  const tiles = inline(items);
  // An emoji list never repeats one: it redraws on every pick, so a repeat shows and says so.
  const taken = emojiOnly(items) ? () => items.map((x) => (x as Face).v) : undefined;
  // A new emoji is one the list doesn't have yet, so closing the picker without a pick leaves no repeat.
  const add = () => (growable ? addSlot(ctx, () => { items.push((taken && unusedEmoji(taken())) || nextRow(items)); return items.at(-1)!; }, tiles) : null);
  const drop = (i: number) => (growable && items.length > 1 ? remove(ctx, () => items.splice(i, 1)) : null);
  const sub = taken ? { ...ctx, taken, onEdit: () => changed(ctx) } : ctx;
  const repeat = (x: Lit) => !!taken && taken().filter((e) => e === (x as Face).v).length > 1;
  // Rows of plain values, like a drum's picture, name, and color, name their columns once.
  const heads = items.every((x) => x.t === "tuple" && !x.items.some(nested)) ? labels : [];
  const item = (x: Lit) => editor(x, sub, [], nested(x) && !heads.length ? labels : []);
  if (tiles) {
    const twice = [...new Set(items.filter(repeat).map((x) => (x.t === "picture" ? `The picture "${(x as Face).v}"` : (x as Face).v)))];
    const tilesEl = h("span", { class: "knob-inline" },
      ...items.map((x, i) => h("span", { class: `knob-item tile${repeat(x) ? " bad" : ""}` }, labelled(labels[i], item(x)), drop(i))), add());
    // An empty slot with the picker open on it: the first pick replaces the list, closing without one keeps it.
    const startOver = (e: MouseEvent) => {
      (e.currentTarget as HTMLElement).hidden = true;
      const cell = emojiCell("", () => "", (v) => { items.splice(0, items.length, { t: isEmoji(v) ? "str" : "picture", v } as Lit); changed(ctx); },
        { pictures: true, empty: "?", onClose: ctx.redraw });
      tilesEl.replaceChildren(h("span", { class: "knob-item tile" }, h("span", { class: "emoji-wrap" }, cell)));
      cell.click();
    };
    const clear = taken && growable && items === ctx.top && items.length > 1
      ? h("button", { type: "button", class: "linkbtn dim small", onclick: startOver }, "Clear and pick your own")
      : null;
    // Wrapped only when there's something to add, so rows that line up their tiles keep doing so.
    return twice.length || clear ? h("span", { class: "knob-tiles" }, tilesEl, clear,
      ...twice.map((e) => h("p", { class: "bad small" }, `${e} is in here twice, and each one needs to be different. Click one of them to pick something else.`))) : tilesEl;
  }
  return rows(items.map((x, i) => row(item(x), drop(i))), add(), heads);
}

// A dict whose first label names a key, like "key" or "number key", is keyed by keys the kid presses.
const KEYED = /\bkey\b/i;

// A new entry's key: the next free number when keys are numbers, the next free letter when they're keys
// the kid presses, else the first label and a number.
function nextKey(d: Dict, like: Lit, noun = "new"): Lit {
  const taken = new Set(d.entries.map(([k]) => keyText(k)));
  const numbered = /^\d+$/.test(keyText(like));
  const free = KEYED.test(noun) && !numbered && [..."abcdefghijklmnopqrstuvwxyz"].find((c) => !taken.has(c));
  if (free) return { t: "str", v: free };
  for (let n = 1; ; n++) {
    const s = numbered ? String(n) : `${noun.replace(/\W+/g, "_")}${n}`;
    if (!taken.has(s)) return like.t === "num" ? { t: "num", v: n } : { t: "str", v: s };
  }
}

function keyIn(d: Dict, k: Lit, ctx: Ctx, pressed: boolean): HTMLElement {
  if (k.t !== "str") return scalar(k, { onEdit: ctx.onEdit });
  let was = k.v;
  const edit = (s: string) => {
    k.v = s;
    el.classList.toggle("bad", d.entries.filter(([o]) => keyText(o) === s).length > 1);
    ctx.onEdit();
  };
  const el = pressed ? pressKeyIn(k.v, edit) : textIn(k.v, edit, { size: fit(k.v), class: "inline key-in" });
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

// A legend's things that aren't colors, as [letter, how it looks] for a dropdown.
const thingsOf = (legend: Dict): [string, string][] => legend.entries
  .filter(([, x]) => !(x.t === "str" && COLOR.test(x.v)))
  .map(([k, x]): [string, string] => [keyText(k), x.t === "picture" ? `${x.v} (picture)` : keyText(x)]);

// A legend's new thing: a letter the map and legend don't use yet, and an emoji it doesn't have, ready to pick over.
function addThing(d: Dict, map: Lit): Lit {
  const taken = new Set([...lettersIn(map), ...d.entries.map(([k]) => keyText(k))]);
  const letter = [...FREE_LETTERS].find((l) => !taken.has(l))!;
  const face = unusedEmoji(d.entries.map(([, x]) => (x.t === "str" || x.t === "picture" ? x.v : "")))!;
  d.entries.push([{ t: "str", v: letter }, face]);
  return face;
}

function dict(d: Dict, ctx: Ctx, peers: Lit[], labels: string[]): HTMLElement {
  const values = d.entries.map(([, x]) => x);
  const template = d.entries.at(-1) ?? peers.flatMap((p) => (p.t === "dict" ? p.entries : [])).at(0);
  const legend = ctx.legend?.dict === d ? ctx.legend : undefined;
  const things = ctx.keyedBy?.dict === d ? thingsOf(ctx.keyedBy.legend) : undefined;
  const add = () => {
    if (legend) return addThing(d, legend.map);
    const free = things?.find(([l]) => !d.entries.some(([k]) => keyText(k) === l));
    if (free) {
      const x = structuredClone(template![1]);
      d.entries.push([{ t: "str", v: free[0] }, x]);
      return x;
    }
    const [k, x] = structuredClone(template!);
    const key = nextKey(d, k, labels[0]);
    d.entries.push([key, x]);
    return key;
  };
  const drop = (i: number) => () => d.entries.splice(i, 1);
  const pressed = KEYED.test(labels[0] ?? "");
  const key = (k: Lit) => labelled(labels[0], focusIfFresh(k, keyIn(d, k, ctx, pressed)));
  const value = (x: Lit) => (ctx.links.has(d) && x.t === "str" ? link(x, ctx) : editor(x, ctx, values));
  const fields = (x: Lit) => x.t === "tuple"
    ? x.items.map((y, j) => labelled(labels[j + 1], editor(y, ctx, values.map((p) => (p.t === "tuple" ? p.items[j] : p)).filter(Boolean))))
    : [labelled(labels[1], value(x))];
  const entries = d.entries.some(([, y]) => nested(y));
  const entry = ([k, x]: [Lit, Lit], i: number) => entries
    ? h("div", { class: "knob-entry knob-item" }, remove(ctx, drop(i)), h("div", { class: "entry-fields" }, key(k), ...fields(x)))
    : row(legend ? h("span", { class: "legend-key", title: "How the Python writes this on the map" }, keyText(k))
      : things ? select(things, keyText(k), (l) => { (k as Str).v = l; changed(ctx); })
      : focusIfFresh(k, keyIn(d, k, ctx, pressed)),
      h("span", { class: "dim" }, "→"), value(x), remove(ctx, drop(i)));
  const full = things && things.every(([l]) => d.entries.some(([k]) => keyText(k) === l));
  return rows(d.entries.map(entry), template && !full ? addSlot(ctx, add) : null, entries ? [] : [labels[0], "", ...labels.slice(1)]);
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
  // Maps paint with the legend's emoji and colors, so they redraw whenever another knob changes.
  const maps: (() => void)[] = [];
  const values = knobs.map((o) => o.value);
  const legends = new Map(values.filter((v) => isMap(v) || isWorld(v)).map((map) => [legendFor(map, values), map] as const));
  // A dict keyed by a legend's letters, like who in the world says what.
  const keyedBy = (v: Lit) => [...legends.keys()].find((l): l is Dict => !!l && v !== l && v.t === "dict" && v.entries.length > 0
    && v.entries.every(([k]) => l.entries.some(([o]) => keyText(o) === keyText(k))));
  const edited = () => { onEdit(); maps.forEach((m) => m()); };
  return h("div", { class: "card knobs" },
    ...knobs.map((k) => {
      const one = !nested(k.value) && !(k.value.t === "str" && k.value.v.length > LONG);
      const card = h("section", { class: `knob${one ? " one-line" : ""}` });
      const head = () => h("div", { class: "knob-head" }, h("h2", {}, roomTitle(k.name.toLowerCase().replace(/_/g, "-"))), k.about && h("p", { class: "dim small" }, k.about));
      if (isMap(k.value) || isWorld(k.value)) {
        const legend = legendFor(k.value, values);
        const [painter, redraw] = mapPainter(k.value, () => legendNames(legend), onEdit);
        maps.push(redraw);
        card.replaceChildren(head(), painter);
        return card;
      }
      const map = k.value.t === "dict" ? legends.get(k.value) : undefined;
      const legend = map && { dict: k.value as Dict, map };
      const by = keyedBy(k.value);
      const range = RANGE.exec(k.about)?.slice(1).map(Number) as [number, number] | undefined;
      const ctx = { onEdit: edited, redraw: () => redraw(), drums: DRUMS.test(`${k.about} ${k.labels.join(" ")}`), stickers: /\bsticker/i.test(k.about), loud: isLoud(k), legend, range,
        keyedBy: by && { dict: k.value as Dict, legend: by }, top: k.value.t === "list" ? k.value.items : undefined, ...linksOf(k.value) };
      const redraw = () => card.replaceChildren(head(), editor(k.value, ctx, [], k.labels),
        legend ? h("p", { class: "dim small" }, "The letter beside each thing is how the Python writes it on the map. You only need it if you open the Python.") : "");
      redraw();
      return card;
    }));
}
