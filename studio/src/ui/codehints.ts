// Help while writing a room's Python: names that fit what's being typed, found by their own start or by
// what they do ("speak" finds say), and what a call takes once its "(" is open. All from the Room guide.
import guide from "../room-guide.md?raw";
import { LIBRARY_NAMES } from "./guide";
import { h } from "./dom";

export interface Hint { name: string; call: string; about: string; insert: string; words: string[] }

// Other words a parent might reach for, when they remember what a call does but not its name.
const ALSO: Record<string, string> = {
  say: "speak talk voice aloud read", show: "display big emoji", write: "text line print", play: "note music piano tune",
  drum: "beat percussion", sound: "audio noise", after: "wait later delay sleep", every: "repeat loop timer interval",
  ask: "input question answer type", background: "color colour", keep: "save remember store", game_over: "end win lose stop",
  "grid.random_empty": "random", status: "score top", clear: "erase empty reset", picture: "image photo", state: "variable score",
};

// The guide writes these as plain words, like say(text); shown with quotes, since words go in quotes and a name like key doesn't.
const EXAMPLE: Record<string, string> = {
  say: 'say("Hello!")', write: 'write("Once upon a time")', status: 'status("Score: 0")', show: 'show("🐶")', game_over: 'game_over("You win!")',
};
// What a call taking words says under it.
const QUOTES = 'Words go in quotes, like "hi". A name, like key, goes without.';

const words = (text: string) => text.toLowerCase().match(/[a-z]{3,}/g) ?? [];
const plain = (md: string) => md.replace(/`/g, "").replace(/\*\*/g, "");
const firstSentence = (text: string) => /^.*?[.!?](\s|$)/.exec(text)?.[0].trim() ?? text;

// A call taking words goes in as name(""), so the caret lands between the quotes.
function hint(written: string, about: string, insert?: string): Hint {
  const name = /^[\w.]+/.exec(written)![0];
  const call = EXAMPLE[name] ?? written;
  const blank = call.includes('("') ? `${name}("")` : call.includes("(") ? `${name}()` : name;
  return { name, call, about, insert: insert ?? blank, words: [...words(ALSO[name] ?? ""), ...words(about)] };
}

// One hint per call in the guide's table, as `name(args)` and the first sentence of what it does.
const HINTS: Hint[] = [
  hint("on_key(key)", "Purple calls it each time a key goes down.", "on_key(key):"),
  hint("on_key_up(key)", "Purple calls it when a key comes back up.", "on_key_up(key):"),
  ...guide.split("\n").filter((line) => line.startsWith("| `")).flatMap((line) => {
    const [, calls, about] = line.split("|");
    return [...calls.matchAll(/`([^`]+)`/g)].map((m) => m[1])
      .filter((c) => LIBRARY_NAMES.includes(c.split(/[.(]/)[0]))
      .map((c) => hint(c, firstSentence(plain(about.trim()))));
  }),
].filter((x, i, all) => all.findIndex((y) => y.name === x.name) === i);
const known = (name: string) => HINTS.find((x) => x.name === name);

// The room's own names, so its variables and functions come up too.
function ownNames(source: string): Hint[] {
  const names = new Set([...source.matchAll(/^\s*(?:def\s+(\w+)|(\w+)\s*=[^=])/gm)].map((m) => m[1] ?? m[2]));
  return [...names].filter((n) => !known(n)).map((n) => ({ name: n, call: n, about: "", insert: n, words: [] }));
}

// The line up to the caret, with strings and comments blanked: in a string or a comment says where it ended.
function scan(line: string): { code: string; inString: boolean; inComment: boolean } {
  let code = "", quote = "";
  for (const ch of line) {
    if (quote) { code += ch === quote ? ch : " "; if (ch === quote) quote = ""; continue; }
    if (ch === "#") return { code, inString: false, inComment: true };
    if (ch === '"' || ch === "'") quote = ch;
    code += ch;
  }
  return { code, inString: !!quote, inComment: false };
}

// The call whose "(" is still open before the caret, like say( in say("hi.
function openCall(code: string): Hint | undefined {
  for (let i = code.length - 1, depth = 0; i >= 0; i--) {
    if (code[i] === ")") depth++;
    if (code[i] !== "(") continue;
    if (depth--) continue;
    return known(/[\w.]*$/.exec(code.slice(0, i))![0]);
  }
}

function matches(typed: string, source: string): Hint[] {
  const t = typed.toLowerCase();
  const starts = (n: string) => n.toLowerCase().startsWith(t) || n.split(".").pop()!.toLowerCase().startsWith(t);
  const own = ownNames(source).filter((x) => x.name !== typed && starts(x.name));
  const byName = HINTS.filter((x) => starts(x.name));
  const byWord = t.length < 3 ? [] : HINTS.filter((x) => !byName.includes(x) && x.words.some((w) => w.startsWith(t)));
  const all = [...byName, ...own, ...byWord];
  return all.length === 1 && all[0].name === typed ? [] : all.slice(0, 6);
}

// What to offer with the caret after `before` in `source`: names that finish the word being typed, or
// else the call whose "(" is open. Never in a comment, and no names inside a string.
export function hintsAt(before: string, source: string, dismissed = false): { typed: string; list: Hint[]; call?: Hint } {
  const { code, inString, inComment } = scan(before.slice(before.lastIndexOf("\n") + 1));
  const typed = inString || inComment ? "" : /[\w.]*$/.exec(code)![0];
  const list = typed.length > 1 && !dismissed && !/^\d/.test(typed) ? matches(typed, source) : [];
  return { typed, list, call: inComment ? undefined : openCall(code) };
}

// Where the caret is inside the textarea, in pixels, from a copy of its text laid out the same way.
function caretAt(area: HTMLTextAreaElement): { left: number; top: number; height: number } {
  const style = getComputedStyle(area);
  const mirror = h("div", {});
  for (const p of ["fontFamily", "fontSize", "fontWeight", "letterSpacing", "lineHeight", "tabSize", "paddingTop", "paddingLeft", "paddingRight", "whiteSpace", "overflowWrap"] as const) mirror.style[p] = style[p];
  Object.assign(mirror.style, { position: "absolute", visibility: "hidden", boxSizing: "border-box",
    width: `${area.clientWidth}px`, left: `${area.clientLeft}px`, top: `${area.clientTop}px` });
  const mark = h("span", {}, "​");
  mirror.append(area.value.slice(0, area.selectionStart), mark);
  document.body.append(mirror);
  const at = { left: area.clientLeft + mark.offsetLeft - area.scrollLeft, top: area.clientTop + mark.offsetTop - area.scrollTop, height: mark.offsetHeight };
  mirror.remove();
  return at;
}

export interface CodeHints {
  element: HTMLElement;
  // True when the key was for the hints (picking one, or closing them), so the editor leaves it alone.
  key(e: KeyboardEvent): boolean;
}

// Wraps the textarea: the hints float under the caret as it moves.
export function codeHints(area: HTMLTextAreaElement): CodeHints {
  // Clicks on the hints keep the caret in the code.
  const box = h("div", { class: "code-hints", hidden: true, role: "listbox", onmousedown: (e: Event) => e.preventDefault() });
  const element = h("div", { class: "code-wrap" }, area, box);
  // chose: an arrow moved the pick, so Enter takes it; otherwise Enter is a new line.
  let shown: Hint[] = [], picked = 0, typed = "", dismissed = false, chose = false;

  const close = () => { box.hidden = true; shown = []; chose = false; };
  const take = (x: Hint) => {
    const end = area.selectionStart;
    area.setRangeText(x.insert, end - typed.length, end, "end");
    const back = x.insert.endsWith('")') ? 2 : x.insert.endsWith(")") ? 1 : 0;
    area.selectionStart = area.selectionEnd = area.selectionStart - back;
    area.dispatchEvent(new Event("input"));
    area.focus();
  };
  const place = () => {
    const at = caretAt(area);
    box.hidden = false;
    Object.assign(box.style, { left: `${Math.max(0, Math.min(at.left, area.clientWidth - box.offsetWidth))}px`, top: `${at.top + at.height + 4}px` });
  };
  const more = (x: Hint) => h("a", { class: "more", href: `#guide/${x.name.split(".")[0]}`, tabindex: -1 }, "More");
  const update = () => {
    if (area.readOnly || area.selectionStart !== area.selectionEnd || document.activeElement !== area) return close();
    const at = hintsAt(area.value.slice(0, area.selectionStart), area.value, dismissed);
    [typed, shown] = [at.typed, at.list];
    picked = Math.min(picked, Math.max(0, shown.length - 1));
    if (shown.length) {
      box.replaceChildren(...shown.map((x, i) => h("div", {
        class: i === picked ? "hint picked" : "hint", role: "option",
        onclick: () => take(x),
      }, h("code", {}, x.call), x.about ? h("span", {}, x.about) : h("span", { class: "dim" }, "in this room"))),
        h("div", { class: "keys" }, "Tab picks it, arrows pick another, Esc hides these"));
      return place();
    }
    const { call } = at;
    if (!call || dismissed) return close();
    box.replaceChildren(h("div", { class: "hint sig" }, h("code", {}, call.call), h("span", {}, call.about), more(call)),
      call.call.includes('("') ? h("div", { class: "keys" }, QUOTES) : "");
    place();
  };

  area.addEventListener("input", () => { [dismissed, picked, chose] = [false, 0, false]; update(); });
  area.addEventListener("click", update);
  area.addEventListener("keyup", (e) => e.key.startsWith("Arrow") || e.key === "Home" || e.key === "End" ? update() : undefined);
  area.addEventListener("scroll", () => !box.hidden && place());
  area.addEventListener("blur", close);

  return {
    element,
    key(e) {
      if (box.hidden) return false;
      if (e.key === "Escape") { dismissed = true; close(); return true; }
      if (!shown.length) return false;
      const step = { ArrowDown: 1, ArrowUp: -1 }[e.key];
      if (step) [picked, chose] = [(picked + step + shown.length) % shown.length, true];
      else if (e.key === "Tab" || (e.key === "Enter" && chose)) take(shown[picked]);
      else return false;
      e.preventDefault();
      return true;
    },
  };
}
