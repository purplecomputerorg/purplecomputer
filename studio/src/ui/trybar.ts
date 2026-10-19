// The one way every page shows whether something is in the family's Purple Pack yet. Everything starts as
// a try that Studio's Purple plays; adding it puts it in the download.
import { changed, type Keepable } from "../state";
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
    ? [h("span", { class: "added" }, "✓ In your Purple Pack"), h("button", { class: "linkbtn dim small", onclick: () => { keep(item, false); render(); } }, "Take it out")]
    : [h("span", { class: "trying" }, "Just trying it. It isn't in your Purple Pack yet."),
      h("button", { class: "btn small", onclick: () => { keep(item, true); render(); } }, "Add to my Purple Pack"),
      remove ? h("button", { class: "linkbtn dim small", onclick: remove }, "Never mind") : null])].filter((e) => e !== null));
  render();
  return bar;
}

// A try in a list, with an × in its corner that throws it away.
export const tryChip = (link: HTMLElement, label: string, remove: () => void): HTMLElement =>
  h("span", { class: "try-chip" }, link,
    h("button", { type: "button", class: "drop", title: `Throw away ${label}`, "aria-label": `Throw away ${label}`, onclick: remove }, "×"));

// For one row of a list: Add, or Added (which takes it off again).
export function keepButton(item: Keepable, onChange: () => void): HTMLElement {
  return h("button", { type: "button", class: `keep${item.kept ? " on" : ""}`, title: item.kept ? "In your Purple Pack. Click to take it out." : "Add to my Purple Pack",
    onclick: () => { keep(item, !item.kept); onChange(); } }, item.kept ? "✓ Added" : "Add");
}

// Under a list: how many are still tries, and one button to add them all.
export function addAllBar(items: Keepable[], what: (n: number) => string, onChange: () => void): HTMLElement | null {
  const trying = items.filter((i) => !i.kept);
  if (!trying.length) return null;
  return h("div", { class: "trybar" },
    h("span", { class: "trying" }, `${what(trying.length)} just being tried, not in your Purple Pack yet.`),
    h("button", { class: "btn small", onclick: () => { trying.forEach((i) => keep(i, true)); onChange(); } }, trying.length > 1 ? "Add them all" : "Add it"));
}
