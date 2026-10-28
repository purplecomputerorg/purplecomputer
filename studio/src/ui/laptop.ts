// A pretend laptop around the preview: a bezel, and below it a keyboard tilted away like a real
// one, with Purple's stickers on the keys. Tapping a key types it into whatever the screen holds;
// every key the screen gets presses down here, so the stickers and the screen visibly match.
// On a phone the keys are too small to hit, so a tap anywhere on the laptop opens the phone's own
// keyboard instead, and what's typed there goes to the screen the same way. A few big keys for the
// room (the tray) sit below for trying it without typing.
import { KEY_EVENT } from "../keys";
import { h } from "./dom";
import { hasSticker, sticker, stickerColors } from "./stickers";

// [key name sent to Purple, or "" for a key that does nothing here; label; width in key units]
type Key = [name: string, label: string, width?: number];
const chars = (s: string): Key[] => [...s].map((c) => [c, c]);
const ROWS: Key[][] = [
  [["escape", "esc"], ...chars("1234567890-="), ["backspace", "⌫", 1.6]],
  [["tab", "tab", 1.5], ...chars("qwertyuiop[]"), ["", "\\", 1.1]],
  [["", "caps", 1.8], ...chars("asdfghjkl;'"), ["enter", "enter", 1.8]],
  [["", "shift", 2.3], ...chars("zxcvbnm,./"), ["", "shift", 2.3]],
  [["", "fn"], ["", "ctrl"], ["", "alt"], ["space", "", 6.4], ["", "alt"], ["left", "←"], ["up", "↑"], ["down", "↓"], ["right", "→"]],
];
const BY_NAME = new Map(ROWS.flat().filter(([name]) => name).map((k) => [k[0], k]));
const NAMED: Record<string, string> = { Enter: "enter", Backspace: "backspace", Escape: "escape", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Tab: "tab" };

// A hand-drawn arrow from the note up into the sticker keys.
const ARROW = Object.assign(document.createElementNS("http://www.w3.org/2000/svg", "svg"), {
  innerHTML: '<path d="M28 56 C 14 56, 6 44, 6 6 M1 13 L6 5 L12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
});
ARROW.setAttribute("viewBox", "0 0 30 60");

// Each word rides a shallow arc, the way a handwritten line bows across a page.
const arched = (text: string) => {
  const words = text.split(" ");
  return h("span", {}, ...words.flatMap((w, i) => {
    const t = (2 * i) / (words.length - 1) - 1;
    return [h("span", { style: `transform: translateY(${(0.1 * t * t - 0.1).toFixed(2)}em) rotate(${(1.5 * t).toFixed(1)}deg)` }, w), " "];
  }));
};

export class Laptop {
  readonly element: HTMLElement;
  readonly screen = h("div", { class: "laptop-screen" });
  private keyboard = h("div", { class: "laptop-keys" });
  readonly tray = h("div", { class: "tray-keys" });
  private trayNames: string[] = [];
  private keys = new Map<string, HTMLElement[]>();
  private painted = "";
  // Holds one space, so a phone keyboard's backspace has something to delete and shows up.
  private typing = h("input", {
    class: "laptop-typing", type: "text", value: " ", autocomplete: "off", autocapitalize: "none", spellcheck: false,
    enterkeyhint: "go", "aria-label": "Type to Purple", tabindex: -1,
  });

  constructor(private tap: (key: string) => void) {
    this.element = h("div", { class: "laptop" },
      h("div", { class: "laptop-lid" }, h("i", { class: "laptop-camera" }), this.screen),
      h("div", { class: "laptop-base" }, h("div", { class: "laptop-deck" }, this.keyboard)),
      h("p", { class: "sticker-callout" }, ARROW, arched("These stickers come in the box. They go on your keyboard.")),
      this.typing,
      h("button", { type: "button", class: "laptop-touch", "aria-label": "Type with your keyboard", onclick: () => this.typing.focus({ preventScroll: true }) }));
    this.typing.setAttribute("autocorrect", "off");
    this.typing.addEventListener("keydown", (e) => {
      const name = NAMED[e.key];
      if (!name || name === "backspace") return;
      e.preventDefault();
      this.type(name);
    });
    this.typing.addEventListener("input", () => {
      const v = this.typing.value;
      if (!v) this.type("backspace");
      for (const c of v.slice(1)) this.type(c === " " ? "space" : c.toLowerCase());
      this.typing.value = " ";
    });
    this.paint();
    addEventListener(KEY_EVENT, (e) => this.press((e as CustomEvent<string>).detail));
  }

  // Redraws the stickers when the family's colors or the tray's keys change.
  paint(tray = this.trayNames): void {
    const colors = stickerColors();
    const painted = JSON.stringify([colors, tray]);
    if (painted === this.painted) return;
    this.painted = painted;
    this.trayNames = tray;
    this.keys.clear();
    const key = ([name, label, width = 1]: Key, cls: string) => {
      const el = h("button", {
        type: "button", class: `${cls}${name ? "" : " idle"}`, style: `flex:${width}`, tabindex: -1, "aria-label": label || name,
        onmousedown: (e: Event) => e.preventDefault(),
        onclick: () => name && this.type(name),
      }, hasSticker(name) ? sticker(name, colors) : h("span", {}, label || name));
      if (name) this.keys.set(name, [...(this.keys.get(name) ?? []), el]);
      return el;
    };
    this.keyboard.replaceChildren(...ROWS.map((row) => h("div", { class: "laptop-row" }, ...row.map((k) => key(k, "laptop-key")))));
    this.tray.replaceChildren(...tray.map((name) => key([name, BY_NAME.get(name)?.[1] ?? name], "laptop-key tray-key")));
  }

  type(key: string): void {
    this.tap(key);
    this.press(key);
  }

  press(key: string): void {
    for (const el of this.keys.get(key === "+" ? "=" : key) ?? []) {
      el.classList.remove("down");
      void el.offsetWidth;
      el.classList.add("down");
    }
  }
}
