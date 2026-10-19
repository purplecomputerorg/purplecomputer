# Purple Studio

Purple Studio is where you make your Purple Computer your family's own. Add photos or your kid's drawings to paint on in the Art room, record your voice saying the letters, teach Purple the words your family uses, shape your own instrument sounds, and pick your colors.

A real Purple runs right there on the page as you work, so you see and hear every change the way your kid will. When you're happy with it, you download one file, your Purple Pack, and put it on a USB drive for Purple to pick up.

You don't need an account, and nothing you add is uploaded anywhere.

## What you can add

- **Pictures.** Drop in a photo or a drawing and see it painted onto the Art room's grid. In Art, your kid finds it under Open (Esc, then O) and can paint on top of it.
- **Your voice.** Record yourself saying any letter or number, or a whole phrase. Purple plays your recording instead of its own voice whenever it would say those words.
- **Words and emoji.** Type a word, pick its emoji. Purple already knows hundreds of words; yours come first when Purple suggests what to type in Play.
- **Instruments.** Start from one of Purple's instruments and move sliders to change how it sounds. Yours shows up in the Music room after the built-in ones.
- **Colors.** Pick the screen color and the paint colors for each row of letters.

Nothing goes in your Purple Pack until you press **Add to my Purple Pack**. Until then you're just trying it, and **Never mind** puts things back.

## Putting it on Purple

1. Press **Download** to save your Purple Pack (a `.purplepack` file).
2. Copy it onto any USB drive. The Purple Key works too.
3. Plug the drive in before turning Purple on.

Purple reads the drive, adds your things, and they're there from the first screen. It only reads the drive, never writes to it. The Download page walks you through the same steps.

## Privacy

Everything Studio does happens in your browser, on your computer.

- **Nothing you add leaves your computer.** There is no server behind Studio to send it to: the site is plain files, and your Purple Pack is built right in the page and saved through your browser's download.
- **Your browser enforces it.** Every Studio page tells the browser it may only talk to Studio's own site (a `Content-Security-Policy` with `connect-src 'self'`), so nothing can be sent anywhere else, even by mistake.
- **No tracking.** No cookies, analytics, or accounts, and no fonts or icons loaded from other sites.
- **Purple's voice runs on your computer too.** The first time Purple speaks, Studio downloads its voice once and keeps it in your browser. If your computer's own voice fills in while that loads, Studio only uses voices that run on your machine, never a cloud voice.
- **Your work is kept in your browser** so a reload or a closed tab doesn't lose it. **Clear everything**, in the More menu, erases it, and **Clear all** at the bottom of a page clears just that part. Browsers can clear this on their own (Safari after about a week away), so your downloaded Purple Pack is the copy to keep: **Open your Purple Pack** brings it back into Studio.
- **The microphone is on only while you're recording.**

The rest of this page is for anyone who wants to look under the hood.

## Running Studio yourself

```bash
just studio            # install and start a dev server on https://localhost:5173 (and https://<this machine>:5173 on your network)
just studio-test       # type check and tests
just studio-fixtures   # regenerate export.json and golden.json from Purple's Python (see below)
just studio-bundle     # build the copy of Purple the page runs (just studio does this for you)
```

Or from `studio/`: `npm install`, `npm run dev`, `npm test`, `npm run build` (static files in `studio/dist/`).

The dev server uses a self-signed certificate, so your browser warns once; accept it to continue. It has to be https: the live Purple needs a cross-origin isolated page, which browsers only allow in a secure context. Recording from the microphone needs it too.

**Rooms are switched off for now:** `features.rooms = false` in `src/state.ts` hides the Rooms page, the Room guide, and `pack.room`. Set it to `true` to turn them back on.

## Hosting

Studio is static files, but the host has to send three headers on every file (`vite.config.ts`, `HEADERS`, which the dev server already sends):

- `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`, so a room's worker can wait on shared memory for a key or an answer. Without them the preview can't run rooms.
- The `Content-Security-Policy` from the same file, which keeps every page and room worker off the network. Pages also carry it as a meta tag; workers only get it from the header.

`purple.html` alone needs `'unsafe-eval'` in its policy, because pygame's WebAssembly build evaluates JavaScript. Every other page keeps the strict one.

## How it's built

Vite, TypeScript, and plain DOM, with no backend. Three runtime dependencies: Blockly for the room editor, Pyodide to run Purple's Python in the browser, and onnxruntime-web for Purple's voice. Everything that doesn't touch the page (tar and gzip, WAV encoding, the synth, the pack builder) lives in `sdk/`, a plain TypeScript library with no dependencies; see `sdk/README.md`. `PACK_FORMAT.md` describes every file in a pack and how to build one by hand.

### The live Purple

`purple.html` boots the real Purple, in Pyodide, in an iframe that stays up for the whole visit. After each edit Studio builds the pack exactly as Download would, and Purple installs it with its own `PackInstaller` and restarts, the same way it reads packs at boot.

- `scripts/studio_bundle.py` zips `purple_tui`, its fonts, the core packs, and the emoji font, and fetches the Pyodide wheels Purple needs.
- `src/live/browser.py` turns what a browser can't do into no-ops before Purple loads (threads, the mixer's subprocess probe, freetype glyph checks) and routes speech to recorded clips or Piper.
- `src/live/live.py` installs a pack, restarts the app, and opens the room a page asks for.
- **Voice:** Piper, with the same model, speaker, and settings as Purple, phonemized by espeak-ng built to WebAssembly (`vendor/espeak-ng/`, GPL-3.0, source linked under the screen) and run in `src/live/piper.worker.ts`. Purple's own `tts` then trims, levels, and caches the audio, so a phrase sounds the way it does on Purple. The model is cached with the browser's Cache API.

### Room code is untrusted

Room code can be pasted from anywhere. In the preview it runs in a Web Worker with its own Pyodide, which can't import `js` or `pyodide` and has its network functions removed. Purple's own `FamilyRoom` hosts it (`src/rooms/guests.ts` stands in for the process it uses on the laptop), checks every reply, and ends a room that's busy for 3 seconds, sends too much, or answers out of turn. The real limits are the CSP and those checks; the import wall only raises the bar. See `guides/family-rooms.md`.

### Staying in sync with Purple

Purple is the source of truth and nothing is copied by hand:

- **`sdk/src/purple/export.json`** is written by `scripts/export_studio.py` from `purple_tui` itself: pack format version, canvas size, colors, the Music grid's pitches, voice clip settings, synth defaults, and the room language.
- **`tests/golden.json`** holds reference renders from `purple_tui/synth.py` that `tests/synth.test.ts` checks the TypeScript port against, to within one sample (the last-bit difference between libm and V8 before truncation).
- **`purple_tui/roomkit/purple.py`**, the module rooms import, is loaded into the preview as is; `tests/rooms.test.ts` runs the examples against it.
- **The core emoji pack** is imported straight from `../packs/core-emoji`.
- **`tests/test_studio_export.py`** rebuilds both JSON files on every `just test` and fails if the checked-in copies differ, so a change to Purple's art, music, voice, synth, or pack format can't land without them.
- **`tests/test_packs.py`** runs a Studio-shaped pack through the loader, the installer's rules, the USB updater, and the CLI.

### Instruments

Purple's Music room plays samples rendered by `purple_tui/synth.py`: additive partials for the marimba and glockenspiel, detuned sawtooths for the accordion, Karplus-Strong for the ukulele. Each generator takes keyword parameters with the shipped sound as the defaults. `src/purple/synth.ts` is a port with the same parameter names, and its noise source is the same seeded mulberry32, so mallet and pluck noise match bit for bit.

Moving a slider re-renders and replays the last note. Downloading renders every pitch the Music grid can reach into `content/<name>/<pitch>.wav` and writes the parameters to `content/instruments/<name>.json`, so Purple can re-render it too. Samples are WAV rather than OGG because browsers have no OGG encoder, and Purple falls back to `.wav`.

### Known differences

- Photos are shrunk with a box filter, not Pillow's Lanczos. At these ratios the two agree to within a shade.
- The number row's drums are shared by every instrument and aren't editable.
- The Rooms stage speaks with the browser's voice, not Piper, since rooms run in their own worker.
- Purple reads packs when it starts. A drive plugged in while it's running is installed right away but shows up after the next restart.
