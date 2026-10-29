// The one way every page shows whether something is in the family's Purple Pack. Studio's examples start
// out of it; anything the family makes or changes goes in, until they take it out.
import { isTheirs, keep, whileShown, type Keepable } from "../state";
import { ask, h } from "./dom";

// For the thing a page is about: in the Purple Pack, or not with one way in. It follows the item as the
// page changes it, and lights up when a change puts it in.
export function tryBar(item: Keepable): HTMLElement {
  const bar = h("div", { class: "trybar" });
  let shown: boolean | undefined;
  const render = () => {
    const kept = !!item.kept;
    if (kept === shown) return;
    bar.classList.toggle("just-added", kept && shown === false);
    shown = kept;
    bar.replaceChildren(...(kept
      ? [h("span", { class: "added" }, "✓ In your Purple Pack. Changes you make here go in it too."), h("button", { class: "linkbtn dim small", onclick: () => keep(item, false) }, "Take it out")]
      : [h("span", { class: "trying" }, "Not in your Purple Pack."), h("button", { class: "btn small", onclick: () => keep(item, true) }, "Add to my Purple Pack")]));
  };
  render();
  whileShown(bar, render);
  return bar;
}

// rename says why a name can't be used, or renames the item and says nothing. keep stands in for the Add button.
export interface YourCard { href: string; title: string; face: Node; current?: boolean; rename?: (text: string) => string | null; keep?: HTMLElement | null }

// What the family made on a list page, one card each with an Add to my Pack button and an × that throws it
// away, plus a pencil beside the name when it can be renamed; "Choose several" throws away many at once. Examples only tried aren't theirs yet, so they aren't listed.
// warn: anything more the confirm should say about throwing these away.
export function yoursList<T extends Keepable>(items: T[], card: (item: T) => YourCard, remove: (gone: T[]) => void, warn?: (gone: T[]) => string): HTMLElement | null {
  const theirs = items.filter(isTheirs);
  if (!theirs.length) return null;
  const throwAway = async (gone: T[], what: string) => (await ask(`Throw away ${what}?${warn?.(gone) ?? ""}`, "Throw away")) && remove(gone);
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
      const head = h("div", { class: "your-head" }, face,
        c.rename ? h("button", { type: "button", class: "rename", title: `Rename ${c.title}`, "aria-label": `Rename ${c.title}`, onclick: () => renaming(el, head, c) }, "✏️") : null);
      const el = h("div", { class: "your-card", "aria-current": c.current ? "page" : null }, head, c.keep === undefined ? keepButton(item) : c.keep,
        h("button", { type: "button", class: "drop", title: `Throw away ${c.title}`, "aria-label": `Throw away ${c.title}`, onclick: () => throwAway([item], c.title) }, "×"));
      return el;
    }));
  };
  // The name turns into a box in place: Enter or leaving it keeps the new name, Esc puts the old one back.
  const renaming = (card: HTMLElement, head: HTMLElement, c: YourCard) => {
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
    head.replaceWith(h("div", { class: "your-face" }, input));
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
