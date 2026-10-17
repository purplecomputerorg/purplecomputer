# Purple Studio

A parent-facing web app for putting a family's own things into their Purple Computer: pictures (photos or a kid's drawings) to paint onto the Art room, a familiar voice for the letters and phrases, the words the family uses, instruments tuned from Purple's own synthesis math, and colors. Everything happens in the browser on the parent's machine. No account, no server, no upload, no AI. The one output is a `.purplepack` file, and Purple reads it.

This is a draft, not a shipping product, and nothing in it is a public commitment. It is the first web code in the repo.

**Rooms are off for now:** `features.rooms = false` in `src/state.ts` hides the Rooms page, the Room guide, and `pack.room`, and drops rooms from the copy that mentions them. Flip it to `true` to turn everything back on.

## Run it

```bash
just studio            # npm install and a dev server on https://localhost:5173 (also https://<this machine>:5173 on the LAN)
just studio-test       # tsc, vitest
just studio-fixtures   # regenerate export.json and golden.json from Purple's Python (see below)
just studio-bundle     # Purple itself for the live preview: .cache/purple.zip, Pyodide wheels (just studio runs it)
```

Or from `studio/`: `npm install`, `npm run dev`, `npm test`, `npm run build` (static output in `studio/dist/`, deployable anywhere that serves files).

The dev server and `vite preview` use https with a self-signed certificate (`@vitejs/plugin-basic-ssl`), so the browser warns once per machine; accept it to continue. It has to be https: the room preview needs a cross-origin isolated page, browsers only allow that in a secure context, and plain http counts as secure only on localhost. Opened over plain http from another machine, the preview says so instead of running rooms.

**Hosting.** Studio needs three response headers on every file it serves, which `vite` and `vite preview` already send (`vite.config.ts`, `HEADERS`): `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`, so a room's worker can block on shared memory while it waits for a key or an answer, and the `Content-Security-Policy` in the same file, whose `connect-src 'self'` keeps the page and every room worker off the network. A static host has to be configured to send them; without the first two the preview cannot run rooms, and without the CSP header room workers are not fenced in (the page itself also carries the CSP as a meta tag).

**Room code is untrusted.** A parent may paste it from anywhere. In the preview it runs in a Web Worker with a fresh Pyodide, which cannot import `js` or `pyodide` and has its network functions removed; Purple's own `FamilyRoom` checks every reply, and ends a room that is busy for 3 seconds, sends too much, or answers out of turn. The hard limits are the CSP and those checks; the import wall only raises the bar.

Stack: Vite, TypeScript, vanilla DOM, no backend. Three runtime dependencies: Blockly for the room editor, Pyodide, which runs Purple, rooms in the preview, and the Python page, and onnxruntime-web, which runs Purple's voice. Everything pure (tar and gzip, WAV encoding, the synth port, the pack builder) is in `sdk/src/`; the app in `src/` is the UI over it.

## Privacy

The "Your privacy" page (`src/ui/privacy.ts`, the 🔒 in the top bar) promises parents that nothing they add leaves their device and nothing is tracked, and links here for the details. Keep both true:

- **No backend.** The site serves static files and takes nothing back. A pack is built in the page and saved through the browser's download.
- **The browser enforces it.** Every page and every room worker carries a `Content-Security-Policy` with `connect-src 'self'` (`vite.config.ts`, `HEADERS`), so nothing can be sent to another site even by mistake. Room workers also have Pyodide's network functions removed.
- **Nothing third party.** Fonts come from `@fontsource` packages and Blockly's icons from its own `media/`, both served by Studio, so a visit contacts no other site. No cookies, analytics, or accounts.
- **Speech stays local.** Purple's voice is Piper running in a worker; the browser's speech fallback uses only `localService` voices, so no text goes to a cloud voice.
- **Storage stays in the browser.** The Cache API holds the 79 MB voice model, and IndexedDB holds the draft (recordings and photos included, `src/saved.ts`) so a reload or a closed tab loses nothing; Start over, on the Download and privacy pages, erases it. Browsers may clear it (Safari after a week away), so the downloaded Purple Pack is the copy that lasts: Open your Purple Pack reads it back from its `studio.json`. The microphone is on only while recording.

## The shape

Built so someone who has never seen Purple gets it in a few seconds, with the computer itself as the centerpiece:

- **Top: what you can add.** Six plain tabs (Pictures, Voice, Emoji, Instruments, Rooms, Colors) with counts, a quiet More menu for the power tools (Room guide, Python console, the file layout, the by-hand install route), and Download.
- **Left: the editor** for the selected thing, headed by its name. File paths live only on "What is in the file".
- **Right, the larger side (on top on a phone): a pretend laptop running the real Purple.** A bezel around the screen and a keyboard tilted away below it, with Purple's stickers on the keys (`cards/make_keyboard_sticker_sheet.py`'s design, in the family's paint colors when they've changed them). Tapping a key types it into Purple, and every key Purple gets presses down on the pretend one. A handwritten note points at the stickers, which come in the box. On a phone the laptop stays the same, and tapping it brings up the phone's own keyboard, which types into Purple. Below it are Purple's rooms as buttons, and on a phone a few big keys for the room Purple is in (C A T and Enter in Play, a word's letters on Emoji), always with Esc; while a menu like the room picker is open they turn into the arrows and Enter. Purple's screen is too small to read whole on a phone, so it shows a close-up of the busy part of the room (the typing line in Play, the cursor in Art and Blocks) and zooms out for menus, with a Whole screen button; turned sideways, the phone shows just the screen, as tall as it fits, with the rooms and keys beside it. There is no full screen: it's a demo of the computer, not a substitute for it. The screen shows Purple in the room the piece shows up in: Play for words and phrases, Music in Say Letters or playing the instrument being edited, Art with the photo painted on or in the family's colors. Rooms opens the room being edited over Play, the way the Esc menu opens a family room. See "The live Purple" below.

## Trying, then adding

Everything starts as a try: a picture, a sound, a word, a recording, a room, new colors. Studio's Purple plays tries straight away, and a piece goes in the Purple Pack only once the parent presses Add to my Purple Pack. One bar (`src/ui/trybar.ts`) shows the state the same way on every page: Just trying it, with Add and Never mind, or In your Purple Pack, with Take it out. Lists get an Add per row and an Add them all. Trying another of Studio's examples replaces the last example tried, unless it was changed or added. The nav counts and the download hold only what was added, and the Download page lists what is still being tried, with one button to add it all. Pictures being tried are painted on the screen without going in Purple's Open; the Python console's `pack.*` calls add directly.

## The live Purple

`purple.html` boots Purple in an iframe that Studio starts at first paint and keeps for the whole visit; until it is running (about 3 seconds on a fast machine, 33 MB on first load) a message on Purple's background covers it, and says "Updating" while Purple restarts after an edit. After each edit settles, Studio builds the pack exactly as Download would, and Purple installs it with its own `PackInstaller` and starts again, the way it reads packs after a reboot. Keys typed on the Voice and Instruments pages are sent to Purple too.

- `scripts/studio_bundle.py` zips `purple_tui`, its fonts, the core packs, and the emoji font, fetches the Pyodide wheels Purple needs (pygame-ce, fonttools, rich, wcwidth).
- `src/live/browser.py` turns what a browser can't do into no-ops before Purple loads: threads don't start, glyph coverage comes from the fonts' character maps (pygame.freetype doesn't initialize in Pyodide), the page draws emoji with the same Noto Color Emoji, the mixer opens without the subprocess probe, and speech plays Purple's recorded clips, or Piper (below).
- `src/live/live.py` installs a pack (turning on its rooms: the parent made them), restarts the app, and sets up the room a page asks for, a family room being tried included.
- Family rooms run in Purple's own `FamilyRoom`, with the room in a Web Worker in place of a process (`src/rooms/guests.ts`, swapped in by `src/live/browser.py`), so the preview is the laptop's room host, limits included.
- **Purple's voice** is Piper, as on Purple: the same model, speaker, and settings (from `export.json`), phonemized by espeak-ng built to WebAssembly from the commit piper-tts pins (`vendor/espeak-ng/`, GPL-3.0, its source linked under the screen), in a worker (`src/live/piper.worker.ts`). Purple's own `tts` trims, levels, and caches what it says, so a phrase sounds the way it does on Purple, to within one step of the 16-bit samples. The model is 79 MB, so it downloads the first time Purple speaks and stays in the browser's Cache API; until it is ready (a few seconds on a fast connection) the computer's own voice speaks, if it has one, and Purple's screen says how long is left, and on later visits it loads at boot. `scripts/studio_bundle.py` puts the model and espeak-ng's English data in `.cache/voice/`; the ONNX runtime is served from `node_modules` as files rather than bundled, since its threads start from the file it is in.
- pygame's WebAssembly build evaluates JavaScript, so `purple.html` alone carries a CSP with `'unsafe-eval'`; a static host has to send that policy for that one file. Studio's own pages keep the strict one.

## What Purple does with each piece

| Piece | In Studio | On Purple |
| --- | --- | --- |
| Your own words and emoji | One table: type a word, press Enter, pick its emoji from a search over the words Purple already knows. Each new word is also ranked, so it comes first in autocomplete. Synonyms stay available from the Python console. | Play room, exactly as the core emoji pack. |
| Your own voice | Record or upload a clip of anything per Music grid key (letters, numbers, and `; , . /`) and per phrase; 22050 Hz mono 16-bit WAV, trimmed and faded like Purple's own clips. | Say Letters plays the family's clip for any key recorded, Purple's for the other letters and numbers, and a plain note for the punctuation keys; a recorded phrase is played instead of the synthesized voice whenever Purple would say those exact words. |
| Your own pictures | Drop a photo or a drawing, see it painted on the Art room's grid at the real 56 by 24 square-cell size. Studio's examples (`src/assets/`: a drawing, a dinosaur coloring page, a dog photo, NASA's Saturn, Hokusai's Great Wave) can be tried on the screen the same way. Trying puts a picture on the screen only; Add to my Purple Pack, with a name the parent can change, puts it in the pack. | Art's Open (Esc, O) lists them beside the kid's saves; choosing one paints it onto the canvas. |
| Your own instrument sounds | Start from any of Purple's four instruments and move the numbers behind its sound with sliders while a Music room keyboard plays it. The full sample set, one note per pitch the grid can reach, is rendered from the same equations. | The Music room lists it after the built-in four; Enter cycles to it and the code panel can choose it by name. The slider numbers ship beside the samples so Purple's own synth can re-render it. |
| Your own rooms | A small game, story, or quiz in Python: built from blocks, from a trivia or soundboard form, from the Snake example, or written by hand. The stage on the right runs it live, in a worker of its own, with the same `purple` module Purple uses. | The room picker gains a row of family rooms. Each runs as a guest in its own process and can only ask Purple to show, say, and play things; see `guides/family-rooms.md`. |
| Your own colors | One screen color (a preset or any color), with text that adjusts to stay readable; any single color under one fold; a hue per letter row for the paint colors and the pretend keyboard's stickers. | The canvas UI draws its whole screen in them and paints with the letter-row colors in every room (`theme.json`). The number row and the physical key stickers keep Purple's colors. |

Two more ways in, for parents who would rather write than click:

- **Python.** A console over the pack: `pack.word(...)`, `pack.instrument(...)`, `pack.room(name, source)`. Pyodide runs it in the browser. `tests/python.test.ts` runs the same prelude under Pyodide in Node.
- **Room guide.** Everything a room can call, in plain words, with the examples, and a button that copies it all as text.

And underneath, `sdk/`: the pack builder, the synth port, the tar and WAV writers, and Purple's exported constants as a plain TypeScript library with no DOM and no dependencies, so someone can build a different Studio. See `sdk/README.md`.

`PACK_FORMAT.md` is the contract: every file, what reads it, what the installer refuses, and the command-line tool for people who would rather write a pack by hand.

## Getting a pack onto Purple

Copy the `.purplepack` onto any USB drive, the Purple Key included, and plug it in before Purple starts. Purple mounts each USB drive read-only, installs any packs at its top level, and unmounts; the rooms have them from the first screen. On a live-booted Key the packs are reinstalled at every boot, since nothing else persists there. The page in Studio spells out the steps, including the by-hand route through the parent menu's terminal. The full mechanism is in `PACK_FORMAT.md`, "Where packs live".

## Staying in sync with Purple

Studio is JavaScript all the way, and Purple is Python. Nothing is hand-copied between them; Python is the source and the JSON it exports is what the browser uses.

- **`sdk/src/purple/export.json`** is written by `scripts/export_studio.py` from `purple_tui` itself: the pack format version, viewport and canvas size, key colors, the pitch set the Music grid can reach, grid-to-pitch mapping, letter keys, the voice clip sample rate, example clip filenames, the synth parameter defaults, and the room language's events, actions, drums, and limits. The app imports it directly.
- **`tests/golden.json`** is written by the same script: reference renders from `purple_tui/synth.py` at two pitches per instrument at the defaults plus one varied parameter set each.
- **`purple_tui/roomkit/purple.py`**, the module rooms import, is loaded into the preview's Pyodide as is (a `?raw` import), so there is no TypeScript port of rooms to keep in step. `tests/rooms.test.ts` runs it with the examples and the forms' output under Pyodide in Node.
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
- Purple reads packs when it starts. A USB drive plugged in while Purple is running is installed at once but shows up at the next start.
- Nothing is saved between browser sessions. Closing the tab loses the draft; the page warns once there is something in it.
- Microphone recording also needs the secure context, which the https dev server provides.

## Not done, on purpose

- **The Rooms stage's voice is the browser's**, not Piper's: rooms run in their own worker, away from the live Purple that loads Piper. The words are the same; the voice is not.
- **A running app noticing a new pack.** Cheap to add as a stat on the packs directory at room switch; left out until the boot-time path has been seen on hardware.
- **Regenerating the shipped OGGs** from the parameterized synth, which needs ffmpeg and a listen.
