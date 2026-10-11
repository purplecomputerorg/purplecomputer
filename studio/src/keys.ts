// Key names as Purple's rooms and Studio's pages pass them around: a lowercase character, or
// space, enter, backspace, escape, tab, up, down, left, right.
const NAMES: Record<string, string> = { " ": "space", Enter: "enter", Backspace: "backspace", Escape: "escape", Tab: "tab", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };

export function browserKey(e: KeyboardEvent): string | null {
  if (e.key in NAMES) return NAMES[e.key];
  return [...e.key].length === 1 ? e.key.toLowerCase() : null;
}

// Every key Purple gets, from any source, is announced so the pretend keyboard can press it.
export const KEY_EVENT = "purple-key";
export const announceKey = (key: string) => dispatchEvent(new CustomEvent(KEY_EVENT, { detail: key }));


// Keys that type a word, each letter once, then Enter: a phone's few keys for typing it.
export function typingKeys(word: string): string[] {
  return [...new Set([...word.toLowerCase()].filter((c) => /^[a-z0-9]$/.test(c)))].slice(0, 5).concat("enter");
}
