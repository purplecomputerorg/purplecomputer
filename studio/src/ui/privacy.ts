import { h } from "./dom";
import type { View } from "./view";

// One line, on every page that takes something of the family's, linking to the full answer.
export const staysHere = (text: string) =>
  h("p", { class: "stays-here" }, "🔒 ", text, " ", h("a", { href: "#privacy" }, "How it stays private"));

export function privacyView(): View {
  const item = (title: string, body: string) => h("li", {}, h("b", {}, title), " ", body);
  return {
    title: "Your privacy",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Studio runs entirely in your web browser. Nothing you add or make leaves your phone or computer."),
      h("ul", { class: "plain privacy" },
        item("Nothing is uploaded.", "Photos, drawings, recordings, words, and rooms stay in your browser. The file you download is the only copy."),
        item("Nothing is tracked.", "No account, cookies, analytics, or ads."),
        item("No AI service.", "Pictures, sounds, and Purple's voice are all made on your device, not sent to a company."),
        item("Closing the tab clears it.", "Your browser keeps only Purple's voice (79 MB), so it doesn't download again."),
      ),
      h("h3", {}, "Not just a promise"),
      h("p", {}, "Your browser blocks Studio from talking to any site but its own, so it couldn't send your things out even by mistake."),
      h("p", {}, "All of Studio's code, and all of Purple's, is open on GitHub, where ", h("a", { href: "https://github.com/purplecomputerorg/purplecomputer/tree/main/studio#privacy", target: "_blank", rel: "noopener" }, "Studio's notes"), " explain how this works in detail."),
    ),
  };
}
