import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { drawable, pieces, type EmojiMap } from "../src/emoji";

// Built by `just studio-bundle` from the Noto Purple's ISO installs.
const MAP = new URL("../.cache/emoji/map.json", import.meta.url);
const map: EmojiMap | null = existsSync(MAP) ? JSON.parse(readFileSync(MAP, "utf8")) : null;

describe.skipIf(!map)("emoji as Purple's pictures", () => {
  const m = map!;
  const pictures = (text: string) => pieces(m, text).map((p) => (typeof p === "string" ? p : p.pictures.length));

  it("finds emoji with Purple's own pattern, each as one picture between plain runs", () => {
    expect(pictures("cat 🐱 dog")).toEqual(["cat ", 1, " dog"]);
    expect(pictures("👨‍👩‍👧👍🏽🇺🇸")).toEqual([1, 1, 1]);
  });

  it("draws a sequence the same with or without VS16, and leaves what Purple draws as text as text", () => {
    expect(pieces(m, "🦸‍♀")).toEqual([{ emoji: "🦸‍♀", pictures: (pieces(m, "🦸‍♀️")[0] as { pictures: number[] }).pictures }]);
    expect(pictures("1️⃣ ❤ ©")).toEqual(["1️⃣ ❤ ©"]);
    expect(pictures("❤️")).toEqual([1]);
  });

  it("keeps an emoji newer than Purple's font as text, and out of the picker", () => {
    const newest = "\u{1FAF9}";  // newer than Purple's Noto: HarfBuzz finds no glyph for it
    expect(pictures(newest)).toEqual([newest]);
    expect(drawable(m, newest)).toBe(false);
    expect(drawable(m, "⭐")).toBe(true);
  });
});
