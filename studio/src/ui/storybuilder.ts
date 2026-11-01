// The story room's builder: pages written in order, each with its picture, its words, what Purple says to ask for
// a choice, and choices that make the next pages as they're added. It edits TITLE, PAGES and PAGE_SOUND in place;
// page names stay in the Python.
import type { Knob } from "../knobs";
import { ask, h, removeButton } from "./dom";
import { emojiCell, isEmoji } from "./emojipicker";
import { spoken } from "./knobsform";
import { isFace, isStr, knobNamed, section, soundRow, str, tupleOf, wordsIn, type Dict, type Face, type Str, type Tuple } from "./builderkit";

// Number keys pick a choice, so a page has at most nine.
const MOST = 9;
const NEW = "\u0000new";
// What a new choice says until it's changed. Each is different, since two choices can't say the same thing.
const ONE = "turn the page";
const SUGGESTED = ["go this way", "go that way", "try something else", "go somewhere new", "take a peek", "be brave", "be sneaky", "be silly", "go home"];
type Page = [Str, Tuple];
// "Press 1 to go to the forest, or 2 to go to the sea."
export const askFor = (whats: string[]) => {
  const press = whats.map((w, j) => `${whats.length === 1 ? "Space" : j + 1} to ${w || ONE}`);
  return press.length ? `Press ${press.length > 1 ? `${press.slice(0, -1).join(", ")}, or ${press.at(-1)}` : press[0]}.` : "";
};
const isChoices = (v: unknown): v is Dict => {
  const d = v as Dict;
  return d?.t === "dict" && d.entries.every(([k, x]) => isStr(k) && isStr(x) && !/^\d+$/.test(k.v));
};

// PAGES as the builder reads it; an older story, whose choices are number keys or that says no line to ask for
// one, gets the plain knobs instead.
export function storyPages(knobs: Knob[]): Dict | null {
  const v = knobNamed(knobs, "PAGES")?.value;
  return v?.t === "dict" && v.entries.length > 0 && v.entries.every(([k, x]) => isStr(k) && tupleOf(x, isFace, isStr, isStr, isChoices)) ? v : null;
}

export function storyBuilder(knobs: Knob[], onEdit: () => void): HTMLElement | null {
  const pages = storyPages(knobs);
  if (!pages) return null;
  const title = knobNamed(knobs, "TITLE")?.value;
  const el = h("div", { class: "card knobs builder story-builder" });
  // The story before Start a new story, to bring back while this page is open.
  let before: { pages: Dict["entries"]; title: string } | null = null;
  let focus: (() => void) | null = null;

  const all = () => pages.entries as Page[];
  const parts = (p: Page) => p[1].items as [Face, Str, Str, Dict];
  const named = (name: string) => all().findIndex(([k]) => k.v === name);
  const ways = (p: Page) => parts(p)[3].entries as [Str, Str][];
  const into = (name: string) => all().flatMap((p, i) => ways(p).filter(([, to]) => to.v === name).map(([what]) => [i, what.v] as const));
  // A page's ask line follows its choices until the family writes their own.
  const asked = new Map<Page, string>();
  const follow = () => all().forEach((p) => {
    const says = parts(p)[2];
    const now = askFor(ways(p).map(([w]) => w.v));
    if (says.v === (asked.get(p) ?? now)) says.v = now;
    asked.set(p, now);
  });
  follow();
  const changed = () => { follow(); draw(); onEdit(); };
  const look = (f: Face) => (f.t === "picture" ? "🖼️" : f.v);
  const short = (i: number) => `Page ${i + 1} ${look(parts(all()[i])[0])}`;

  // A new blank page after the one its choice is on and that page's other next pages, so they read in choice
  // order, with the page's picture to start.
  const newPage = (from: number): string => {
    let n = all().length + 1;
    while (named(`page${n}`) >= 0) n++;
    const name = `page${n}`;
    const after = Math.max(from, ...ways(all()[from]).map(([, to]) => named(to.v)));
    pages.entries.splice(after + 1, 0, [str(name), { t: "tuple", items: [structuredClone(parts(all()[from])[0]), str(""), str(""), { t: "dict", entries: [] }] }]);
    return name;
  };
  const addWay = (i: number) => {
    const list = ways(all()[i]);
    if (list.length === 1 && list[0][0].v === ONE) list[0][0].v = SUGGESTED[0];
    const used = new Set(list.map(([w]) => w.v));
    const what = list.length ? SUGGESTED.find((w) => !used.has(w)) ?? `choice ${list.length + 1}` : ONE;
    const to = newPage(i);
    list.push([str(what), str(to)]);
    return to;
  };
  const focusWords = (name: string) => () => {
    const area = el.querySelector<HTMLTextAreaElement>(`[data-page="${CSS.escape(name)}"] textarea`);
    area?.scrollIntoView({ behavior: "smooth", block: "center" });
    area?.focus({ preventScroll: true });
  };
  const focusWay = (i: number, j: number) => () => el.querySelectorAll<HTMLElement>(`[data-page="${CSS.escape(all()[i][0].v)}"] .way input`)[j]?.focus();

  // A page nobody can reach and with nothing on it goes with the choice that made it.
  const dropIfBlank = (name: string) => {
    const i = named(name);
    if (i > 0 && !into(name).length && !parts(all()[i])[1].v.trim() && !ways(all()[i]).length) pages.entries.splice(i, 1);
  };
  const removePage = async (i: number) => {
    const name = all()[i][0].v;
    if (parts(all()[i])[1].v.trim() && !(await ask("Remove this page and its words?", "Remove it"))) return;
    pages.entries.splice(i, 1);
    for (const p of all()) parts(p)[3].entries = ways(p).filter(([, to]) => to.v !== name);
    changed();
  };

  // Which page a choice turns to: any page, or a new one made right then.
  const pageSelect = (i: number, to: Str) => {
    const sel = h("select", { class: "inline page-pick" });
    const fill = () => {
      const missing = named(to.v) < 0;
      sel.replaceChildren(...(missing ? [h("option", { value: to.v }, "a page that's gone")] : []),
        ...all().map(([k], n) => h("option", { value: k.v }, short(n))), h("option", { value: NEW }, "+ A new page"));
      sel.value = to.v;
      sel.classList.toggle("bad", missing);
    };
    fill();
    sel.addEventListener("pointerdown", fill);
    sel.addEventListener("focus", fill);
    sel.addEventListener("change", () => {
      const was = to.v;
      to.v = sel.value === NEW ? newPage(i) : sel.value;
      dropIfBlank(was);
      if (sel.value === NEW) focus = focusWords(to.v);
      changed();
    });
    return sel;
  };

  const choicesOf = (i: number) => {
    const list = ways(all()[i]);
    if (!list.length) {
      return h("div", { class: "page-end" }, h("span", { class: "dim small" }, "The end, for now."),
        h("button", { class: "btn small", onclick: () => { focus = focusWords(addWay(i)); changed(); } }, "+ Next page"),
        h("button", { class: "btn small secondary", onclick: () => { addWay(i); addWay(i); focus = focusWay(i, 0); changed(); } }, "+ Let them choose"));
    }
    const one = list.length === 1;
    const says = parts(all()[i])[2];
    const asking = wordsIn(says, onEdit, askFor(list.map(([w]) => w.v)));
    const area = asking.querySelector("textarea")!;
    return h("div", { class: "page-ways" },
      ...list.map(([what, to], j) => {
        const label = h("input", { type: "text", class: "inline", value: what.v, placeholder: one ? ONE : "go to the forest" });
        label.addEventListener("input", () => {
          what.v = label.value;
          const was = says.v;
          follow();
          if (says.v === was) return onEdit();
          area.value = says.v;
          area.dispatchEvent(new Event("input"));
        });
        const drop = removeButton(() => { list.splice(j, 1); dropIfBlank(to.v); changed(); });
        return h("div", { class: "way" }, h("span", { class: "way-say" }, "Press", h("span", { class: "key-cap" }, one ? "Space" : String(j + 1)), "to"), label, pageSelect(i, to), drop);
      }),
      list.length < MOST ? h("button", { class: "add-row", onclick: () => { addWay(i); focus = focusWay(i, list.length - 1); changed(); } }, one ? "+ Let them choose" : "+ Another choice") : null,
      h("p", { class: "dim small" }, "Then Purple says"), asking);
  };

  const card = (p: Page, i: number) => {
    const [face, words] = parts(p);
    const from = into(p[0].v);
    const came = i === 0 ? h("span", { class: "dim small" }, "The story starts here")
      : from.length ? h("span", { class: "dim small" }, `after page ${[...new Set(from.map(([n]) => n + 1))].join(", ")}`)
      : h("span", { class: "bad small" }, "Nothing leads here yet");
    const pick = emojiCell(face.v, () => words.v, (e) => { Object.assign(face, { t: isEmoji(e) ? "str" : "picture", v: e }); changed(); }, { pictures: true });
    return h("article", { class: "story-page", "data-page": p[0].v },
      h("div", { class: "page-head" }, h("b", {}, `Page ${i + 1}`), came, i ? removeButton(() => void removePage(i)) : null),
      h("div", { class: "page-body" }, h("span", { class: "emoji-wrap page-pic" }, pick), wordsIn(words, onEdit, i ? "What happens on this page?" : "How does the story start?")),
      choicesOf(i));
  };

  // Every page as a chip to jump to: not written yet shows dashed, and one nothing leads to shows red.
  const strip = () => h("div", { class: "page-strip" }, ...all().map(([k], i) => {
    const lost = i > 0 && !into(k.v).length;
    const blank = !parts(all()[i])[1].v.trim();
    return h("button", { type: "button", class: `page-chip${blank ? " blank" : ""}${lost ? " lost" : ""}`, title: lost ? "Nothing leads here yet" : blank ? "Not written yet" : "", onclick: focusWords(k.v) },
      h("b", {}, String(i + 1)), look(parts(all()[i])[0]));
  }));

  const startOver = async () => {
    if (!(await ask("Start a new story? This one goes away, and you can bring it back until you leave this page.", "Start a new story"))) return;
    before = { pages: structuredClone(pages.entries), title: isStr(title) ? title.v : "" };
    pages.entries = [[str("start"), { t: "tuple", items: [str("📖"), str(""), str(""), { t: "dict", entries: [] }] }]];
    if (isStr(title)) title.v = "My story";
    focus = () => el.querySelector<HTMLInputElement>(".story-title input")?.select();
    changed();
  };
  const bringBack = () => {
    if (!before) return;
    pages.entries = before.pages;
    if (isStr(title)) title.v = before.title;
    before = null;
    changed();
  };

  const draw = () => {
    const titleIn = isStr(title) ? (() => {
      const input = h("input", { type: "text", class: "inline", value: title.v, placeholder: "The story's name" });
      input.addEventListener("input", () => { title.v = input.value; onEdit(); });
      return h("div", { class: "story-title" }, spoken(input, title));
    })() : null;
    el.replaceChildren(
      section("The story", "Write it a page at a time. Each page says what comes next.",
        titleIn,
        h("div", { class: "story-tools" }, strip(),
          h("button", { class: "btn small secondary", onclick: () => void startOver() }, "✨ New story"),
          before ? h("button", { class: "linkbtn small", onclick: bringBack }, "Bring back the story you had") : null)),
      h("div", { class: "story-pages" }, ...all().map(card)),
      section("Sound", "", soundRow("When a page turns", knobNamed(knobs, "PAGE_SOUND"), onEdit)));
    const f = focus;
    focus = null;
    if (f) queueMicrotask(f);
  };
  draw();
  return el;
}

