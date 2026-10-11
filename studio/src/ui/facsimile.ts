// The Art, Music, and Play rooms as Purple's canvas UI draws them (purple_tui/canvas/rooms/),
// laid out on its 1366x768 screen and playable: recognizable, not pixel exact.
import { ASDF_ROW, CANVAS_ALT, CANVAS_BG, CANVAS_HEIGHT, CANVAS_WIDTH, KEY_COLORS, QWERTY_ROW, ZXCV_ROW, generateRowGradient } from "@sdk/purple/art";
import { CORE_EMOJI, CORE_SYNONYMS } from "@sdk/purple/core";
import { GRID_ROWS, LETTER_KEYS, PERCUSSION_ROW } from "@sdk/purple/sounds";
import { paintCells } from "../photo";
import { playDrum, playGridKey, sayKey, sayPhrase } from "../sounds";
import { draft, type Theme } from "../state";
import { Playable } from "./playable";
import { FRAME, MONO, P, SANS, drawScreen, pill, rounded, text } from "./screen";

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

export interface MusicMode { instrument: string; sayLetters: boolean }

// Music: the letter rows play notes, the number row plays drums, or every key says its name.
export type MusicPreview = Playable & { press(key: string): void };

export function musicPreview(mode: () => MusicMode, onPress?: (key: string) => void): MusicPreview {
  let active: string | null = null;
  const draw = (ctx: CanvasRenderingContext2D) => drawScreen(ctx, { title: "♫ Music", right: "Arrows change key  ← →" }, () => {
    const { instrument, sayLetters } = mode();
    pill(ctx, sayLetters ? "Saying Letters" : `♫ ${instrument}`, 135, 114, true);
    text(ctx, "Key of C", FRAME.x + FRAME.w - 34, 114, 18, P.dim, "right");
    [PERCUSSION_ROW, ...GRID_ROWS].forEach((keys, r) => {
      const y = 210 + r * 108;
      keys.forEach((k, c) => {
        const x = 198 + c * 107.8;
        const on = k === active;
        if (on) rounded(ctx, x - 44, y - 44, 88, 88, 12, keyColor(k) ?? P.primary);
        if (sayLetters && k in draft.letters) rounded(ctx, x - 4, y + 30, 8, 8, 4, on ? P.on_primary : P.good);
        text(ctx, k === "/" ? "÷" : k.toUpperCase(), x, y, 32, on ? P.on_primary : P.dim, "center", MONO, 600);
      });
    });
    text(ctx, "Space: notes   Tab: say letters   Enter: instrument   Hold Enter: loop", 190, 622, 16, P.dim);
  });
  const press = (key: string) => {
    const { instrument, sayLetters } = mode();
    if (sayLetters && LETTER_KEYS.includes(key)) sayKey(key);
    else if (!sayLetters && PERCUSSION_ROW.includes(key)) playDrum(key);
    else if (sayLetters || !playGridKey(instrument, key)) return;
    active = key;
    onPress?.(key);
    preview.redraw();
  };
  const preview = Object.assign(new Playable(draw, press, "then press keys to hear them"), { press });
  return preview;
}

export interface PlayLine { ask: string; answer: string }

const isPicture = (s: string) => !/[a-z0-9]/i.test(s);

export function emojiFor(word: string): string | undefined {
  const w = word.toLowerCase();
  const alias = draft.synonyms.find((s) => s.alias === w)?.word ?? CORE_SYNONYMS[w];
  return draft.words.find((e) => e.word === w)?.emoji ?? CORE_EMOJI[w] ?? (alias ? emojiFor(alias) : undefined);
}

// Play's answer to a line, a word at a time: a word with a picture becomes its picture.
const answer = (line: string) => line.split(/\s+/).map((w) => emojiFor(w.replace(/[!?.,]+$/, "")) ?? w).join(" ");

// Play: type a word and press Enter. "say ..." or a line ending in ! is spoken, in the family's
// recording when it matches a phrase.
export function playPreview(seed: () => PlayLine[], tryLine: () => string): Playable {
  let history: PlayLine[] | null = null;
  let input = "";
  const lines = () => history ?? seed();
  const draw = (ctx: CanvasRenderingContext2D) => drawScreen(ctx, { title: "Play", right: "Arrows scroll  ↑ ↓" }, () => {
    const x = 135;
    const shown = lines().slice(-3);
    shown.forEach(({ ask, answer }, i) => {
      const y = 542 - (shown.length - i) * 96;
      const w = text(ctx, "Type", x, y, 19, P.muted, "left", MONO, 700);
      text(ctx, `→ ${ask}`, x + w + 10, y, 19, P.muted);
      if (isPicture(answer.replace(/\s/g, ""))) text(ctx, answer, x, y + 41, 34, P.text, "left", SANS);
      else text(ctx, answer, x, y + 38, 20, P.text);
    });
    const w = text(ctx, "Type →", x, 542, 21, P.accent, "left", MONO, 700);
    rounded(ctx, x + w + 14, 524, 372, 36, 7, P.field, P.line);
    const tw = text(ctx, input, x + w + 25, 542, 19, P.text);
    ctx.fillStyle = P.caret;
    ctx.fillRect(x + w + 25 + tw, 532, 10, 20);
    text(ctx, "Type a word, then press Enter", x + w + 25, 578, 16, P.dim);
    text(ctx, tryLine(), x, 620, 16, P.dim);
  });
  const preview = new Playable(draw, (key) => {
    if (key === "enter") {
      const said = input.match(/^\s*say\s+(.+)$/i)?.[1] ?? input.match(/^(.+)!\s*$/)?.[1];
      if (input.trim()) history = [...lines(), { ask: input, answer: answer(said ?? input) }];
      if (said) sayPhrase(said);
      input = "";
    } else if (key === "backspace") input = input.slice(0, -1);
    else if (key === "space") input += " ";
    else if (key.length === 1 && input.length < 32) input += key;
    preview.redraw();
  }, "then type a word and press Enter");
  return preview;
}
