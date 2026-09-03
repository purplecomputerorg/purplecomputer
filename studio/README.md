# Purple Studio (v1 draft)

A parent-facing web app for putting a family's own things into their Purple Computer: photos to draw on in the Art room, a familiar voice for the letters and phrases, the words the family uses, instruments tuned from Purple's own synthesis math, and colors. Everything happens in the browser on the parent's machine. No account, no server, no upload, no AI. The one output is a `.purplepack` file.

This is a sketch to feel out the idea, not a shipping product, and nothing in it is a public commitment. It is the first web code in the repo.

## Run it

```bash
just studio          # npm install and a dev server on http://localhost:5173 (also reachable on the LAN)
just studio-test     # tsc, vitest
```

Or from `studio/`: `npm install`, `npm run dev`, `npm test`, `npm run build` (static output in `studio/dist/`, deployable anywhere that serves files).

Stack: Vite, TypeScript, vanilla DOM, no runtime dependencies. Tar and gzip, WAV encoding, resampling, the synth port, and the room facsimiles are all in `src/`. The core emoji pack is imported straight from `../packs/core-emoji` so Studio cannot drift from what Purple ships.

## The shape

A small, calm editor in three panes:

- **Left: the pack.** A tree of what is in it, with counts, and each photo and instrument as its own entry. This is the actual file layout the parent will download.
- **Middle: the editor** for the selected thing. Every editor is headed by the real path inside the pack and a tag saying whether Purple reads it today or whether it is a proposal.
- **Right: the stage.** A facsimile of the room the kid would see or hear, redrawn as the parent works: the Art room for photos and colors, the Music room for instruments and letters, Play for words and phrases. Drawn at the real 134 by 29 cell viewport with the TUI's own colors.

## What it does with each survey piece

| Piece | Built | What Purple reads today |
| --- | --- | --- |
| Your own words and emoji | Fully. Words, synonyms, autocomplete picks. | All of it. Emitted in the exact core-emoji format. |
| Your own photos | Fully. Drop a photo, see it painted on the Art room canvas at the real 132 by 25 cell size. | Nothing. Emitted as a proposed `content/pictures/` layout. |
| Your own voice | Fully. Record or upload a clip per key (A to Z, 0 to 9) and per phrase. 22050 Hz mono 16-bit WAV, trimmed and faded like Purple's own clips. | Nothing. Emitted in the exact `core-sounds` layout as a proposal. |
| Your own instrument sounds | Fully. Start from any of Purple's four instruments and move the numbers behind its sound with sliders while a Music room keyboard plays it. The 67-note sample set is rendered from the same equations. | Nothing. Proposed layout, plus the slider values as JSON. |
| Your own colors | Lighter. Background, canvas, and a hue per letter row, previewed on the Art frame. | Nothing. Proposed `theme.json`. |
| Your own rooms or games | Out of scope. Not stubbed. | |

`PACK_FORMAT.md` is the write-up of the real format and the proposed additions.

## Instruments, specifically

Purple's Music room plays pre-rendered samples, but those samples come from `purple_tui/synth.py` and `scripts/generate_sounds.py`: additive partials for the marimba and glockenspiel, band-limited detuned sawtooths for the accordion, Karplus-Strong with a body resonator for the ukulele. `src/purple/synth.ts` is a port of those four generators where every constant that shapes the sound is a parameter: bar and tube decay, the woody 4x partial, mallet noise, reed detune and harmonic rolloff, tremolo, string damping and pluck position, body resonance, bell partials, mallet ping. The slider defaults are the Python's constants, so an untouched instrument renders the same sound Purple ships (up to the noise generator, see below).

Sliding a control re-renders and replays the last key within a frame or two; all rendering is synchronous TypeScript at 44100 Hz. Downloading renders all 67 pitches per instrument into `content/<name>/<pitch>.wav` and writes the parameters to `content/instruments/<name>.json`.

## Delivery, honestly

- On a **permanently installed** Purple, `~/.purple/packs/<id>/` is honored by the runtime. There is no file manager or browser on the machine, so the pack goes in through the parent menu's terminal. The "Getting it onto Purple" page gives the commands.
- On a **live-booted Key**, nothing persists: `$HOME` is tmpfs, the ISO is read-only, and `flash-to-usb.sh` zeroes persistence signatures on purpose. A pack copied onto the Key does nothing. The page says so.
- The `PURPLE_UPDATE` second-stick channel (`config/udev/99-purple-update.rules`, `config/systemd/purple-usb-update@.service`) is wired to run `purple_tui.usb_updater`, which does not exist. Studio does not describe it as a feature.

## Verified against the repo (2026-09-03)

- `tests/art.test.ts` checks the TypeScript port of `fit_to_canvas`, the canvas size, and every `KEY_COLORS` entry against `tests/art-fixtures.json`, which was exported from the Python side with a one-off script. Re-export and re-run if `art_room.py` or `photo_to_art.py` change.
- `tests/synth.test.ts` checks each generator's output length, peak normalization (including the low-frequency loudness boost), determinism, and slider ranges. `tests/pack.test.ts` checks an instrument lands as 67 WAVs at 44100 Hz plus its JSON.
- A pack emitted by `src/pack.ts` was fed to `PackInstaller.install_pack` and then `ContentManager.load_all` in a temp packs dir: it installed, `octopus`, the synonym `octo`, and an overridden `cat` all resolved, and the WAV read back as 22050 Hz mono 16-bit with Python's `wave` module.
- Screenshots of every view and of a photo dropped into the facsimile were taken in headless Firefox. A 1146 by 1258 photo landed at 46 by 25 cells, matching the Python sizing.

## Known differences and cuts

- Photo downsampling is a box filter, not Pillow's Lanczos. At the shrink ratios involved (30x or more) the two agree to within a shade.
- Instrument samples are WAV, not OGG, because browsers do not ship an OGG encoder and `music_room._find_sound` already falls back to `.wav`. A 67-file marimba is about 3 MB; a glockenspiel about 9 MB.
- The synth port uses a small seeded PRNG for mallet and pluck noise, not Python's Mersenne Twister, so the first few milliseconds of a note differ from the shipped files bit for bit. Everything else is the same arithmetic.
- Percussion (the number row) is shared by every instrument and is not editable here.
- Nothing is saved between browser sessions. Closing the tab loses the draft; the page warns once there is something in it.
- Microphone recording needs a secure context, so over plain http on a LAN the Record button reports the mic unavailable; uploading a file still works. An SSH tunnel to localhost fixes it.

## Obvious next steps (none of them promised)

1. `purple_tui/usb_updater.py`: the second-stick channel is already wired at the udev and systemd level and is the only path that could work on a live-booted Key. Since `$HOME` is tmpfs it would re-install the pack on every boot from the stick, which is fine.
2. Loader: read `content/letters/`, `content/voice/`, and instrument directories from user packs, the same way `letters-kid/` is preferred over `letters/` today.
3. Replace `secret_photo.OPS` with a reader for `content/pictures/`.
4. Let `generate_sounds.py` read `content/instruments/<name>.json` so a family instrument can be re-rendered on the Python side from the same numbers.
