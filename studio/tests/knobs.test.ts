import { describe, expect, it } from "vitest";
import { EXAMPLES } from "../src/examples";
import { type Lit, readKnobs, writeKnobs } from "../src/knobs";
import { searchEmoji } from "../src/ui/emojipicker";
import { isMap, legendFor } from "../src/ui/mappainter";

const ROOM = `from purple import *

# A room.

# The seeds, by key
SEEDS = {
    "1": ("sunflower", ["🌱", "🌻"]),  # tall
    '2': ('tulip', ["🌷"]),
}
# How fast
SPEED = 0.5
SOIL = ("#7a5230",)
OK = True
seed = "1"
LATER = 3
`;

describe("knobs", () => {
  it("reads the settings at the top, with the comment above each, and stops at the first other line", () => {
    const knobs = readKnobs(ROOM);
    expect(knobs.map((k) => [k.name, k.about])).toEqual([["SEEDS", "The seeds, by key"], ["SPEED", "How fast"], ["SOIL", ""], ["OK", ""]]);
    expect(knobs[0].value).toEqual({ t: "dict", entries: [
      [{ t: "str", v: "1" }, { t: "tuple", items: [{ t: "str", v: "sunflower" }, { t: "list", items: [{ t: "str", v: "🌱" }, { t: "str", v: "🌻" }] }] }],
      [{ t: "str", v: "2" }, { t: "tuple", items: [{ t: "str", v: "tulip" }, { t: "list", items: [{ t: "str", v: "🌷" }] }] }],
    ] });
  });

  it("writes edits back in place and leaves the rest of the Python alone", () => {
    const knobs = readKnobs(ROOM);
    const speed = knobs[1].value as { v: number };
    speed.v = 2;
    const soil = knobs[2].value as { items: { v: string }[] };
    soil.items[0].v = 'say "hi"';
    const out = writeKnobs(ROOM, knobs);
    expect(out).toContain("SPEED = 2\n");
    expect(out).toContain('SOIL = ("say \\"hi\\"",)\n');
    expect(out).toContain('seed = "1"\nLATER = 3\n');
    expect(readKnobs(out).map((k) => k.name)).toEqual(["SEEDS", "SPEED", "SOIL", "OK"]);
    speed.v = 3;
    expect(writeKnobs(out, knobs)).toContain("SPEED = 3\n");
  });

  it("takes a Labels line out of the comment and splits it", () => {
    const [k] = readKnobs('from purple import *\n# The pages.\n# Labels: page, picture,words\nPAGES = {}\n');
    expect([k.about, k.labels]).toEqual(["The pages.", ["page", "picture", "words"]]);
  });

  it("gives up on anything that isn't a plain value", () => {
    expect(readKnobs('from purple import *\nA = 1\nB = f"{A}"\nC = 2\n').map((k) => k.name)).toEqual(["A"]);
    expect(readKnobs("from purple import *\nA = [1, 2] + [3]\n")).toEqual([]);
  });

  it("finds knobs in every starter room, and writing them back changes nothing", () => {
    for (const e of EXAMPLES) {
      const knobs = readKnobs(e.source);
      expect(knobs.length, e.name).toBeGreaterThan(0);
      expect(writeKnobs(e.source, knobs), e.name).toBe(e.source);
    }
  });

  it("offers only the fun settings of each starter room", () => {
    const names = Object.fromEntries(EXAMPLES.map((e) => [e.name, readKnobs(e.source).map((k) => k.name)]));
    expect(names).toEqual({
      explore: ["MAP", "THINGS", "GROUND", "HERO_COLORS", "TALK"],
      garden: ["SEEDS", "SOIL"],
      beats: ["DRUMS", "SPEED"],
      memory: ["CARDS", "PLAYERS"],
      story: ["PAGES"],
      snake: ["SNAKE", "LENGTH", "TRAIL"],
    });
  });

  it("reads and writes the pack's pictures beside emoji, and a legend can hold them", () => {
    const source = `THINGS = {"T": picture( "oak" ), "*": "⭐"}\nCARDS = ["🐶", picture('biscuit')]\nMAP = ["T*T", "...", "T.T"]\n`;
    const knobs = readKnobs(source);
    expect(knobs.map((k) => k.name)).toEqual(["THINGS", "CARDS", "MAP"]);
    expect(knobs[1].value).toEqual({ t: "list", items: [{ t: "str", v: "🐶" }, { t: "picture", v: "biscuit" }] });
    expect(writeKnobs(source, knobs)).toBe(source);
    (knobs[1].value as { items: Lit[] }).items[0] = { t: "picture", v: "mochi" };
    expect(writeKnobs(source, knobs)).toContain('CARDS = [picture("mochi"), picture("biscuit")]');
    expect(legendFor(knobs[2].value as { items: Lit[] }, knobs.map((k) => k.value))).toBe(knobs[0].value);
  });

  it("leaves out emoji already in the list, so an emoji setting never repeats one", () => {
    expect(searchEmoji("dog").map((r) => r.emoji)).toContain("🐶");
    expect(searchEmoji("dog", 32, ["🐶"]).map((r) => r.emoji)).not.toContain("🐶");
    expect(searchEmoji("", 32, ["🐶"]).map((r) => r.emoji)).not.toContain("🐶");
    expect(searchEmoji("🐶", 32, ["🐶"])).toEqual([]);
  });

  it("paints a map of even rows, using a dict of one-letter keys as its legend", () => {
    const knobs = readKnobs(EXAMPLES.find((e) => e.name === "explore")!.source);
    expect(knobs.filter((k) => isMap(k.value)).map((k) => k.name)).toEqual(["MAP"]);
    const map = knobs.find((k) => k.name === "MAP")!.value as { items: Lit[] };
    expect(legendFor(map, knobs.map((k) => k.value))).toBe(knobs.find((k) => k.name === "THINGS")!.value);
    const uneven = readKnobs('X = ["abc", "abcd", "abc"]\n')[0].value;
    expect(isMap(uneven)).toBe(false);
  });
});
