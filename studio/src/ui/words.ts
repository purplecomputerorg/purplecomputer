import { CORE_EMOJI } from "@sdk/purple/core";
import type { Clip } from "../audio";
import { changed, draft, putPhrase, type WordEntry } from "../state";
import { typingKeys } from "../keys";
import { h } from "./dom";
import { closeEmojiPicker, emojiCell } from "./emojipicker";
import { hear, soundControl, voiceStays } from "./record";
import { addAllBar, keepButton, plural } from "./trybar";
import box from "../assets/purple-box.jpg";
import type { View } from "./view";

const tabs = (which: "words" | "phrases") => h("div", { class: "tabs", role: "tablist" },
  h("a", { class: "tab", href: "#words", "aria-selected": String(which === "words") }, "Words and emoji"),
  h("a", { class: "tab", href: "#words/phrases", "aria-selected": String(which === "phrases") }, "What Purple says"));

const clean = (s: string) => s.trim().toLowerCase();
const WORD = /^[a-z][a-z'-]*$/;
// purple_tui/content.py MEANING_MAX.
const MEANING_MAX = 200;

// Shown, never added: what a word can be, before the family has any.
const EXAMPLES: { word: string; pic: string | Node; says: string; means: string }[] = [
  { word: "trex", pic: "🦖", says: "what is trex", means: "A giant dinosaur who stomps, roars, and has teeny tiny arms" },
  { word: "nana", pic: "👵", says: "who is nana", means: "Nana tells the best stories and gives the biggest hugs" },
  { word: "box", pic: h("img", { src: box, alt: "" }), says: "box", means: `Your own photo, instead of Purple's ${CORE_EMOJI.box ?? "emoji"}` },
];

function examples(): HTMLElement {
  return h("div", { class: "word-examples" }, ...EXAMPLES.map((x) => h("div", { class: "word-example" },
    h("div", { class: "head" }, h("span", { class: "pic" }, x.pic), h("b", {}, x.word)),
    h("div", {}, h("kbd", {}, x.says)), h("div", { class: "dim" }, x.means))));
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
    return h("div", { class: `word-row${entry ? "" : " blank"}` }, word, h("div", { class: "emoji-wrap" }, emoji), was, remove, ...(entry ? [meaning(entry)] : []));
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

function phrasesView(): View {
  const list = h("div", { class: "stack" });
  const text = h("input", { type: "text", placeholder: "Good night, Maya", "aria-label": "Phrase" });
  const status = h("div", { class: "status" });

  function render() {
    list.replaceChildren(...draft.phrases.map((p, i) => h("div", { class: "phrase-row" },
      h("span", {}, h("strong", {}, p.text), p.said ? h("span", { class: "dim small" }, ` says "${p.said}"`) : null),
      h("div", { class: "row" }, hear(p.clip), keepButton(p, render),
        h("button", { class: "remove", title: "Remove", "aria-label": `Remove ${p.text}`, onclick: () => { draft.phrases.splice(i, 1); changed(); render(); } }, "✕")))),
      addAllBar(draft.phrases, (n) => plural(n, "phrase"), render) ?? "");
  }
  const onClip = (clip: Clip, said?: string) => {
    const t = text.value.trim();
    if (!t) return void (status.textContent = "Type the phrase first, so Purple knows when to play it.");
    status.textContent = "";
    putPhrase(t, clip, false, said);
    text.value = "";
    render();
  };
  const sound = soundControl(onClip, "Or type other words for Purple to say");
  text.addEventListener("keydown", (e) => e.key === "Enter" && text.value.trim() && sound.querySelector("button")?.click());
  render();

  return {
    title: "Words",
    editor: h(
      "section",
      {},
      tabs("phrases"),
      h("p", { class: "lead" }, "Purple reads things out loud in Play when a kid types ", h("span", { class: "mono" }, "say"), " first, like ", h("span", { class: "mono" }, "say good night"), ". Record a phrase and they hear you instead, or type other words for Purple to say back."),
      list,
      h("div", { class: "card" }, h("div", { class: "phrase-new" },
        h("label", { class: "field" }, h("span", {}, "When your kid types say and"), text), sound), status),
      h("p", { class: "dim small" }, "Capitals and spacing don't matter. Anything you haven't given a sound, Purple says in its own voice."),
      voiceStays(),
    ),
    live: { room: "play" },
    previewTitle: "What your kid hears",
    caption: "Purple's Play room. Type say and your phrase, then press Enter.",
  };
}

export function wordsView(item: string | null): View {
  if (item === "phrases") return phrasesView();
  const table = wordTable();
  return {
    title: "Words",
    editor: h(
      "section",
      {},
      tabs("words"),
      h("p", { class: "lead" }, "In Play, kids type a word and see its emoji. Add the words your family uses, a pet's name or a word only you say, and give each one an emoji or your own photo. Yours shows in place of Purple's."),
      h("p", {}, "Give a word a meaning too. When your kid types \"what is trex\" or \"who is nana\" in Play, Purple shows its picture and your answer. Ending with ! reads the answer aloud."),
      examples(),
      table,
      h("p", { class: "dim small" }, "Purple already knows hundreds of words, like cat and dog. Your words come first when Purple suggests what to type."),
    ),
    live: { room: "play" },
    keys: () => typingKeys(draft.words[0]?.word || "cat"),
    caption: "Purple's Play room, with your words in it. Type one and press Enter.",
    mounted: () => table.querySelector<HTMLInputElement>(".blank input")?.focus(),
  };
}
