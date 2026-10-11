import { buildPack, packFilename } from "../pack";
import { changed, draft, pieces } from "../state";
import { clear, field, h } from "./dom";
import type { View } from "./view";

export function downloadView(): View {
  const nameIn = h("input", { type: "text", placeholder: "The Nathansons", value: draft.familyName });
  const summary = h("ul", { class: "summary" });
  const status = h("div", { class: "status" });
  const button = h("button", { class: "btn logo" }, "Download");

  function render() {
    clear(summary);
    const list = pieces();
    for (const p of list) summary.append(h("li", {}, h("span", {}, p.label), h("span", { class: "n" }, String(p.count))));
    if (!list.length) summary.append(h("li", { class: "dim" }, "Nothing added yet. Pick something on the left to start."));
    button.disabled = !list.length;
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
      status.textContent = `Downloaded ${packFilename()}.`;
    } catch (e) {
      status.textContent = `Something went wrong while packing. (Technical: ${e instanceof Error ? e.message : String(e)})`;
    }
    button.disabled = false;
  };

  return {
    title: "Download",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Everything you made goes into one file."),
      h("div", { class: "card" }, field("Your family's name", nameIn), summary),
      h("div", { class: "row", style: "margin-top:22px" }, button),
      status,
      h("h3", {}, "Then put it on Purple"),
      h("ol", { class: "steps" },
        h("li", {}, "Name a USB stick ", h("span", { class: "mono" }, "PURPLE_UPDATE"), "."),
        h("li", {}, "Copy the file onto it."),
        h("li", {}, "Plug it into Purple, then turn Purple on."),
      ),
      h("p", { class: "dim small" }, "Step by step, and other ways: ", h("a", { href: "#install" }, "Putting it on Purple"), "."),
    ),
  };
}
