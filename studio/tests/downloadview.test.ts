// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

window.matchMedia = () => ({ matches: false, addEventListener() {} }) as unknown as MediaQueryList;
const { draft, putPhrase, replaceDraft } = await import("../src/state");
const { downloadView } = await import("../src/ui/download");

const clip = { samples: new Float32Array([0.5]), rate: 22050 };
const chips = () => [...document.querySelectorAll(".in-pack .pack-item")].map((c) => c.textContent);
const headings = () => [...document.querySelectorAll(".in-pack .pack-heading")].map((h) => h.textContent);

beforeEach(() => replaceDraft());

describe("the Download summary", () => {
  it("lists a word once, with its voice on its chip", () => {
    draft.words = [{ word: "abuela", emoji: "👵", kept: true }, { word: "zebra", emoji: "🦓", kept: true }, { word: "cat", emoji: "🐱", kept: true }];
    putPhrase("abuela", clip, true);
    putPhrase("zebra", clip, true, "stripes");
    putPhrase("hello there", clip, true);
    document.body.replaceChildren(downloadView().editor);
    expect(chips()).toEqual(expect.arrayContaining(["👵abuela 🎤", "🦓zebra 🔊", "🐱cat", "🎤“hello there”"]));
    expect(chips()).toHaveLength(4);
    expect(headings()).toEqual(expect.arrayContaining(["3 words"]));
  });
});
