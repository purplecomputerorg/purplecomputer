// The Art, Music, and Play rooms as Purple's canvas UI draws them (purple_tui/canvas/rooms/),
// laid out on its 1366x768 screen: recognizable, not pixel exact.
import { CANVAS_ALT, CANVAS_BG, CANVAS_HEIGHT, CANVAS_WIDTH, KEY_COLORS } from "@sdk/purple/art";
import { GRID_ROWS, PERCUSSION_ROW } from "@sdk/purple/sounds";
import { paintCells } from "../photo";
import { FRAME, MONO, P, SANS, pill, rounded, screen, text } from "./screen";

export interface FrameColors { background: string; surface: string }
export const DEFAULT_COLORS: FrameColors = { background: P.bg, surface: CANVAS_BG };

// The checkerboard partner of a family's canvas color: the same small step Purple's own pair takes.
function alt(surface: string): string {
  if (surface === CANVAS_BG) return CANVAS_ALT;
  const n = parseInt(surface.slice(1), 16);
  const up = (v: number) => Math.min(255, v + 6).toString(16).padStart(2, "0");
  return `#${up(n >> 16)}${up((n >> 8) & 255)}${up(n & 255)}`;
}

const ART_CELL = 20;
const ART = { x: 122, y: 128 };

export function artFrame(cells: string[][] | null, colors: FrameColors = DEFAULT_COLORS) {
  return screen({ title: "Art", right: "Arrows move  ← ↑ ↓ →", ground: colors.background }, (ctx) => {
    // One pixel per cell, scaled up unsmoothed: crisp squares with no seams at any size.
    const grid = new OffscreenCanvas(CANVAS_WIDTH, CANVAS_HEIGHT);
    const g = grid.getContext("2d")!;
    const a = alt(colors.surface);
    for (let y = 0; y < CANVAS_HEIGHT; y++)
      for (let x = 0; x < CANVAS_WIDTH; x++) {
        g.fillStyle = (x + y) % 2 ? a : colors.surface;
        g.fillRect(x, y, 1, 1);
      }
    if (cells) paintCells(g, cells, 1, null);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(grid, ART.x, ART.y, CANVAS_WIDTH * ART_CELL, CANVAS_HEIGHT * ART_CELL);
    const x = pill(ctx, "Paint", 622, 105, true);
    text(ctx, "ABC", 622 + x + 20, 105, 17, P.muted, "left", MONO, 700);
    text(ctx, "Tab to write", FRAME.x + FRAME.w - 18, 105, 16, P.muted, "right");
    text(ctx, "Type to paint! Every letter is a color. Space puts the pen down.", 119, 631, 16, P.dim);
  });
}

export interface MusicFrameOptions { instrument: string; sayLetters?: boolean; activeKey?: string | null }

export function musicFrame({ instrument, sayLetters = false, activeKey = null }: MusicFrameOptions, colors: FrameColors = DEFAULT_COLORS) {
  return screen({ title: "♫ Music", right: "Arrows change key  ← →", ground: colors.background }, (ctx) => {
    pill(ctx, sayLetters ? "Saying Letters" : `♫ ${instrument}`, 135, 114, true);
    text(ctx, "Key of C", FRAME.x + FRAME.w - 34, 114, 18, P.dim, "right");
    [PERCUSSION_ROW, ...GRID_ROWS].forEach((keys, r) => {
      const y = 210 + r * 108;
      keys.forEach((k, c) => {
        const x = 198 + c * 107.8;
        const shown = k === "/" ? "÷" : k.toUpperCase();
        const on = k === activeKey;
        if (on) rounded(ctx, x - 44, y - 44, 88, 88, 12, KEY_COLORS[k] ?? P.primary);
        text(ctx, shown, x, y, 32, on ? P.on_primary : P.dim, "center", MONO, 600);
      });
    });
    text(ctx, "Space: notes   Tab: say letters   Enter: instrument   Hold Enter: loop", 190, 622, 16, P.dim);
  });
}

export interface PlayLine { ask: string; answer: string }

const isPicture = (s: string) => !/[a-z0-9]/i.test(s);

export function playFrame(lines: PlayLine[], colors: FrameColors = DEFAULT_COLORS) {
  return screen({ title: "Play", right: "Arrows scroll  ↑ ↓", ground: colors.background }, (ctx) => {
    const x = 135;
    const shown = lines.slice(-3);
    shown.forEach(({ ask, answer }, i) => {
      const y = 542 - (shown.length - i) * 96;
      const w = text(ctx, "Type", x, y, 19, P.muted, "left", MONO, 700);
      text(ctx, `→ ${ask}`, x + w + 10, y, 19, P.muted);
      if (isPicture(answer)) text(ctx, answer, x, y + 41, 34, P.text, "left", SANS);
      else text(ctx, answer, x, y + 38, 20, P.text);
    });
    const w = text(ctx, "Type →", x, 542, 21, P.accent, "left", MONO, 700);
    rounded(ctx, x + w + 14, 524, 372, 36, 7, P.field, P.line);
    ctx.fillStyle = P.caret;
    ctx.fillRect(x + w + 25, 532, 10, 20);
    text(ctx, "Type a word, then press Enter", x + w + 25, 578, 16, P.dim);
    text(ctx, "Try: cat * 5  •  say yellow", x, 620, 16, P.dim);
  });
}
