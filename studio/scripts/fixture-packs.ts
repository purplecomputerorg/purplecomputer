// Packs built by the SDK itself for the Studio to Purple tests (tests/canvas/test_studio_to_purple.py):
// "everything" uses every file Purple reads, "everything-before" is an earlier download of it, and
// "words" holds only words, under its own id. vite-node scripts/fixture-packs.ts <out dir>
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { buildPack, cellsToOps, DEFAULT_THEME, defaults, encodeWav, type PackSpec } from "@sdk";
import { solid, tone } from "./fixtures";

const ROOM = `from purple import *

def on_key(key):
    show(picture("dot"))
    sound("ding")
    say("zorb")
`;

const cells = Array.from({ length: 4 }, (_, y) => Array.from({ length: 6 }, (_, x) => ((x + y) % 2 ? "#ff0000" : "#00aaff")));

export const EVERYTHING: PackSpec = {
  name: "The Tests' Purple",
  id: "pack-e2e00001",
  words: [
    { word: "zorb", emoji: "🐙", means: "Zorb is the octopus who lives in the tests." },
    { word: "biscuit", emoji: "dot" },
  ],
  synonyms: [{ alias: "zorbo", word: "zorb" }],
  ranked: ["zorb"],
  letters: { a: tone(440), "1": tone(660) },
  phrases: [{ text: "Hi there", clip: tone(550) }],
  pictures: [
    { name: "grandmas-dog", title: "Grandma's dog", ops: cellsToOps(cells), letters: [[1, 1, "D", "#ffffff"]], png: solid(6, 4, [255, 0, 0]) },
    { name: "palm", ops: cellsToOps([["#00ff00"]]) }, // untitled: Purple shows the file name tidied, "Palm"
  ],
  instruments: [{ name: "kitchen", title: "Kitchen", base: "marimba", params: { ...defaults("marimba"), duration: 0.05 }, icon: "🥄" }],
  rooms: [{ name: "zorb-room", source: ROOM, icon: "🐙" }],
  roomFiles: [{ kind: "images", name: "dot", data: solid(8, 8, [0, 200, 0]) }, { kind: "sounds", name: "ding", data: encodeWav(tone(880)) }],
  roomVoice: [{ text: "zorb", clip: tone(330) }],
  theme: { ...DEFAULT_THEME, base: "#0d2233" },
};
const BEFORE: PackSpec = { ...EVERYTHING, words: EVERYTHING.words.slice(0, 1) };
const WORDS: PackSpec = {
  name: "Just Words", id: "pack-e2e00002", words: [{ word: "flib", emoji: "🦑" }],
  synonyms: [], ranked: [], letters: {}, phrases: [], pictures: [], instruments: [], rooms: [], theme: null,
};

const out = process.argv[2];
if (out) {
  for (const [file, spec] of [["everything", EVERYTHING], ["everything-before", BEFORE], ["words", WORDS]] as const) {
    writeFileSync(join(out, `${file}.purplepack`), new Uint8Array(await (await buildPack(spec)).arrayBuffer()));
  }
}
