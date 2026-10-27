import { CORE_EMOJI } from "@sdk/purple/core";
import { play } from "../audio";
import { roomLine } from "../roomvoice";
import { changed, draft, phraseFor, putPhrase, type WordEntry } from "../state";
import { typingKeys } from "../keys";
import { h } from "./dom";
import { closeEmojiPicker, emojiCell } from "./emojipicker";
import { soundPicker, voiceStays } from "./record";
import box from "../assets/purple-box.jpg";
import daddy from "../assets/daddy.mp3";
import type { View } from "./view";

const clean = (s: string) => s.trim().toLowerCase();
const WORD = /^[a-z][a-z'-]*$/;
// purple_tui/content.py MEANING_MAX.
const MEANING_MAX = 200;

// Shown, never added: one card for each thing a word can do, before the family has any.
// hears: what Purple says for it, played in Purple's voice unless voice is a real recording of it.
const EXAMPLES: { word: string; pic: string | Node; tag: string; types: string; then: string; hears?: string; voice?: string }[] = [
  { word: "box", pic: h("img", { src: box, alt: "" }), tag: "📷 Your photo", types: "box", then: `Shows your photo, instead of Purple's ${CORE_EMOJI.box ?? "emoji"}` },
  { word: "trex", pic: "🦖", tag: "💬 A meaning", types: "what is trex!", then: "A giant dinosaur who stomps, roars, and has teeny tiny arms", hears: "A giant dinosaur who stomps, roars, and has teeny tiny arms" },
  { word: "daddy", pic: "👨", tag: "🎤 Your voice", types: "daddy!", then: "Plays your recording: “Hey, it's daddy! I love you guys!”", hears: "Hey, it's daddy! I love you guys!", voice: daddy },
  { word: "biscuit", pic: "🐶", tag: "🔊 Purple's voice", types: "say biscuit", then: "Purple says the words you typed: “Biscuit is our silly dog”", hears: "Biscuit is our silly dog" },
];

function examples(): HTMLElement {
  return h("div", { class: "word-examples" }, ...EXAMPLES.map((x) => h("div", { class: "word-example" },
    h("div", { class: "head" }, h("span", { class: "pic" }, x.pic), h("b", {}, x.word), h("span", { class: "tag" }, x.tag)),
    h("div", {}, "Your kid types ", h("kbd", {}, x.types)), h("div", { class: "dim" }, x.then),
    x.hears ? hearExample(x.hears, x.voice) : null)));
}

function hearExample(text: string, voice?: string): HTMLElement {
  const button = h("button", { type: "button", class: "btn secondary small", onclick: async () => {
    if (voice) return void new Audio(voice).play();
    button.disabled = true;
    const clip = await roomLine(text);
    button.disabled = false;
    if (clip) play(clip);
  } }, "▶ Hear it");
  return button;
}

// One table, a row per word and a blank row at the end: type a word, press Enter, pick its emoji,
// and the next blank row is ready.
function wordTable(): HTMLElement {
  const rows = h("div", { class: "word-rows" });
  const status = h("div", { class: "status" });

  const checkWord = (word: string, self: WordEntry | null): string | null => {
    if (!WORD.test(word)) return "A word is letters only, no spaces. Kids type one word at a time.";
    if (draft.words.some((w) => w !== self && w.word === word)) return `"${word}" is already in the list.`;
    return null;
  };

  function row(entry: WordEntry | null): HTMLElement {
    const pending = { emoji: entry?.emoji ?? "" };
    const word = h("input", { type: "text", value: entry?.word ?? "", placeholder: entry ? "" : "Type a word", "aria-label": "Word", autocomplete: "off", spellcheck: false });
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
      if (entry) rename(entry, w);
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
      putPhrase(entry.word, null);
      render();
    } }, "✕") : h("span");
    return h("div", { class: `word-row${entry ? "" : " blank"}` }, word, h("div", { class: "emoji-wrap" }, emoji), was, remove, ...(entry ? [meaning(entry), voice(entry)] : []));
  }

  function meaning(entry: WordEntry): HTMLElement {
    const input = h("input", { type: "text", value: entry.means ?? "", maxlength: MEANING_MAX, autocomplete: "off",
      placeholder: "Optional" });
    input.addEventListener("change", () => {
      entry.means = input.value.trim() || undefined;
      changed();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      rows.querySelector<HTMLInputElement>(".blank input")?.focus();
    });
    return h("label", { class: "means" }, h("span", { class: "ask" }, "Type ", h("kbd", {}, `what is ${entry.word}`), " or ",
      h("kbd", {}, `who is ${entry.word}`), " in Play and Purple answers:"), input);
  }

  // A word's recording is the phrase of the word itself: Purple plays it whenever it says the word.
  function rename(entry: WordEntry, word: string) {
    const p = phraseFor(entry.word);
    if (p && word !== entry.word) { putPhrase(entry.word, null); putPhrase(word, p.clip, p.kept, p.said); }
    entry.word = word;
  }

  function voice(entry: WordEntry): HTMLElement {
    const p = phraseFor(entry.word);
    return h("div", { class: "says" }, h("span", { class: "ask" }, "Type ", h("kbd", {}, `${entry.word}!`), " in Play and Purple says:"),
      soundPicker({ clip: p?.clip, said: p?.said, fallback: entry.word, placeholder: entry.word, small: true,
        onClip: (clip, said) => { putPhrase(entry.word, clip, true, said); render(); },
        onClear: () => { putPhrase(entry.word, null); render(); } }));
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
  return h("div", { class: "card" }, rows, status);
}

export function wordsView(): View {
  const table = wordTable();
  return {
    title: "Words",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "In Play, kids type a word and see its emoji. Add the words your family uses, like a pet's name, and give each one an emoji or your own photo."),
      h("p", {}, "Each word can also have a meaning, and a sound in your voice or Purple's."),
      examples(),
      h("p", { class: "dim small" }, "Purple talks when your kid ends with ", h("kbd", {}, "!"), " or starts with ", h("kbd", {}, "say"), ": ", h("kbd", {}, "nana!"), " and ", h("kbd", {}, "say nana"), " both work. Plain ", h("kbd", {}, "nana"), " just shows the picture."),
      table,
      h("p", { class: "dim small" }, "Purple already knows hundreds of words, like cat and dog. Your words come first when Purple suggests what to type."),
      voiceStays(),
    ),
    live: { room: "play" },
    keys: () => typingKeys(draft.words[0]?.word || "cat"),
    caption: "Purple's Play room, with your words in it. Type one and press Enter.",
    mounted: () => table.querySelector<HTMLInputElement>(".blank input")?.focus(),
  };
}
