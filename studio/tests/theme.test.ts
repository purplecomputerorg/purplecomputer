import { describe, expect, it } from "vitest";
import { DEFAULT_PALETTE, DEFAULT_THEME, contrast, derivePalette, themeJson, themePalette, toHsl } from "../sdk/src/purple/theme";

const BASES = ["#0d2233", "#10241a", "#2a1420", "#000000", "#4a4a4a", "#ff0000", "#efe9f7", "#ffffff", "#ffe066"];
const distance = (a: string, b: string) => Math.max(...[1, 3, 5].map((i) => Math.abs(parseInt(a.slice(i, i + 2), 16) - parseInt(b.slice(i, i + 2), 16))));

describe("one color, a whole palette", () => {
  it("leaves Purple's own palette alone", () => {
    expect(themePalette(DEFAULT_THEME)).toEqual(DEFAULT_PALETTE);
  });

  it("rebuilds Purple's palette from its own background, near enough to look the same", () => {
    const derived = derivePalette(DEFAULT_PALETTE.bg);
    for (const [role, color] of Object.entries(DEFAULT_PALETTE)) expect(distance(derived[role as keyof typeof derived], color), role).toBeLessThanOrEqual(6);
  });

  it.each(BASES)("keeps every kind of text readable on %s", (base) => {
    const p = derivePalette(base);
    expect(p.bg).toBe(base);
    expect(contrast(p.text, p.surface)).toBeGreaterThanOrEqual(6.9);
    expect(contrast(p.muted, p.surface)).toBeGreaterThanOrEqual(4.4);
    expect(contrast(p.on_primary, p.primary)).toBeGreaterThanOrEqual(4.4);
    expect(toHsl(p.text)[2] < 0.5).toBe(toHsl(base)[2] > 0.5);
  });

  it("writes theme.json as Purple reads it, with a hand-set color winning", () => {
    const json = themeJson({ ...DEFAULT_THEME, base: "#0d2233", colors: { text: "#ffffff" } });
    expect(json.colors.bg).toBe("#0d2233");
    expect(json.colors.text).toBe("#ffffff");
    expect(json.canvas).toMatch(/^#[0-9a-f]{6}$/);
    expect("canvas" in json.colors).toBe(false);
    expect(Object.keys(json.keys)).toContain("q");
  });
});
