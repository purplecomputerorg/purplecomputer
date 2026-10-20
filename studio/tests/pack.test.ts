import { describe, expect, it } from "vitest";
import { buildEntries, manifest, roomTitle, type PackSpec } from "../sdk/src/pack";
import { SAMPLE_PITCHES } from "../sdk/src/purple/sounds";
import { defaults } from "../sdk/src/purple/synth";
import { gzip, tar } from "../sdk/src/tar";
import { buildPack, openPack, packChanges, packSpec } from "../src/pack";
import { scaleCrop } from "../src/photo";
import type { Draft } from "../src/state";
import roomLibrary from "../../purple_tui/roomkit/purple.py?raw";

const base: PackSpec = { name: "", pictures: [], letters: {}, phrases: [], words: [], synonyms: [], ranked: [], instruments: [], rooms: [], theme: null };
const draftBase: Draft = { ...base, id: "pack-test", letters: {}, pictures: [], rooms: [], roomFiles: [], colors: {} };

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

  it("keeps a picture's photo outside content/, where Purple never reads", async () => {
    const pic = { name: "dog", ops: [], png: new Uint8Array([1]), source: new Uint8Array([2]) };
    const paths = (await buildEntries({ ...base, pictures: [pic] })).map((e) => e.path);
    expect(paths).toEqual(["manifest.json", "content/pictures/dog.json", "content/pictures/dog.png", "studio/pictures/dog.jpg"]);
  });

  it("scales a crop with the photo it was made on", () => {
    expect(scaleCrop({ x: 100, y: 40, w: 1000, h: 400 }, 0.5)).toEqual({ x: 50, y: 20, w: 500, h: 200 });
    expect(scaleCrop(undefined, 0.5)).toBeUndefined();
  });

  const packOf = async (files: Record<string, string | Uint8Array>) =>
    new Blob([(await gzip(tar(Object.entries(files).map(([path, data]) => ({ path, data: typeof data === "string" ? new TextEncoder().encode(data) : data }))))) as BlobPart]);

  it("opens a pack made by hand or by an AI helper as its rooms, with their pictures and sounds", async () => {
    const png = new Uint8Array([137, 80, 78, 71]);
    const back = await openPack(await packOf({
      "manifest.json": JSON.stringify({ id: "pack-cat", name: "Our Cat", version: "1.0.0", type: "emoji" }),
      "content/rooms/cat.py": "from purple import *\nshow(picture('mochi'))\n",
      "content/rooms/purple.py": "# a library",
      "content/images/mochi.png": png,
      "content/images/Not OK.png": png,
      "content/sounds/purr.wav": png,
    }));
    expect([back.id, back.name]).toEqual(["pack-cat", "Our Cat"]);
    expect(back.rooms).toEqual([{ name: "cat", source: "from purple import *\nshow(picture('mochi'))\n", made: null, kept: true }]);
    expect(back.roomFiles.map((f) => [f.kind, f.name, f.data])).toEqual([["images", "mochi", png], ["sounds", "purr", png]]);
    const paths = (await buildEntries(await packSpec(back))).map((e) => e.path);
    expect(paths).toEqual(expect.arrayContaining(["content/rooms/cat.py", "content/images/mochi.png", "content/sounds/purr.wav"]));
  });

  it("says why a file with nothing Studio can open can't be opened", async () => {
    const words = await packOf({ "manifest.json": JSON.stringify({ id: "w", name: "W", version: "1.0.0", type: "emoji" }), "content/emoji.json": "{}" });
    await expect(openPack(words)).rejects.toThrow(/studio.json is missing/);
  });

  it("keeps a room's pictures and sounds when a Studio pack is reopened", async () => {
    const png = new Uint8Array([1, 2, 3]);
    const d: Draft = { ...draftBase, rooms: [{ name: "pets", source: "", made: null, kept: true }], roomFiles: [{ kind: "images", name: "rex", data: png, kept: true }] };
    const back = await openPack(await buildPack(undefined, d));
    expect(back.roomFiles).toEqual([{ kind: "images", name: "rex", data: png, kept: true }]);
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

  it("writes a picture's letters beside its paint, and leaves them out when there are none", async () => {
    const spec: PackSpec = { ...base, pictures: [
      { name: "t-rex", title: "T. rex", ops: [[0, 0, "#00ff00"]], letters: [[1, 0, "T", "#ffffff"]] },
      { name: "palm", ops: [[0, 0, "#00ff00"]], letters: [] },
    ] };
    const read = async (path: string) => JSON.parse(new TextDecoder().decode((await buildEntries(spec)).find((e) => e.path === path)!.data));
    expect(await read("content/pictures/t-rex.json")).toEqual({ name: "T. rex", ops: [[0, 0, "#00ff00"]], letters: [[1, 0, "T", "#ffffff"]] });
    expect(await read("content/pictures/palm.json")).toEqual({ name: "palm", ops: [[0, 0, "#00ff00"]] });
  });

  it("writes a room's Python next to the rules it came from, and the library it runs on", async () => {
    const source = "from purple import *\nshow('🐄')";
    const spec: PackSpec = { ...base, rooms: [{ name: "farm", source, made: { kind: "rules", rules: [] } }] };
    const entries = await buildEntries(spec);
    expect(entries.map((e) => e.path)).toEqual(["manifest.json", "content/rooms/purple.py", "content/rooms/farm.py", "content/rooms/farm.studio.json"]);
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

describe("updating Studio's Purple", () => {
  const entries = (files: Record<string, string>) => Object.entries(files).map(([path, data]) => ({ path, data: new TextEncoder().encode(data) }));
  const paths = (p: { files: [string, Uint8Array][] }) => p.files.map(([path]) => path);
  const before = { "manifest.json": "{}", "content/emoji.json": '{"dog":"🐶"}', "content/pictures/dog.png": "png" };
  const last = { id: "pack-1", files: new Map(entries(before).map((e) => [e.path, e.data])) };

  it("sends nothing when nothing changed, and only the changed file after an edit", () => {
    expect(packChanges("pack-1", entries(before), last)).toEqual({ id: "pack-1", fresh: false, files: [], removed: [] });
    expect(paths(packChanges("pack-1", entries({ ...before, "content/emoji.json": '{"dog":"🐕"}' }), last))).toEqual(["content/emoji.json"]);
  });

  it("names the files a removed piece leaves behind", () => {
    const pack = packChanges("pack-1", entries({ "manifest.json": "{}", "content/emoji.json": '{"dog":"🐶"}' }), last);
    expect(pack.removed).toEqual(["content/pictures/dog.png"]);
    expect(pack.files).toEqual([]);
  });

  it("sends a whole pack when it's another pack, or Purple may have nothing", () => {
    const now = entries({ "manifest.json": "{}", "content/emoji.json": '{"dog":"🐶"}' });
    for (const pack of [packChanges("pack-2", now, last), packChanges("pack-1", now, { ...last, id: "" })]) {
      expect(pack.fresh).toBe(true);
      expect(paths(pack)).toEqual(["manifest.json", "content/emoji.json"]);
      expect(pack.removed).toEqual([]);
    }
  });
});
