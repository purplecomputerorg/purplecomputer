import { buildPack, packFilename } from "../pack";
import { addAll, changed, countOf, draft, pieces, tryingPieces } from "../state";
import { clear, field, h } from "./dom";
import { putItOnPurple } from "./install";
import { openPackButton, startOverButton } from "./packfile";
import { staysHere } from "./privacy";
import type { View } from "./view";

export function downloadView(): View {
  const nameIn = h("input", { type: "text", value: draft.name, oninput: () => { draft.name = nameIn.value; changed(); } });
  const summary = h("ul", { class: "summary" });
  const trying = h("div");
  const status = h("div", { class: "status" });
  const button = h("button", { class: "btn logo" }, "Download my Purple Pack");

  function render() {
    clear(summary);
    const list = pieces();
    for (const p of list) summary.append(h("li", {}, countOf(p)));
    if (!list.length) summary.append(h("li", { class: "dim" }, "Nothing added yet. Try something, then press Add to my Purple Pack."));
    button.disabled = !list.length;
    const left = tryingPieces();
    trying.replaceChildren(...(left.length ? [h("div", { class: "trybar" },
      h("span", { class: "trying" }, `Still trying, not in your Purple Pack: ${left.map(countOf).join(", ")}.`),
      h("button", { class: "btn small", onclick: () => { addAll(); changed(); render(); } }, left.reduce((n, p) => n + p.count, 0) > 1 ? "Add them too" : "Add it too"))] : []));
  }
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
    title: "Your Purple Pack",
    editor: h(
      "section",
      {},
      h("p", { class: "lead" }, "Everything you added goes into your Purple Pack."),
      staysHere("Your Purple Pack is made in your browser and saved to your downloads. No copy goes anywhere else."),
      h("div", { class: "card" }, summary),
      trying,
      field("File name", h("div", { class: "row", style: "flex-wrap:nowrap" }, nameIn, h("span", { class: "mono dim" }, ".purplepack"))),
      h("div", { class: "row", style: "margin-top:22px" }, button),
      status,
      h("h3", {}, "Then put it on Purple"),
      putItOnPurple(),
      h("p", { class: "dim small" }, "To change it later, ", openPackButton("open your Purple Pack"), " here, change what you like, and download it again. Or ", startOverButton(), "."),
    ),
  };
}
