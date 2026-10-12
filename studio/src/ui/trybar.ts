// The one way every page shows whether something is on the family's Purple yet. Everything starts as
// a try that Studio's Purple plays; adding it puts it in the download.
import { changed, type Keepable } from "../state";
import { h } from "./dom";

const keep = (item: Keepable, kept: boolean) => {
  item.kept = kept;
  item.sample = false;
  changed();
};

// For the thing a page is about: "Trying it" with Add, or "On your Purple" with Take it off.
// remove: "Never mind", which drops a try altogether.
export function tryBar(item: Keepable, remove?: () => void): HTMLElement {
  const bar = h("div", { class: "trybar" });
  const render = () => bar.replaceChildren(...[...(item.kept
    ? [h("span", { class: "added" }, "✓ On your Purple"), h("button", { class: "linkbtn dim small", onclick: () => { keep(item, false); render(); } }, "Take it off")]
    : [h("span", { class: "trying" }, "Just trying it. It isn't on your Purple yet."),
      h("button", { class: "btn small", onclick: () => { keep(item, true); render(); } }, "Add to my Purple"),
      remove ? h("button", { class: "linkbtn dim small", onclick: remove }, "Never mind") : null])].filter((e) => e !== null));
  render();
  return bar;
}

// For one row of a list: Add, or Added (which takes it off again).
export function keepButton(item: Keepable, onChange: () => void): HTMLElement {
  return h("button", { type: "button", class: `keep${item.kept ? " on" : ""}`, title: item.kept ? "On your Purple. Click to take it off." : "Add to my Purple",
    onclick: () => { keep(item, !item.kept); onChange(); } }, item.kept ? "✓ Added" : "Add");
}

// Under a list: how many are still tries, and one button to add them all.
export function addAllBar(items: Keepable[], what: (n: number) => string, onChange: () => void): HTMLElement | null {
  const trying = items.filter((i) => !i.kept);
  if (!trying.length) return null;
  return h("div", { class: "trybar" },
    h("span", { class: "trying" }, `${what(trying.length)} just being tried, not on your Purple yet.`),
    h("button", { class: "btn small", onclick: () => { trying.forEach((i) => keep(i, true)); onChange(); } }, trying.length > 1 ? "Add them all" : "Add it"));
}
