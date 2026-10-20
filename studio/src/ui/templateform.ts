// The forms behind the picture keyboard and picture quiz. Each edit changes the form data in place
// and calls onEdit; the room's Python is regenerated from the data, never edited here.
import { roomTitle } from "@sdk/pack";
import { parseNote } from "@sdk/purple/sounds";
import { encodeWav } from "../audio";
import type { RoomFileKind } from "@sdk/pack";
import { MAX_OTHERS, normalizeKey, type QuizChoice, type QuizData, type Sound, type SoundboardData, type TemplateDraft } from "../examples";
import { draft } from "../state";
import { addRowButton, h, removeButton } from "./dom";
import { emojiCell } from "./emojipicker";
import { recordButton } from "./record";
import { addRoomData } from "./roomfiles";
import { textIn } from "./rulesform";

const mine = (kind: RoomFileKind) => draft.roomFiles.filter((f) => f.kind === kind).map((f) => f.name);
const checked = (el: HTMLInputElement, check: (v: string) => boolean) => {
  const mark = () => el.classList.toggle("bad", !check(el.value));
  el.addEventListener("input", mark);
  mark();
  return el;
};

interface Ctx { onEdit: () => void; say: (text: string) => void; rerender: () => void }

// An emoji, or one of the family's pictures, from the same picker as the Knobs. blank: what an empty one
// shows, and the picker's way back to empty, where empty means something.
const pictureIn = (o: { emoji: string }, c: Ctx, query: () => string, blank?: { empty: string; clear: string }) =>
  h("span", { class: "emoji-wrap" }, emojiCell(o.emoji, query, (e) => { o.emoji = e; c.rerender(); c.onEdit(); }, { pictures: true, ...blank }));

const NOTES = ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5", "D5", "E5"];

// A note, or one of the pack's sounds: picked from one short list, or recorded right here.
function soundIn(o: Sound, c: Ctx, nameFor: () => string): HTMLElement {
  const notes = NOTES.includes(o.note) || !parseNote(o.note) ? NOTES : [o.note, ...NOTES];
  const opts = (names: string[], label: (n: string) => string) => names.map((n) => h("option", { value: n }, label(n)));
  const pick = h("select", { class: "inline", onchange: () => { o.note = pick.value; c.onEdit(); } },
    h("option", { value: "" }, "No sound"),
    h("optgroup", { label: "Notes" }, ...opts(notes, (n) => `♪ ${n}`)),
    mine("sounds").length ? h("optgroup", { label: "Your sounds" }, ...opts(mine("sounds"), (n) => `🎤 ${roomTitle(n)}`)) : null);
  pick.value = o.note;
  const record = recordButton((clip) => {
    o.note = addRoomData("sounds", nameFor(), encodeWav(clip)).name;
    c.rerender();
    c.onEdit();
  }, c.say, true);
  return h("span", { class: "sound-in" }, pick, record);
}

const wordIn = (o: { word: string }, c: Ctx, placeholder: string) => textIn(o.word, (v) => { o.word = v; c.onEdit(); }, { placeholder });
const edits = (c: Ctx, fn: () => void) => () => { fn(); c.rerender(); c.onEdit(); };
const remove = (list: unknown[], i: number, c: Ctx) => removeButton(edits(c, () => list.splice(i, 1)));
const add = (label: string, onAdd: () => void, c: Ctx) => addRowButton(label, edits(c, onAdd));
// Rows that share columns, under one line of headings.
const sheet = (cols: string, heads: string[], ...rows: (Node | null)[]) =>
  h("div", { class: "sheet", style: `--cols: ${cols}` }, h("div", { class: "sheet-row sheet-head" }, ...heads.map((t) => h("span", {}, t))), ...rows);
const row = (...cells: (Node | null)[]) => h("div", { class: "sheet-row knob-item" }, ...cells);

function soundboardForm(data: SoundboardData, c: Ctx): Node[] {
  const KEY = { empty: "Key", clear: "Show the key itself" };
  const cells = (s: Sound & { emoji: string }, name: () => string, hint = "cow") =>
    [pictureIn(s, c, () => s.word, KEY), wordIn(s, c, hint), soundIn(s, c, name)];
  return [
    h("p", { class: "dim small" }, "A key is a letter, a number, or space, enter, up, down, left, right. A key with no picture shows itself. Others is every key not in the list."),
    sheet("3.5em 52px minmax(4em, 1fr) auto 26px", ["Key", "Picture", "Purple says", "Sound"],
      ...data.rows.map((r, i) => row(
        checked(textIn(r.key, (v) => { r.key = v; c.onEdit(); }, { placeholder: "c", class: "inline key-in" }), (v) => !!normalizeKey(v)),
        ...cells(r, () => r.word || `key-${r.key}`), remove(data.rows, i, c))),
      add("Add a key", () => data.rows.push({ key: "", emoji: "", word: "", note: "" }), c),
      h("div", { class: "sheet-row sheet-other" }, h("span", { class: "tag" }, "Others"), ...cells(data.other, () => data.other.word || "other-keys", "nothing"))),
  ];
}

function quizForm(data: QuizData, c: Ctx): Node[] {
  const choice = (tag: HTMLElement, ch: QuizChoice, x: Node | null = null) => row(tag, pictureIn(ch, c, () => ch.word), wordIn(ch, c, "cow"), x);
  return [
    h("p", { class: "dim small" }, "Purple reads each question out loud and mixes up the choices. When one is picked, Purple says its word."),
    ...data.rows.map((q, i) => h("div", { class: "q-block knob-item" },
      remove(data.rows, i, c),
      h("div", { class: "q-ask" },
        textIn(q.question, (v) => { q.question = v; c.onEdit(); }, { placeholder: "Which one says moo?" }),
        pictureIn(q, c, () => "", { empty: "Picture", clear: "No picture" })),
      sheet("4.5em 4.25em minmax(5em, 1fr) 26px", ["", "Picture", "Purple says"],
        choice(h("span", { class: "tag right" }, "Right"), q.right),
        ...q.others.map((o, j) => choice(h("span", { class: "tag" }, "Other"), o, remove(q.others, j, c))),
        q.others.length < MAX_OTHERS ? add("Another choice", () => q.others.push({ emoji: "", word: "" }), c) : null))),
    add("Add a question", () => data.rows.push({ question: "", emoji: "", right: { emoji: "", word: "" }, others: [{ emoji: "", word: "" }] }), c),
  ];
}

// onRedraw redraws the page's tray too, since pictures and sounds can be added here.
export function templateForm(t: TemplateDraft, onEdit: () => void, onRedraw: () => void): HTMLElement {
  const card = h("div", { class: "card form-card" });
  const status = h("p", { class: "dim small" });
  const c: Ctx = {
    onEdit,
    say: (text) => void (status.textContent = text),
    rerender: () => {
      card.replaceChildren(...(t.kind === "quiz" ? quizForm(t.data, c) : soundboardForm(t.data, c)), status);
      onRedraw();
    },
  };
  c.rerender();
  return card;
}
