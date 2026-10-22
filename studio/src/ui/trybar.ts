// The one way every page shows whether something is in the family's Purple Pack yet. Everything starts as
// a try that Studio's Purple plays; adding it puts it in the download.
import { changed, isTheirs, type Keepable } from "../state";
import { h } from "./dom";

const keep = (item: Keepable, kept: boolean) => {
  item.kept = kept;
  item.sample = false;
  changed();
};

// For the thing a page is about: "Trying it" with Add, or "In your Purple Pack" with Take it out.
// remove: "Never mind", which drops a try altogether.
export function tryBar(item: Keepable, remove?: () => void): HTMLElement {
  const bar = h("div", { class: "trybar" });
  const render = () => bar.replaceChildren(...[...(item.kept
    ? [h("span", { class: "added" }, "✓ In your Purple Pack. Changes you make here go in it too."), h("button", { class: "linkbtn dim small", onclick: () => { keep(item, false); render(); } }, "Take it out")]
    : [h("span", { class: "trying" }, "Just trying it. It isn't in your Purple Pack yet."),
      h("button", { class: "btn small", onclick: () => { keep(item, true); render(); } }, "Add to my Purple Pack"),
      remove ? h("button", { class: "linkbtn dim small", onclick: remove }, "Never mind") : null])].filter((e) => e !== null));
  render();
  return bar;
}

// rename says why a name can't be used, or renames the item and says nothing.
export interface YourCard { href: string; title: string; face: Node; current?: boolean; rename?: (text: string) => string | null }

// What the family made on a list page, one card each with an Add to my Pack button and an × that throws it
// away, plus a pencil when it can be renamed; "Choose several" throws away many at once. Examples only tried aren't theirs yet, so they aren't listed.
export function yoursList<T extends Keepable>(items: T[], card: (item: T) => YourCard, remove: (gone: T[]) => void): HTMLElement | null {
  const theirs = items.filter(isTheirs);
  if (!theirs.length) return null;
  const throwAway = (gone: T[], what: string) => confirm(`Throw away ${what}?`) && remove(gone);
  const chosen = new Set<T>();
  const bin = h("button", { type: "button", class: "btn small", onclick: () => throwAway([...chosen], chosen.size > 1 ? `these ${chosen.size}` : "this one") });
  const counted = () => { bin.disabled = !chosen.size; bin.textContent = chosen.size ? `Throw away ${chosen.size}` : "Throw away"; };
  const head = h("div", { class: "row between" });
  const list = h("div", { class: "yours" });
  const render = (choosing: boolean) => {
    chosen.clear();
    counted();
    const boxes: HTMLInputElement[] = [];
    const tick = (box: HTMLInputElement, item: T) => { box.checked ? chosen.add(item) : chosen.delete(item); counted(); };
    head.replaceChildren(h("h3", {}, "Yours"), h("div", { class: "row" }, ...(choosing
      ? [h("button", { class: "linkbtn dim small", onclick: () => boxes.forEach((b) => { b.checked = true; b.dispatchEvent(new Event("change")); }) }, "Choose all"),
        h("button", { class: "linkbtn dim small", onclick: () => render(false) }, "Cancel"), bin]
      : theirs.length > 1 ? [h("button", { class: "linkbtn dim small", onclick: () => render(true) }, "Choose several to throw away")] : [])));
    list.replaceChildren(...theirs.map((item) => {
      const c = card(item);
      const face = h(choosing ? "span" : "a", { class: "your-face", href: choosing ? null : c.href }, c.face, h("b", {}, c.title));
      if (choosing) {
        const box = h("input", { type: "checkbox", class: "choose", "aria-label": `Choose ${c.title}`, onchange: () => tick(box, item) });
        boxes.push(box);
        return h("label", { class: "your-card" }, face, box);
      }
      const el = h("div", { class: "your-card", "aria-current": c.current ? "page" : null }, face, keepButton(item),
        c.rename ? h("button", { type: "button", class: "rename", title: `Rename ${c.title}`, "aria-label": `Rename ${c.title}`, onclick: () => renaming(el, face, c) }, "✏️") : null,
        h("button", { type: "button", class: "drop", title: `Throw away ${c.title}`, "aria-label": `Throw away ${c.title}`, onclick: () => throwAway([item], c.title) }, "×"));
      return el;
    }));
  };
  // The name turns into a box in place: Enter or leaving it keeps the new name, Esc puts the old one back.
  const renaming = (card: HTMLElement, face: HTMLElement, c: YourCard) => {
    const note = h("span", { class: "dim small" });
    const input = h("input", { type: "text", class: "your-rename", value: c.title, maxLength: 40, "aria-label": "New name" });
    let done = false;
    const finish = (keepIt: boolean) => {
      if (done) return;
      const why = keepIt && input.value.trim() !== c.title ? c.rename!(input.value) : null;
      if (why) return void (note.textContent = why);
      done = true;
      render(false);
    };
    input.onkeydown = (e) => { if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); };
    input.onblur = () => finish(true);
    face.replaceWith(h("div", { class: "your-face" }, input));
    card.append(note);
    input.select();
  };
  render(false);
  return h("div", {}, head, list);
}

// Add, or In my Pack (which takes it out again).
export function keepButton(item: Keepable, onChange?: () => void): HTMLElement {
  const button = h("button", { type: "button", onclick: () => { keep(item, !item.kept); paint(); onChange?.(); } });
  const paint = () => {
    button.className = `keep${item.kept ? " on" : ""}`;
    button.title = item.kept ? "In the Purple Pack you download. Click to take it out." : "Put it in the Purple Pack you download";
    button.textContent = item.kept ? "✓ In my Pack" : "Add to my Pack";
  };
  paint();
  return button;
}

// Under a list: how many are still tries, and one button to add them all.
export function addAllBar(items: Keepable[], what: (n: number) => string, onChange: () => void): HTMLElement | null {
  const trying = items.filter((i) => !i.kept);
  if (!trying.length) return null;
  return h("div", { class: "trybar" },
    h("span", { class: "trying" }, `${what(trying.length)} just being tried, not in your Purple Pack yet.`),
    h("button", { class: "btn small", onclick: () => { trying.forEach((i) => keep(i, true)); onChange(); } }, trying.length > 1 ? "Add them all" : "Add it"));
}
