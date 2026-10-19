import { describe, expect, it } from "vitest";
import { CANVAS_HEIGHT, CANVAS_WIDTH, canvasOrigin, fitToCanvas } from "../sdk/src/purple/art";
import { DEFAULT_PALETTE, contrast } from "../sdk/src/purple/theme";
import { CANVAS_SHAPE, clampCrop, fillCrop, wordLetters, wordsAt, type Picture, type Words } from "../src/photo";

describe("cropping to the Art canvas", () => {
  it("fills the canvas from a tall photo and a wide one", () => {
    for (const [w, h] of [[1146, 1258], [4000, 1000], [56, 24]]) {
      const c = fillCrop(w, h);
      expect(c.w / c.h).toBeCloseTo(CANVAS_SHAPE);
      expect(c.x >= 0 && c.y >= 0 && c.x + c.w <= w + 1e-9 && c.y + c.h <= h + 1e-9).toBe(true);
      expect(fitToCanvas(Math.round(c.w), Math.round(c.h))).toEqual([CANVAS_WIDTH, CANVAS_HEIGHT]);
    }
  });

  it("keeps a moved or resized crop inside the photo at the canvas shape", () => {
    expect(clampCrop({ x: -50, y: 1200, w: 300, h: 1 }, 1146, 1258)).toEqual({ x: 0, y: 1258 - 300 / CANVAS_SHAPE, w: 300, h: 300 / CANVAS_SHAPE });
    expect(clampCrop({ x: 0, y: 0, w: 5000, h: 0 }, 1146, 1258)).toEqual({ ...fillCrop(1146, 1258), y: 0 });
    expect(clampCrop({ x: 10, y: 10, w: 2, h: 1 }, 1146, 1258).w).toBe(CANVAS_WIDTH);
  });
});

describe("words on a picture", () => {
  // A 10 by 4 photo, white on its left half and black on its right, centered on the canvas.
  const cells = Array.from({ length: 4 }, () => [...Array(5).fill("#ffffff"), ...Array(5).fill("#000000")]);
  const pic = (words?: Words) => ({ cells, words }) as Picture;
  const [x0, y0] = canvasOrigin(10, 4);

  it("centers them near the bottom until moved, skipping spaces, in the ink that reads on each cell", () => {
    const [light, dark] = [DEFAULT_PALETTE.text, DEFAULT_PALETTE.on_primary].sort((a, b) => contrast(b, "#000000") - contrast(a, "#000000"));
    expect(wordLetters(pic({ text: "hi yo" }))).toEqual([
      [x0 + 2, y0 + 2, "h", dark], [x0 + 3, y0 + 2, "i", dark], [x0 + 5, y0 + 2, "y", light], [x0 + 6, y0 + 2, "o", light],
    ]);
  });

  it("keeps moved words and their lines inside the photo", () => {
    expect(wordsAt(pic({ text: "ab\nlong line here", x: 7, y: -3 }))).toEqual({ lines: ["ab", "long line "], x: 0, y: 0 });
    expect(wordsAt(pic({ text: "ab", x: 99, y: 99 }))).toMatchObject({ x: 8, y: 3 });
    expect(wordsAt(pic({ text: " \n" }))).toBeNull();
    expect(wordLetters(pic())).toEqual([]);
  });
});
