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

export function field(label: string, input: HTMLElement): HTMLLabelElement {
  return h("label", { class: "field" }, h("span", {}, label), input);
}

export function filePicker(accept: string, onFile: (f: File) => void, label = "or choose a file"): HTMLElement {
  const input = h("input", { type: "file", accept, hidden: true, onchange: () => input.files?.[0] && onFile(input.files[0]) });
  return h("span", {}, h("button", { class: "linkbtn dim", onclick: () => input.click() }, label), input);
}

export const seconds = (n: number) => `${n.toFixed(1)}s`;
