# The purplepack format

A `.purplepack` is a gzipped tar of `manifest.json` and a `content/` directory, the same thing `just build-packs` produces for `packs/core-emoji`. This page is the format as Purple reads it: which files the rooms look at, what each must contain, how a pack gets onto a machine, and what the installer refuses. The one section at the end marked **proposed** is a file Studio writes that nothing reads yet.

Loader: `purple_tui/content.py` (`ContentManager`). Rules and installer: `purple_tui/pack_manager.py` (`check_pack`, `PackInstaller`). Rooms: `purple_tui/room_program.py` and `purple_tui/rooms/pack_room.py`. USB channel: `purple_tui/usb_updater.py`. Command line: `scripts/purplepack.py`. A TypeScript library that builds all of this without Studio's UI: `studio/sdk/`.

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
- `type` must be one of `emoji`, `sounds`, `stories`; only `emoji` dispatches to anything in the loader. Studio always declares `emoji`. The directories below are read from every user pack regardless of type.
- `format` is the layout version, `1` today and the default when absent. `content.PACK_FORMAT` is the newest a build reads; a pack declaring a higher one is skipped whole rather than half-loaded, and the installer refuses it with a message that says so.
- An `entrypoint` key, or any `.py` file anywhere in the pack, makes the installer refuse the pack. Packs are data.

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

`a.wav` through `z.wav` and `0.wav` through `9.wav`, lowercase, one per key. 22050 Hz, mono, 16-bit PCM, the numbers Piper writes for the core clips. The Music room's Say Letters mode searches user packs first, then `letters-kid/` when Kid Voice is on, then the core `letters/`, per key, so a pack that records only some keys falls back for the others.

### voice/<phrase>.wav

Filename is `text.strip().lower().replace(" ", "_") + ".wav"`, the rule in `tts.voice_clip_filename`. Same audio format as letters. Whenever Purple is about to say exactly that text, it plays the clip instead of synthesizing, checking user packs before the core `voice/`.

### pictures/<name>.json and <name>.png

```json
{ "name": "palm", "ops": [[43, 0, "#ffffff"], [44, 0, "#fefefe"]] }
```

`ops` is the `[x, y, "#rrggbb"]` paint-op list `tools/photo_to_art.py` generates, on the 132 by 25 Art canvas with the photo fitted and centered. Every op must be on the canvas. The parent menu shows a Pictures entry when any pack has one; choosing a picture switches to the Art room and paints it onto a fresh canvas. `<name>.png` is a preview for people; Purple does not open it.

### instruments/<name>.json and <name>/<pitch>.wav

```json
{ "name": "kitchen-marimba", "base": "marimba", "params": { "duration": 0.55, "wood": 0.9, "tube": 0.4 } }
```

`base` is one of the four generators in `purple_tui/synth.py` and `params` are keyword arguments to it; every key must exist in `synth.DEFAULTS[base]` and every value must be a number. The samples live beside it in `content/<name>/`, one file per pitch the Music grid can reach (66, from `music_constants.reachable_pitches`), named by `pitch_filename` (`C#4` becomes `cs4`), 44100 Hz mono 16-bit WAV, or OGG. The Music room lists the instrument after Purple's four, under the JSON `name` title-cased, and Enter cycles to it; the code panel's `choose` finds it by name. A pack instrument whose id matches a built-in (`marimba`, `ukulele`, `accordion`, `glockenspiel`) replaces that instrument's samples, the way an emoji entry replaces a built-in word.

Studio renders the WAVs in the browser from its port of the synth. `scripts/purplepack.py render` renders the same files from the Python, the renderer of record, for a pack written by hand or one whose samples were left out to keep the file small. An instrument JSON with no sample directory is not listed.

### rooms/<name>.json

```json
{"name": "farm", "title": "Farm", "background": "#1e1033", "rules": [
  {"when": {"event": "key", "key": "c"},
   "do": [{"do": "show", "text": "🐄"}, {"do": "say", "text": "cow"}, {"do": "play", "note": "C4", "instrument": "marimba"}]},
  {"when": {"event": "any_key"}, "do": [{"do": "add", "text": {"key": true}}, {"do": "drum", "name": "woodblock"}]}
]}
```

A family-made room. Purple interprets the file; nothing in it runs as code. The room picker (a tap of Esc) grows a row of these under Play, Music, and Art, on keys 4 to 7, and the room opens as a screen over the current room; Esc leaves. `name` must match the filename and be lowercase letters, digits, and dashes; `title` is what the picker shows; `background` is optional.

The language, in full, is the docstring of `purple_tui/room_program.py`. In short:

- **Events:** `start` (the room opens), `key` with a `key` (one character, or `space`, `enter`, `up`, `down`, `left`, `right`), `any_key`, `every` with `seconds` (0.5 to 60). A key press runs its own `key` rules, then the `any_key` rules.
- **Actions:** `show` (big, centered, replaces), `add` (appends to a line that fills up), `say` (Purple's voice, or a pack phrase clip if one matches), `play` (a `note` like `C4` or `F#3` on an `instrument`, built-in or from this pack), `drum` (one of the number-row percussion names), `clear`, `background`, `wait` (seconds, capped at 5), `set` and `change` a variable, `if` with `then` and `else`, `repeat` with `body`.
- **Values:** a number, a string, `{"var": name}`, `{"key": true}` (the key just pressed), `{"pick": [...]}`, `{"join": [...]}`, `{"random": {"from": a, "to": b}}`, `{"math": op, "a": x, "b": y}`. **Tests:** `{"compare": op, "a": x, "b": y}` with `=`, `!=`, `<`, `>`, plus `and`, `or`, `not`.
- **Limits**, so a mashed keyboard stays calm: 500 steps per event, 100 repeats, 5 second waits, 200 character texts, 8 levels of nesting. A new key press cancels a run that is still waiting.

Studio's block editor writes this file and saves the Blockly workspace beside it as `<name>.blocks.json`, which Purple ignores; it is there so the room can be reopened for editing. `studio/sdk/src/room.ts` is the same interpreter in TypeScript, and `studio/tests/room-golden.json` (written by `scripts/export_studio.py` from the Python) holds the two to the same trace, so what a parent tries in Studio is what the kid gets.

## Where packs live and how they get there

- Built-in: `packs/`, copied to `/opt/purple/packs/` at image build.
- User: `~/.purple/packs/<id>/` of the `purple` user. Loaded after the built-ins, in name order, so a later pack wins any per-file lookup.

**PURPLE_UPDATE stick.** A USB stick whose filesystem label is `PURPLE_UPDATE` is the delivery channel. `config/udev/99-purple-update.rules` starts `config/systemd/purple-usb-update@.service` for it, which mounts the stick read-only with `nosuid,nodev,noexec`, runs `purple_tui.usb_updater`, and unmounts. The updater installs every `*.purplepack` in the stick's top directory into the purple user's packs, replacing a pack with the same id, and appends a line per pack to `/var/log/purple/usb-update.log`. Sticks with any other label are never touched. The unit orders itself before `purple-x11.service`, so a stick present at boot is installed before the first screen; a stick plugged in later is installed on the spot but the running app only reads packs at startup, so it takes effect at the next start. On a live-booted Key `$HOME` is tmpfs, so the packs vanish at shutdown and come back at the next boot from the stick, which is the intended way to use a pack from the Key.

**By hand.** On an installed Purple, from the parent menu's terminal: mount the stick and run `python3 -m purple_tui.usb_updater /mnt/stick`, or unpack the tar into `~/.purple/packs/<id>/` yourself.

**From a development checkout.** `just python scripts/purplepack.py install my-pack.purplepack --replace`, or `--packs-dir` to install somewhere else.

## What the installer checks

`check_pack` runs on every install, from the stick or by hand, and the pack is refused with the first few problems listed if any of these fail:

- manifest present and valid as above; `format` not newer than this build reads
- no `.py`, `.pyc`, `.pyo`, `.pyw` files, and no extensionless or `.sh` file whose first line mentions python
- no absolute paths, no `..` segments, no symlinks or hard links in the archive
- `emoji.json` and `synonyms.json`, if present, are JSON objects mapping strings to non-empty strings
- every file in `letters/` and `voice/` is a WAV at 22050 Hz, mono, 16-bit
- every `instruments/<name>.json` names a known base, has only that base's parameters with numeric values, and has a `content/<name>/` directory whose WAVs are 44100 Hz, mono, 16-bit
- every `pictures/<name>.json` has an `ops` list of `[x, y, "#rrggbb"]` on the canvas
- every `rooms/<name>.json` parses as a room program and its `name` matches the filename

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

## Proposed, not read by Purple

### content/theme.json

```json
{
  "background": "#1e1033",
  "surface": "#2a1845",
  "keys": { "q": "#F2A5A5", "w": "#EE8D8D" }
}
```

`background` and `surface` are the two dark-theme colors registered in `purple_tui.py`. `keys` is the full letter-row map from `art_room.generate_row_gradient`, ported byte for byte, with the parent's hue per row. The number row is intentionally absent: it stays grayscale so the keycap stickers keep matching. Nothing reads this; the keyboard-row colors are shared truth with the printed stickers, so changing them is a product decision, not a loader change.
