# Purple Studio (v1 draft)

A parent-facing web app for putting a family's own things into their Purple Computer: photos to draw on in the Art room, a familiar voice for the letters and phrases, the words the family uses, instruments tuned from Purple's own synthesis math, and colors. Everything happens in the browser on the parent's machine. No account, no server, no upload, no AI. The one output is a `.purplepack` file.

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
- **Middle: the editor** for the selected thing. Every editor is headed by the real path inside the pack and a tag saying whether Purple reads it today or whether it is a proposal.
- **Right: the stage.** A facsimile of the room the kid would see or hear, redrawn as the parent works: the Art room for photos and colors, the Music room for instruments and letters, Play for words and phrases. Drawn at the real 134 by 29 cell viewport with the TUI's own colors.

## Staying in sync with Purple

Studio is JavaScript all the way, and Purple is Python. Nothing is hand-copied between them; Python is the source and the JSON it exports is what the browser uses.

- **`src/purple/export.json`** is written by `scripts/export_studio.py` from `purple_tui` itself: viewport and canvas size, key colors, the pitch set the Music grid can reach, grid-to-pitch mapping, letter keys, the voice clip sample rate, example clip filenames, and the synth parameter defaults. The app imports it directly.
- **`tests/golden.json`** is written by the same script: reference renders from `purple_tui/synth.py` at two pitches per instrument at the defaults plus one varied parameter set each.
- **The core emoji pack** is imported straight from `../packs/core-emoji`.
- **On the Python side**, `tests/test_studio_export.py` rebuilds both files in memory on every `just test` and fails if the checked-in ones differ, with the message to run `just studio-fixtures`. So a change to `art_room.py`, `music_constants.py`, `tts.py`, or `synth.py` cannot land without the export moving with it.
- **On the TypeScript side**, `tests/art.test.ts` and `tests/sounds.test.ts` check the few functions that must run live (canvas fitting, the row gradient, pitch naming, grid pitches, clip filenames) against the export, and `tests/synth.test.ts` holds every generator to within one sample of the golden renders. One sample of slack is the last-bit difference between libm and V8 before `int()` truncation; nothing else may differ.

The noise source is shared too: `synth.noise` in Python and `noise` in `synth.ts` are the same mulberry32, seeded the same way, so mallet and pluck noise is bit-identical on both sides.

## What it does with each survey piece

| Piece | Built | What Purple reads today |
| --- | --- | --- |
| Your own words and emoji | Fully. Words, synonyms, autocomplete picks. | All of it. Emitted in the exact core-emoji format. |
| Your own photos | Fully. Drop a photo, see it painted on the Art room canvas at the real 132 by 25 cell size. | Nothing. Emitted as a proposed `content/pictures/` layout. |
| Your own voice | Fully. Record or upload a clip per key (A to Z, 0 to 9) and per phrase. 22050 Hz mono 16-bit WAV, trimmed and faded like Purple's own clips. | Nothing. Emitted in the exact `core-sounds` layout as a proposal. |
| Your own instrument sounds | Fully. Start from any of Purple's four instruments and move the numbers behind its sound with sliders while a Music room keyboard plays it. The full sample set, one note per pitch the grid can reach, is rendered from the same equations. | Nothing. Proposed layout, plus the slider values as JSON. |
| Your own colors | Lighter. Background, canvas, and a hue per letter row, previewed on the Art frame. | Nothing. Proposed `theme.json`. |
| Your own rooms or games | Out of scope. Not stubbed. | |

`PACK_FORMAT.md` is the write-up of the real format and the proposed additions.

## Instruments, specifically

Purple's Music room plays pre-rendered samples, but those samples come from `purple_tui/synth.py`: additive partials for the marimba and glockenspiel, band-limited detuned sawtooths for the accordion, Karplus-Strong with a body resonator for the ukulele. Those four generators now take keyword parameters, with the shipped sound as the defaults: bar and tube decay, the woody 4x partial, mallet noise, reed detune and harmonic rolloff, tremolo, string damping and pluck position, body resonance, bell partials, mallet ping. `src/purple/synth.ts` is a port with the same parameter names, held to the Python by the golden renders.

Sliding a control re-renders and replays the last key within a frame or two; all rendering is synchronous TypeScript at 44100 Hz. Downloading renders every reachable pitch per instrument into `content/<name>/<pitch>.wav` and writes the parameters to `content/instruments/<name>.json`.

## Delivery, honestly

- On a **permanently installed** Purple, `~/.purple/packs/<id>/` is honored by the runtime. There is no file manager or browser on the machine, so the pack goes in through the parent menu's terminal. The "Getting it onto Purple" page gives the commands.
- On a **live-booted Key**, nothing persists: `$HOME` is tmpfs, the ISO is read-only, and `flash-to-usb.sh` zeroes persistence signatures on purpose. A pack copied onto the Key does nothing. The page says so.
- The `PURPLE_UPDATE` second-stick channel (`config/udev/99-purple-update.rules`, `config/systemd/purple-usb-update@.service`) is wired to run `purple_tui.usb_updater`, which does not exist. Studio does not describe it as a feature.

## Also verified (2026-09-03)

- A pack emitted by `src/pack.ts` was fed to `PackInstaller.install_pack` and then `ContentManager.load_all` in a temp packs dir: it installed, `octopus`, the synonym `octo`, and an overridden `cat` all resolved, and the WAV read back as 22050 Hz mono 16-bit with Python's `wave` module.
- Screenshots of every view and of a photo dropped into the facsimile were taken in headless Firefox. A 1146 by 1258 photo landed at 46 by 25 cells, matching the Python sizing.
- The export surfaced a real discrepancy: the shipped instrument directories hold a few stale files (`cs7`, the `gs` notes) that no grid cell can reach. Studio emits the 66 reachable pitches.

## Known differences and cuts

- Photo downsampling is a box filter, not Pillow's Lanczos. At the shrink ratios involved (30x or more) the two agree to within a shade.
- Instrument samples are WAV, not OGG, because browsers do not ship an OGG encoder and `music_room._find_sound` already falls back to `.wav`. A marimba set is about 3 MB; a glockenspiel about 9 MB.
- The shipped `.ogg` files in `packs/core-sounds` were rendered before the generators moved to the shared noise source and to a time-based fade on the ukulele, so they differ from a fresh `generate_sounds.py` run in the first few milliseconds of noise and the last few of the fade. Regenerating them is a `just`-and-ffmpeg step, not done in this pass.
- Percussion (the number row) is shared by every instrument and is not editable here.
- Nothing is saved between browser sessions. Closing the tab loses the draft; the page warns once there is something in it.
- Microphone recording needs a secure context, so over plain http on a LAN the Record button reports the mic unavailable; uploading a file still works. An SSH tunnel to localhost fixes it.

## Obvious next steps (none of them promised)

1. `purple_tui/usb_updater.py`: the second-stick channel is already wired at the udev and systemd level and is the only path that could work on a live-booted Key. Since `$HOME` is tmpfs it would re-install the pack on every boot from the stick, which is fine.
2. Loader: read `content/letters/`, `content/voice/`, and instrument directories from user packs, the same way `letters-kid/` is preferred over `letters/` today.
3. Replace `secret_photo.OPS` with a reader for `content/pictures/`.
4. Let Purple render an instrument from `content/instruments/<name>.json` with `synth.py` on first load, so the shipped sound is always Python's and the WAVs become optional.
5. A `format` version in the manifest, so Studio targets a spec rather than a commit.
