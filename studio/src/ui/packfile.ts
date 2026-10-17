import { openPack } from "../pack";
import { allPieces, replaceDraft, type Draft } from "../state";
import { filePicker, h } from "./dom";

const working = () => allPieces().some((p) => p.items.length);

function swapIn(d?: Draft) {
  replaceDraft(d);
  if (location.hash === "#pack") window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = "#pack";
}

export function openPackButton(label: string): HTMLElement {
  const status = h("span", { class: "dim small" });
  const open = async (file: File) => {
    if (working() && !confirm("Open this Purple Pack instead of what you're working on now?")) return;
    try {
      swapIn(await openPack(file));
    } catch (e) {
      status.textContent = ` That file isn't a Purple Pack this page can open. (Technical: ${e instanceof Error ? e.message : String(e)})`;
    }
  };
  return h("span", {}, filePicker(".purplepack", open, label), status);
}

export const startOverButton = () => h("button", { class: "linkbtn dim", onclick: () => {
  if (confirm("Erase everything here and start a new Purple Pack? One you already downloaded stays as it is.")) swapIn();
} }, "Start over");
