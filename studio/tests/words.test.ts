import { describe, expect, it } from "vitest";
import { typedWord, wordProblem } from "../src/keys";

describe("family words", () => {
  it("fold accents to what Purple's keyboard types", () => {
    expect(typedWord(" Piñata ")).toBe("pinata");
    expect(typedWord("Corazón")).toBe("corazon");
    expect(wordProblem(typedWord("piñata"))).toBeNull();
  });
  it("refuse what a kid can't type", () => {
    for (const w of ["中文", "two words", "🐶", "", "a".repeat(31)].map(typedWord)) expect(wordProblem(w)).not.toBeNull();
    expect(wordProblem("a".repeat(30))).toBeNull();
  });
});
