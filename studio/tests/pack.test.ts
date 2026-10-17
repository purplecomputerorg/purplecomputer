import { describe, expect, it } from "vitest";
import { buildEntries, manifest, roomTitle, type PackSpec } from "../sdk/src/pack";
import { SAMPLE_PITCHES } from "../sdk/src/purple/sounds";
import { defaults } from "../sdk/src/purple/synth";
import { gunzip, gzip, tar, untar } from "../sdk/src/tar";
import { buildPack, openPack, packSpec } from "../src/pack";
import type { Draft } from "../src/state";
import roomLibrary from "../../purple_tui/roomkit/purple.py?raw";

const base: PackSpec = { name: "", pictures: [], letters: {}, phrases: [], words: [], synonyms: [], ranked: [], instruments: [], rooms: [], theme: null };
const draftBase: Draft = { ...base, id: "pack-test", letters: {}, pictures: [], rooms: [], colors: {} };

describe("pack assembly", () => {
  it("ranks a family's own words after anything ranked by hand, leaving Purple's ranked words alone", async () => {
    const d: Draft = { ...draftBase, words: [{ word: "biscuit", emoji: "🐶", kept: true }, { word: "cat", emoji: "🐈", kept: true }, { word: "tractor", emoji: "🚜", kept: true }], ranked: ["tractor"] };
    expect((await packSpec(d)).ranked).toEqual(["tractor", "biscuit"]);
  });

  it("downloads only what the family added, while Studio's Purple plays what they're trying too", async () => {
    const d: Draft = { ...draftBase, words: [{ word: "biscuit", emoji: "🐶", kept: true }, { word: "zorbo", emoji: "🐙" }] };
    expect((await packSpec(d)).words.map((w) => w.word)).toEqual(["biscuit"]);
    expect((await packSpec(d, true)).words.map((w) => w.word)).toEqual(["biscuit", "zorbo"]);
  });

  it("installs under the pack's own id whatever the file is called, and keeps the manifest loader-shaped", () => {
    expect(manifest({ name: "Purple 2026-10-17", id: "pack-1a2b3c4d" })).toEqual({
      id: "pack-1a2b3c4d", name: "Purple 2026-10-17", version: "1.0.0", type: "emoji", format: 1, description: "Made with Purple Studio.",
    });
    expect(manifest({ name: "Purple 2026-10-17" }).id).toBe("purple-2026-10-17");
    expect(manifest(base).id).toBe("purple");
  });

  it("reopens a downloaded Purple Pack as what was added, under the same id", async () => {
    const clip = { samples: new Float32Array([0, 0.5, -0.5, 0.25]), rate: 22050 };
    const d: Draft = {
      ...draftBase, id: "pack-1a2b3c4d", name: "grandmas-pack",
      words: [{ word: "biscuit", emoji: "🐶", kept: true }, { word: "zorbo", emoji: "🐙" }],
      synonyms: [{ alias: "doggo", word: "dog", kept: true }],
      ranked: ["tractor"],
      letters: { a: { clip, kept: true }, b: { clip } },
      phrases: [{ text: "hi there", clip, kept: true }],
    };
    const back = await openPack(await buildPack(undefined, d));
    expect(back.id).toBe("pack-1a2b3c4d");
    expect(back.name).toBe("grandmas-pack");
    expect(back.words).toEqual([{ word: "biscuit", emoji: "🐶", kept: true }]);
    expect(back.synonyms).toEqual([{ alias: "doggo", word: "dog", kept: true }]);
    expect(back.ranked).toEqual(["tractor"]);
    expect(Object.keys(back.letters)).toEqual(["a"]);
    expect(back.phrases.map((p) => p.text)).toEqual(["hi there"]);
    expect(back.letters.a.clip.rate).toBe(22050);
    [...back.phrases[0].clip.samples].forEach((s, i) => expect(s).toBeCloseTo(clip.samples[i], 4));
  });

  it("says why a file that isn't a Studio Purple Pack can't be opened", async () => {
    const handMade = await buildPack(undefined, { ...draftBase, words: [{ word: "cat", emoji: "🐈", kept: true }] });
    const entries = untar(await gunzip(new Uint8Array(await handMade.arrayBuffer()))).filter((e) => e.path !== "studio.json");
    await expect(openPack(new Blob([(await gzip(tar(entries))) as BlobPart]))).rejects.toThrow(/studio.json is missing/);
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

  it("writes a room's Python next to the blocks it came from, and the library it runs on", async () => {
    const source = "from purple import *\nshow('🐄')";
    const spec: PackSpec = { ...base, rooms: [{ name: "farm", source, blocks: { blocks: { languageVersion: 0, blocks: [] } } }] };
    const entries = await buildEntries(spec);
    expect(entries.map((e) => e.path)).toEqual(["manifest.json", "content/rooms/purple.py", "content/rooms/farm.py", "content/rooms/farm.blocks.json"]);
    expect(new TextDecoder().decode(entries[1].data)).toBe(roomLibrary);
    expect(new TextDecoder().decode(entries[2].data)).toBe(source + "\n");
  });

  it("refuses a room name Purple would not load, and titles rooms the way Purple does", async () => {
    await expect(buildEntries({ ...base, rooms: [{ name: "Big Farm", source: "" }] })).rejects.toThrow(/lowercase/);
    await expect(buildEntries({ ...base, rooms: [{ name: "purple", source: "" }] })).rejects.toThrow(/not purple/);
    expect(roomTitle("dinosaur-trivia")).toBe("Dinosaur Trivia");
    expect(roomTitle("snake2go_fast")).toBe("Snake2Go Fast");
  });
});
