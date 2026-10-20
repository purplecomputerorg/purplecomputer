import { describe, expect, it } from "vitest";
import { buildEntries, type PackSpec } from "../sdk/src/pack";
import { fixedSays } from "../sdk/src/says";

describe("a room's fixed lines", () => {
  it("finds say() with one plain string, in either quote and with escapes, once per clip name", () => {
    const source = [
      `say("Pick a seed with a number, then press space to plant it.")`,
      `purple.say('It\\'s a "sunflower"!')`,
      `say(r"C:\\path")`,
      `say("Hi")`, `say("hi")`,
      `say('caf\\u00e9')`,
    ].join("\n");
    expect(fixedSays(source)).toEqual(["Pick a seed with a number, then press space to plant it.", `It's a "sunflower"!`, "C:\\path", "hi", "café"]);
  });

  it("leaves lines built while the room runs to Purple's own voice", () => {
    expect(fixedSays(`say(f"You planted {n}")\nsay("You have " + str(n))\nsay(name)\nsay("")\nmysay("no")\nsay("\\N{BULLET}")`)).toEqual([]);
  });

  it("cuts a line where Purple does and skips one too long to name a file", () => {
    expect(fixedSays(`say("${"a".repeat(250)}")`)).toEqual(["a".repeat(200)]);
    expect(fixedSays(`say("${"🌻".repeat(100)}")`)).toEqual([]);
  });

  it("packs each line under content/room-voice/, named the way Purple looks it up", async () => {
    const spec: PackSpec = { name: "", pictures: [], letters: {}, phrases: [], words: [], synonyms: [], ranked: [], instruments: [], rooms: [], theme: null,
      roomVoice: [{ text: "Good job, Maya!", clip: { samples: new Float32Array([0, 0.5]), rate: 22050 } }] };
    expect((await buildEntries(spec)).map((e) => e.path)).toContain("content/room-voice/good_job,_maya!.wav");
  });
});
