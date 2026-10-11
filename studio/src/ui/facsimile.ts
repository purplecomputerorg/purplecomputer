// The Art room as Purple's canvas UI draws it (purple_tui/canvas/rooms/art_room.py), playable, for
// the one thing the real Purple can't show yet: a family's colors. Recognizable, not pixel exact.
import { ASDF_ROW, CANVAS_ALT, CANVAS_BG, CANVAS_HEIGHT, CANVAS_WIDTH, KEY_COLORS, QWERTY_ROW, ZXCV_ROW, generateRowGradient } from "@sdk/purple/art";
import { paintCells } from "../photo";
import { draft, type Theme } from "../state";
import { Playable } from "./playable";
import { FRAME, MONO, P, drawScreen, pill, rounded, text } from "./screen";

export const LETTER_ROWS = [
  ["qwerty", "Top row", QWERTY_ROW],
  ["asdf", "Middle row", ASDF_ROW],
  ["zxcv", "Bottom row", ZXCV_ROW],
] as const;

// The color a key paints with, in the family's colors when they have picked some.
export function keyColor(key: string, theme: Theme | null = draft.theme): string | undefined {
  const row = theme && LETTER_ROWS.find(([, , keys]) => (keys as readonly string[]).includes(key));
  return row ? generateRowGradient(theme.hues[row[0]], [...row[2]])[key] : KEY_COLORS[key];
}

// The checkerboard partner of a family's canvas color: the same small step Purple's own pair takes.
function alt(surface: string): string {
  if (surface === CANVAS_BG) return CANVAS_ALT;
  const n = parseInt(surface.slice(1), 16);
  const up = (v: number) => Math.min(255, v + 6).toString(16).padStart(2, "0");
  return `#${up(n >> 16)}${up((n >> 8) & 255)}${up(n & 255)}`;
}

const ART_CELL = 20;
const ART = { x: 122, y: 128 };

// Art: type to paint, arrows move, Space puts the pen down so arrows paint a trail.
export function artPreview(picture: () => string[][] | null): Playable {
  const painted = new Map<string, string>();
  let cx = 0, cy = 0, pen = false, last = KEY_COLORS.a;
  const paint = () => painted.set(`${cx},${cy}`, last);
  const step = (dx: number, dy: number) => {
    cx = (cx + dx + CANVAS_WIDTH) % CANVAS_WIDTH;
    cy = (cy + dy + CANVAS_HEIGHT) % CANVAS_HEIGHT;
  };
  const moves: Record<string, [number, number]> = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

  const draw = (ctx: CanvasRenderingContext2D) => drawScreen(ctx, { title: "Art", right: "Arrows move  ← ↑ ↓ →" }, () => {
    const surface = draft.theme?.surface ?? CANVAS_BG;
    // One pixel per cell, scaled up unsmoothed: crisp squares with no seams at any size.
    const grid = new OffscreenCanvas(CANVAS_WIDTH, CANVAS_HEIGHT);
    const g = grid.getContext("2d")!;
    const a = alt(surface);
    for (let y = 0; y < CANVAS_HEIGHT; y++)
      for (let x = 0; x < CANVAS_WIDTH; x++) {
        g.fillStyle = (x + y) % 2 ? a : surface;
        g.fillRect(x, y, 1, 1);
      }
    const cells = picture();
    if (cells) paintCells(g, cells, 1, null);
    for (const [at, color] of painted) {
      const [x, y] = at.split(",").map(Number);
      g.fillStyle = color;
      g.fillRect(x, y, 1, 1);
    }
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(grid, ART.x, ART.y, CANVAS_WIDTH * ART_CELL, CANVAS_HEIGHT * ART_CELL);
    rounded(ctx, ART.x + cx * ART_CELL, ART.y + cy * ART_CELL, ART_CELL, ART_CELL, 4, pen ? last : undefined, P.caret, 2.5);
    const x = pill(ctx, "Paint", 622, 105, true);
    text(ctx, "ABC", 622 + x + 20, 105, 17, P.muted, "left", MONO, 700);
    text(ctx, "Tab to write", FRAME.x + FRAME.w - 18, 105, 16, P.muted, "right");
    text(ctx, pen ? "Pen is down! Arrows paint a trail. Space lifts the pen." : "Type to paint! Every letter is a color. Space puts the pen down.", 119, 631, 16, P.dim);
  });

  const preview = new Playable(draw, (key) => {
    if (key in moves) {
      step(...moves[key]);
      if (pen) paint();
    } else if (key === "space") {
      pen = !pen;
      if (pen) paint();
    } else if (key === "backspace") {
      step(-1, 0);
      painted.delete(`${cx},${cy}`);
    } else if (key === "enter") {
      cx = 0;
      step(0, 1);
    } else if (keyColor(key)) {
      last = keyColor(key)!;
      paint();
      step(1, 0);
    }
    preview.redraw();
  }, "then type letters to paint");
  return preview;
}
