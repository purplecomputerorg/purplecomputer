import dinosaur from "./assets/dinosaur.svg";
import dog from "./assets/dog.jpg";
import saturn from "./assets/saturn.jpg";
import greatWave from "./assets/great-wave.jpg";
import house from "./assets/sample-drawing.svg";
import { slug } from "@sdk/pack";
import type { Keepable } from "./state";
import { CANVAS_BG, CANVAS_HEIGHT, CANVAS_WIDTH, CELL_ASPECT, canvasOrigin, cellsToOps, fitToCanvas, type PaintOp } from "@sdk/purple/art";

// crop: the part of the photo on the screen, in its own pixels and the Art canvas's shape; none is the whole photo.
export interface Crop { x: number; y: number; w: number; h: number }
export interface Picture extends Keepable { name: string; title?: string; cells: string[][]; ops: PaintOp[]; sourceUrl: string; bitmap: ImageBitmap; crop?: Crop }

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
// the family adds it.
export interface Example { name: string; src: string; alt: string; credit?: string }
export const EXAMPLES: Example[] = [
  { name: "our-house", src: house, alt: "A drawing of a house, a sun, and a tree" },
  { name: "dinosaur", src: dinosaur, alt: "A dinosaur to color in" },
  { name: "dog", src: dog, alt: "A black dog looking up" },
  { name: "saturn", src: saturn, alt: "Saturn and its rings", credit: "NASA, from the Cassini spacecraft" },
  { name: "great-wave", src: greatWave, alt: "A giant wave curling over boats", credit: "Katsushika Hokusai, around 1831" },
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

// The picture on the Art grid, centered the way Purple paints it; a cell is cellPx wide.
export function paintCells(ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D, cells: string[][], cellPx: number, bg: string | null = CANVAS_BG) {
  const ch = cellPx * CELL_ASPECT;
  if (bg) {
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, CANVAS_WIDTH * cellPx, CANVAS_HEIGHT * ch);
  }
  const [x0, y0] = canvasOrigin(cells[0].length, cells.length);
  cells.forEach((row, cy) =>
    row.forEach((color, cx) => {
      ctx.fillStyle = color;
      ctx.fillRect((x0 + cx) * cellPx, (y0 + cy) * ch, cellPx, ch);
    }),
  );
}

export async function previewPng(cells: string[][], cellPx = 10): Promise<Uint8Array> {
  const canvas = new OffscreenCanvas(CANVAS_WIDTH * cellPx, CANVAS_HEIGHT * cellPx * CELL_ASPECT);
  paintCells(canvas.getContext("2d")!, cells, cellPx);
  return new Uint8Array(await (await canvas.convertToBlob({ type: "image/png" })).arrayBuffer());
}
