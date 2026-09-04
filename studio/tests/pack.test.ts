import { describe, expect, it } from "vitest";
import { buildEntries, manifest } from "../src/pack";
import { SAMPLE_PITCHES } from "../src/purple/sounds";
import { defaults } from "../src/purple/synth";
import type { Draft } from "../src/state";

const base: Draft = { familyName: "", pictures: [], letters: {}, phrases: [], words: [], synonyms: [], ranked: [], instruments: [], theme: null };

describe("pack assembly", () => {
  it("names the pack after the family and keeps the manifest loader-shaped", () => {
    expect(manifest({ ...base, familyName: "The Nathansons" })).toEqual({
      id: "the-nathansons-pack", name: "The Nathansons' Purple", version: "1.0.0", type: "emoji", format: 1, description: "Made with Purple Studio.",
    });
    expect(manifest(base).id).toBe("our-family-pack");
  });

  it("renders an instrument into one file per reachable pitch plus its numbers", async () => {
    const d: Draft = { ...base, instruments: [{ name: "kitchen", base: "marimba", params: { ...defaults("marimba"), duration: 0.2 } }] };
    const entries = await buildEntries(d);
    const paths = entries.map((e) => e.path);
    expect(paths.filter((p) => p.startsWith("content/kitchen/") && p.endsWith(".wav")).length).toBe(SAMPLE_PITCHES.length);
    expect(paths).toContain("content/kitchen/cs4.wav");
    expect(paths).toContain("content/instruments/kitchen.json");
    const wav = entries.find((e) => e.path === "content/kitchen/a4.wav")!.data;
    expect(new DataView(wav.buffer).getUint32(24, true)).toBe(44100);
  });

  it("emits only the emoji files the loader reads when that is all there is", async () => {
    const d: Draft = { ...base, words: [{ word: "octopus", emoji: "🐙" }], ranked: ["octopus"] };
    expect((await buildEntries(d)).map((e) => e.path)).toEqual(["manifest.json", "content/emoji.json", "content/rankings.txt"]);
  });
});
