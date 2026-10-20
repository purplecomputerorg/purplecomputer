// Find an emoji by name: the words Purple already knows come first, so "dog" finds 🐶, then every
// emoji Purple's font can draw, by its name and keywords (emojibase), so "lol" finds 😂. A pasted
// emoji works too.
import { CORE_EMOJI, CORE_RANKED_WORDS, CORE_SYNONYMS } from "@sdk/purple/core";
import { h } from "./dom";

const INDEX: [name: string, emoji: string][] = [
  ...Object.entries(CORE_EMOJI),
  ...Object.entries(CORE_SYNONYMS).flatMap(([alias, word]): [string, string][] => (CORE_EMOJI[word] ? [[alias, CORE_EMOJI[word]]] : [])),
];
const CORE_SIZE = INDEX.length;
// Purple's Noto Color Emoji (Ubuntu 24.04) draws emoji through Unicode 15.0.
const FONT_VERSION = 15;
let loading: Promise<void> | null = null;
function loadAll(): Promise<void> {
  loading ??= import("emojibase-data/en/data.json").then(({ default: all }) => {
    for (const e of all) {
      if (e.version > FONT_VERSION || e.group === 2) continue;  // group 2 is skin tones and hair parts
      INDEX.push([e.label, e.emoji], ...(e.tags ?? []).map((t): [string, string] => [t, e.emoji]));
    }
  });
  return loading;
}
const POPULAR = [...new Set(CORE_RANKED_WORDS.map((w) => CORE_EMOJI[w]).filter(Boolean))];
const LETTERS = /[a-z0-9]/i;
export const isEmoji = (s: string) => !!s.trim() && !LETTERS.test(s);

// taken: emoji already used beside this one, left out so a list never repeats.
export function searchEmoji(query: string, limit = 32, taken: string[] = []): { emoji: string; name: string }[] {
  const q = query.trim().toLowerCase();
  if (isEmoji(q)) return taken.includes(q) ? [] : [{ emoji: q, name: "" }];
  const names = new Map<string, string>(INDEX.map(([n, e]) => [e, n]));
  if (!q) return POPULAR.filter((e) => !taken.includes(e)).slice(0, limit).map((emoji) => ({ emoji, name: names.get(emoji) ?? "" }));
  const score = (n: string) => (n === q ? 0 : n.startsWith(q) ? 1 : n.includes(q) ? 2 : 3);
  const seen = new Set(taken);
  const rank = INDEX.map(([n], i) => score(n) * 2 + (i < CORE_SIZE ? 0 : 1));
  return INDEX.map((e, i) => [e, rank[i]] as const).filter(([[n]]) => score(n) < 3)
    .sort((a, b) => a[1] - b[1] || a[0][0].length - b[0][0].length)
    .map(([e]) => e)
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
export function openEmojiPicker(anchor: HTMLElement, query: string, onPick: (emoji: string) => void, taken: string[] = []): void {
  closeEmojiPicker();
  const search = h("input", { type: "text", class: "emoji-search", placeholder: "Search, like dog or star", value: query });
  const grid = h("div", { class: "emoji-grid" });
  const pick = (emoji: string) => { closeEmojiPicker(); onPick(emoji); };
  const render = () => {
    const found = searchEmoji(search.value, 32, taken);
    grid.replaceChildren(...(found.length
      ? found.map((r) => h("button", { type: "button", title: r.name, onclick: () => pick(r.emoji) }, r.emoji))
      : [h("p", { class: "dim small" }, isEmoji(search.value) ? "That one's already here. Pick a different one." : "Nothing by that name. Try a simpler word, or paste any emoji.")]));
  };
  search.addEventListener("input", render);
  void loadAll().then(() => open === pop && render());
  search.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); closeEmojiPicker(); anchor.focus(); }
    if (e.key === "Enter") {
      e.preventDefault();
      const first = searchEmoji(search.value, 1, taken)[0];
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

// A button showing an emoji that opens the picker, searching for query(). Wrap it in .emoji-wrap.
export function emojiCell(value: string, query: () => string, onPick: (emoji: string) => void, taken = (): string[] => []): HTMLButtonElement {
  const cell = h("button", { type: "button", class: `emoji-cell${value ? "" : " empty"}`, "aria-label": "Pick an emoji" }, value || "Pick");
  cell.onclick = () => openEmojiPicker(cell, query(), (e) => {
    cell.textContent = e;
    cell.classList.remove("empty");
    onPick(e);
  }, taken());
  return cell;
}
