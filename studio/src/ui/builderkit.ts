// What a room's own builder (story, world) shares: reading its knobs by name, and the pieces every builder shows.
// A builder edits the knobs' values in place and calls onEdit, as the generic knob form does.
import type { Knob, Lit } from "../knobs";
import { h } from "./dom";
import { spoken } from "./knobsform";
import { drumIn } from "./rulesform";

export type Str = Extract<Lit, { t: "str" }>;
export type Face = Extract<Lit, { t: "str" | "picture" }>;
export type Dict = Extract<Lit, { t: "dict" }>;
export type Tuple = { t: "tuple"; items: Lit[] };

export const str = (v: string): Str => ({ t: "str", v });
export const isStr = (v: Lit | undefined): v is Str => v?.t === "str";
export const isFace = (v: Lit | undefined): v is Face => v?.t === "str" || v?.t === "picture";
export const COLOR = /^#[0-9a-f]{6}$/i;
export const knobNamed = (knobs: Knob[], name: string) => knobs.find((k) => k.name === name);
// A tuple of exactly these kinds of parts.
export const tupleOf = (v: Lit, ...tests: ((x: Lit | undefined) => boolean)[]): v is Tuple =>
  v.t === "tuple" && v.items.length === tests.length && tests.every((t, i) => t(v.items[i]));

export const section = (title: string, about: string, ...children: (Node | string | null)[]) =>
  h("section", { class: "knob builder-part" }, h("div", { class: "knob-head" }, h("h2", {}, title), about ? h("p", { class: "dim small" }, about) : null), ...children);

// Words said out loud: typed, and read by Purple or recorded in the family's voice.
export function wordsIn(v: Str, onEdit: () => void, placeholder = ""): HTMLElement {
  const el = h("textarea", { class: "words-in", rows: 2, value: v.v, placeholder });
  el.addEventListener("input", () => { v.v = el.value; onEdit(); });
  return spoken(el, v);
}

// A moment's sound, from a knob like FIND_SOUND: none, or a drum or one of the pack's sounds.
export function soundRow(label: string, k: Knob | undefined, onEdit: () => void): HTMLElement | null {
  const v = k?.value;
  if (!isStr(v)) return null;
  return h("label", { class: "sound-row" }, h("span", {}, label), drumIn(v.v, (s) => { v.v = s; onEdit(); }, true));
}
