import { h } from "./dom";
import type { View } from "./view";

// One line, on every page that takes something of the family's, linking to the full answer.
export const staysHere = (text: string) =>
  h("p", { class: "stays-here" }, "🔒 ", text, " ", h("a", { href: "#privacy" }, "How we know"));

export function privacyView(): View {
  const item = (title: string, body: string) => h("li", {}, h("b", {}, title), " ", body);
  return {
    title: "Your privacy",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Everything in Studio happens in this web browser, on this computer. Nothing you make is sent anywhere."),
      h("ul", { class: "plain privacy" },
        item("Nothing is uploaded.", "Your photos, your kid's drawings, your recordings, your words, your rooms, and your colors stay in this browser tab. Studio has nowhere to send them: its site only hands out Studio's own files, and nothing on it takes anything back."),
        item("Your voice stays here.", "The microphone is on only while you record. The recording stays in this tab, and Purple's voice runs on this computer too, so even what Purple says is never sent out to be spoken."),
        item("Nothing is tracked.", "No account, no sign-in, no cookies, no analytics, no ads. Studio doesn't know who you are and doesn't count what you do."),
        item("No AI service.", "Nothing you give Studio goes to a company to be processed. Pictures, sounds, and instruments are all worked out right here."),
        item("The file is made here.", "Download builds your pack in this browser and saves it where your downloads go. That file is the only copy, and you decide who gets it."),
        item("Closing the tab clears it.", "Nothing you made is kept after you close Studio. The one thing your browser keeps is Purple's voice (79 MB), so it doesn't download again next time."),
      ),
      h("h3", {}, "What does travel"),
      h("p", {}, "Your browser downloads Studio itself from this site: the page, a copy of Purple to run in it, and Purple's voice. Like any website, the site sees that those files were asked for. Downloads only come to you; nothing goes back."),
      h("h3", {}, "How we know"),
      h("p", {}, "It isn't only a promise. Every Studio page tells your browser it may only talk to the site it came from, and your browser enforces that, so the page couldn't send your things elsewhere even by mistake. Rooms you paste in run walled off with their internet access removed. Studio's fonts, icons, and voice are all served from this site, and when the browser's own voice fills in for Purple's, Studio uses only voices installed on this computer."),
      h("p", { class: "dim small" }, "(Technical: a Content-Security-Policy with ", h("span", { class: "mono" }, "connect-src 'self'"), " on every page and room worker, no backend, no cookies or storage beyond the Cache API for the voice model, and only ", h("span", { class: "mono" }, "localService"), " speech voices. The source is in Purple's repository under ", h("span", { class: "mono" }, "studio/"), ".)"),
    ),
  };
}
