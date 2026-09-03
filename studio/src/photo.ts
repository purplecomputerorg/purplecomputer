import { CANVAS_HEIGHT, CANVAS_WIDTH, DEFAULT_BG_DARK, canvasOrigin, cellsToOps, fitToCanvas, type PaintOp } from "./purple/art";

export interface Picture { name: string; cells: string[][]; ops: PaintOp[]; sourceUrl: string }

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

export async function pictureFromFile(file: File): Promise<Picture> {
  const bitmap = await createImageBitmap(file);
  const [cols, rows] = fitToCanvas(bitmap.width, bitmap.height);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bitmap, 0, 0);
  const cells = downsample(ctx.getImageData(0, 0, bitmap.width, bitmap.height), cols, rows);
  const name = file.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "picture";
  return { name, cells, ops: cellsToOps(cells), sourceUrl: URL.createObjectURL(file) };
}

// Same rendering as tools/photo_to_art.write_preview: a cell is PREVIEW_CELL_PX wide and twice as tall.
export function paintCells(ctx: CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D, cells: string[][], cellPx: number, bg = DEFAULT_BG_DARK) {
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, CANVAS_WIDTH * cellPx, CANVAS_HEIGHT * cellPx * 2);
  const [x0, y0] = canvasOrigin(cells[0].length, cells.length);
  cells.forEach((row, cy) =>
    row.forEach((color, cx) => {
      ctx.fillStyle = color;
      ctx.fillRect((x0 + cx) * cellPx, (y0 + cy) * cellPx * 2, cellPx, cellPx * 2);
    }),
  );
}

export async function previewPng(cells: string[][], cellPx = 10): Promise<Uint8Array> {
  const canvas = new OffscreenCanvas(CANVAS_WIDTH * cellPx, CANVAS_HEIGHT * cellPx * 2);
  paintCells(canvas.getContext("2d")!, cells, cellPx);
  return new Uint8Array(await (await canvas.convertToBlob({ type: "image/png" })).arrayBuffer());
}
