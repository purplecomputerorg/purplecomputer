// A preview you can play: Purple's screen that takes keys once clicked. Studio's room stage is one.
import { announceKey, browserKey } from "../keys";
import { h } from "./dom";
import { ScreenCanvas } from "./screen";

const REPEATS = new Set(["up", "down", "left", "right", "backspace"]);

// Covers a screen that isn't getting keys. Once someone has played with it (the screen marked
// "tried"), it shrinks to a small reminder, since they already know how.
export function tryHint(tag: "div" | "button", hint: string): HTMLElement {
  return h(tag, { class: "playable-hint", type: tag === "button" ? "button" : null },
    h("strong", {}, "Click to try it"), h("span", {}, hint), h("em", {}, "Click to type here"));
}

export class Playable {
  readonly element: HTMLElement;
  private screen: ScreenCanvas;

  constructor(draw: (ctx: CanvasRenderingContext2D) => void, onKey: (key: string) => void, hint: string) {
    this.screen = new ScreenCanvas(draw);
    this.element = this.screen.element;
    this.element.classList.add("playable");
    this.element.tabIndex = 0;
    // The hint covers the screen whenever it isn't getting keys; CSS hides it on focus.
    this.element.append(tryHint("div", hint));
    this.element.addEventListener("focus", () => this.element.classList.add("tried"));
    this.element.addEventListener("keydown", (e) => {
      const key = browserKey(e);
      if (!key || key === "escape" || key === "tab" || e.metaKey || e.ctrlKey || e.altKey) return;
      e.preventDefault();
      announceKey(key);
      if (!e.repeat || REPEATS.has(key)) onKey(key);
    });
  }

  redraw(): void {
    this.screen.redraw();
  }

  focus(): void {
    this.element.focus({ preventScroll: true });
  }

  dispose(): void {
    this.screen.dispose();
  }
}
