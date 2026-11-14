// The Room guide: room-guide.md with the starter rooms after it, shown as the page and copied whole,
// for a parent to read or to hand to an AI helper.
import { EXAMPLES } from "../examples";
import guide from "../room-guide.md?raw";
import roomLibrary from "../../../purplecomputer/roomkit/purple.py?raw";
import { h } from "./dom";
import { markdown } from "./markdown";
import type { View } from "./view";

export const LIBRARY_NAMES: string[] = JSON.parse(/__all__ = (\[[^\]]*\])/.exec(roomLibrary)![1].replace(/'/g, '"'));
const starters = EXAMPLES.map((e) => `### ${e.label}\n\n${e.about}\n\n\`\`\`python\n${e.source.trimEnd()}\n\`\`\``);
export const GUIDE = [guide.trimEnd(), "## The starter rooms", ...starters].join("\n\n") + "\n";

// The table row for one of Purple's names: `show` finds show(thing), `grid` finds grid.set.
function rowFor(name: string): HTMLElement | null {
  const codes = [...document.querySelectorAll<HTMLElement>(".guide td code")];
  return codes.find((c) => new RegExp(`^${name}($|[(.\\[])`).test(c.textContent ?? ""))?.closest("tr") ?? null;
}

// GUIDE as plain text, for an AI helper to read: vite.config.ts serves and builds it.
export const AI_GUIDE = "ai.md";
export const aiGuideLink = () => {
  const url = new URL(AI_GUIDE, location.href).href;
  return h("a", { href: url, target: "_blank", class: "mono" }, url.replace(/^https?:\/\//, ""));
};

// A whole room copied out of an AI helper's answer, with or without the ``` fence around it.
export function roomFromPaste(text: string): string | null {
  const code = /```[a-z]*\n([\s\S]*?)```/.exec(text)?.[1] ?? text;
  return /^from purple import \*/m.test(code) ? code.trim() + "\n" : null;
}

// The link to hand an AI helper, and a button that copies the whole guide for one that can't open links.
export function copyGuideRow(): HTMLElement {
  const status = h("span", { class: "status" });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(GUIDE);
      status.textContent = "Copied. Paste it to an AI helper along with what you'd like to make.";
    } catch {
      status.textContent = "Your browser did not allow copying. Select the text on the Room guide page instead.";
    }
  };
  return h("div", { class: "row between copy-guide" }, h("span", { class: "small" }, "Using an AI helper? Give it ", aiGuideLink(), " and say what you'd like."), h("button", { class: "btn small secondary", onclick: copy }, "Copy the Room guide"), status);
}

export function guideView(item: string | null): View {
  return {
    title: "Room guide",
    editor: h(
      "section",
      { class: "guide" },
      copyGuideRow(),
      ...markdown(GUIDE),
      h("details", { class: "more-options" },
        h("summary", {}, "Purple's own code, for the curious"),
        h("p", {}, "Every room runs on this file, which Studio puts in the pack beside the rooms. ", h("code", {}, "from purple import *"),
          " brings in the names in its ", h("code", {}, "__all__"), " list, all of them described above. It isn't part of the copied guide: rooms use it as it is and can't change it."),
        h("pre", {}, h("code", {}, roomLibrary))),
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
