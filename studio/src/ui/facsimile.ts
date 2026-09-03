import { paintCells } from "../photo";
import { APP_BG_DARK, CANVAS_HEIGHT, CANVAS_WIDTH, DEFAULT_BG_DARK, GUTTER_BG_DARK, VIEWPORT_HEIGHT, VIEWPORT_WIDTH } from "../purple/art";
import { h } from "./dom";

export interface FrameColors { background: string; surface: string }
const DEFAULT_COLORS: FrameColors = { background: APP_BG_DARK, surface: DEFAULT_BG_DARK };
const PRIMARY = "#9b7bc4";
const MUTED = "#8a78a8";
const PAD = 1;

// A faithful Art room frame: header row, gutter checkerboard, the 132 by 25 canvas, hint bar.
// Cells are drawn `cellPx` wide and twice as tall, the same shape the terminal uses.
export function artFrame(cells: string[][] | null, colors: FrameColors = DEFAULT_COLORS, cellPx = 5): HTMLCanvasElement {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const cols = VIEWPORT_WIDTH + 2 * PAD;
  const rows = VIEWPORT_HEIGHT + 2 * PAD;
  const canvas = h("canvas", { class: "frame", width: cols * cellPx * dpr, height: rows * cellPx * 2 * dpr });
  canvas.style.aspectRatio = `${cols} / ${rows * 2}`;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(dpr, dpr);
  const cw = cellPx;
  const ch = cellPx * 2;
  const cell = (x: number, y: number, color: string, w = 1, hgt = 1) => {
    ctx.fillStyle = color;
    ctx.fillRect((x + PAD) * cw, (y + PAD) * ch, w * cw, hgt * ch);
  };

  ctx.fillStyle = colors.background;
  ctx.fillRect(0, 0, cols * cw, rows * ch);
  ctx.strokeStyle = PRIMARY;
  ctx.lineWidth = Math.max(1, cellPx / 3);
  ctx.strokeRect(PAD * cw - cw / 2, PAD * ch - ch / 4, VIEWPORT_WIDTH * cw + cw, VIEWPORT_HEIGHT * ch + ch / 2);

  cell(0, 0, colors.surface, VIEWPORT_WIDTH);
  for (let x = 0; x < VIEWPORT_WIDTH; x++) {
    const g = GUTTER_BG_DARK[x % 2];
    cell(x, 1, g);
    cell(x, VIEWPORT_HEIGHT - 2, g);
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

  ctx.font = `${cellPx * 1.8}px ui-monospace, Menlo, monospace`;
  ctx.textBaseline = "middle";
  const text = (t: string, x: number, y: number, color: string) => {
    ctx.fillStyle = color;
    ctx.fillText(t, (x + PAD) * cw, (y + PAD + 0.5) * ch);
  };
  const legend = ["#DF7070", "#DFC070", "#7090DF"];
  cell(60, 0, "#ffffff", 5);
  legend.forEach((c, i) => cell(61 + i, 0, c));
  text("ABC", 67, 0, MUTED);
  text("Tab to write", 96, 0, MUTED);
  const hint = "Type to paint! Every letter is a color. Space puts the pen down.";
  text(hint, Math.floor((VIEWPORT_WIDTH - hint.length) / 2), VIEWPORT_HEIGHT - 1, MUTED);
  return canvas;
}
