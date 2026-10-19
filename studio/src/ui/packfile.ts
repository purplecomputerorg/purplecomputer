import { openPack } from "../pack";
import { clearSection, hasWork, replaceDraft, type Draft } from "../state";
import { filePicker, go, h } from "./dom";

function swapIn(d?: Draft) {
  replaceDraft(d);
  go("#pack");
}

export function openPackButton(label: string): HTMLElement {
  const status = h("span", { class: "dim small" });
  const open = async (file: File) => {
    if (hasWork() && !confirm("Open this Purple Pack instead of what you're working on now?")) return;
    try {
      swapIn(await openPack(file));
    } catch (e) {
      status.textContent = ` That file isn't a Purple Pack this page can open. (Technical: ${e instanceof Error ? e.message : String(e)})`;
    }
  };
  return h("span", {}, filePicker(".purplepack", open, label), status);
}

const KEEP_IT = "Download your Purple Pack first if you want to keep it.";

export const clearEverythingButton = (cls = "linkbtn dim") => h("button", { type: "button", class: cls, onclick: () => {
  if (!confirm(`Clear everything you've made in Purple Studio and start fresh? ${KEEP_IT}`)) return;
  replaceDraft();
  go("");
} }, "Clear everything");

export const clearSectionButton = (section: string, what: string) => h("button", { type: "button", class: "linkbtn dim", onclick: () => {
  if (!confirm(`Clear all your ${what}? ${KEEP_IT}`)) return;
  clearSection(section);
  go(`#${section}`);
} }, `Clear all ${what}`);
