// The rules editor: each rule is a row, "When this happens" then the things to do, built with buttons
// and dropdowns. Each edit changes the rules in place and calls onEdit; the room's Python is generated.
import { INSTRUMENTS, parseNote } from "@sdk/purple/sounds";
import { normalizeKey } from "../examples";
import { ACTIONS, BACKGROUNDS, DRUMS, WHENS, type Action, type Rule, type Thing } from "../rules";
import { draft } from "../state";
import { h } from "./dom";

type Options = [value: string, label: string][];

export function select(options: Options, value: string, onPick: (v: string) => void): HTMLSelectElement {
  const el = h("select", { class: "inline", onchange: () => onPick(el.value) }, ...options.map(([v, label]) => h("option", { value: v }, label)));
  el.value = value;
  return el;
}

export function textIn(value: string, onText: (v: string) => void, attrs: Record<string, unknown> = {}): HTMLInputElement {
  const el = h("input", { type: "text", class: "inline", value, ...attrs });
  el.addEventListener("input", () => onText(el.value));
  return el;
}

const numIn = (value: number, min: number, max: number, onNum: (n: number) => void) => {
  const el = h("input", { type: "number", class: "inline num", value: String(value), min, max });
  el.addEventListener("input", () => Number.isFinite(el.valueAsNumber) && onNum(el.valueAsNumber));
  return el;
};

const roomFiles = (kind: "images" | "sounds"): Options => draft.roomFiles.filter((f) => f.kind === kind).map((f) => [f.name, f.name]);
const instruments = (): Options => [...INSTRUMENTS, ...draft.instruments.map((i) => i.name)].map((n) => [n, n]);

export function rulesForm(rules: Rule[], onEdit: () => void): HTMLElement {
  const box = h("div", { class: "rules" });
  const restructure = () => { render(); onEdit(); };

  const thingEditor = (t: Thing, inKey: boolean) => {
    const kinds: Options = [["text", "this"], ...(inKey ? [["key", "the key pressed"] as [string, string]] : []), ["picture", "my picture"], ["pick", "one of these, at random"]];
    const value = t.kind === "key" ? null
      : t.kind === "picture" ? (roomFiles("images").length ? select([["", "pick one"], ...roomFiles("images")], t.value, (v) => { t.value = v; onEdit(); }) : h("span", { class: "dim small" }, "add one below first"))
      : textIn(t.value, (v) => { t.value = v; onEdit(); }, { placeholder: t.kind === "pick" ? "🐄, 🐖, 🐑" : "⭐", size: t.kind === "pick" ? 14 : 6 });
    return [select(kinds, t.kind, (k) => { t.kind = k as Thing["kind"]; t.value = ""; restructure(); }), value];
  };

  const args = (a: Action, inKey: boolean): (Node | string | null)[] => {
    switch (a.kind) {
      case "show": return thingEditor(a.thing, inKey);
      case "put": return [...thingEditor(a.thing, inKey), "at column", numIn(a.x, 0, 23, (n) => { a.x = n; onEdit(); }), "row", numIn(a.y, 0, 11, (n) => { a.y = n; onEdit(); })];
      case "write": case "say": return [textIn(a.text, (v) => { a.text = v; onEdit(); }, { size: 18 })];
      case "play": {
        const note = textIn(a.note, (v) => { a.note = v; note.classList.toggle("bad", !parseNote(v)); onEdit(); }, { size: 4 });
        return [note, "on", select(instruments(), a.instrument, (v) => { a.instrument = v; onEdit(); })];
      }
      case "drum": return [select(DRUMS.map((d) => [d, d]), a.name, (v) => { a.name = v; onEdit(); })];
      case "sound": return [roomFiles("sounds").length ? select([["", "pick one"], ...roomFiles("sounds")], a.name, (v) => { a.name = v; onEdit(); }) : h("span", { class: "dim small" }, "add one below first")];
      case "background": return [select(BACKGROUNDS.map(([label, c]) => [c, label]), a.color, (v) => { a.color = v; onEdit(); })];
      case "clear": return [];
    }
  };

  const actionRow = (rule: Rule, a: Action, i: number) => {
    const inKey = rule.when.kind === "key" || rule.when.kind === "other";
    const verbs = Object.entries(ACTIONS).map(([k, v]) => [k, v.label] as [string, string]);
    return h("div", { class: "rule-do" },
      select(verbs, a.kind, (k) => { rule.actions[i] = ACTIONS[k as Action["kind"]].fresh(); restructure(); }),
      ...args(a, inKey),
      h("button", { class: "linkbtn dim small", title: "Remove", onclick: () => { rule.actions.splice(i, 1); restructure(); } }, "✕"));
  };

  const whenRow = (rule: Rule, i: number) => {
    const w = rule.when;
    const extra = w.kind === "key"
      ? textIn(w.key, (v) => { const k = normalizeKey(v); if (k) { w.key = k; onEdit(); } }, { size: 6, title: "A letter, a number, or space, enter, up, down, left, right" })
      : w.kind === "every" ? h("span", {}, numIn(w.seconds, 0.1, 60, (n) => { w.seconds = n; onEdit(); }), " seconds") : null;
    return h("div", { class: "rule-when" }, h("b", {}, "When"),
      select(Object.entries(WHENS).map(([k, v]) => [k, v.label]), w.kind, (k) => { rule.when = WHENS[k as Rule["when"]["kind"]].fresh(); restructure(); }),
      extra,
      h("button", { class: "linkbtn dim small push", onclick: () => { rules.splice(i, 1); restructure(); } }, "Remove this rule"));
  };

  const render = () => box.replaceChildren(
    ...rules.map((rule, i) => h("div", { class: "rule" }, whenRow(rule, i),
      ...rule.actions.map((a, j) => actionRow(rule, a, j)),
      h("button", { class: "linkbtn small", onclick: () => { rule.actions.push(ACTIONS.show.fresh()); restructure(); } }, "+ do something else"))),
    h("button", { class: "btn secondary small", onclick: () => { rules.push({ when: WHENS.key.fresh(), actions: [ACTIONS.show.fresh()] }); restructure(); } }, "+ Add a rule"),
  );
  render();
  return box;
}
