import { describe, expect, it } from "vitest";
import { PURPLE } from "../sdk/src";
import { EXAMPLES } from "../src/examples";
import { AI_GUIDE, GUIDE, LIBRARY_NAMES, roomFromPaste } from "../src/ui/guide";

describe("the Room guide", () => {
  it("names every drum and key a room gets, and the grid's size", () => {
    for (const drum of PURPLE.room.drums as string[]) expect(GUIDE).toContain(drum);
    for (const key of PURPLE.room.keys as string[]) expect(GUIDE).toContain(`"${key}"`);
    const [w, h] = PURPLE.room.grid as [number, number];
    expect(GUIDE).toContain(`grid of ${w} by ${h} squares`);
  });

  it("describes every name `from purple import *` brings in", () => {
    for (const name of LIBRARY_NAMES) expect(GUIDE).toMatch(new RegExp(`\\b${name}\\b`));
  });

  it("ends with every starter room's Python, for an AI helper to learn from", () => {
    for (const e of EXAMPLES) expect(GUIDE).toContain(e.source.trimEnd());
  });

  it("gives an AI helper its own address", () => {
    expect(GUIDE).toContain(`https://studio.purplecomputer.org/${AI_GUIDE}`);
  });
});

describe("pasting a room from an AI helper", () => {
  const room = "from purple import *\n\ndef on_key(key):\n    say(key)\n";
  it("takes the room bare or out of its code fence", () => {
    expect(roomFromPaste(room)).toBe(room);
    expect(roomFromPaste(`Here's your room:\n\n\`\`\`python\n${room}\`\`\`\n\nHave fun!`)).toBe(room);
  });
  it("ignores anything that isn't a room", () => {
    expect(roomFromPaste("hello")).toBeNull();
    expect(roomFromPaste("print('hi')")).toBeNull();
  });
});
