import { openPack } from "../pack";
import { allPieces, replaceDraft, type Draft } from "../state";
import { filePicker, go, h } from "./dom";

const working = () => allPieces().some((p) => p.items.length);

function swapIn(d?: Draft) {
  replaceDraft(d);
  go("#pack");
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
  if (confirm("Erase everything currently loaded in Purple Studio and start a new Purple Pack?")) swapIn();
} }, "Start over");
