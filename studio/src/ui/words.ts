import { CORE_EMOJI } from "@sdk/purple/core";
import { play } from "../audio";
import { roomLine } from "../roomvoice";
import { changed, draft, phraseFor, putPhrase, type WordEntry } from "../state";
import { typingKeys } from "../keys";
import { h, removeButton } from "./dom";
import { closeEmojiPicker, emojiCell, openEmojiPicker } from "./emojipicker";
import { roomPicture } from "./roomfiles";
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
    h("div", { class: "types" }, "Your kid types ", h("kbd", {}, x.types), x.hears ? hearExample(x.hears, x.voice) : null),
    h("div", { class: "dim" }, x.then))));
}

function hearExample(text: string, voice?: string): HTMLElement {
  const button = h("button", { type: "button", class: "rec-mini", title: "Hear it", "aria-label": "Hear it", onclick: async () => {
    if (voice) return void new Audio(voice).play();
    button.disabled = true;
    const clip = await roomLine(text);
    button.disabled = false;
    if (clip) play(clip);
  } }, "▶");
  return button;
}

// A row per word, each reading as Purple shows it: the word, then its emoji or picture. One at a time is
// open to its labeled fields, starting with the newest. Adding a word asks what it shows when Purple has no emoji for it.
function wordTable(): HTMLElement {
  const rows = h("div", { class: "word-rows" });
  const status = h("div", { class: "status" });
  let open: WordEntry | null = null;

  const checkWord = (word: string, self: WordEntry | null): string | null => {
    if (!WORD.test(word)) return "A word is letters only, no spaces. Kids type one word at a time.";
    if (draft.words.some((w) => w !== self && w.word === word)) return `"${word}" is already in the list.`;
    return null;
  };
  const focusNew = () => rows.querySelector<HTMLInputElement>(".word-new input")?.focus({ preventScroll: true });
  const showsTitle = (word: string) => `What should “${word}” show?`;
  const face = (emoji: string) => roomPicture(emoji) ?? emoji;

  function newWord(): HTMLElement {
    const input = h("input", { type: "text", placeholder: "Type a new word", "aria-label": "New word", autocomplete: "off", spellcheck: false });
    const add = () => {
      const word = clean(input.value);
      status.textContent = checkWord(word, null) ?? "";
      if (status.textContent) return;
      const create = (emoji: string) => {
        draft.words.push(open = { word, emoji, kept: true });
        status.textContent = "";
        changed();
        render();
        focusNew();
      };
      if (CORE_EMOJI[word]) return create(CORE_EMOJI[word]);
      status.textContent = `Pick what “${word}” shows to add it.`;
      openEmojiPicker(input, word, create, { pictures: true, title: showsTitle(word) });
    };
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      add();
    });
    return h("div", { class: "word-new emoji-wrap" }, input, h("button", { type: "button", class: "btn small", onclick: add }, "Add word"));
  }

  function row(entry: WordEntry): HTMLElement {
    const isOpen = entry === open;
    const toggle = () => { open = isOpen ? null : entry; render(); };
    const phrase = phraseFor(entry.word);
    const marks = [entry.means ? "💬" : "", phrase ? (phrase.said ? "🔊" : "🎤") : ""].join(" ");
    const head = h("div", { class: "word-head", onclick: (e: Event) => (e.target as Element).closest("button") || toggle() },
      h("b", { class: "word" }, entry.word), h("span", { class: "shows" }, face(entry.emoji)), h("span", { class: "marks", title: "Has a meaning or a sound" }, marks),
      h("button", { type: "button", class: "x chevron", "aria-expanded": String(isOpen), "aria-label": isOpen ? "Close" : `Open ${entry.word}`, onclick: toggle }, isOpen ? "▲" : "▼"),
      removeButton(() => {
        draft.words.splice(draft.words.indexOf(entry), 1);
        putPhrase(entry.word, null);
        render();
      }));
    return h("div", { class: `word-row${isOpen ? " open" : ""}` }, head,
      isOpen ? h("div", { class: "word-fields" }, wordField(entry), showsField(entry), meaning(entry), voice(entry)) : null);
  }

  function wordField(entry: WordEntry): HTMLElement {
    const input = h("input", { type: "text", value: entry.word, "aria-label": "Word", autocomplete: "off", spellcheck: false });
    const commit = () => {
      const word = clean(input.value);
      if (word === entry.word) return;
      status.textContent = checkWord(word, entry) ?? "";
      if (status.textContent) return void (input.value = entry.word);
      rename(entry, word);
      changed();
      render();
    };
    input.addEventListener("change", commit);
    input.addEventListener("keydown", (e) => e.key === "Enter" && input.blur());
    return field("Word", input);
  }

  function showsField(entry: WordEntry): HTMLElement {
    const core = CORE_EMOJI[entry.word];
    const pick = emojiCell(entry.emoji, () => entry.word, (e) => {
      entry.emoji = e;
      changed();
      render();
    }, { pictures: true, title: showsTitle(entry.word) });
    const note = !core ? "Click it to change it." : core === entry.emoji ? "Purple's own. Click it to change it." : `Instead of Purple's ${core}.`;
    return field("Shows", h("div", { class: "row emoji-wrap" }, pick, h("span", { class: "dim small" }, note)));
  }

  const field = (label: string, control: Node, ...types: string[]) => h("div", { class: "word-field" }, h("span", { class: "label" }, label),
    h("div", {}, control, types.length ? h("div", { class: "types" }, "Your kid types ", ...types.flatMap((t, i) => [i ? " or " : "", h("kbd", {}, t)])) : null));

  function meaning(entry: WordEntry): HTMLElement {
    const input = h("input", { type: "text", value: entry.means ?? "", maxlength: MEANING_MAX, autocomplete: "off", placeholder: "What Purple answers (optional)", "aria-label": "Meaning" });
    input.addEventListener("change", () => {
      entry.means = input.value.trim() || undefined;
      changed();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      focusNew();
    });
    return field("Meaning", input, `what is ${entry.word}`, `who is ${entry.word}`);
  }

  // A word's recording is the phrase of the word itself: Purple plays it whenever it says the word.
  function rename(entry: WordEntry, word: string) {
    const p = phraseFor(entry.word);
    if (p && word !== entry.word) { putPhrase(entry.word, null); putPhrase(word, p.clip, p.kept, p.said); }
    entry.word = word;
  }

  function voice(entry: WordEntry): HTMLElement {
    const p = phraseFor(entry.word);
    return field("Sound", soundPicker({ clip: p?.clip, said: p?.said, fallback: entry.word, placeholder: `Purple says “${entry.word}”`, small: true,
      onClip: (clip, said) => { putPhrase(entry.word, clip, true, said); render(); },
      onClear: () => { putPhrase(entry.word, null); render(); } }), `${entry.word}!`);
  }

  function render() {
    closeEmojiPicker();
    rows.replaceChildren(...draft.words.map(row), newWord());
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
      h("h3", {}, "What can a word do?"),
      examples(),
      h("p", { class: "dim small" }, "Purple talks when your kid ends with ", h("kbd", {}, "!"), " or starts with ", h("kbd", {}, "say"), ": ", h("kbd", {}, "nana!"), " and ", h("kbd", {}, "say nana"), " both work. Plain ", h("kbd", {}, "nana"), " just shows the picture."),
      table,
      h("p", { class: "dim small" }, "Purple already knows hundreds of words, like cat and dog. Your words come first when Purple suggests what to type."),
      voiceStays(),
    ),
    live: { room: "play" },
    keys: () => typingKeys(draft.words[0]?.word || "cat"),
    caption: "Purple's Play room, with your words in it. Type one and press Enter.",
    mounted: () => table.querySelector<HTMLInputElement>(".word-new input")?.focus({ preventScroll: true }),
  };
}
