# Purple pack SDK

The part of Studio that knows nothing about Studio: a TypeScript library for building a `.purplepack` and for running the same math Purple runs. No DOM, no dependencies, no network. Anyone building their own Purple tool, a command-line packer, a different editor, a script that turns a spreadsheet of words into a pack, can import this and skip the UI.

It is a directory, not a published package. Import it as `@sdk` inside Studio (a Vite alias and a `tsconfig` path both point at `sdk/src`), or copy `sdk/src` into another project; the only build-time need is JSON imports and one `?raw` text import for the core word list.

## What is in it

| Module | What it gives you |
| --- | --- |
| `pack` | `buildPack(spec)` and `buildEntries(spec)`: a `PackSpec` (family name, words, synonyms, rankings, letter and phrase clips, pictures, instruments, rooms, theme) in, a gzipped tar out, in the layout Purple's installer accepts, with the room library beside any rooms. `manifest`, `packId`, `slug`. |
| `purple/synth` | Purple's four instrument generators with every keyword parameter, and `renderNote(base, params, freq)`. Held to the Python to within one sample by `tests/synth.test.ts`. |
| `purple/art` | Viewport and canvas sizes, `fitToCanvas`, `generateRowGradient`, key colors, `cellsToOps`. |
| `purple/sounds` | `parseNote`, letter keys, clip sample rate, `voiceClipFilename`, `pitchFilename`, `pitchFor`, `noteFrequency`, the reachable pitch set. |
| `purple/core` | The core emoji pack, imported from the repo. |
| `purple/export.json` | Every constant above, written by `scripts/export_studio.py` from `purple_tui`. Regenerate with `just studio-fixtures`. |
| `wav` | `encodeWav`, `tidy`, `normalize`, `peak` for mono 16-bit clips. |
| `tar` | `tar`, `gzip`. |

## A pack in twenty lines

```ts
import { buildPack, defaults, type PackSpec } from "@sdk";

const spec: PackSpec = {
  name: "nathanson-purple",
  words: [{ word: "octopus", emoji: "🐙" }],
  synonyms: [{ alias: "octo", word: "octopus" }],
  ranked: ["octopus"],
  letters: {}, phrases: [], pictures: [], theme: null,
  instruments: [{ name: "kitchen", base: "marimba", params: { ...defaults("marimba"), wood: 0.9 } }],
  rooms: [{ name: "farm", source: 'from purple import *\n\ndef on_key(key):\n    show("🐄")\n    say("cow")\n' }],
};
const blob = await buildPack(spec, (msg) => console.log(msg));
```

`buildPack` renders the instrument's 66 notes with the synth port as it goes, so it is async and reports progress.

## Running a room outside Purple

A room is Python that imports `purple_tui/roomkit/purple.py`. `roomkit/runner.py`'s `serve(recv_line, send_line)` runs one: the first line in is the start event, carrying the room and the library, and after that each event line gets one reply line back; `guides/family-rooms.md` has the protocol. Purple's host is `purple_tui/canvas/rooms/family_room.py`. Studio runs that same host in its live Purple, with the room in a Web Worker (`studio/src/rooms/`).

## Staying honest

- `export.json` is generated. Do not edit it; change Purple and run `just studio-fixtures`.
- `tests/golden.json` holds Python's synth renders. The SDK tests fail when the port drifts.
- Rooms are Python, run by `purple_tui/roomkit/purple.py` itself, so the SDK only packs them (`content/rooms/<name>.py`) along with that file (`content/rooms/purple.py`).
- The pack layout has a `format` version in the manifest. Purple skips packs newer than it reads.
