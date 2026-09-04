import { CORE_EMOJI, CORE_SYNONYMS, isCoreRanked, isCoreWord } from "@sdk/purple/core";
import { changed, draft } from "../state";
import { clear, h } from "./dom";
import { playFrame, type PlayLine } from "./facsimile";
import type { View } from "./view";

const clean = (s: string) => s.trim().toLowerCase();
const knownWords = () => new Set([...Object.keys(CORE_EMOJI), ...draft.words.map((w) => w.word)]);
const emojiFor = (word: string) => draft.words.find((w) => w.word === word)?.emoji ?? CORE_EMOJI[word] ?? "";

// One editable list shape for words, synonyms, and rankings: an add row above a table with remove links.
function listCard<T>(opts: {
  headers: string[];
  items: () => T[];
  row: (item: T) => (Node | string)[];
  note?: (item: T) => string | null;
  inputs: HTMLInputElement[];
  add: () => string | null;
  addLabel: string;
}): HTMLElement {
  const table = h("table");
  const status = h("div", { class: "status" });
  const render = () => {
    clear(table);
    if (!opts.items().length) return;
    const body = h("tbody");
    for (const item of opts.items()) {
      const note = opts.note?.(item);
      body.append(
        h("tr", { class: note ? "warn" : "" }, ...opts.row(item).map((c) => h("td", {}, c)), h("td", { class: "dim small" }, note ?? ""), h("td", {}, h("button", { class: "linkbtn dim", onclick: () => { opts.items().splice(opts.items().indexOf(item), 1); changed(); render(); } }, "Remove"))),
      );
    }
    table.append(h("thead", {}, h("tr", {}, ...opts.headers.map((t) => h("th", {}, t)), h("th"), h("th"))), body);
  };
  const submit = () => {
    const err = opts.add();
    status.textContent = err ?? "";
    if (!err) {
      opts.inputs.forEach((i) => (i.value = ""));
      opts.inputs[0].focus();
      changed();
      render();
    }
  };
  opts.inputs.forEach((i) => (i.onkeydown = (e) => e.key === "Enter" && submit()));
  render();
  return h("div", { class: "card" }, h("div", { class: "row" }, ...opts.inputs, h("button", { class: "btn secondary small", onclick: submit }, opts.addLabel)), status, table);
}

export function wordsView(): View {
  const wordIn = h("input", { type: "text", class: "inline", placeholder: "word", style: "width:170px" });
  const emojiIn = h("input", { type: "text", class: "emoji-input", placeholder: "🐙" });
  const words = listCard({
    headers: ["Word", "Emoji"],
    items: () => draft.words,
    row: (w) => [w.word, h("span", { class: "emoji" }, w.emoji)],
    note: (w) => (w.word in CORE_EMOJI ? `Replaces Purple's ${CORE_EMOJI[w.word]}` : null),
    inputs: [wordIn, emojiIn],
    addLabel: "Add word",
    add: () => {
      const word = clean(wordIn.value);
      const emoji = emojiIn.value.trim();
      if (!/^[a-z][a-z'-]*$/.test(word)) return "A word is letters only, no spaces. Kids type one word at a time.";
      if (!emoji || /[a-z0-9]/i.test(emoji)) return "Paste an emoji in the second box. On a Mac, press Control, Command, and Space. On Windows, the Windows key and period.";
      draft.words = draft.words.filter((w) => w.word !== word);
      draft.words.push({ word, emoji });
      return null;
    },
  });

  const aliasIn = h("input", { type: "text", class: "inline", placeholder: "kitty", style: "width:150px" });
  const targetIn = h("input", { type: "text", class: "inline", placeholder: "cat", style: "width:150px" });
  const synonyms = listCard({
    headers: ["When a kid types", "Show"],
    items: () => draft.synonyms,
    row: (s) => [s.alias, `${s.word} ${emojiFor(s.word)}`],
    note: (s) => (s.alias in CORE_SYNONYMS ? `Purple already sends this to ${CORE_SYNONYMS[s.alias]}` : null),
    inputs: [aliasIn, targetIn],
    addLabel: "Add synonym",
    add: () => {
      const alias = clean(aliasIn.value);
      const word = clean(targetIn.value);
      if (!/^[a-z][a-z'-]*$/.test(alias)) return "The synonym is one word, letters only.";
      if (!knownWords().has(word)) return `"${word}" is not an emoji word yet. Add it above first, or pick one Purple already has.`;
      draft.synonyms = draft.synonyms.filter((s) => s.alias !== alias);
      draft.synonyms.push({ alias, word });
      return null;
    },
  });

  const rankIn = h("input", { type: "text", class: "inline", placeholder: "octopus", style: "width:190px" });
  const ranked = listCard({
    headers: ["First to appear"],
    items: () => draft.ranked,
    row: (w) => [w],
    note: (w) => (isCoreRanked(w) ? "Purple already ranks this word, so this line has no effect" : null),
    inputs: [rankIn],
    addLabel: "Add",
    add: () => {
      const word = clean(rankIn.value);
      if (!word) return "Type a word.";
      if (!isCoreWord(word) && !knownWords().has(word) && !draft.synonyms.some((s) => s.alias === word)) return `"${word}" is not a word Purple knows. Add it first.`;
      if (!draft.ranked.includes(word)) draft.ranked.push(word);
      return null;
    },
  });

  const lines = (): PlayLine[] => {
    const out: PlayLine[] = draft.words.slice(-3).map((w) => ({ ask: w.word, answer: w.emoji }));
    for (const s of draft.synonyms.slice(-2)) out.push({ ask: s.alias, answer: emojiFor(s.word) });
    return out.length ? out : [{ ask: "cat", answer: CORE_EMOJI.cat }];
  };

  return {
    title: "Words",
    path: "content/emoji.json  ·  synonyms.json  ·  rankings.txt",
    tag: "real",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "In Play, a kid types a word and Purple answers with an emoji. Add the words your family uses: a pet's name, a favorite animal, a word only you say."),
      h("h3", {}, "Words"),
      h("p", { class: "dim small" }, `Purple knows ${Object.keys(CORE_EMOJI).length} words already. A word you add that Purple has replaces its emoji; a new word joins the list.`),
      words,
      h("h3", {}, "Synonyms"),
      h("p", { class: "dim small" }, "Another spelling or nickname that should show the same emoji."),
      synonyms,
      h("h3", {}, "What autocompletes first"),
      h("p", { class: "dim small" }, "As a kid types, Purple suggests words. The words here come ahead of everything Purple has not already ranked. Purple's own top words, like cat and dog, stay where they are."),
      ranked,
      h("div", { class: "note" }, h("strong", {}, "What Purple does with this today: "), "all of it. This is the one part of the pack an installed Purple reads exactly as written."),
    ),
    stage: () => playFrame(lines()),
    caption: draft.words.length ? "Play, answering your words." : "Play, answering a word Purple already knows. Add yours to see them here.",
  };
}
