import { openPack } from "../pack";
import { forget, shelf, shelveDraft } from "../shelf";
import { clearSection, hasWork, replaceDraft, type Draft } from "../state";
import { ask, filePicker, go, h } from "./dom";

function swapIn(d?: Draft) {
  if (d) shelveDraft(d);
  replaceDraft(d);
  go("#pack");
}

export function openPackButton(label: string): HTMLElement {
  const status = h("span", { class: "dim small" });
  const open = async (file: File) => {
    if (hasWork() && !(await ask("Open this Purple Pack instead of what you're working on now?", "Open it"))) return;
    try {
      swapIn(await openPack(file));
    } catch (e) {
      status.textContent = ` That file isn't a Purple Pack this page can open. (Technical: ${e instanceof Error ? e.message : String(e)})`;
    }
  };
  return h("span", {}, filePicker(".purplepack", open, label), status);
}

const KEEP_IT = "Download your Purple Pack first if you want to keep it.";

// The pictures get their own question: they live apart from the pack (shelf.ts).
async function clearEverything() {
  const pictures = h("input", { type: "checkbox" });
  if (!(await ask(`Clear everything you've made in Purple Studio and start fresh? ${KEEP_IT}`, "Clear everything",
    shelf.length ? h("label", { class: "row" }, pictures, `Also delete your ${shelf.length > 1 ? `${shelf.length} pictures` : "picture"} from this computer`) : null))) return;
  if (pictures.checked) forget(...shelf);
  replaceDraft();
  go("");
}

export const clearEverythingButton = (cls = "linkbtn dim") => h("button", { type: "button", class: cls, onclick: clearEverything }, "Clear everything");

export const clearSectionButton = (section: string, what: string) => h("button", { type: "button", class: "linkbtn dim", onclick: async () => {
  if (!(await ask(`Clear all your ${what}? ${KEEP_IT}`, `Clear all ${what}`))) return;
  clearSection(section);
  go(`#${section}`);
} }, `Clear all ${what}`);
