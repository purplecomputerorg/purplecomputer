import { describe, expect, it } from "vitest";
import exported from "../src/purple/export.json";
import { ASDF_ROW, KEY_COLORS, QWERTY_ROW, ROW_HUES, ZXCV_ROW, cellsToOps, fitToCanvas, generateRowGradient } from "../src/purple/art";

// Constants are imported from export.json; these check the two ported functions against it.
describe("art port matches purple_tui", () => {
  it("fit_to_canvas for every exported size", () => {
    for (const [size, expected] of Object.entries(exported.art.fit)) {
      const [w, h] = size.split("x").map(Number);
      expect(fitToCanvas(w, h), size).toEqual(expected);
    }
  });

  it("generate_row_gradient reproduces KEY_COLORS byte for byte", () => {
    const rows: [number, string[]][] = [[ROW_HUES.qwerty, QWERTY_ROW], [ROW_HUES.asdf, ASDF_ROW], [ROW_HUES.zxcv, ZXCV_ROW]];
    for (const [hue, keys] of rows) for (const [k, hex] of Object.entries(generateRowGradient(hue, keys))) expect(KEY_COLORS[k], k).toBe(hex);
  });

  it("ops are centered like photo_to_art.convert", () => {
    const cells = [["#000000", "#111111"], ["#222222", "#333333"]];
    const ops = cellsToOps(cells);
    expect(ops[0]).toEqual([65, 11, "#000000"]);
    expect(ops[3]).toEqual([66, 12, "#333333"]);
  });
});
