// A family's screen colors, all from one: Purple's own palette turned to a new base color with
// the same relationships between its colors, then nudged so every kind of text stays readable on
// it. A light base flips the palette, dark words on a light screen. Purple applies whatever ends
// up in theme.json (purple_tui/canvas/theme.py); the deriving happens only here.
import exported from "./export.json";
import { ASDF_ROW, CANVAS_BG, QWERTY_ROW, ROW_HUES, ZXCV_ROW, generateRowGradient, hslToHex } from "./art";

// The roles Purple's screen is drawn with (purple_tui/palette.py), plus the Art canvas.
export const ROLES = ["bg", "surface", "canvas", "tile", "field", "hair", "line", "primary", "on_primary", "accent", "text", "muted", "dim"] as const;
export type Role = (typeof ROLES)[number];
export type Palette = Record<Role, string>;
export type Hues = { qwerty: number; asdf: number; zxcv: number };
// Every row runs red to violet, each row a step lighter or darker than the last.
export type Rainbow = { violetFirst: boolean; darkTop: boolean };
// base: the one color; colors: any roles set by hand; hues: one per letter row, unless rainbow.
export interface Theme { base: string; colors: Partial<Palette>; hues: Hues; rainbow?: Rainbow }

const P = exported.screen.palette as Record<string, string>;
export const DEFAULT_PALETTE: Palette = Object.fromEntries(ROLES.map((r) => [r, r === "canvas" ? CANVAS_BG : P[r]])) as Palette;
export const DEFAULT_THEME: Theme = { base: DEFAULT_PALETTE.bg, colors: {}, hues: { ...ROW_HUES } };
// The screen's own surfaces; everything else is ink drawn on them.
const GROUND = new Set<Role>(["bg", "surface", "canvas", "tile", "field", "hair"]);
// Contrast each kind of ink needs against the stage (WCAG ratios).
const READABLE: [Role, number][] = [["text", 7], ["accent", 4.5], ["muted", 4.5], ["dim", 3], ["primary", 3], ["line", 1.8]];

type Hsl = [h: number, s: number, l: number];
const clamp = (v: number) => Math.min(1, Math.max(0, v));

export function toHsl(hex: string): Hsl {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  if (!d) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [(h * 60 + 360) % 360, s, l];
}

export function fromHsl([h, s, l]: Hsl): string {
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return "#" + [r, g, b].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, "0")).join("");
}

function luminance(hex: string): number {
  const ch = (i: number) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(1) + 0.7152 * ch(3) + 0.0722 * ch(5);
}

export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

// Moves color's lightness away from bg until the two reach the ratio, or as far as it can go.
function readable(color: string, bg: string, ratio: number): string {
  const [h, s, l0] = toHsl(color);
  const step = luminance(bg) > 0.18 ? -0.02 : 0.02;
  let l = l0;
  while (contrast(fromHsl([h, s, l]), bg) < ratio && l > 0 && l < 1) l = clamp(l + step);
  return fromHsl([h, s, l]);
}

export function derivePalette(base: string): Palette {
  const [hb, sb, lb] = toHsl(base);
  const [h0, s0, l0] = toHsl(DEFAULT_PALETTE.bg);
  const light = lb > 0.5;
  const turn = (role: Role): string => {
    const [h, s, l] = toHsl(DEFAULT_PALETTE[role]);
    // Panels stay dark enough (or light enough) for text to read on them, even when the base is a
    // bright middle color like pure red; the base itself still frames the screen.
    const ground = light ? Math.max(lb - (l - l0), 0.8) : Math.min(lb + (l - l0), 0.3);
    const lift = GROUND.has(role) ? ground : light ? 1 - l : l;
    return fromHsl([(h + hb - h0 + 360) % 360, clamp(s * (sb / s0)), clamp(lift)]);
  };
  const p = Object.fromEntries(ROLES.map((r) => [r, r === "bg" ? base : turn(r)])) as Palette;
  for (const [role, ratio] of READABLE) p[role] = readable(p[role], p.surface, ratio);
  p.on_primary = readable(p.on_primary, p.primary, 4.5);
  return p;
}

export function themePalette(t: Theme): Palette {
  const derived = t.base.toLowerCase() === DEFAULT_PALETTE.bg.toLowerCase() ? DEFAULT_PALETTE : derivePalette(t.base);
  return { ...derived, ...t.colors };
}

const VIOLET = 285;
const RAINBOW_LIGHTNESS = [0.72, 0.56, 0.4];

function rainbowColors({ violetFirst, darkTop }: Rainbow): Record<string, string> {
  return Object.fromEntries([QWERTY_ROW, ASDF_ROW, ZXCV_ROW].flatMap((keys, row) => keys.map((key, i) => {
    const t = i / (keys.length - 1);
    return [key, hslToHex((violetFirst ? 1 - t : t) * VIOLET, 0.75, RAINBOW_LIGHTNESS[darkTop ? 2 - row : row])];
  })));
}

export function rowColors({ hues, rainbow }: Theme): Record<string, string> {
  if (rainbow) return rainbowColors(rainbow);
  return { ...generateRowGradient(hues.qwerty, QWERTY_ROW), ...generateRowGradient(hues.asdf, ASDF_ROW), ...generateRowGradient(hues.zxcv, ZXCV_ROW) };
}

// content/theme.json, as purple_tui/canvas/theme.py reads it.
export function themeJson(t: Theme) {
  const { canvas, ...colors } = themePalette(t);
  return { colors, canvas, keys: rowColors(t) };
}
