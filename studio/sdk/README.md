# Purple pack SDK

The part of Studio that knows nothing about Studio: a TypeScript library for building a `.purplepack` and for running the same math Purple runs. No DOM, no dependencies, no network. Anyone building their own Purple tool, a command-line packer, a different editor, a script that turns a spreadsheet of words into a pack, can import this and skip the UI.

It is a directory, not a published package. Import it as `@sdk` inside Studio (a Vite alias and a `tsconfig` path both point at `sdk/src`), or copy `sdk/src` into another project; the only build-time need is JSON imports and one `?raw` text import for the core word list.

## What is in it

| Module | What it gives you |
| --- | --- |
| `pack` | `buildPack(spec)` and `buildEntries(spec)`: a `PackSpec` (family name, words, synonyms, rankings, letter and phrase clips, pictures, instruments, rooms, theme) in, a gzipped tar out, in the layout Purple's installer accepts. `manifest`, `packId`, `slug`. |
| `room` | The room language: `parse`, `Runner`, `Host`, `TraceHost`, `formatValue`, `parseNote`, and the limits. The same interpreter as `purple_tui/room_program.py`, held to it by `tests/room.test.ts`. |
| `purple/synth` | Purple's four instrument generators with every keyword parameter, and `renderNote(base, params, freq)`. Held to the Python to within one sample by `tests/synth.test.ts`. |
| `purple/art` | Viewport and canvas sizes, `fitToCanvas`, `generateRowGradient`, key colors, `cellsToOps`. |
| `purple/sounds` | Letter keys, clip sample rate, `voiceClipFilename`, `pitchFilename`, `pitchFor`, `noteFrequency`, the reachable pitch set. |
| `purple/core` | The core emoji pack, imported from the repo. |
| `purple/export.json` | Every constant above, written by `scripts/export_studio.py` from `purple_tui`. Regenerate with `just studio-fixtures`. |
| `wav` | `encodeWav`, `tidy`, `normalize`, `peak` for mono 16-bit clips. |
| `tar` | `tar`, `gzip`. |

## A pack in twenty lines

```ts
import { buildPack, defaults, parse, type PackSpec } from "@sdk";

const spec: PackSpec = {
  familyName: "The Nathansons",
  words: [{ word: "octopus", emoji: "🐙" }],
  synonyms: [{ alias: "octo", word: "octopus" }],
  ranked: ["octopus"],
  letters: {}, phrases: [], pictures: [], theme: null,
  instruments: [{ name: "kitchen", base: "marimba", params: { ...defaults("marimba"), wood: 0.9 } }],
  rooms: [{ program: parse({
    name: "farm", title: "Farm",
    rules: [{ when: { event: "key", key: "c" }, do: [{ do: "show", text: "🐄" }, { do: "say", text: "cow" }, { do: "play", note: "C4" }] }],
  }) }],
};
const blob = await buildPack(spec, (msg) => console.log(msg));
```

`buildPack` renders the instrument's 66 notes with the synth port as it goes, so it is async and reports progress.

## Running a room outside Purple

```ts
import { Runner, parse, type Host } from "@sdk";

const host: Host = {
  show: (t) => console.log("show", t), add: (t) => console.log("add", t), say: (t) => console.log("say", t),
  play: (note, inst) => console.log("play", note, inst), drum: (n) => console.log("drum", n),
  clear: () => console.log("clear"), background: (c) => console.log("bg", c),
  wait: (s) => new Promise((r) => setTimeout(r, s * 1000)),
};
const runner = new Runner(parse(program), host);
await runner.fire("start");
await runner.fire("key", "c");
```

Studio's stage does exactly this with a canvas, Web Audio, and the browser's speech voice. Purple does it with Textual, pygame, and Piper. The program is the same file.

## Staying honest

- `export.json` is generated. Do not edit it; change Purple and run `just studio-fixtures`.
- `tests/golden.json` and `tests/room-golden.json` are Python's renders and traces. The SDK tests fail when the port drifts.
- The pack layout has a `format` version in the manifest. Purple skips packs newer than it reads.
