import { openPack } from "../pack";
import { forget, shelf, shelveDraft } from "../shelf";
import { clearSection, hasWork, replaceDraft, type Draft } from "../state";
import { filePicker, go, h } from "./dom";

function swapIn(d?: Draft) {
  if (d) shelveDraft(d);
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

// A dialog rather than confirm(), for the second question: the pictures live apart from the pack (shelf.ts).
function clearEverything() {
  const pictures = h("input", { type: "checkbox" });
  const dialog = h("dialog", { class: "card stack", onclose: () => {
    dialog.remove();
    if (dialog.returnValue !== "clear") return;
    if (pictures.checked) forget(...shelf);
    replaceDraft();
    go("");
  } }, h("form", { method: "dialog", class: "stack" },
    h("p", {}, `Clear everything you've made in Purple Studio and start fresh? ${KEEP_IT}`),
    shelf.length ? h("label", { class: "row" }, pictures, `Also delete your ${shelf.length > 1 ? `${shelf.length} pictures` : "picture"} from this computer`) : null,
    h("p", { class: "row" },
      h("button", { class: "btn small", value: "clear" }, "Clear everything"),
      h("button", { class: "btn secondary small", value: "", autofocus: true }, "Cancel"))));
  document.body.append(dialog);
  dialog.showModal();
}

export const clearEverythingButton = (cls = "linkbtn dim") => h("button", { type: "button", class: cls, onclick: clearEverything }, "Clear everything");

export const clearSectionButton = (section: string, what: string) => h("button", { type: "button", class: "linkbtn dim", onclick: () => {
  if (!confirm(`Clear all your ${what}? ${KEEP_IT}`)) return;
  clearSection(section);
  go(`#${section}`);
} }, `Clear all ${what}`);
