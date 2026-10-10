// The forms behind the trivia and soundboard templates. Each edit changes the form data in place
// and calls onEdit; the room's Python is regenerated from the data, never edited here.
import { parseNote } from "@sdk/purple/sounds";
import { normalizeKey, type Sound, type TemplateDraft } from "../examples";
import { h } from "./dom";

type Row = Record<string, string>;
interface Column { field: string; label: string; width: string; placeholder: string; check?: (v: string) => string }

const noteCheck = (v: string) => (!v.trim() || parseNote(v) ? "" : "A note looks like C4 or F#3");
const keyCheck = (v: string) => (normalizeKey(v) ? "" : "Which key?");

function input(row: Row, col: Column, onEdit: () => void): HTMLElement {
  const el = h("input", { type: "text", value: row[col.field] ?? "", placeholder: col.placeholder, style: `width:${col.width}` });
  const problem = () => { el.title = col.check?.(el.value) ?? ""; el.classList.toggle("bad", !!el.title); };
  el.addEventListener("input", () => { row[col.field] = el.value; problem(); onEdit(); });
  problem();
  return el;
}

function rowsTable(rows: Row[], cols: Column[], blank: () => Row, addLabel: string, onEdit: () => void): HTMLElement {
  const body = h("div", { class: "form-rows" });
  const render = () => body.replaceChildren(
    h("div", { class: "form-row head" }, ...cols.map((c) => h("span", { style: `width:${c.width}` }, c.label))),
    ...rows.map((row, i) => h("div", { class: "form-row" }, ...cols.map((c) => input(row, c, onEdit)),
      h("button", { class: "linkbtn dim small", title: "Remove", onclick: () => { rows.splice(i, 1); render(); onEdit(); } }, "✕"))),
    h("button", { class: "btn secondary small", onclick: () => { rows.push(blank()); render(); onEdit(); } }, addLabel),
  );
  render();
  return body;
}

const SOUND_COLS: Column[] = [
  { field: "emoji", label: "Picture", width: "5em", placeholder: "🐄" },
  { field: "word", label: "Word to say", width: "10em", placeholder: "cow" },
  { field: "note", label: "Note", width: "4.5em", placeholder: "C4", check: noteCheck },
];

export function templateForm(t: TemplateDraft, onEdit: () => void): HTMLElement {
  if (t.kind === "trivia") {
    return h("div", { class: "card" },
      h("p", { class: "dim small" }, "One row per question. The answer is checked without caring about capitals or spaces at the ends."),
      rowsTable(t.data.rows as unknown as Row[], [
        { field: "emoji", label: "Picture", width: "5em", placeholder: "🦕" },
        { field: "question", label: "Question", width: "22em", placeholder: "Which dinosaur had a very long neck?" },
        { field: "answer", label: "Answer", width: "10em", placeholder: "brachiosaurus" },
      ], () => ({ emoji: "", question: "", answer: "" }), "Add a question", onEdit));
  }
  return h("div", { class: "card" },
    h("p", { class: "dim small" }, "One row per key: a letter, a number, or space, enter, up, down, left, right. A blank picture shows the key itself."),
    rowsTable(t.data.rows as unknown as Row[], [{ field: "key", label: "Key", width: "4.5em", placeholder: "c", check: keyCheck }, ...SOUND_COLS],
      () => ({ key: "", emoji: "", word: "", note: "" }), "Add a key", onEdit),
    h("p", { class: "dim small", style: "margin-top:16px" }, "Every other key:"),
    h("div", { class: "form-row" }, ...SOUND_COLS.map((c) => input(t.data.other as unknown as Sound & Row, c, onEdit))),
  );
}
