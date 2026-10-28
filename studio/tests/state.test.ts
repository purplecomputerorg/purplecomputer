import { describe, expect, it } from "vitest";
import { clearSection, draft, emptyDraft, freeName, hasWork, keep, madeOf, mine, onChange, phraseFor, notInPieces, pieces, putPhrase, replaceDraft, withSample, type WordEntry } from "../src/state";

describe("rooms saved before the picture quiz", () => {
  it("keeps a trivia room's Python but not its old form, and keeps every other form", () => {
    expect(madeOf({ kind: "trivia", data: { rows: [] } })).toBeNull();
    expect(madeOf(undefined)).toBeNull();
    expect(madeOf({ kind: "rules", rules: [] })).toEqual({ kind: "rules", rules: [] });
  });
});

describe("pack names", () => {
  it("gives a new pack a name of words, and swaps the old dated name for one while keeping the pack's id", () => {
    replaceDraft();
    expect(draft.name).toMatch(/^purple-[a-z]+-[a-z]+$/);
    replaceDraft({ ...emptyDraft(), id: "pack-old", name: "purple-2026-10-17" });
    expect(draft.name).toMatch(/^purple-[a-z]+-[a-z]+$/);
    expect(draft.id).toBe("pack-old");
    replaceDraft({ ...emptyDraft(), name: "Grandma's rooms" });
    expect(draft.name).toBe("Grandma's rooms");
  });
});

describe("recordings of what rooms say", () => {
  it("finds a recording by the words as Purple looks them up, and keeps one a room recorded when it's recorded again", () => {
    replaceDraft();
    const clip = { samples: new Float32Array(1), rate: 22050 };
    putPhrase("The owl says hello.", clip, true);
    expect(phraseFor("the owl says hello.")?.text).toBe("The owl says hello.");
    expect(phraseFor("The owl says hello!")).toBeUndefined();
    putPhrase("THE OWL SAYS HELLO.", clip);
    expect(draft.phrases.map((p) => [p.text, p.kept])).toEqual([["THE OWL SAYS HELLO.", true]]);
    putPhrase("the owl says hello.", null);
    expect(draft.phrases).toEqual([]);
  });
});

describe("clearing", () => {
  it("clears one section and leaves the rest", () => {
    replaceDraft({ ...emptyDraft(), words: [{ word: "dog", emoji: "🐶" }], synonyms: [{ alias: "pup", word: "dog" }], ranked: ["dog"], instruments: [{ name: "bells", base: "glockenspiel", params: {} }] });
    const id = draft.id;
    clearSection("words");
    expect([draft.words, draft.synonyms, draft.ranked]).toEqual([[], [], []]);
    expect(hasWork("words")).toBe(false);
    expect(hasWork("instruments")).toBe(true);
    expect(draft.id).toBe(id);
  });

  it("clears phrases with words, and letters on their own", () => {
    const clip = { samples: new Float32Array(1), rate: 22050 };
    replaceDraft({ ...emptyDraft(), letters: { d: { clip, said: "D is for Dad" } }, phrases: [{ text: "good night", clip }] });
    clearSection("words");
    expect([draft.phrases, hasWork("keys")]).toEqual([[], true]);
    clearSection("keys");
    expect(draft.letters).toEqual({});
  });

  it("clears everything", () => {
    replaceDraft();
    expect(hasWork()).toBe(false);
  });
});

describe("the draft", () => {
  it("names a new piece from what was typed, never one already used", () => {
    const taken = new Set(["fairy-bells", "fairy-bells-2"]);
    expect(freeName("Fairy Bells!", (n) => taken.has(n))).toBe("fairy-bells-3");
    expect(freeName("Grandma's Song", () => false)).toBe("grandmas-song");
    expect(freeName("🎵🎵", () => false, "instrument")).toBe("instrument");
    expect(freeName("a".repeat(39) + " b", () => false)).toBe("a".repeat(39));
  });

  it("swaps the example being tried for the next one, keeping any the family changed or added", () => {
    const mine: WordEntry = { word: "biscuit", emoji: "🐶", kept: true };
    const added: WordEntry = { word: "dino", emoji: "🦕", sample: true, kept: true };
    const tried = withSample([mine, added], { word: "cat", emoji: "🐈" });
    expect(withSample(tried, { word: "owl", emoji: "🦉" }).map((w) => w.word)).toEqual(["biscuit", "dino", "owl"]);
  });

  it("counts what's added apart from what isn't: examples tried and what was taken out", () => {
    const zorbo: WordEntry = { word: "zorbo", emoji: "🐙", sample: true };
    const owl: WordEntry = { word: "owl", emoji: "🦉", kept: false };
    replaceDraft({ ...draft, words: [{ word: "biscuit", emoji: "🐶", kept: true }, zorbo, owl], ranked: ["biscuit"] });
    expect(pieces().map((p) => [p.id, p.count])).toEqual([["words", 1], ["autocomplete_picks", 1]]);
    expect(notInPieces().map((p) => p.items)).toEqual([[zorbo, owl]]);
    keep(owl, true);
    expect(notInPieces().map((p) => p.items)).toEqual([[zorbo]]);
  });

  it("puts an example in the Purple Pack once it's changed, and leaves the family's own as they chose", () => {
    const tried: WordEntry = { word: "cat", emoji: "🐈", sample: true };
    const out: WordEntry = { word: "owl", emoji: "🦉", kept: false };
    mine(tried);
    mine(out);
    expect([tried, out].map((w) => [w.sample, w.kept])).toEqual([[false, true], [undefined, false]]);
  });

  it("starts another Purple Pack in the same draft object, telling every page", () => {
    const held = draft;
    let told = 0;
    onChange(() => told++);
    replaceDraft();
    expect(draft).toBe(held);
    expect(draft.words).toEqual([]);
    expect(draft.id).toMatch(/^pack-[0-9a-f]{8}$/);
    expect(told).toBe(1);
  });
});
