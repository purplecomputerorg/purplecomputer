import { features } from "../state";
import { h } from "./dom";
import { startOverButton } from "./packfile";
import type { View } from "./view";

// One line, on every page that takes something of the family's, linking to the full answer.
export const staysHere = (text: string) =>
  h("p", { class: "stays-here" }, "🔒 ", text, " ", h("a", { href: "#privacy" }, "How it stays private"));

export function privacyView(): View {
  const item = (title: string, ...body: (string | Node)[]) => h("li", {}, h("b", {}, title), " ", ...body);
  return {
    title: "Your privacy",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Purple Studio runs entirely in your web browser. Nothing you add or make leaves your phone or computer."),
      h("ul", { class: "plain privacy" },
        item("Nothing is uploaded.", `Photos, drawings, recordings, ${features.rooms ? "words, and rooms" : "and words"} stay in your browser.`),
        item("Purple runs fully in your browser.", "Purple Studio is JavaScript, and Purple's Python runs with ", h("a", { href: "https://pyodide.org", target: "_blank", rel: "noopener" }, "Pyodide"), "."),
        item("Nothing is tracked.", "No account, cookies, analytics, or ads."),
        item("No AI service.", "Nothing you add or make is sent to an AI company."),
        item("Saved in this browser.", "What you're working on stays on this computer, never online. ", startOverButton(), " erases it."),
      ),
      h("h3", {}, "See all the code for yourself"),
      h("p", {}, "All of Purple Studio's code, and all of Purple's, is open on GitHub, where ", h("a", { href: "https://github.com/purplecomputerorg/purplecomputer/tree/main/studio#privacy", target: "_blank", rel: "noopener" }, "Purple Studio's notes"), " explain how this works in detail."),
    ),
  };
}
