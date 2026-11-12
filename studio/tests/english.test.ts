// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { ENGLISH_ONLY, englishOnly, keepTypingEnglish } from "../src/english";

describe("English letters only, while Purple's language support is off", () => {
  it("keeps accents, digits, symbols and emoji, and drops other alphabets", () => {
    expect(englishOnly(`niño é 3 <b> " ' ); \\ 🎉👶🏽`)).toBe(`niño é 3 <b> " ' ); \\ 🎉👶🏽`);
    expect(englishOnly("hi 中文 Привет שלום")).toBe("hi   ");
  });

  it("cleans a field as it's typed, before the field's own handler reads it, and says why", () => {
    keepTypingEnglish(document);
    const seen: string[] = [];
    const field = document.body.appendChild(document.createElement("textarea"));
    field.addEventListener("input", () => seen.push(field.value));
    field.value = "dog 中文";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    expect(seen).toEqual(["dog "]);
    expect(field.validationMessage).toBe(ENGLISH_ONLY);
    field.value = "dog";
    field.dispatchEvent(new Event("input", { bubbles: true }));
    expect(field.validationMessage).toBe("");
  });

  it("leaves a room's code alone", () => {
    const code = document.body.appendChild(document.createElement("textarea"));
    code.className = "code";
    code.value = 'say("中文")';
    code.dispatchEvent(new Event("input", { bubbles: true }));
    expect(code.value).toBe('say("中文")');
  });
});
