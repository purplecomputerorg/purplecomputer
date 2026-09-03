import { paintCells } from "../photo";
import { APP_BG_DARK, CANVAS_HEIGHT, CANVAS_WIDTH, DEFAULT_BG_DARK, GUTTER_BG_DARK, VIEWPORT_HEIGHT, VIEWPORT_WIDTH } from "../purple/art";
import { GRID_ROWS, PERCUSSION_ROW } from "../purple/sounds";
import { h } from "./dom";

export interface FrameColors { background: string; surface: string }
export const DEFAULT_COLORS: FrameColors = { background: APP_BG_DARK, surface: DEFAULT_BG_DARK };
const PRIMARY = "#9b7bc4";
const MUTED = "#8a78a8";
const WHITE = "#f4eefc";
const PAD = 1;

interface Pen {
  cell: (x: number, y: number, color: string, w?: number, hgt?: number) => void;
  text: (t: string, x: number, y: number, color: string, bold?: boolean) => void;
  ctx: CanvasRenderingContext2D;
  cw: number;
  ch: number;
}

// The shared viewport: app background, heavy border, then whatever the room draws inside.
// Cells are `cellPx` wide and twice as tall, the same shape as the terminal's.
function frame(colors: FrameColors, draw: (pen: Pen) => void, cellPx = 5): HTMLCanvasElement {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const cols = VIEWPORT_WIDTH + 2 * PAD;
  const rows = VIEWPORT_HEIGHT + 2 * PAD;
  const canvas = h("canvas", { class: "frame", width: cols * cellPx * dpr, height: rows * cellPx * 2 * dpr });
  canvas.style.aspectRatio = `${cols} / ${rows * 2}`;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(dpr, dpr);
  const cw = cellPx;
  const ch = cellPx * 2;
  ctx.fillStyle = colors.background;
  ctx.fillRect(0, 0, cols * cw, rows * ch);
  ctx.strokeStyle = PRIMARY;
  ctx.lineWidth = Math.max(1, cellPx / 3);
  ctx.strokeRect(PAD * cw - cw / 2, PAD * ch - ch / 4, VIEWPORT_WIDTH * cw + cw, VIEWPORT_HEIGHT * ch + ch / 2);
  ctx.textBaseline = "middle";
  draw({
    ctx, cw, ch,
    cell: (x, y, color, w = 1, hgt = 1) => {
      ctx.fillStyle = color;
      ctx.fillRect((x + PAD) * cw, (y + PAD) * ch, w * cw, hgt * ch);
    },
    text: (t, x, y, color, bold = false) => {
      ctx.font = `${bold ? "600 " : ""}${cellPx * 1.8}px ui-monospace, Menlo, monospace`;
      ctx.fillStyle = color;
      ctx.fillText(t, (x + PAD) * cw, (y + PAD + 0.5) * ch);
    },
  });
  return canvas;
}

export function artFrame(cells: string[][] | null, colors: FrameColors = DEFAULT_COLORS): HTMLCanvasElement {
  return frame(colors, ({ cell, text, ctx, cw, ch }) => {
    cell(0, 0, colors.surface, VIEWPORT_WIDTH);
    for (let x = 0; x < VIEWPORT_WIDTH; x++) {
      cell(x, 1, GUTTER_BG_DARK[x % 2]);
      cell(x, VIEWPORT_HEIGHT - 2, GUTTER_BG_DARK[x % 2]);
    }
    for (let y = 2; y < VIEWPORT_HEIGHT - 2; y++) {
      cell(0, y, GUTTER_BG_DARK[y % 2]);
      cell(VIEWPORT_WIDTH - 1, y, GUTTER_BG_DARK[y % 2]);
    }
    cell(1, 2, colors.surface, CANVAS_WIDTH, CANVAS_HEIGHT);
    if (cells) {
      ctx.save();
      ctx.translate((1 + PAD) * cw, (2 + PAD) * ch);
      paintCells(ctx, cells, cw, colors.surface);
      ctx.restore();
    }
    cell(60, 0, "#ffffff", 5);
    ["#DF7070", "#DFC070", "#7090DF"].forEach((c, i) => cell(61 + i, 0, c));
    text("ABC", 67, 0, MUTED);
    text("Tab to write", 96, 0, MUTED);
    const hint = "Type to paint! Every letter is a color. Space puts the pen down.";
    text(hint, Math.floor((VIEWPORT_WIDTH - hint.length) / 2), VIEWPORT_HEIGHT - 1, MUTED);
  });
}

export interface MusicFrameOptions { instrument: string; sayLetters?: boolean; activeKey?: string | null }

export function musicFrame({ instrument, sayLetters = false, activeKey = null }: MusicFrameOptions, colors: FrameColors = DEFAULT_COLORS): HTMLCanvasElement {
  return frame(colors, ({ cell, text }) => {
    const label = ` ${instrument} `;
    const pillX = Math.floor((VIEWPORT_WIDTH - label.length - 13) / 2);
    if (sayLetters) {
      text(label, pillX, 1, MUTED);
      cell(pillX + label.length + 1, 1, PRIMARY, 13);
      text(" Say Letters ", pillX + label.length + 1, 1, APP_BG_DARK, true);
    } else {
      cell(pillX, 1, PRIMARY, label.length);
      text(label, pillX, 1, APP_BG_DARK, true);
      text("Say Letters", pillX + label.length + 2, 1, MUTED);
    }
    text("← Key C →", 2, 1, MUTED);
    text("Tab to say letters", VIEWPORT_WIDTH - 22, 1, MUTED);
    const rows = [PERCUSSION_ROW, ...GRID_ROWS];
    rows.forEach((keys, r) => {
      const y = 6 + r * 5;
      keys.forEach((k, c) => {
        const x = 7 + c * 13;
        const shown = k === "/" ? "÷" : k.toUpperCase();
        if (k === activeKey) {
          cell(x - 1, y, PRIMARY, 3);
          text(shown, x, y, APP_BG_DARK, true);
        } else text(shown, x, y, r === 0 ? MUTED : WHITE, true);
      });
    });
    const hint = "Space: show notes   Arrows: switch key   Enter: instrument   Hold Enter: loop";
    text(hint, Math.floor((VIEWPORT_WIDTH - hint.length) / 2), VIEWPORT_HEIGHT - 1, MUTED);
  });
}

export interface PlayLine { ask: string; answer: string }

export function playFrame(lines: PlayLine[], colors: FrameColors = DEFAULT_COLORS): HTMLCanvasElement {
  return frame(colors, ({ cell, text }) => {
    let y = 2;
    for (const { ask, answer } of lines.slice(-5)) {
      text("Ask →", 2, y, PRIMARY, true);
      text(ask, 8, y, WHITE);
      text("→ " + answer, 6, y + 1, WHITE);
      y += 3;
    }
    text("Ask →", 2, VIEWPORT_HEIGHT - 4, PRIMARY, true);
    cell(8, VIEWPORT_HEIGHT - 4, "#d7e8a0");
    const hint = "Try: say hi  (or hello!, both speak aloud)  •  red sun";
    text(hint, Math.floor((VIEWPORT_WIDTH - hint.length) / 2), VIEWPORT_HEIGHT - 1, MUTED);
  });
}
