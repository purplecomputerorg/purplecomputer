import dinosaur from "./assets/dinosaur.svg";
import dog from "./assets/dog.jpg";
import saturn from "./assets/saturn.jpg";
import greatWave from "./assets/great-wave.jpg";
import house from "./assets/sample-drawing.svg";
import { slug } from "@sdk/pack";
import type { Keepable } from "./state";
import { CANVAS_BG, CANVAS_HEIGHT, CANVAS_WIDTH, CELL_ASPECT, KEY_COLORS, canvasOrigin, cellsToOps, fitToCanvas, type ArtPicture, type LetterOp, type PaintOp } from "@sdk/purple/art";

// crop: the part of the photo on the screen, in its own pixels and the Art canvas's shape; none is the whole photo.
// painted: Purple's screen as kept after painting or writing on the photo, which goes in the pack in its place.
export interface Crop { x: number; y: number; w: number; h: number }
export interface Picture extends Keepable { name: string; title?: string; cells: string[][]; ops: PaintOp[]; sourceUrl: string; bitmap: ImageBitmap; crop?: Crop; painted?: ArtPicture }

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

export async function pictureFromFile(file: File): Promise<Picture> {
  return pictureFromBitmap(await createImageBitmap(file), slug(file.name.replace(/\.[^.]+$/, "")) || "picture", await dataUrl(file));
}

// Studio's examples, painted the same way as a family's pictures. One goes in the pack only if
// the family adds it. doodle: what a kid might paint on it, shown before anyone tries it.
// paint: rows of the keys pressed, from a cell of the Art canvas, a space painting nothing.
export interface Doodle { paint: [x: number, y: number, rows: string[]][]; words?: [x: number, y: number, text: string, ink: string][] }
export interface Example { name: string; src: string; alt: string; credit?: string; doodle: Doodle }
export const EXAMPLES: Example[] = [
  { name: "dog", src: dog, alt: "A black dog looking up", doodle: {
    paint: [[25, 0, ["   g   ", "   t   ", "  ttt  ", "  fff  ", " ttttt ", "ttttttt"]]],
    words: [[13, 21, "WOOF", "#FFFFFF"]] } },
  { name: "dinosaur", src: dinosaur, alt: "A dinosaur to color in", doodle: {
    paint: [[2, 1, ["g  g  g", " ggggg ", "ggggggg", " ggggg ", "g  g  g"]],
      [25, 10, ["     vv     ", "vv   vv  vv ", "vv       vv ", "   vv       ", "   vv   vv  ", "        vv  "]]],
    words: [[4, 10, "ROAR", "#000000"]] } },
  { name: "our-house", src: house, alt: "A drawing of a house, a sun, and a tree", doodle: {
    paint: [[13, 0, ["   tttttt   ", " ttggggggtt ", "tggvvvvvvggt", "tgv      vgt", "tgv      vgt"]]] } },
  { name: "saturn", src: saturn, alt: "Saturn and its rings", credit: "NASA, from the Cassini spacecraft", doodle: {
    paint: [[24, 13, [" ==    == ", " ==    == ", "          ", "=        =", " ======== "]],
      ...[[6, 3], [46, 4], [10, 18], [44, 19]].map(([x, y]): [number, number, string[]] => [x, y, [" g ", "ggg", " g "]])] } },
  { name: "great-wave", src: greatWave, alt: "A giant wave curling over boats", credit: "Katsushika Hokusai, around 1831", doodle: {
    paint: [[33, 1, [" rrr ", "rrrrr", "rrrrr", " rrr "]]] } },
];
const examples = new Map<string, Promise<Picture>>();
export function examplePicture({ name, src }: Example): Promise<Picture> {
  if (!examples.has(name)) examples.set(name, (async () => {
    const img = new Image();
    img.src = src;
    await img.decode();
    return pictureFromBitmap(await createImageBitmap(img), name, src);
  })());
  return examples.get(name)!;
}

function pictureFromBitmap(bitmap: ImageBitmap, name: string, sourceUrl: string): Picture {
  const pic: Picture = { name, cells: [], ops: [], sourceUrl, bitmap };
  cropTo(pic);
  return pic;
}

// A new crop is a new painting of the photo, so whatever was kept from the screen goes.
export function cropTo(pic: Picture, crop?: Crop) {
  pic.crop = crop;
  pic.painted = undefined;
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

const doodlePaint = ({ paint }: Doodle): PaintOp[] => paint.flatMap(([x, y, rows]) =>
  rows.flatMap((row, dy) => [...row].flatMap((key, dx): PaintOp[] => (key === " " ? [] : [[x + dx, y + dy, KEY_COLORS[key]]]))));
const doodleWords = ({ words = [] }: Doodle): LetterOp[] => words.flatMap(([x, y, text, ink]) => [...text].map((c, i): LetterOp => [x + i, y, c, ink]));

// An example as Purple paints it with its doodle on top.
export async function doodled(ex: Example): Promise<ArtPicture> {
  return { ops: [...(await examplePicture(ex)).ops, ...doodlePaint(ex.doodle)], letters: doodleWords(ex.doodle) };
}

// An example's photo with its doodle painted over in Purple's square cells, as an image URL.
const doodledImages = new Map<string, Promise<string>>();
export function doodledImage(ex: Example): Promise<string> {
  if (!doodledImages.has(ex.name)) doodledImages.set(ex.name, (async () => {
    const pic = await examplePicture(ex);
    const [cols, rows] = [pic.cells[0].length, pic.cells.length];
    const [x0, y0] = canvasOrigin(cols, rows);
    const cell = Math.ceil(240 / rows);
    const canvas = new OffscreenCanvas(cols * cell, rows * cell);
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(pic.bitmap, 0, 0, canvas.width, canvas.height);
    ctx.translate(-x0 * cell, -y0 * cell);
    fillOps(ctx, doodlePaint(ex.doodle), cell);
    drawLetters(ctx, doodleWords(ex.doodle), cell);
    return URL.createObjectURL(await canvas.convertToBlob({ type: "image/png" }));
  })());
  return doodledImages.get(ex.name)!;
}

// What Purple paints for a picture: the photo, or what was kept from its screen.
export const onScreen = (pic: Picture): ArtPicture => pic.painted ?? { ops: pic.ops, letters: [] };

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
  drawLetters(ctx, letters, cellPx);
}

function drawLetters(ctx: Ctx2D, letters: LetterOp[], cellPx: number) {
  const ch = cellPx * CELL_ASPECT;
  ctx.font = `bold ${Math.round(ch * 0.85)}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (const [x, y, char, ink] of letters) {
    ctx.fillStyle = ink;
    ctx.fillText(char, (x + 0.5) * cellPx, (y + 0.5) * ch);
  }
}

export async function previewPng(art: ArtPicture, cellPx = 10): Promise<Uint8Array> {
  const canvas = new OffscreenCanvas(CANVAS_WIDTH * cellPx, CANVAS_HEIGHT * cellPx * CELL_ASPECT);
  paintPicture(canvas.getContext("2d")!, art, cellPx);
  return new Uint8Array(await (await canvas.convertToBlob({ type: "image/png" })).arrayBuffer());
}
