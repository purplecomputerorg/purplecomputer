import { describe, expect, it } from "vitest";
import { clearSection, draft, emptyDraft, hasWork, replaceDraft } from "../src/state";

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

  it("clears everything", () => {
    replaceDraft();
    expect(hasWork()).toBe(false);
  });
});
