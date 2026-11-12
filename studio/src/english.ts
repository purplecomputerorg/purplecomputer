// Purple shows English letters only while its language support is off (purple_tui/i18n.py ENABLED), so
// letters from other alphabets are taken out as they're typed. Accents, digits, symbols and emoji stay.
const OTHER_ALPHABETS = /(?!\p{Script=Latin})\p{L}/gu;
export const ENGLISH_ONLY = "Purple can only show English letters for now.";

export const englishOnly = (s: string) => s.replace(OTHER_ALPHABETS, "");

// Runs before a field's own input handler, so what Studio keeps is already cleaned.
export function keepTypingEnglish(root: Document = document): void {
  root.addEventListener("input", (e) => {
    const el = e.target;
    if (!(el instanceof HTMLInputElement && el.type === "text" || el instanceof HTMLTextAreaElement) || el.classList.contains("code")) return;
    const clean = englishOnly(el.value);
    if (clean === el.value) return el.setCustomValidity("");
    const caret = (el.selectionStart ?? el.value.length) - (el.value.length - clean.length);
    el.value = clean;
    el.setSelectionRange(Math.max(0, caret), Math.max(0, caret));
    el.setCustomValidity(ENGLISH_ONLY);
    el.reportValidity();
  }, true);
}
