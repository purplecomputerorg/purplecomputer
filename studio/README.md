# Purple Studio (v1 draft)

A parent-facing web app for putting a family's own things into their Purple Computer: photos to draw on in the Art room, a familiar voice for the letters and phrases, the words the family uses, one home-made instrument, and colors. Everything happens in the browser on the parent's machine. No account, no server, no upload, no AI. The one output is a `.purplepack` file.

This is a sketch to feel out the idea, not a shipping product, and nothing in it is a public commitment. It is the first web code in the repo.

## Run it

```bash
just studio          # npm install (first time) and a dev server on http://localhost:5173
just studio-test     # tsc, vitest
```

Or from `studio/`: `npm install`, `npm run dev`, `npm test`, `npm run build` (static output in `studio/dist/`, deployable anywhere that serves files).

Stack: Vite, TypeScript, vanilla DOM, no runtime dependencies. Tar and gzip, WAV encoding, resampling, pitch detection, and the Art room facsimile are all in `src/`. The core emoji pack is imported straight from `../packs/core-emoji` so Studio cannot drift from what Purple ships.

## What it does with each survey piece

| Piece | Built | What Purple reads today |
| --- | --- | --- |
| Your own words and emoji | Fully. Words, synonyms, autocomplete picks. | All of it. Emitted in the exact core-emoji format. |
| Your own photos | Fully. Drop a photo, see the Art room frame with the pixelated result at the real 132 by 25 cell size. | Nothing. Emitted as a proposed `content/pictures/` layout. |
| Your own voice | Fully. Record or upload a clip per key (A to Z, 0 to 9) and per phrase. 22050 Hz mono 16-bit WAV, trimmed and faded like Purple's own clips. | Nothing. Emitted in the exact `core-sounds` layout as a proposal. |
| Your own instrument | Lighter. One recorded note, pitch detected (overridable), resampled into the 67-pitch sample set as WAV. | Nothing. Proposed layout. No synth UI, because Purple has no runtime synthesis. |
| Your own colors | Lighter. Background, canvas, and a hue per letter row, previewed on the frame. | Nothing. Proposed `theme.json`. |
| Your own rooms or games | Out of scope. Not stubbed. | |

The UI says, on every page, what Purple does with that piece today. `PACK_FORMAT.md` is the write-up of the real format and the proposed additions.

## Delivery, honestly

- On a **permanently installed** Purple, `~/.purple/packs/<id>/` is honored by the runtime. There is no file manager or browser on the machine, so the pack goes in through the parent menu's terminal. The "Getting it onto Purple" page gives the commands.
- On a **live-booted Key**, nothing persists: `$HOME` is tmpfs, the ISO is read-only, and `flash-to-usb.sh` zeroes persistence signatures on purpose. A pack copied onto the Key does nothing. The page says so.
- The `PURPLE_UPDATE` second-stick channel (`config/udev/99-purple-update.rules`, `config/systemd/purple-usb-update@.service`) is wired to run `purple_tui.usb_updater`, which does not exist. Studio does not describe it as a feature.

## Verified against the repo (2026-09-03)

- `tests/art.test.ts` checks the TypeScript port of `fit_to_canvas`, the canvas size, and every `KEY_COLORS` entry against `tests/art-fixtures.json`, which was exported from the Python side with a one-off script (`fit_to_canvas` over ten sizes, `KEY_COLORS`, the background constants). Re-export and re-run if `art_room.py` or `photo_to_art.py` change.
- A pack emitted by `src/pack.ts` was fed to `PackInstaller.install_pack` and then `ContentManager.load_all` in a temp packs dir: it installed, `octopus`, the synonym `octo`, and an overridden `cat` all resolved, and the WAV read back as 22050 Hz mono 16-bit with Python's `wave` module.
- Screenshots of every view and of a photo dropped into the facsimile were taken in headless Firefox. A 1146 by 1258 photo landed at 46 by 25 cells, matching the Python sizing.

## Known differences and cuts

- Photo downsampling is a box filter, not Pillow's Lanczos. At the shrink ratios involved (30x or more) the two agree to within a shade. If exact parity matters, port Lanczos.
- Instrument samples are WAV, not OGG, because browsers do not ship an OGG encoder and `music_room._find_sound` already falls back to `.wav`. A 67-file set from a one-second note is about 3 MB.
- Pitch detection is plain autocorrelation. It is fine for a clean single note and the UI lets the parent pick the note by hand when it is not.
- Colors and instrument are lighter than the first three pieces on purpose, since nothing on Purple's side reads them.
- Nothing is saved between browser sessions. Closing the tab loses the draft; the page warns once there is something in it.

## Obvious next steps (none of them promised)

1. `purple_tui/usb_updater.py`: the second-stick channel is already wired at the udev and systemd level and is the only path that could work on a live-booted Key. The design constraint is that `$HOME` is tmpfs, so it would have to re-install the pack on every boot from the stick, which is fine.
2. Loader: read `content/letters/`, `content/voice/`, and instrument directories from user packs, the same way `letters-kid/` is preferred over `letters/` today.
3. Replace `secret_photo.OPS` with a reader for `content/pictures/`.
