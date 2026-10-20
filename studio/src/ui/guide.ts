// The Room guide: room-guide.md with the starter rooms after it, shown as the page and copied whole,
// for a parent to read or to hand to an AI helper.
import { EXAMPLES } from "../examples";
import guide from "../room-guide.md?raw";
import roomLibrary from "../../../purple_tui/roomkit/purple.py?raw";
import { h } from "./dom";
import { markdown } from "./markdown";
import type { View } from "./view";

const starters = EXAMPLES.map((e) => `### ${e.label}\n\n${e.about}\n\n\`\`\`python\n${e.source.trimEnd()}\n\`\`\``);
export const GUIDE = [guide.trimEnd(), "## The starter rooms", ...starters].join("\n\n") + "\n";

// The table row for one of Purple's names: `show` finds show(thing), `grid` finds grid.set.
function rowFor(name: string): HTMLElement | null {
  const codes = [...document.querySelectorAll<HTMLElement>(".guide td code")];
  return codes.find((c) => new RegExp(`^${name}($|[(.\\[])`).test(c.textContent ?? ""))?.closest("tr") ?? null;
}

// Purple's room library, read-only: what `from purple import *` brings in.
export function libraryView(): View {
  return {
    title: "Purple's room library",
    back: ["#guide", "Room guide"],
    editor: h("section", {},
      h("p", {}, "Every room in a Purple Pack runs on this file, which Studio puts in the pack beside the rooms. ", h("code", {}, "from purple import *"),
        " brings in the names in its ", h("code", {}, "__all__"), " list; the rest is how it talks to Purple. Rooms use it as it is and can't change it."),
      h("pre", {}, h("code", {}, roomLibrary))),
  };
}

export function guideView(item: string | null): View {
  const status = h("span", { class: "dim small" });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(GUIDE);
      status.textContent = "Copied. Paste it to an AI helper along with what you'd like to make.";
    } catch {
      status.textContent = "Your browser did not allow copying. Select the page text instead.";
    }
  };
  return {
    title: "Room guide",
    editor: h(
      "section",
      { class: "guide" },
      h("p", { class: "row" }, h("button", { class: "btn small", onclick: copy }, "Copy the guide"), status),
      ...markdown(GUIDE),
    ),
    mounted: () => {
      const row = item && rowFor(item);
      if (!row) return;
      row.scrollIntoView({ block: "center" });
      row.classList.add("flash");
      setTimeout(() => row.classList.remove("flash"), 1500);
    },
  };
}
