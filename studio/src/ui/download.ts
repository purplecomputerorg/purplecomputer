import { buildPack, manifest, packFilename } from "../pack";
import { changed, draft, packId, pieces } from "../state";
import { clear, field, h } from "./dom";

export function downloadView(): HTMLElement {
  const nameIn = h("input", { type: "text", placeholder: "The Nathansons", value: draft.familyName });
  const summary = h("ul", { class: "summary" });
  const idLine = h("p", { class: "dim small" });
  const status = h("div", { class: "status" });
  const button = h("button", { class: "btn logo" }, "Download the pack");

  function render() {
    clear(summary);
    const list = pieces();
    for (const p of list) summary.append(h("li", {}, h("span", {}, p.label), h("span", { class: "n" }, String(p.count))));
    if (!list.length) summary.append(h("li", { class: "dim" }, "Nothing in the pack yet. Every part is optional, but an empty pack changes nothing."));
    button.disabled = !list.length;
    idLine.replaceChildren("Saved as ", h("span", { class: "mono" }, packFilename()), ". Purple will list it as ", h("strong", {}, manifest().name), " and keep it at ", h("span", { class: "mono" }, `~/.purple/packs/${packId()}/`), ".");
  }
  nameIn.oninput = () => {
    draft.familyName = nameIn.value;
    changed();
    render();
  };
  render();

  button.onclick = async () => {
    button.disabled = true;
    try {
      const blob = await buildPack((msg) => (status.textContent = `${msg}…`));
      const a = h("a", { href: URL.createObjectURL(blob), download: packFilename() });
      a.click();
      URL.revokeObjectURL(a.href);
      status.replaceChildren("Downloaded. Next: ", h("a", { href: "#install" }, "getting it onto Purple"), ".");
    } catch (e) {
      status.textContent = `Something went wrong while packing: ${e instanceof Error ? e.message : String(e)}`;
    }
    button.disabled = false;
  };

  return h(
    "section",
    {},
    h("h2", {}, "Your pack"),
    h("p", { class: "lead" }, "One file holds everything you made here. It never leaves this computer unless you move it."),
    h("div", { class: "card" }, field("Your family's name, for the pack's label", nameIn), idLine, summary),
    h("div", { class: "row", style: "margin-top:24px" }, button),
    status,
    h("div", { class: "note" },
      h("strong", {}, "What an installed Purple reads from this pack today: "), "the words, synonyms, and autocomplete picks. ",
      "Photos, recordings, an instrument, and colors ride along in the same file in the layout described in ", h("a", { href: "#format" }, "the pack format"), ", waiting for Purple to learn to read them. Nothing in the pack can run as a program."),
  );
}
