import { describe, expect, it } from "vitest";
import fixtures from "./art-fixtures.json";
import { CANVAS_HEIGHT, CANVAS_WIDTH, CELL_ASPECT, DEFAULT_BG_DARK, DEFAULT_BG_LIGHT, GUTTER_BG_DARK, KEY_COLORS, cellsToOps, fitToCanvas } from "../src/purple/art";

// art-fixtures.json is exported from the Python side (see README) so the port can be checked against it.
describe("art port matches purple_tui", () => {
  it("canvas dimensions", () => {
    expect([CANVAS_WIDTH, CANVAS_HEIGHT]).toEqual(fixtures.canvas);
    expect(CELL_ASPECT).toBe(fixtures.cellAspect);
    expect(DEFAULT_BG_DARK).toBe(fixtures.bgDark);
    expect(DEFAULT_BG_LIGHT).toBe(fixtures.bgLight);
    expect([...GUTTER_BG_DARK]).toEqual(fixtures.gutter);
  });

  it("fit_to_canvas for every fixture size", () => {
    for (const [size, expected] of Object.entries(fixtures.fit)) {
      const [w, h] = size.split("x").map(Number);
      expect(fitToCanvas(w, h), size).toEqual(expected);
    }
  });

  it("KEY_COLORS byte for byte, including hsl truncation", () => {
    for (const [key, hex] of Object.entries(fixtures.keyColors)) {
      if (key === "÷" || key === "×") continue;
      expect(KEY_COLORS[key], key).toBe(hex);
    }
  });

  it("ops are centered like photo_to_art.convert", () => {
    const cells = [["#000000", "#111111"], ["#222222", "#333333"]];
    const ops = cellsToOps(cells);
    expect(ops[0]).toEqual([65, 11, "#000000"]);
    expect(ops[3]).toEqual([66, 12, "#333333"]);
  });
});
