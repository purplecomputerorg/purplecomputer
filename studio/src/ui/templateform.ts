// The forms behind the picture keyboard and picture quiz. Each edit changes the form data in place
// and calls onEdit; the room's Python is regenerated from the data, never edited here.
import { parseNote } from "@sdk/purple/sounds";
import { encodeWav } from "../audio";
import type { RoomFileKind } from "@sdk/pack";
import { MAX_OTHERS, normalizeKey, type QuizChoice, type QuizData, type Sound, type SoundboardData, type TemplateDraft } from "../examples";
import { draft } from "../state";
import { filePicker, h } from "./dom";
import { recordButton } from "./record";
import { addRoomData, addRoomFile } from "./roomfiles";
import { select, textIn } from "./rulesform";

const mine = (kind: RoomFileKind) => draft.roomFiles.filter((f) => f.kind === kind).map((f) => f.name);
const checked = (el: HTMLInputElement, check: (v: string) => boolean) => {
  const mark = () => el.classList.toggle("bad", !check(el.value));
  el.addEventListener("input", mark);
  mark();
  return el;
};

interface Ctx { onEdit: () => void; say: (text: string) => void; rerender: () => void }

// An emoji, or one of the pack's pictures: picked from the list, or added right here.
function pictureIn(o: { emoji: string }, c: Ctx, placeholder: string): HTMLElement {
  const pictures = mine("images");
  const isMine = pictures.includes(o.emoji);
  const text = textIn(isMine ? "" : o.emoji, (v) => { o.emoji = v; pick.value = ""; c.onEdit(); }, { size: 5, placeholder });
  const pick = select([["", "or a picture of mine"], ...pictures.map((n): [string, string] => [n, n])], isMine ? o.emoji : "",
    (v) => { o.emoji = v; text.value = ""; c.onEdit(); });
  const add = filePicker("image/*", (file) => addRoomFile("images", file)
    .then((f) => { o.emoji = f.name; c.rerender(); c.onEdit(); })
    .catch(() => c.say("That picture didn't open. Try a photo saved as JPG or PNG.")), pictures.length ? "add one" : "or add a photo");
  return h("span", { class: "row" }, text, pictures.length ? pick : null, add);
}

// A note, or one of the pack's sounds: picked from the list, or recorded right here.
function soundIn(o: Sound, c: Ctx, nameFor: () => string): HTMLElement {
  const sounds = mine("sounds");
  const kind = sounds.includes(o.note) ? o.note : o.note.trim() ? "note" : "";
  const pick = select([["", "no sound"], ["note", "a note"], ...sounds.map((n): [string, string] => [n, `my sound: ${n}`])], kind,
    (v) => { o.note = v === "note" ? "C4" : v; c.rerender(); c.onEdit(); });
  const note = kind === "note" && checked(textIn(o.note, (v) => { o.note = v; c.onEdit(); }, { size: 4, title: "A note looks like C4 or F#3" }), (v) => !!parseNote(v));
  const record = recordButton((clip) => {
    o.note = addRoomData("sounds", nameFor(), encodeWav(clip)).name;
    c.rerender();
    c.onEdit();
  }, c.say, true);
  return h("span", { class: "row" }, pick, note, record);
}

const wordIn = (o: { word: string }, c: Ctx, placeholder: string) => textIn(o.word, (v) => { o.word = v; c.onEdit(); }, { size: 12, placeholder });
const remove = (label: string, list: unknown[], i: number, c: Ctx) =>
  h("button", { class: "linkbtn dim small push", onclick: () => { list.splice(i, 1); c.rerender(); c.onEdit(); } }, label);
const addButton = (label: string, onAdd: () => void, c: Ctx, cls = "btn secondary small") =>
  h("button", { class: cls, onclick: () => { onAdd(); c.rerender(); c.onEdit(); } }, label);

function soundboardForm(data: SoundboardData, c: Ctx): Node[] {
  const sound = (s: Sound, name: () => string) => [h("span", {}, "says"), wordIn(s, c, "cow"), h("span", {}, "plays"), soundIn(s, c, name)];
  return [
    h("p", { class: "dim small" }, "A key is a letter, a number, or space, enter, up, down, left, right. A blank picture shows the key itself."),
    h("div", { class: "rules" },
      ...data.rows.map((row, i) => h("div", { class: "rule" },
        h("div", { class: "rule-when" }, h("b", {}, "Key"),
          checked(textIn(row.key, (v) => { row.key = v; c.onEdit(); }, { size: 6, placeholder: "c" }), (v) => !!normalizeKey(v)),
          h("span", {}, "shows"), pictureIn(row, c, "🐄"), remove("Remove this key", data.rows, i, c)),
        h("div", { class: "rule-do" }, ...sound(row, () => row.word || `key-${row.key}`)))),
      addButton("+ Add a key", () => data.rows.push({ key: "", emoji: "", word: "", note: "" }), c),
      h("div", { class: "rule" },
        h("div", { class: "rule-when" }, h("b", {}, "Every other key"), h("span", {}, "shows"), pictureIn(data.other, c, "")),
        h("div", { class: "rule-do" }, ...sound(data.other, () => data.other.word || "other-keys")))),
  ];
}

function quizForm(data: QuizData, c: Ctx): Node[] {
  const choice = (label: string, ch: QuizChoice, placeholder: string, extra: Node | null = null) => h("div", { class: "rule-do" },
    h("span", {}, label), pictureIn(ch, c, placeholder), h("span", {}, "Purple says"), wordIn(ch, c, "cow"), extra);
  return [
    h("p", { class: "dim small" }, "Purple reads each question out loud and mixes up the choices. A choice is an emoji or one of your pictures, and the word Purple says when it's picked."),
    h("div", { class: "rules" },
      ...data.rows.map((row, i) => h("div", { class: "rule" },
        h("div", { class: "rule-when" }, h("b", {}, "Ask"),
          textIn(row.question, (v) => { row.question = v; c.onEdit(); }, { size: 28, placeholder: "Which one says moo?" }),
          h("span", {}, "with"), pictureIn(row, c, "🌧️"), remove("Remove this question", data.rows, i, c)),
        choice("Right answer", row.right, "🐄"),
        ...row.others.map((o, j) => choice("Another choice", o, "🐖",
          h("button", { class: "linkbtn dim small", title: "Remove", onclick: () => { row.others.splice(j, 1); c.rerender(); c.onEdit(); } }, "✕"))),
        row.others.length < MAX_OTHERS ? addButton("+ another choice", () => row.others.push({ emoji: "", word: "" }), c, "linkbtn small") : null)),
      addButton("+ Add a question", () => data.rows.push({ question: "", emoji: "", right: { emoji: "", word: "" }, others: [{ emoji: "", word: "" }] }), c)),
  ];
}

// onRedraw redraws the page's tray too, since pictures and sounds can be added here.
export function templateForm(t: TemplateDraft, onEdit: () => void, onRedraw: () => void): HTMLElement {
  const card = h("div", { class: "card" });
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
