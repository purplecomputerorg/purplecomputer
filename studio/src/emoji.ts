// Emoji on Studio's pages as the pictures Purple draws: Noto's own, pulled out of the font Purple's ISO
// installs (scripts/studio_bundle.py), since no one emoji font format draws in every browser. Text boxes,
// menus and code keep the browser's emoji: a picture can't go inside them.
import { h } from "./ui/dom";

export interface EmojiMap { version: string; pattern: string; glyphs: Record<string, number[]>; seqs: Record<string, number[]> }

const VS16 = "️";
const KEEP = "input, textarea, select, option, script, style, svg, canvas, [contenteditable]";
let map: EmojiMap | null = null;
let loading: Promise<EmojiMap | null> | null = null;
const patterns = new WeakMap<EmojiMap, RegExp>();

export function loadEmojiMap(): Promise<EmojiMap | null> {
  loading ??= Promise.resolve()
    .then(() => fetch(new URL("purple/emoji/map.json", document.baseURI)))
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)
    .then((m: EmojiMap | null) => (map = m));
  return loading;
}

// One emoji's glyphs, found as Purple finds them (purple_tui/canvas/emoji_pictures.py).
function glyphsFor(m: EmojiMap, emoji: string): number[] {
  return m.seqs[emoji] ?? m.seqs[emoji.replaceAll(VS16, "")] ?? [...emoji].flatMap((c) => m.seqs[c] ?? [0]);
}

// Text split into plain runs and emoji, each emoji as its pictures. One the font has no picture for
// (newer than it) stays text. Emoji are found by Purple's own pattern, so a keycap or a bare ❤ is text here too.
export function pieces(m: EmojiMap, text: string): (string | { emoji: string; pictures: number[] })[] {
  let re = patterns.get(m);
  if (!re) patterns.set(m, (re = new RegExp(m.pattern, "gu")));
  const out: (string | { emoji: string; pictures: number[] })[] = [];
  const add = (s: string) => s && (typeof out.at(-1) === "string" ? (out[out.length - 1] += s) : out.push(s));
  let pos = 0;
  for (const match of text.matchAll(re)) {
    add(text.slice(pos, match.index));
    const glyphs = glyphsFor(m, match[0]);
    const drawn = glyphs.every((g) => m.glyphs[g]?.length === 3 || m.glyphs[g]?.[0] === 0);
    if (drawn) out.push({ emoji: match[0], pictures: glyphs.filter((g) => m.glyphs[g].length === 3) });
    else add(match[0]);
    pos = match.index + match[0].length;
  }
  add(text.slice(pos));
  return out;
}

// Whether Purple draws this emoji with pictures of its own.
export const drawable = (m: EmojiMap, emoji: string) => pieces(m, emoji).every((p) => typeof p !== "string");

const pictureUrl = (m: EmojiMap, glyph: number) => new URL(`purple/emoji/${encodeURIComponent(m.version)}/${glyph}.png`, document.baseURI).href;

function show(m: EmojiMap, node: Text): void {
  if (!node.parentElement || node.parentElement.closest(KEEP)) return;
  const parts = pieces(m, node.data);
  if (parts.length === 1 && typeof parts[0] === "string") return;
  node.replaceWith(...parts.map((p) => typeof p === "string" ? p : h("span", { class: "emoji", role: "img", "aria-label": p.emoji },
    ...p.pictures.map((g) => h("img", { src: pictureUrl(m, g), alt: "", width: 136, height: 128, draggable: "false", decoding: "async" })))));
}

function showAll(m: EmojiMap, root: Node): void {
  if (root instanceof Text) return show(m, root);
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  while (walk.nextNode()) texts.push(walk.currentNode as Text);
  texts.forEach((t) => show(m, t));
}

// Every emoji on the page from now on, as it appears or changes.
export async function startEmojiPictures(): Promise<void> {
  const m = await loadEmojiMap();
  if (!m) return;
  showAll(m, document.body);
  new MutationObserver((records) => records.forEach((r) => (r.type === "characterData" ? showAll(m, r.target) : r.addedNodes.forEach((n) => showAll(m, n)))))
    .observe(document.body, { childList: true, subtree: true, characterData: true });
}

// Fetched ahead, so the first look at them (the emoji picker's opening list) is instant.
export function preloadEmoji(emoji: string[]): void {
  const m = map;
  if (!m) return;
  for (const e of emoji) for (const p of pieces(m, e)) if (typeof p !== "string") p.pictures.forEach((g) => (new Image().src = pictureUrl(m, g)));
}
