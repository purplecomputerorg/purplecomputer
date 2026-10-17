import { describe, expect, it } from "vitest";
import { CANVAS_HEIGHT, CANVAS_WIDTH, fitToCanvas } from "../sdk/src/purple/art";
import { CANVAS_SHAPE, clampCrop, fillCrop } from "../src/photo";

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
