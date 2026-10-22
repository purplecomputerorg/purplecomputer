import { CORE_EMOJI } from "@sdk/purple/core";
import { changed, draft, type WordEntry } from "../state";
import { typingKeys } from "../keys";
import { h } from "./dom";
import { closeEmojiPicker, emojiCell } from "./emojipicker";
import { addRoomPicture } from "./roomfiles";
import { skippedNote } from "./download";
import { skippedBy, WORD_PICTURES_PATH } from "@sdk/pack";
import boxes from "../assets/purple-boxes.jpg";
import type { View } from "./view";

const clean = (s: string) => s.trim().toLowerCase();
const WORD = /^[a-z][a-z'-]*$/;

// One table, a row per word and a blank row at the end: type a word, press Enter, pick its emoji,
// and the next blank row is ready.
function wordTable(): HTMLElement & { refresh: () => void } {
  const rows = h("div", { class: "word-rows" });
  const status = h("div", { class: "status" });

  const checkWord = (word: string, self: WordEntry | null): string | null => {
    if (!WORD.test(word)) return "A word is letters only, no spaces. Kids type one word at a time.";
    if (draft.words.some((w) => w !== self && w.word === word)) return `"${word}" is already in the list.`;
    return null;
  };

  function row(entry: WordEntry | null): HTMLElement {
    const pending = { emoji: entry?.emoji ?? "" };
    const word = h("input", { type: "text", value: entry?.word ?? "", placeholder: entry ? "" : "Type a word, like biscuit", "aria-label": "Word", autocomplete: "off", spellcheck: false });
    const emoji = emojiCell(pending.emoji, () => clean(word.value), (e) => {
      pending.emoji = e;
      if (entry) { entry.emoji = e; changed(); showWas(); rows.querySelector<HTMLInputElement>(".blank input")?.focus(); }
      else if (word.value.trim()) commit();
      else word.focus();
    }, { pictures: true });
    const pick = () => emoji.click();
    const was = h("span", { class: "dim small was" });
    const showWas = () => {
      const core = CORE_EMOJI[clean(word.value)];
      was.textContent = core && core !== pending.emoji ? `instead of ${core}` : "";
    };

    const commit = (): boolean => {
      const w = clean(word.value);
      const err = checkWord(w, entry);
      status.textContent = err ?? "";
      if (err) return false;
      if (entry) entry.word = w;
      else draft.words.push({ word: w, emoji: pending.emoji, kept: true });
      changed();
      render();
      return true;
    };
    word.addEventListener("input", showWas);
    word.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      if (entry) return void (commit() && rows.querySelector<HTMLInputElement>(".blank input")?.focus());
      if (checkWord(clean(word.value), null)) return void commit();
      // The picker opens searching for the word, so "dog", Enter, Enter is a whole row.
      if (pending.emoji) return void commit();
      pick();
    });
    if (entry) word.addEventListener("change", () => commit() || (word.value = entry.word));
    showWas();

    const remove = entry ? h("button", { type: "button", class: "remove", title: "Remove", "aria-label": `Remove ${entry.word}`, onclick: () => {
      draft.words.splice(draft.words.indexOf(entry), 1);
      changed();
      render();
    } }, "✕") : h("span");
    return h("div", { class: `word-row${entry ? "" : " blank"}` }, word, h("div", { class: "emoji-wrap" }, emoji), was, remove);
  }

  function render() {
    closeEmojiPicker();
    rows.replaceChildren(
      h("div", { class: "word-row head" }, h("span", {}, "Word"), h("span", {}, "Emoji or picture")),
      ...draft.words.map(row),
      row(null),
    );
    rows.querySelector<HTMLInputElement>(".blank input")?.focus({ preventScroll: true });
  }
  render();
  return Object.assign(h("div", { class: "card" }, rows, status), { refresh: render });
}

const EXAMPLE_WORD = "box";

// What a word can do beyond emoji: Play showing a photo, and our own photo to try it with.
function picturesCard(added: () => void): HTMLElement {
  const photo = () => h("img", { src: boxes, alt: "" });
  const tried = () => draft.words.some((w) => w.word === EXAMPLE_WORD);
  const button = h("button", { type: "button", class: "btn secondary", disabled: tried(), onclick: async () => {
    button.disabled = true;
    const f = await addRoomPicture("purple-boxes", boxes);
    draft.words.push({ word: EXAMPLE_WORD, emoji: f.name, kept: true });
    changed();
    added();
  } }, "Try it with our photo");
  return h("div", { class: "card word-pictures" },
    h("div", { class: "word-pictures-demo", "aria-hidden": "true" }, h("span", {}, "Type → 3 boxes"), h("span", {}, photo(), photo(), photo())),
    h("div", {},
      h("h2", {}, "Your own pictures, too"),
      h("p", {}, "A word can show a photo where its emoji would go: your dog, Grandma, the boxes Purple came in. Click any word's emoji and choose Add photo."),
      button,
      ...skippedBy([{ path: WORD_PICTURES_PATH, data: new Uint8Array() }]).map((s) => h("p", { class: "dim small skipped-note" }, skippedNote(s)))));
}

export function wordsView(): View {
  const table = wordTable();
  const pictures = picturesCard(table.refresh);
  return {
    title: "Emoji",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "In Play, kids type a word and see its emoji. Add the words your family uses: a pet's name, a favorite food, a word only you say."),
      pictures,
      table,
      h("p", { class: "dim small" }, "Purple already knows hundreds of words, like cat and dog. Your words come first when Purple suggests what to type."),
    ),
    live: { room: "play" },
    keys: () => typingKeys(draft.words[0]?.word || "cat"),
    caption: "Purple's Play room, with your words in it. Type one and press Enter.",
    mounted: () => table.querySelector<HTMLInputElement>(".blank input")?.focus(),
  };
}
