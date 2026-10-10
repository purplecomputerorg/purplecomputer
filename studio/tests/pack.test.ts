import { describe, expect, it } from "vitest";
import { buildEntries, manifest, roomTitle, type PackSpec } from "../sdk/src/pack";
import { SAMPLE_PITCHES } from "../sdk/src/purple/sounds";
import { defaults } from "../sdk/src/purple/synth";

const base: PackSpec = { familyName: "", pictures: [], letters: {}, phrases: [], words: [], synonyms: [], ranked: [], instruments: [], rooms: [], theme: null };

describe("pack assembly", () => {
  it("names the pack after the family and keeps the manifest loader-shaped", () => {
    expect(manifest({ familyName: "The Nathansons" })).toEqual({
      id: "the-nathansons-pack", name: "The Nathansons' Purple", version: "1.0.0", type: "emoji", format: 1, description: "Made with Purple Studio.",
    });
    expect(manifest(base).id).toBe("our-family-pack");
  });

  it("renders an instrument into one file per reachable pitch plus its numbers", async () => {
    const spec: PackSpec = { ...base, instruments: [{ name: "kitchen", base: "marimba", params: { ...defaults("marimba"), duration: 0.2 } }] };
    const entries = await buildEntries(spec);
    const paths = entries.map((e) => e.path);
    expect(paths.filter((p) => p.startsWith("content/kitchen/") && p.endsWith(".wav")).length).toBe(SAMPLE_PITCHES.length);
    expect(paths).toContain("content/kitchen/cs4.wav");
    expect(paths).toContain("content/instruments/kitchen.json");
    const wav = entries.find((e) => e.path === "content/kitchen/a4.wav")!.data;
    expect(new DataView(wav.buffer).getUint32(24, true)).toBe(44100);
  });

  it("emits only the emoji files the loader reads when that is all there is", async () => {
    const spec: PackSpec = { ...base, words: [{ word: "octopus", emoji: "🐙" }], ranked: ["octopus"] };
    expect((await buildEntries(spec)).map((e) => e.path)).toEqual(["manifest.json", "content/emoji.json", "content/rankings.txt"]);
  });

  it("writes a room's Python next to the blocks it came from", async () => {
    const source = "from purple import *\nshow('🐄')";
    const spec: PackSpec = { ...base, rooms: [{ name: "farm", source, blocks: { blocks: { languageVersion: 0, blocks: [] } } }] };
    const entries = await buildEntries(spec);
    expect(entries.map((e) => e.path)).toEqual(["manifest.json", "content/rooms/farm.py", "content/rooms/farm.blocks.json"]);
    expect(new TextDecoder().decode(entries[1].data)).toBe(source + "\n");
  });

  it("refuses a room name Purple would not load, and titles rooms the way Purple does", async () => {
    await expect(buildEntries({ ...base, rooms: [{ name: "Big Farm", source: "" }] })).rejects.toThrow(/lowercase/);
    expect(roomTitle("dinosaur-trivia")).toBe("Dinosaur Trivia");
    expect(roomTitle("snake2go_fast")).toBe("Snake2Go Fast");
  });
});
