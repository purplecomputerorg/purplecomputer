// Purple's screen as the canvas UI draws it (purple_tui/canvas/app.py at 1366x768): the
// computer's name and the room title above a rounded stage, the keyboard note and the Esc pill
// below. Every preview on the right goes through here, so they all look like the laptop.
import { PURPLE } from "@sdk";
import { h } from "./dom";

export const P = PURPLE.screen.palette;
export const W = 1366;
export const H = 768;
export const FRAME = { x: 101, y: 74, w: 1164, h: 588 };
export const MONO = `"IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace`;
export const SANS = `"IBM Plex Sans", Figtree, Inter, system-ui, sans-serif`;
const EXPAND_ICON = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>`;

export interface Chrome {
  title: string;
  right?: string;
  // A family's proposed theme: the ground around the stage, and the stage itself.
  ground?: string;
  stage?: string;
}

type Align = CanvasTextAlign;

export function text(ctx: CanvasRenderingContext2D, t: string, x: number, y: number, px: number, color: string,
                     align: Align = "left", font = MONO, weight = 400): number {
  ctx.font = `${weight} ${px}px ${font}`;
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "middle";
  ctx.fillText(t, x, y);
  return ctx.measureText(t).width;
}

// Shrinks px until t fits in maxWidth.
export function fit(ctx: CanvasRenderingContext2D, t: string, px: number, maxWidth: number, font = SANS, weight = 600): number {
  for (; px > 12; px -= 2) {
    ctx.font = `${weight} ${px}px ${font}`;
    if (ctx.measureText(t).width <= maxWidth) break;
  }
  return px;
}

export function rounded(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, hgt: number, r: number,
                        fill?: string, stroke?: string, lineWidth = 1): void {
  ctx.beginPath();
  ctx.roundRect(x, y, w, hgt, r);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth; ctx.stroke(); }
}

export function pill(ctx: CanvasRenderingContext2D, label: string, x: number, y: number, on: boolean, px = 17): number {
  ctx.font = `700 ${px}px ${MONO}`;
  const w = ctx.measureText(label).width + px * 1.4;
  rounded(ctx, x, y - px * 0.95, w, px * 1.9, 7, on ? P.primary : undefined, on ? undefined : P.hair);
  text(ctx, label, x + w / 2, y, px, on ? P.on_primary : P.muted, "center", MONO, 700);
  return w;
}

// The whole screen; body draws inside the stage, clipped to its rounded corners.
export function drawScreen(ctx: CanvasRenderingContext2D, chrome: Chrome, body: (ctx: CanvasRenderingContext2D) => void): void {
  ctx.fillStyle = chrome.ground ?? P.bg;
  ctx.fillRect(0, 0, W, H);
  text(ctx, "My Purple Computer", FRAME.x, 44, 19, P.muted);
  text(ctx, chrome.title, W / 2, 44, 19, P.accent, "center", MONO, 700);
  ctx.save();
  rounded(ctx, FRAME.x, FRAME.y, FRAME.w, FRAME.h, 10, chrome.stage ?? P.surface);
  ctx.clip();
  body(ctx);
  ctx.restore();
  rounded(ctx, FRAME.x, FRAME.y, FRAME.w, FRAME.h, 10, undefined, P.line, 1.5);
  const y = H - 34;
  text(ctx, "Keyboard only, on purpose", FRAME.x, y, 16, P.dim);
  ctx.font = `400 16px ${MONO}`;
  const escW = ctx.measureText("Esc").width + 22;
  rounded(ctx, W / 2 - escW / 2, y - 15, escW, 30, 7, undefined, P.hair);
  text(ctx, "Esc", W / 2, y, 16, P.muted, "center");
  if (chrome.right) text(ctx, chrome.right, FRAME.x + FRAME.w, y, 16, P.dim, "right");
}

// A preview canvas that draws at its displayed size times devicePixelRatio, so it stays sharp
// at any width and in full screen. Call redraw() when what it shows changes.
export class ScreenCanvas {
  readonly element: HTMLElement;
  readonly canvas = h("canvas", { class: "screen" });
  private frame = 0;
  private observer: ResizeObserver;

  constructor(private draw: (ctx: CanvasRenderingContext2D) => void, focusable = false) {
    const full = h("button", { class: "screen-full", title: "Full screen", "aria-label": "Full screen" });
    full.innerHTML = EXPAND_ICON;
    full.addEventListener("click", (e) => {
      e.stopPropagation();
      if (document.fullscreenElement) void document.exitFullscreen();
      else void this.element.requestFullscreen?.().then(() => focusable && this.element.focus({ preventScroll: true }));
    });
    this.element = h("div", { class: "screen-wrap" }, this.canvas, full);
    this.observer = new ResizeObserver(() => this.redraw());
    this.observer.observe(this.canvas);
    this.redraw();
  }

  redraw(): void {
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(() => {
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round((this.canvas.clientWidth || 480) * dpr));
      const height = Math.round((width * H) / W);
      if (this.canvas.width !== width) { this.canvas.width = width; this.canvas.height = height; }
      const ctx = this.canvas.getContext("2d")!;
      ctx.setTransform(width / W, 0, 0, height / H, 0, 0);
      this.draw(ctx);
    });
  }

  dispose(): void {
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
  }
}

// For previews that are drawn once per render of the page.
export function screen(chrome: Chrome, body: (ctx: CanvasRenderingContext2D) => void): HTMLElement {
  return new ScreenCanvas((ctx) => drawScreen(ctx, chrome, body)).element;
}
