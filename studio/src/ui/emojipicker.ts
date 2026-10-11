// Find an emoji by name: searches the words Purple already knows, so "dog" finds 🐶. A pasted
// emoji works too.
import { CORE_EMOJI, CORE_RANKED_WORDS, CORE_SYNONYMS } from "@sdk/purple/core";
import { h } from "./dom";

const INDEX: [name: string, emoji: string][] = [
  ...Object.entries(CORE_EMOJI),
  ...Object.entries(CORE_SYNONYMS).flatMap(([alias, word]): [string, string][] => (CORE_EMOJI[word] ? [[alias, CORE_EMOJI[word]]] : [])),
];
const POPULAR = [...new Set(CORE_RANKED_WORDS.map((w) => CORE_EMOJI[w]).filter(Boolean))];
const LETTERS = /[a-z0-9]/i;
export const isEmoji = (s: string) => !!s.trim() && !LETTERS.test(s);

export function searchEmoji(query: string, limit = 32): { emoji: string; name: string }[] {
  const q = query.trim().toLowerCase();
  if (isEmoji(q)) return [{ emoji: q, name: "" }];
  const names = new Map<string, string>(INDEX.map(([n, e]) => [e, n]));
  if (!q) return POPULAR.slice(0, limit).map((emoji) => ({ emoji, name: names.get(emoji) ?? "" }));
  const score = (n: string) => (n === q ? 0 : n.startsWith(q) ? 1 : n.includes(q) ? 2 : 3);
  const seen = new Set<string>();
  return INDEX.filter(([n]) => score(n) < 3)
    .sort((a, b) => score(a[0]) - score(b[0]) || a[0].length - b[0].length)
    .filter(([, e]) => !seen.has(e) && seen.add(e))
    .slice(0, limit)
    .map(([name, emoji]) => ({ emoji, name }));
}

let open: HTMLElement | null = null;

export function closeEmojiPicker(): void {
  open?.remove();
  open = null;
}

// Opens under anchor with the search box focused; Enter picks the first match, Esc closes.
export function openEmojiPicker(anchor: HTMLElement, query: string, onPick: (emoji: string) => void): void {
  closeEmojiPicker();
  const search = h("input", { type: "text", class: "emoji-search", placeholder: "Search, like dog or star", value: query });
  const grid = h("div", { class: "emoji-grid" });
  const pick = (emoji: string) => { closeEmojiPicker(); onPick(emoji); };
  const render = () => {
    const found = searchEmoji(search.value);
    grid.replaceChildren(...(found.length
      ? found.map((r) => h("button", { type: "button", title: r.name, onclick: () => pick(r.emoji) }, r.emoji))
      : [h("p", { class: "dim small" }, "Nothing by that name. Try a simpler word, or paste any emoji.")]));
  };
  search.addEventListener("input", render);
  search.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); closeEmojiPicker(); anchor.focus(); }
    if (e.key === "Enter") {
      e.preventDefault();
      const first = searchEmoji(search.value, 1)[0];
      if (first) pick(first.emoji);
    }
  });
  const pop = h("div", { class: "emoji-pop" }, search, grid);
  open = pop;
  render();
  anchor.after(pop);
  search.focus();
  search.select();
  const outside = (e: MouseEvent) => {
    if (open !== pop) return document.removeEventListener("mousedown", outside);
    if (!pop.contains(e.target as Node) && e.target !== anchor) { closeEmojiPicker(); document.removeEventListener("mousedown", outside); }
  };
  document.addEventListener("mousedown", outside);
}
