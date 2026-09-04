# Purple Studio

A parent-facing web app for putting a family's own things into their Purple Computer: photos to paint onto the Art room, a familiar voice for the letters and phrases, the words the family uses, instruments tuned from Purple's own synthesis math, and colors. Everything happens in the browser on the parent's machine. No account, no server, no upload, no AI. The one output is a `.purplepack` file, and Purple reads it.

This is a draft, not a shipping product, and nothing in it is a public commitment. It is the first web code in the repo.

## Run it

```bash
just studio            # npm install and a dev server on http://localhost:5173 (also reachable on the LAN)
just studio-test       # tsc, vitest
just studio-fixtures   # regenerate export.json and golden.json from Purple's Python (see below)
```

Or from `studio/`: `npm install`, `npm run dev`, `npm test`, `npm run build` (static output in `studio/dist/`, deployable anywhere that serves files).

Stack: Vite, TypeScript, vanilla DOM, no runtime dependencies, no backend. Tar and gzip, WAV encoding, resampling, the synth port, and the room facsimiles are all in `src/`.

## The shape

A small, calm editor in three panes:

- **Left: the pack.** A tree of what is in it, with counts, and each photo and instrument as its own entry. This is the actual file layout the parent will download.
- **Middle: the editor** for the selected thing. Every editor is headed by the real path inside the pack and a tag saying whether Purple reads it or whether it is a proposal.
- **Right: the stage.** A facsimile of the room the kid would see or hear, redrawn as the parent works: the Art room for photos and colors, the Music room for instruments and letters, Play for words and phrases. Drawn at the real 134 by 29 cell viewport with the TUI's own colors.

## What Purple does with each piece

| Piece | In Studio | On Purple |
| --- | --- | --- |
| Your own words and emoji | Words, synonyms, autocomplete picks. | Play room, exactly as the core emoji pack. |
| Your own voice | Record or upload a clip per key (A to Z, 0 to 9) and per phrase; 22050 Hz mono 16-bit WAV, trimmed and faded like Purple's own clips. | Say Letters plays the family's clip for any key recorded and Purple's for the rest; a recorded phrase is played instead of the synthesized voice whenever Purple would say those exact words. |
| Your own photos | Drop a photo, see it painted on the Art room canvas at the real 132 by 25 cell size. | The parent menu gains a Pictures entry; choosing one paints it onto the Art canvas. |
| Your own instrument sounds | Start from any of Purple's four instruments and move the numbers behind its sound with sliders while a Music room keyboard plays it. The full sample set, one note per pitch the grid can reach, is rendered from the same equations. | The Music room lists it after the built-in four; Enter cycles to it and the code panel can choose it by name. The slider numbers ship beside the samples so Purple's own synth can re-render it. |
| Your own colors | Background, canvas, and a hue per letter row, previewed on the Art frame. | Nothing yet. Emitted as a proposed `theme.json`. |
| Your own rooms or games | Out of scope. | |

`PACK_FORMAT.md` is the contract: every file, what reads it, what the installer refuses, and the command-line tool for people who would rather write a pack by hand.

## Getting a pack onto Purple

A USB stick labeled `PURPLE_UPDATE` with the `.purplepack` on it, plugged in before Purple starts. Purple mounts it read-only, checks and installs the packs, and unmounts; the rooms have them from the first screen. This works on an installed Purple and on a live-booted Key alike; from the Key the packs are reinstalled from the stick at every boot, since nothing persists there. The page in Studio spells out the steps, including the by-hand route through the parent menu's terminal. The full mechanism is in `PACK_FORMAT.md`, "Where packs live".

## Staying in sync with Purple

Studio is JavaScript all the way, and Purple is Python. Nothing is hand-copied between them; Python is the source and the JSON it exports is what the browser uses.

- **`src/purple/export.json`** is written by `scripts/export_studio.py` from `purple_tui` itself: the pack format version, viewport and canvas size, key colors, the pitch set the Music grid can reach, grid-to-pitch mapping, letter keys, the voice clip sample rate, example clip filenames, and the synth parameter defaults. The app imports it directly.
- **`tests/golden.json`** is written by the same script: reference renders from `purple_tui/synth.py` at two pitches per instrument at the defaults plus one varied parameter set each.
- **The core emoji pack** is imported straight from `../packs/core-emoji`.
- **On the Python side**, `tests/test_studio_export.py` rebuilds both files in memory on every `just test` and fails if the checked-in ones differ, with the message to run `just studio-fixtures`. So a change to `art_room.py`, `music_constants.py`, `tts.py`, `synth.py`, or the pack format cannot land without the export moving with it.
- **On the TypeScript side**, `tests/art.test.ts` and `tests/sounds.test.ts` check the few functions that must run live (canvas fitting, the row gradient, pitch naming, grid pitches, clip filenames) against the export, and `tests/synth.test.ts` holds every generator to within one sample of the golden renders. One sample of slack is the last-bit difference between libm and V8 before `int()` truncation; nothing else may differ.
- **The pack itself** is checked on the Python side: `tests/test_packs.py` builds a Studio-shaped pack and runs it through the loader, the installer's rules, the USB updater, and the CLI.

The noise source is shared too: `synth.noise` in Python and `noise` in `synth.ts` are the same mulberry32, seeded the same way, so mallet and pluck noise is bit-identical on both sides.

## Instruments, specifically

Purple's Music room plays pre-rendered samples, but those samples come from `purple_tui/synth.py`: additive partials for the marimba and glockenspiel, band-limited detuned sawtooths for the accordion, Karplus-Strong with a body resonator for the ukulele. Those four generators take keyword parameters, with the shipped sound as the defaults: bar and tube decay, the woody 4x partial, mallet noise, reed detune and harmonic rolloff, tremolo, string damping and pluck position, body resonance, bell partials, mallet ping. `src/purple/synth.ts` is a port with the same parameter names, held to the Python by the golden renders.

Sliding a control re-renders and replays the last key within a frame or two; all rendering is synchronous TypeScript at 44100 Hz. Downloading renders every reachable pitch per instrument into `content/<name>/<pitch>.wav` and writes the parameters to `content/instruments/<name>.json`. `scripts/purplepack.py render` produces the same files from the Python for a pack that left them out.

## Verified

- A pack emitted by `src/pack.ts` was fed to `PackInstaller.install_pack` and then `ContentManager.load_all` in a temp packs dir: it installed, the words resolved, and the WAV read back as 22050 Hz mono 16-bit with Python's `wave` module.
- Screenshots of every view and of a photo dropped into the facsimile were taken in headless Firefox. A 1146 by 1258 photo landed at 46 by 25 cells, matching the Python sizing.
- The export surfaced a real discrepancy: the shipped instrument directories hold a few stale files (`cs7`, the `gs` notes) that no grid cell can reach. Studio emits the 66 reachable pitches.
- The loader, installer, updater, and CLI paths are covered by `tests/test_packs.py`, including the format gate, the replace-on-reinstall behavior, and the refusal of code, symlinks, off-canvas ops, wrong sample rates, and unknown synth parameters.

## Known differences and cuts

- Photo downsampling is a box filter, not Pillow's Lanczos. At the shrink ratios involved (30x or more) the two agree to within a shade.
- Instrument samples are WAV, not OGG, because browsers do not ship an OGG encoder and `music_room._find_sound` already falls back to `.wav`. A marimba set is about 3 MB; a glockenspiel about 9 MB.
- The shipped `.ogg` files in `packs/core-sounds` were rendered before the generators moved to the shared noise source and to a time-based fade on the ukulele, so they differ from a fresh `generate_sounds.py` run in the first few milliseconds of noise and the last few of the fade. Regenerating them is a `just`-and-ffmpeg step, not done in this pass.
- Percussion (the number row) is shared by every instrument and is not editable here.
- Purple reads packs when it starts. A stick plugged in while Purple is running is installed at once but shows up at the next start.
- Nothing is saved between browser sessions. Closing the tab loses the draft; the page warns once there is something in it.
- Microphone recording needs a secure context, so over plain http on a LAN the Record button reports the mic unavailable; uploading a file still works. An SSH tunnel to localhost fixes it.

## Not done, on purpose

- **Theme.** `theme.json` is written and not read. The letter-row colors are shared truth with the printed keycap stickers, so changing them per family is a product decision first.
- **Rooms.** A family's own rooms or games would need a room format that survives the move off the Textual TUI: a small declarative file (keys, what each shows, says, and plays) that Purple interprets, rather than a script Purple runs. Packs stay data. Nothing here is stubbed.
- **A running app noticing a new pack.** Cheap to add as a stat on the packs directory at room switch; left out until the boot-time path has been seen on hardware.
- **Regenerating the shipped OGGs** from the parameterized synth, which needs ffmpeg and a listen.
