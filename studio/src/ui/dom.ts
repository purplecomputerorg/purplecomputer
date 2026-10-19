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

export function filePicker(accept: string, onFile: (f: File) => void, label = "or choose a file"): HTMLElement {
  const input = h("input", { type: "file", accept, hidden: true, onchange: () => input.files?.[0] && onFile(input.files[0]) });
  return h("span", {}, h("button", { class: "linkbtn dim", onclick: () => input.click() }, label), input);
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
