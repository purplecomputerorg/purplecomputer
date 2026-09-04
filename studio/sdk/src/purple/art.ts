// Art room facts come from export.json (written by scripts/export_studio.py from purple_tui itself).
// Only the two functions Studio needs live, fit_to_canvas and generate_row_gradient, are ported,
// and tests/art.test.ts checks both against the export.
import exported from "./export.json";

const art = exported.art;

export const VIEWPORT_WIDTH = art.viewport[0];
export const VIEWPORT_HEIGHT = art.viewport[1];
export const CANVAS_WIDTH = art.canvas[0];
export const CANVAS_HEIGHT = art.canvas[1];
export const CELL_ASPECT = art.cell_aspect;

export const APP_BG_DARK = art.app_bg;
export const DEFAULT_BG_DARK = art.bg_dark;
export const DEFAULT_BG_LIGHT = art.bg_light;
export const GUTTER_BG_DARK = art.gutter as [string, string];
export const KEY_COLORS: Record<string, string> = art.key_colors;

export const QWERTY_ROW = [..."qwertyuiop[]"];
export const ASDF_ROW = [..."asdfghjkl;'"];
export const ZXCV_ROW = [..."zxcvbnm,./"];
export const ROW_HUES = { qwerty: 0, asdf: 50, zxcv: 220 } as const;

const hex2 = (v: number) => Math.trunc(v * 255).toString(16).toUpperCase().padStart(2, "0");

// colorsys.hls_to_rgb, then int() truncation like the Python.
export function hslToHex(h: number, s: number, l: number): string {
  const hue = h / 360;
  if (s === 0) return `#${hex2(l)}${hex2(l)}${hex2(l)}`;
  const m2 = l <= 0.5 ? l * (1 + s) : l + s - l * s;
  const m1 = 2 * l - m2;
  const v = (t: number) => {
    t = ((t % 1) + 1) % 1;
    if (t < 1 / 6) return m1 + (m2 - m1) * t * 6;
    if (t < 0.5) return m2;
    if (t < 2 / 3) return m1 + (m2 - m1) * (2 / 3 - t) * 6;
    return m1;
  };
  return `#${hex2(v(hue + 1 / 3))}${hex2(v(hue))}${hex2(v(hue - 1 / 3))}`;
}

export function generateRowGradient(hue: number, keys: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  keys.forEach((key, i) => {
    const lightness = 0.8 - (i / Math.max(keys.length - 1, 1)) * 0.6;
    out[key] = hslToHex(hue, 0.75, lightness);
  });
  return out;
}

export function fitToCanvas(width: number, height: number): [cols: number, rows: number] {
  const scale = Math.min(CANVAS_WIDTH / width, (CANVAS_HEIGHT * CELL_ASPECT) / height);
  return [Math.max(1, pyRound(width * scale)), Math.max(1, pyRound((height * scale) / CELL_ASPECT))];
}

// Python's round() is banker's rounding.
function pyRound(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

export function canvasOrigin(cols: number, rows: number): [x0: number, y0: number] {
  return [Math.floor((CANVAS_WIDTH - cols) / 2), Math.floor((CANVAS_HEIGHT - rows) / 2)];
}

export type PaintOp = [x: number, y: number, hex: string];

export function cellsToOps(cells: string[][]): PaintOp[] {
  const [x0, y0] = canvasOrigin(cells[0].length, cells.length);
  return cells.flatMap((row, cy) => row.map((hex, cx): PaintOp => [x0 + cx, y0 + cy, hex]));
}
