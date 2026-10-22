import { beforeEach, describe, expect, it } from "vitest";
import { TEMPLATES } from "../src/examples";
import { draft, replaceDraft } from "../src/state";
import { addRoomData, dropUnusedSound } from "../src/ui/roomfiles";

const wav = (n: number) => new Uint8Array([82, 73, 70, 70, n]);

beforeEach(() => replaceDraft());

describe("a pack's pictures and sounds for its rooms", () => {
  it("keeps one of each, however often the very same one is added", () => {
    const moo = addRoomData("sounds", "cow", wav(1));
    expect(addRoomData("sounds", "moo", wav(1))).toBe(moo);
    expect(addRoomData("sounds", "cow", wav(2)).name).toBe("cow-2");
    expect(addRoomData("images", "cow", wav(1)).name).toBe("cow");
    expect(draft.roomFiles).toHaveLength(3);
  });

  it("throws away a key's old recording once no room says it, as its form stands now", () => {
    const data = TEMPLATES.soundboard.defaults();
    const [cow, dog] = data.rows;
    draft.rooms = [{ name: "animals", source: "", made: { kind: "soundboard", data }, kept: true }];
    cow.voice = addRoomData("sounds", "cow", wav(1)).name;
    dog.voice = cow.voice;
    cow.voice = "";
    dropUnusedSound("cow");
    expect(draft.roomFiles).toHaveLength(1);
    dog.voice = "";
    dropUnusedSound("cow");
    expect(draft.roomFiles).toEqual([]);
  });
});
