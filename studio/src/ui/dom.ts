type Child = Node | string | null | undefined | false;
type Attrs = Record<string, unknown>;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: Child[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v as EventListener);
    else if (k === "class") el.className = String(v);
    else if (k in el && k !== "style") (el as unknown as Record<string, unknown>)[k] = v;
    else el.setAttribute(k, String(v));
  }
  el.append(...children.filter((c): c is Node | string => !!c));
  return el;
}

export const clear = (el: Element) => el.replaceChildren();

// Goes to a page, drawing it again when it's the one showing.
export function go(hash: string) {
  if (location.hash === hash) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = hash;
}

export function field(label: string, input: HTMLElement): HTMLLabelElement {
  return h("label", { class: "field" }, h("span", {}, label), input);
}

// The forms' shared remove and add buttons, so every list in a room's settings grows and shrinks the same way.
export const removeButton = (onclick: () => void) => h("button", { class: "x", title: "Remove", "aria-label": "Remove", onclick }, "×");
export const addRowButton = (label: string, onclick: () => void) => h("button", { class: "add-row", onclick }, `+ ${label}`);

// A Studio dialog; resolves with the value of the button picked, or "" for Esc.
function dialog(question: string, buttons: Child[], extra: Child[] = []): Promise<string> {
  return new Promise((done) => {
    const box = h("dialog", { class: "card stack", onclose: () => { box.remove(); done(box.returnValue); } },
      h("form", { method: "dialog", class: "stack" }, h("p", {}, question), ...extra, h("p", { class: "row" }, ...buttons)));
    document.body.append(box);
    box.showModal();
  });
}

// Studio's own confirm(): resolves true when the family picks yes. Cancel has focus so Enter is safe, unless
// extra brings its own autofocus (an earlier one wins). Esc cancels.
export async function ask(question: string, yes: string, ...extra: Child[]): Promise<boolean> {
  return (await dialog(question, [h("button", { class: "btn small", value: "yes" }, yes),
    h("button", { class: "btn secondary small", value: "", autofocus: true }, "Cancel")], extra)) === "yes";
}

// Studio's own alert().
export async function tell(message: string): Promise<void> {
  await dialog(message, [h("button", { class: "btn small", value: "ok", autofocus: true }, "OK")]);
}

// Studio's own prompt(): the new text, or null when cancelled or left empty.
export async function askText(question: string, value: string, yes: string): Promise<string | null> {
  const input = h("input", { type: "text", value, maxLength: 40, autofocus: true, "aria-label": question });
  return (await ask(question, yes, input)) ? input.value.trim() || null : null;
}

export function filePicker(accept: string, onFile: (f: File) => void, label = "or choose a file", cls = "linkbtn dim"): HTMLElement {
  const input = h("input", { type: "file", accept, hidden: true, onchange: () => input.files?.[0] && onFile(input.files[0]) });
  return h("span", {}, h("button", { type: "button", class: cls, onclick: () => input.click() }, label), input);
}

// True when a key is going into a text field, so page-wide key shortcuts leave it alone.
export function typingIn(e: Event): boolean {
  const t = e.target as HTMLElement;
  return t.tagName === "TEXTAREA" || t.isContentEditable || (t.tagName === "INPUT" && (t as HTMLInputElement).type === "text");
}

// Calls onKey for plain single key presses on the page that aren't going into a text field or
// already handled (a focused preview handles its own). Returns the remover.
export function pageKeys(onKey: (key: string) => void): () => void {
  const listener = (e: KeyboardEvent) => {
    if (e.defaultPrevented || typingIn(e) || e.metaKey || e.ctrlKey || e.altKey || e.repeat || [...e.key].length !== 1) return;
    onKey(e.key.toLowerCase());
  };
  document.addEventListener("keydown", listener);
  return () => document.removeEventListener("keydown", listener);
}
