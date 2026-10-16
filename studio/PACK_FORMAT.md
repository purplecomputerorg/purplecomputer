# The purplepack format

A `.purplepack` is a gzipped tar of `manifest.json` and a `content/` directory, the same thing `just build-packs` produces for `packs/core-emoji`. This page is the format as Purple reads it: which files the rooms look at, what each must contain, how a pack gets onto a machine, and what the installer refuses. The one section at the end marked **proposed** is a file Studio writes that nothing reads yet.

Loader: `purple_tui/content.py` (`ContentManager`). Rules and installer: `purple_tui/pack_manager.py` (`check_pack`, `PackInstaller`). Rooms: `purple_tui/roomkit/` and `purple_tui/canvas/rooms/family_room.py`, described in `guides/family-rooms.md`. USB channel: `purple_tui/usb_updater.py`. Command line: `scripts/purplepack.py`. A TypeScript library that builds all of this without Studio's UI: `studio/sdk/`.

## manifest.json

```json
{
  "id": "the-nathansons-pack",
  "name": "The Nathansons' Purple",
  "version": "1.0.0",
  "type": "emoji",
  "format": 1,
  "description": "Made with Purple Studio."
}
```

- `id`, `name`, `version`, `type` are required. `id` is the directory name the pack installs under, so it must be a single plain path segment. `version` must be `x.y.z`. `description` and `author` are optional.
- `type` must be one of `emoji`, `sounds`, `stories`, `language`; only `emoji` and `language` dispatch to anything in the loader. Studio always declares `emoji`. The directories below are read from every user pack regardless of type.
- `format` is the layout version, `1` today and the default when absent. `content.PACK_FORMAT` is the newest a build reads; a pack declaring a higher one is skipped whole rather than half-loaded, and the installer refuses it with a message that says so.
- An `entrypoint` key, or any `.py` file anywhere in the pack outside the rooms below, makes the installer refuse the pack. Packs are data.

## What each file is

Everything below `content/` that is not listed here is ignored.

### emoji.json, synonyms.json, rankings.txt

```json
{ "octopus": "🐙", "cat": "😺" }
```
```json
{ "octo": "octopus" }
```

`emoji.json` is a flat map of word to glyph, merged over the built-in map: a word Purple already has gets your glyph, a new word joins the list. `synonyms.json` maps an alias to a primary word, which must resolve to an emoji (built-in or from this pack) or the alias is dropped. `rankings.txt` is one word per line, position being autocomplete priority; built-in packs are read first and first occurrence wins, so a user pack can only rank words the core pack has not ranked.

### letters/<key>.wav

One clip per Music grid key, any of them: `a.wav` through `z.wav` and `0.wav` through `9.wav`, lowercase, plus `semicolon.wav`, `comma.wav`, `period.wav` and `slash.wav` (the names in `canvas/sounds.CLIP_NAMES`). The clip can be anything, not just the key's name. 22050 Hz, mono, 16-bit PCM, the numbers Piper writes for the core clips. The Music room's Say Letters mode searches user packs first, then `letters-kid/` when Kid Voice is on, then the core `letters/`, per key, so a pack that records only some keys falls back for the others; the four punctuation keys have no core clip and stay plain notes unless a pack gives them one. The Textual UI reads only the letters and numbers.

### voice/<phrase>.wav

Filename is `text.strip().lower().replace(" ", "_") + ".wav"`, the rule in `tts.voice_clip_filename`. Same audio format as letters. Whenever Purple is about to say exactly that text, it plays the clip instead of synthesizing, checking user packs before the core `voice/`.

### pictures/<name>.json and <name>.png

```json
{ "name": "palm", "ops": [[43, 0, "#ffffff"], [44, 0, "#fefefe"]] }
```

`name` is what the kid sees in Open, exactly as the family typed it ("Grandma's dog"), cut to 24 characters; when it is missing or the same as the file name, Purple tidies the file name instead (`palm` shows as Palm). `ops` is a `[x, y, "#rrggbb"]` paint-op list on the canvas UI's 56 by 24 Art grid of square cells, the photo fitted and centered; Purple paints each op on its cell. Every op must be on the grid. The Art room's Open (Esc, O) lists them after the kid's saves; choosing one paints it onto a fresh canvas as a new Time Travel step. `<name>.png` is a preview for people; Purple does not open it.

### instruments/<name>.json and <name>/<pitch>.wav

```json
{ "name": "kitchen-marimba", "base": "marimba", "params": { "duration": 0.55, "wood": 0.9, "tube": 0.4 } }
```

`base` is one of the four generators in `purple_tui/synth.py` and `params` are keyword arguments to it; every key must exist in `synth.DEFAULTS[base]` and every value must be a number. The samples live beside it in `content/<name>/`, one file per pitch the Music grid can reach (66, from `music_constants.reachable_pitches`), named by `pitch_filename` (`C#4` becomes `cs4`), 44100 Hz mono 16-bit WAV, or OGG. The Music room lists the instrument after Purple's four, under the JSON `name` title-cased, and Enter cycles to it; the code panel's `choose` finds it by name. A pack instrument whose id matches a built-in (`marimba`, `ukulele`, `accordion`, `glockenspiel`) replaces that instrument's samples, the way an emoji entry replaces a built-in word.

Studio renders the WAVs in the browser from its port of the synth. `scripts/purplepack.py render` renders the same files from the Python, the renderer of record, for a pack written by hand or one whose samples were left out to keep the file small. An instrument JSON with no sample directory is not listed.

### rooms/<name>.py

```python
from purple import *

show("🐄")


def on_key(key):
    show(key)
    play("C4")
```

A family-made room: a Python file that runs as a guest. Purple starts it in a sealed process of its own that can't touch anything else on the machine, and the room can only answer Purple's events with what to show and play. A room that errors, hangs, or asks for too much is ended and shows a calm "this room needs fixing" card. Once a parent turns a room on in the Parent Menu's Family Rooms list, the room picker (a tap of Esc) shows it in a row of family rooms; Esc always leaves. `<name>` is lowercase letters, digits, and dashes, never `purple`, and the picker shows it title-cased (`dinosaur-trivia` becomes Dinosaur Trivia).

What a room can call, the keys it receives, and the message protocol are in `guides/family-rooms.md`; `purple_tui/roomkit/purple.py` is the module itself. Studio runs the same file in its preview, so what a parent tries there is what the kid gets.

Studio saves the Blockly workspace a room was built from beside it as `<name>.blocks.json`, which Purple ignores; it is there so the room can be reopened for editing.

### rooms/purple.py

The library the pack's rooms import as `purple`: the copy of `purple_tui/roomkit/purple.py` Studio had when it built the pack. Purple runs the rooms on it, so a pack made by a newer Studio brings its newer library to an older Purple; a pack without one runs on the copy Purple was built with. It runs in the same sealed process as the room, never in Purple itself.

### theme.json

```json
{
  "colors": { "bg": "#0d2233", "surface": "#123045", "text": "#c7def3", "accent": "#8fc3f0" },
  "canvas": "#112c40",
  "keys": { "q": "#F2A5A5", "w": "#EE8D8D" }
}
```

A family's colors, read by the canvas UI when Purple starts (`purple_tui/canvas/theme.py`; the Textual UI ignores it). `colors` sets any of the screen's palette roles from `purple_tui/palette.py` by their lowercase names: `bg`, `surface`, `tile`, `field`, `hair`, `line`, `primary`, `on_primary`, `accent`, `text`, `muted`, `dim`. `canvas` is the Art canvas (its checkerboard partner is a small step away). `keys` maps letter-row keys to the colors they paint with in Art, light up in Music, and mark in Play; the row legend beside the screen follows them. Every field is optional, anything that isn't a `#rrggbb` color or a known role or letter-row key is ignored, and the number row always stays gray. The key stickers keep Purple's own colors, so themed paint colors no longer match them. With several themed packs, the last installed wins.

Studio writes the whole palette, derived from one color the parent picks (`sdk/src/purple/theme.ts`): Purple's own palette turned to that color with the same relationships between its colors, a light color flipping it to dark text on a light screen, and each kind of text nudged until it reads on the panels it sits on.

### language.json, strings.json, words.json, input.json (type "language")

A language pack (`packs/lang-es`, `packs/lang-zh`) declares `"type": "language"` and needs `language.json`:

```json
{ "code": "es", "name": "Español", "english_name": "Spanish", "voice": "es_MX-ald-medium", "font": "MyFont.ttf" }
```

`code` is any code but `en`. `voice` names a Piper model, found in the usual voice folders or as `content/<voice>.onnx` (plus `.onnx.json`) in the pack itself. `font` is a file in `content/` that draws the language's script when the built-in faces can't; it joins the font fallback chain at startup. The other files are optional:

- `strings.json`: the interface, English text as drawn mapped to its translation. `{0}`, `{1}` stand for values filled in at run time (a translation may reorder them); `{Enter}`-style keycaps and `[bold]` markup are kept as they are. Anything missing stays English. `just python scripts/i18n_strings.py <code> --json` lists what's missing.
- `words.json`: English Play words (emoji names, colors) to the language's word, `"dog": "perro"`, or `[word, reading]`, `"dog": ["狗", "gǒu"]`. Play shows and says them next to English when this is the second language, and understands them typed (unaccented and plural too, and the reading without tones).
- `input.json`: toneless pinyin to characters, most common first, `{"gou": ["狗", "够"]}`. With it, the number keys pick a character for the pinyin just typed in Play.
- `blocked.txt`: words Purple never says aloud, base64 of one word per line (so no plaintext profanity sits in the repo). Every installed language's list applies whatever the settings, since a kid can type Spanish with Spanish off. Chinese entries match anywhere in the text; others match a whole word, with or without accents. A family pack can add words but never remove them.

A second pack with the same `code` adds to the first, its entries winning, so a family can fix a few words without replacing the language. The setting is in the parent menu: Language (the interface) and Second Language (Play). Design: `guides/languages.md`.

## Where packs live and how they get there

- Built-in: `packs/`, copied to `/opt/purple/packs/` at image build.
- User: `~/.purple/packs/<id>/` of the `purple` user. Loaded after the built-ins, in name order, so a later pack wins any per-file lookup.

**Any USB drive.** `config/udev/99-purple-update.rules` starts `config/systemd/purple-usb-update@.service` for every FAT, exFAT or NTFS partition on a USB drive, the Purple Key's own PURPLEUSB partition included; there is no label to set. The unit mounts it read-only with `nosuid,nodev,noexec` under `/run/purple-update/<device>`, and if `*.purplepack` files sit in its top directory runs `purple_tui.usb_updater`, then unmounts. A drive without packs never starts Python. The updater installs each pack into the purple user's packs, replacing a pack with the same id, and appends a line per pack to `/var/log/purple/usb-update.log`. The unit orders itself before `purple-x11.service`, so a drive present at boot is installed before the first screen; one plugged in later is installed on the spot, but the running app only reads packs at startup, so it takes effect at the next start. On a live-booted Key `$HOME` is tmpfs, so the packs vanish at shutdown and come back at the next boot from the Key itself.

**By hand.** On an installed Purple, from the parent menu's terminal: mount the drive and run `python3 -m purple_tui.usb_updater /mnt/drive`, or unpack the tar into `~/.purple/packs/<id>/` yourself.

**From a development checkout.** `just python scripts/purplepack.py install my-pack.purplepack --replace`, or `--packs-dir` to install somewhere else.

## What the installer checks

`check_pack` runs on every install, from a USB drive or by hand, and the pack is refused with the first few problems listed if any of these fail:

- manifest present and valid as above; `format` not newer than this build reads
- no `.py` files except `rooms/<name>.py` and `rooms/purple.py`, no `.pyc`, `.pyo`, `.pyw`, and no extensionless or `.sh` file whose first line mentions python
- no absolute paths, no `..` segments, no symlinks or hard links in the archive
- `emoji.json` and `synonyms.json`, if present, are JSON objects mapping strings to non-empty strings
- every file in `letters/` and `voice/` is a WAV at 22050 Hz, mono, 16-bit
- every `instruments/<name>.json` names a known base, has only that base's parameters with numeric values, and has a `content/<name>/` directory whose WAVs are 44100 Hz, mono, 16-bit
- every `pictures/<name>.json` has an `ops` list of `[x, y, "#rrggbb"]` on the canvas
- every `rooms/<name>.py`, and `rooms/purple.py`, has a valid name, is UTF-8 text that compiles, and is at most 64 KB

`scripts/purplepack.py check` runs the same function on a directory or a `.purplepack`.

## The command line

```
just python scripts/purplepack.py check   my-pack/            # the checks above, exit 1 on any problem
just python scripts/purplepack.py render  my-pack/            # instruments/*.json -> <name>/<pitch>.wav, skipping files that exist
just python scripts/purplepack.py build   my-pack/            # checks, then writes <id>.purplepack next to the directory
just python scripts/purplepack.py show    my-pack.purplepack  # every file and which room reads it
just python scripts/purplepack.py install my-pack.purplepack [--packs-dir DIR] [--replace]
```

A pack directory is `manifest.json` plus `content/`; this page is the whole contract. Someone building on Purple without Studio needs nothing else.
