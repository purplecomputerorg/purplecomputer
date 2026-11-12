// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

const clip = { samples: new Float32Array([0.5]), rate: 22050 };
vi.mock("../src/roomvoice", () => ({ roomLine: vi.fn(async () => clip) }));
vi.mock("../src/speakable", () => ({ speakable: async (text: string) => text }));
vi.mock("../src/audio", async (real) => ({ ...(await real<object>()), play: vi.fn(), previewUrl: vi.fn() }));

const { roomLine } = await import("../src/roomvoice");
const { play } = await import("../src/audio");
const { draft, phraseFor, replaceDraft } = await import("../src/state");
const { wordsView } = await import("../src/ui/words");

const settle = () => new Promise((r) => setTimeout(r, 0));
const input = (label: string) => document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!;
const button = (text: RegExp) => [...document.querySelectorAll("button")].find((b) => text.test(b.textContent ?? ""))!;
function typeIn(el: HTMLInputElement, text: string, commit = true) {
  el.value = text;
  el.dispatchEvent(new Event("input"));
  if (commit) el.dispatchEvent(new Event("change"));
}
function addWord(word: string) {
  typeIn(input("New word"), word, false);
  button(/Add new word/).click();
}

// Words Purple has an emoji for, so adding one doesn't ask what it shows.
beforeEach(() => {
  Element.prototype.scrollIntoView = () => {};
  replaceDraft();
  document.body.replaceChildren(wordsView().editor);
});

describe("the word editor", () => {
  it("keeps the words for Purple to say when the box is left, without Say it", async () => {
    addWord("zebra");
    typeIn(input("Words for Purple to say"), "stripes stripes");
    await settle();
    expect(phraseFor("zebra")?.said).toBe("stripes stripes");
    expect(draft.phrases).toHaveLength(1);
  });

  it("reads the words once when Say it follows leaving the box, and plays them", async () => {
    vi.mocked(roomLine).mockClear();
    vi.mocked(play).mockClear();
    addWord("zebra");
    typeIn(input("Words for Purple to say"), "stripes");
    button(/Say it/).click();
    button(/Done/).click();
    await settle();
    expect([vi.mocked(roomLine).mock.calls.length, vi.mocked(play).mock.calls.length]).toEqual([1, 1]);
    expect(phraseFor("zebra")?.said).toBe("stripes");
  });

  it("keeps a meaning as it's typed, before Done", () => {
    addWord("cat");
    typeIn(input("Meaning"), "Our fluffy cat", false);
    expect(draft.words[0].means).toBe("Our fluffy cat");
  });

  it("asks for a recording, instead of saying nothing, when Your voice has none yet", () => {
    addWord("zebra");
    button(/Your voice/).click();
    expect(document.querySelector(".sound-picker .status")?.textContent).toMatch(/Record yourself/);
  });

  it("says why a rename is refused in the word being renamed, not under the new word box", () => {
    addWord("dog");
    addWord("zebra");
    typeIn(input("Word"), "dog");
    expect(document.querySelector(".word-row.open .word-note")?.textContent).toMatch(/already in the list/);
    expect(document.querySelector(".card > .status")?.textContent).toBe("");
    expect(draft.words.map((w) => w.word)).toEqual(["dog", "zebra"]);
  });
});
