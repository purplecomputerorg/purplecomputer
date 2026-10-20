// The Room guide: room-guide.md with the starter rooms after it, shown as the page and copied whole,
// for a parent to read or to hand to an AI helper.
import { EXAMPLES } from "../examples";
import guide from "../room-guide.md?raw";
import { h } from "./dom";
import { markdown } from "./markdown";
import type { View } from "./view";

const starters = EXAMPLES.map((e) => `### ${e.label}\n\n${e.about}\n\n\`\`\`python\n${e.source.trimEnd()}\n\`\`\``);
export const GUIDE = [guide.trimEnd(), "## The starter rooms", ...starters].join("\n\n") + "\n";

export function guideView(): View {
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
  };
}
