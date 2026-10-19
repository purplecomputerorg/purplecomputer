import { describe, expect, it } from "vitest";
import { browserKey, typingKeys } from "../src/keys";

describe("keys", () => {
  it("names a browser's keys the way Purple's rooms take them", () => {
    const key = (k: string) => browserKey({ key: k } as KeyboardEvent);
    expect(["A", "z", "7", " ", "Enter", "Escape", "ArrowUp", "Backspace"].map(key)).toEqual(["a", "z", "7", "space", "enter", "escape", "up", "backspace"]);
    expect(key("🐶")).toBe("🐶");
    expect([key("Shift"), key("F5"), key("Meta")]).toEqual([null, null, null]);
  });

  it("types a word on a phone's few keys: each letter once, at most five, then Enter", () => {
    expect(typingKeys("Biscuit")).toEqual(["b", "i", "s", "c", "u", "enter"]);
    expect(typingKeys("ma ma!")).toEqual(["m", "a", "enter"]);
  });
});
