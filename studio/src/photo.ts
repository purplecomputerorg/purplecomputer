import dinosaur from "./assets/dinosaur.svg";
import dog from "./assets/dog.jpg";
import saturn from "./assets/saturn.jpg";
import starryNight from "./assets/starry-night.jpg";
import type { Keepable } from "./state";
import { CANVAS_BG, CANVAS_HEIGHT, CANVAS_WIDTH, CELL_ASPECT, canvasOrigin, cellsToOps, fitToCanvas, type ArtPicture, type LetterOp, type PaintOp } from "@sdk/purple/art";
import { DEFAULT_PALETTE, contrast } from "@sdk/purple/theme";

// crop: the part of the photo on the screen, in its own pixels and the Art canvas's shape; none is the whole photo.
// words: written over the photo in Art's letters; x and y are their top left in the photo's cells, centered near the bottom until moved.
export interface Crop { x: number; y: number; w: number; h: number }
export interface Words { text: string; x?: number; y?: number }
// shelfId: the picture on the family's shelf (shelf.ts) it was painted from.
export interface Picture extends Keepable { name: string; title?: string; cells: string[][]; ops: PaintOp[]; sourceUrl: string; bitmap: ImageBitmap; crop?: Crop; words?: Words; shelfId?: string }

const hex = (r: number, g: number, b: number) =>
  "#" + [r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");

// Box-filter downsample: every source pixel contributes to exactly one cell, weighted by overlap.
// Python uses Pillow's LANCZOS; at these shrink ratios the two agree to within a shade.
export function downsample(img: ImageData, cols: number, rows: number): string[][] {
  const { width, height, data } = img;
  const cells: string[][] = [];
  for (let cy = 0; cy < rows; cy++) {
    const y0 = (cy * height) / rows;
    const y1 = ((cy + 1) * height) / rows;
    const row: string[] = [];
    for (let cx = 0; cx < cols; cx++) {
      const x0 = (cx * width) / cols;
      const x1 = ((cx + 1) * width) / cols;
      let r = 0, g = 0, b = 0, w = 0;
      for (let y = Math.floor(y0); y < Math.ceil(y1); y++) {
        const wy = Math.min(y + 1, y1) - Math.max(y, y0);
        for (let x = Math.floor(x0); x < Math.ceil(x1); x++) {
          const wt = wy * (Math.min(x + 1, x1) - Math.max(x, x0));
          const i = (y * width + x) * 4;
          r += data[i] * wt;
          g += data[i + 1] * wt;
          b += data[i + 2] * wt;
          w += wt;
        }
      }
      row.push(hex(r / w, g / w, b / w));
    }
    cells.push(row);
  }
  return cells;
}

// A picture's name is its file name in the pack; Purple shows its title as typed, or else the name tidied.

// A data URL rather than an object URL, so the photo is still there when the draft is recalled.
export const dataUrl = (blob: Blob) => new Promise<string>((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(r.result as string);
  r.onerror = () => reject(r.error);
  r.readAsDataURL(blob);
});

export async function pictureFromSrc(src: string, name: string): Promise<Picture> {
  const img = new Image();
  img.src = src;
  await img.decode();
  return pictureFromBitmap(await createImageBitmap(img), name, src);
}

// Studio's examples, painted the same way as a family's pictures. One goes in the pack only if
// the family adds it.
export interface Example { name: string; src: string; alt: string; credit?: string }
export const EXAMPLES: Example[] = [
  { name: "dog", src: dog, alt: "A black dog looking up" },
  { name: "dinosaur", src: dinosaur, alt: "A dinosaur to color in" },
  { name: "saturn", src: saturn, alt: "Saturn and its rings", credit: "NASA, from the Cassini spacecraft" },
  { name: "starry-night", src: starryNight, alt: "A swirling night sky over a sleepy village", credit: "Vincent van Gogh, 1889" },
];
const examples = new Map<string, Promise<Picture>>();
export function examplePicture({ name, src }: Example): Promise<Picture> {
  if (!examples.has(name)) examples.set(name, pictureFromSrc(src, name));
  return examples.get(name)!;
}

function pictureFromBitmap(bitmap: ImageBitmap, name: string, sourceUrl: string): Picture {
  const pic: Picture = { name, cells: [], ops: [], sourceUrl, bitmap };
  cropTo(pic);
  return pic;
}

export function cropTo(pic: Picture, crop?: Crop) {
  pic.crop = crop;
  const { x, y, w, h } = crop ?? { x: 0, y: 0, w: pic.bitmap.width, h: pic.bitmap.height };
  const [sw, sh] = [Math.max(1, Math.round(w)), Math.max(1, Math.round(h))];
  const ctx = new OffscreenCanvas(sw, sh).getContext("2d")!;
  ctx.drawImage(pic.bitmap, x, y, w, h, 0, 0, sw, sh);
  pic.cells = downsample(ctx.getImageData(0, 0, sw, sh), ...fitToCanvas(sw, sh));
  pic.ops = cellsToOps(pic.cells);
}

export const CANVAS_SHAPE = CANVAS_WIDTH / (CANVAS_HEIGHT * CELL_ASPECT);
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

// The biggest canvas-shaped crop of a w by h photo, centered.
export function fillCrop(w: number, h: number): Crop {
  const cw = Math.min(w, h * CANVAS_SHAPE);
  const ch = cw / CANVAS_SHAPE;
  return { x: (w - cw) / 2, y: (h - ch) / 2, w: cw, h: ch };
}

// A crop pulled back inside the photo at the canvas's shape, no narrower than the canvas has cells.
export function clampCrop(c: Crop, w: number, h: number): Crop {
  const max = fillCrop(w, h).w;
  const cw = clamp(c.w, Math.min(CANVAS_WIDTH, max), max);
  const ch = cw / CANVAS_SHAPE;
  return { x: clamp(c.x, 0, w - cw), y: clamp(c.y, 0, h - ch), w: cw, h: ch };
}

// A line broken at spaces to fit cols; a word longer than that is cut where it must be.
export function wrap(line: string, cols: number): string[] {
  const out: string[] = [];
  let cur = "";
  for (const word of line.split(" ")) {
    const next = cur ? `${cur} ${word}` : word;
    if (next.length <= cols) {
      cur = next;
      continue;
    }
    if (cur) out.push(cur);
    for (cur = word; cur.length > cols; cur = cur.slice(cols)) out.push(cur.slice(0, cols));
  }
  return [...out, cur];
}

// The words' lines, wrapped to the photo's width, and their top left, kept inside the photo.
export function wordsAt(pic: Picture): { lines: string[]; x: number; y: number } | null {
  const [rows, cols] = [pic.cells.length, pic.cells[0].length];
  const lines = (pic.words?.text ?? "").trimEnd().split("\n").flatMap((l) => wrap(l, cols)).slice(0, rows);
  const wide = Math.max(...lines.map((l) => l.length));
  if (!wide) return null;
  const { x = (cols - wide) >> 1, y = rows - lines.length - 1 } = pic.words!;
  return { lines, x: clamp(x, 0, cols - wide), y: clamp(y, 0, rows - lines.length) };
}

// Art's auto ink: whichever of the screen's two inks reads better on the cell (auto_ink in canvas/ui.py).
const INKS = [DEFAULT_PALETTE.text, DEFAULT_PALETTE.on_primary];
const autoInk = (bg: string) => INKS.reduce((a, b) => (contrast(b, bg) > contrast(a, bg) ? b : a));

// The words as Art letters on the photo's cells, the way Purple writes them.
export function wordLetters(pic: Picture): LetterOp[] {
  const at = wordsAt(pic);
  if (!at) return [];
  const [x0, y0] = canvasOrigin(pic.cells[0].length, pic.cells.length);
  return at.lines.flatMap((line, dy) => [...line].flatMap((char, dx): LetterOp[] => {
    const [cx, cy] = [at.x + dx, at.y + dy];
    return char === " " ? [] : [[x0 + cx, y0 + cy, char, autoInk(pic.cells[cy][cx])]];
  }));
}

export const onScreen = (pic: Picture): ArtPicture => ({ ops: pic.ops, letters: wordLetters(pic) });

// Purple's Art letters (MartianMonoArt-Bold, declared in styles.css), sized as _letter_px in art_room.py.
export const ART_FONT = "PurpleArt";
export const letterPx = (cellPx: number) => Math.max(6, Math.round(cellPx * 0.85));

type Ctx2D = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

function fillOps(ctx: Ctx2D, ops: PaintOp[], cellPx: number) {
  const ch = cellPx * CELL_ASPECT;
  for (const [x, y, color] of ops) {
    ctx.fillStyle = color;
    ctx.fillRect(x * cellPx, y * ch, cellPx, ch);
  }
}

// The photo a pack keeps so Studio can crop again after reopening, at most SOURCE_MAX pixels a side. Drawing it
// through a canvas also drops its EXIF, a phone photo's location included.
const SOURCE_MAX = 2048;
export const scaleCrop = (c: Crop | undefined, s: number): Crop | undefined => c && { x: c.x * s, y: c.y * s, w: c.w * s, h: c.h * s };

export async function sourceJpeg(pic: Picture): Promise<{ jpg: Uint8Array; crop?: Crop }> {
  const { width, height } = pic.bitmap;
  const s = Math.min(1, SOURCE_MAX / Math.max(width, height));
  const canvas = new OffscreenCanvas(Math.round(width * s), Math.round(height * s));
  const ctx = canvas.getContext("2d")!;
  // JPEG has no transparency; black is what downsample already makes of it.
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(pic.bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.85 });
  return { jpg: new Uint8Array(await blob.arrayBuffer()), crop: scaleCrop(pic.crop, s) };
}

// A picture on the Art grid the way Purple paints it; a cell is cellPx wide.
export function paintPicture(ctx: Ctx2D, { ops, letters }: ArtPicture, cellPx: number) {
  const ch = cellPx * CELL_ASPECT;
  ctx.fillStyle = CANVAS_BG;
  ctx.fillRect(0, 0, CANVAS_WIDTH * cellPx, CANVAS_HEIGHT * ch);
  fillOps(ctx, ops, cellPx);
  ctx.font = `${letterPx(cellPx)}px ${ART_FONT}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const [x, y, char, ink] of letters) {
    ctx.fillStyle = ink;
    ctx.fillText(char, (x + 0.5) * cellPx, (y + 0.5) * ch);
  }
}

// Kept by what's painted: the live pack rebuilds every picture's PNG on each edit.
const previews = new Map<string, Promise<Uint8Array>>();

export function previewPng(art: ArtPicture, cellPx = 10): Promise<Uint8Array> {
  const key = `${cellPx}|${JSON.stringify(art)}`;
  let png = previews.get(key);
  if (!png) {
    const canvas = new OffscreenCanvas(CANVAS_WIDTH * cellPx, CANVAS_HEIGHT * cellPx * CELL_ASPECT);
    png = document.fonts.load(`${cellPx}px ${ART_FONT}`)
      .then(() => paintPicture(canvas.getContext("2d")!, art, cellPx))
      .then(() => canvas.convertToBlob({ type: "image/png" }))
      .then(async (b) => new Uint8Array(await b.arrayBuffer()));
    if (previews.size >= 32) previews.delete(previews.keys().next().value!);
    previews.set(key, png);
  }
  return png;
}
