// Ported from purple_tui/rooms/art_room.py, purple_tui/art_config.py, and tools/photo_to_art.py.
// Keep numerically identical to the Python: tests/art.test.ts checks against fixtures exported from it.

export const VIEWPORT_WIDTH = 134;
export const VIEWPORT_HEIGHT = 29;
const GUTTER = 1;
const ART_HEADER_ROWS = 1;
const ART_HINT_BAR_ROWS = 1;

export const CANVAS_WIDTH = VIEWPORT_WIDTH - 2 * GUTTER;
export const CANVAS_HEIGHT = VIEWPORT_HEIGHT - ART_HEADER_ROWS - ART_HINT_BAR_ROWS - 2 * GUTTER;
export const CELL_ASPECT = 2;

export const DEFAULT_BG_DARK = "#2a1845";
export const DEFAULT_BG_LIGHT = "#e8daf0";
export const APP_BG_DARK = "#1e1033";
export const GUTTER_BG_DARK = ["#2F1D4C", "#382358"] as const;
export const TEXT_MUTED_DARK = "#8a78a8";

export const GRAYSCALE: Record<string, string> = {
  "1": "#FFFFFF", "2": "#E8E8E8", "3": "#D0D0D0", "4": "#B8B8B8", "5": "#A0A0A0", "6": "#888888",
  "7": "#707070", "8": "#585858", "9": "#404040", "0": "#282828", "-": "#101010", "=": "#000000", "+": "#000000",
};
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

export function keyColors(hues = ROW_HUES): Record<string, string> {
  return {
    ...GRAYSCALE,
    ...generateRowGradient(hues.qwerty, QWERTY_ROW),
    ...generateRowGradient(hues.asdf, ASDF_ROW),
    ...generateRowGradient(hues.zxcv, ZXCV_ROW),
  };
}

export const KEY_COLORS = keyColors();

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
