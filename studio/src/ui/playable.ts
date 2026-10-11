// A preview you can play: Purple's screen that takes keys once clicked, the same way in the side
// panel and in full screen. Every preview on the right is one of these.
import { h } from "./dom";
import { ScreenCanvas } from "./screen";

export function browserKey(e: KeyboardEvent): string | null {
  const map: Record<string, string> = { " ": "space", Enter: "enter", Backspace: "backspace", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
  if (e.key in map) return map[e.key];
  return [...e.key].length === 1 ? e.key.toLowerCase() : null;
}

const REPEATS = new Set(["up", "down", "left", "right", "backspace"]);

export class Playable {
  readonly element: HTMLElement;
  private screen: ScreenCanvas;

  constructor(draw: (ctx: CanvasRenderingContext2D) => void, onKey: (key: string) => void, hint: string) {
    this.screen = new ScreenCanvas(draw, true);
    this.element = this.screen.element;
    this.element.classList.add("playable");
    this.element.tabIndex = 0;
    // The hint covers the screen whenever it isn't getting keys; CSS hides it on focus.
    this.element.append(h("div", { class: "playable-hint" }, h("strong", {}, "Click to try it"), h("span", {}, hint)));
    this.element.addEventListener("keydown", (e) => {
      const key = browserKey(e);
      if (!key || e.metaKey || e.ctrlKey || e.altKey) return;
      e.preventDefault();
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
