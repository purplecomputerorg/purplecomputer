import { describe, expect, it } from "vitest";
import { buildEntries, PACK_FORMATS, type PackSpec } from "../sdk/src/pack";
import { upgrade } from "../src/saved";
import { shelveDraft } from "../src/shelf";
import { emptyDraft } from "../src/state";

// Studio changes on every deploy; families keep the Purple and the saves they have (studio/PACK_FORMAT.md, Format versions).
describe("compatibility with what families already have", () => {
  it("loads a draft saved before newer fields existed, and keeps what it holds", () => {
    const { roomFiles, ...old } = emptyDraft();
    const back = upgrade({ ...old, id: "pack-old", rooms: [{ name: "pets", source: "", template: { kind: "rules", rules: [] } } as never] })!;
    expect(back.id).toBe("pack-old");
    expect(back.roomFiles).toEqual(roomFiles);
    expect(back.rooms[0].made).toEqual({ kind: "rules", rules: [] });
    expect(() => shelveDraft(back)).not.toThrow();
  });

  it("asks for format 1 when a pack uses nothing newer, rooms and all, so it opens on every Purple out there", async () => {
    const spec: PackSpec = { name: "", pictures: [], letters: {}, phrases: [], words: [{ word: "cat", emoji: "🐈" }], synonyms: [], ranked: [],
      instruments: [], rooms: [{ name: "hello", source: "from purple import *\nwrite('hi')\n" }], theme: null };
    const manifest = JSON.parse(new TextDecoder().decode((await buildEntries(spec))[0].data));
    expect(manifest.format).toBe(1);
  });

  it("has Purple's whole ledger, oldest first, with a date and markers for each format", () => {
    expect(PACK_FORMATS.map((f) => f.format)).toEqual(PACK_FORMATS.map((_, i) => i + 1));
    for (const f of PACK_FORMATS) expect(f.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    for (const f of PACK_FORMATS.slice(1)) expect(f.needs.files.length + f.needs.calls.length).toBeGreaterThan(0);
  });
});
