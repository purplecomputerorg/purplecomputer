# The purplepack format, real and proposed

A `.purplepack` is a gzipped tar of `manifest.json` and a `content/` directory, the same thing `just build-packs` produces for `packs/core-emoji`. This page describes what Purple reads today, then the additions Purple Studio writes into the same file. Everything under "Proposed" is **proposed, not read by Purple today**.

## What Purple reads today

Loader: `purple_tui/content.py` (`ContentManager`). Installer: `purple_tui/pack_manager.py` (`PackInstaller`), which is currently imported nowhere; there is no install UI.

### manifest.json

```json
{
  "id": "the-nathansons-pack",
  "name": "The Nathansons' Purple",
  "version": "1.0.0",
  "type": "emoji",
  "description": "Made with Purple Studio."
}
```

- `id`, `name`, `version`, `type` are required. `version` must be `x.y.z`. `description` and `author` are optional.
- `type` must be one of `emoji`, `sounds`, `stories`. Only `emoji` and `sounds` dispatch in the loader, and the `sounds` branch parses a `sounds.json` that nothing reads. `stories` loads nothing.
- An `entrypoint` key, or any `.py` file, makes the installer refuse the pack.
- The installer refuses `..` and absolute paths inside the archive and will not overwrite an existing `~/.purple/packs/<id>/`.

Studio always declares `type: "emoji"`, because that is the only type whose content the loader reads. Everything else in the pack sits alongside in directories the loader ignores. That is deliberate: a mixed pack installs and works for words today, and the proposed directories cost nothing until Purple learns to read them.

### content/emoji.json

Flat map of word to glyph. Merged over the built-in map, so a word Purple already has gets your glyph, and a new word joins the list.

```json
{ "octopus": "🐙", "cat": "😺" }
```

### content/synonyms.json

Alias to primary word. The primary must resolve to an emoji (built-in or from this pack) or the alias is dropped.

```json
{ "octo": "octopus" }
```

### content/rankings.txt

One word per line; position is autocomplete priority. Read from every installed pack regardless of type. Built-in packs are read first and first occurrence wins, so a user pack can only rank words the core pack has not ranked. Studio says this in the UI rather than pretending otherwise.

## Where packs live

- Built-in: `packs/`, copied to `/opt/purple/packs/` at image build.
- User: `~/.purple/packs/<id>/`. Honored by the runtime on an installed Purple. On a live-booted Key `$HOME` is tmpfs, so there is nowhere for a pack to persist. See `studio/README.md`, Delivery.

## Proposed additions (not read by Purple today)

Each mirrors a layout Purple already uses somewhere else, so the eventual loader change is small and directory-shaped.

### content/letters/<key>.wav

`a.wav` through `z.wav` and `0.wav` through `9.wav`, lowercase, one per key. Identical to `packs/core-sounds/content/letters/`, which `music_room._load_letter_sounds()` reads by path. 22050 Hz, mono, 16-bit PCM, silence trimmed with 10 ms fades, the same numbers Piper writes for the core clips. Proposed loader change: search user packs' `content/letters/` ahead of the core directory, the way `letters-kid/` is searched ahead of `letters/` today.

### content/voice/<phrase>.wav

Filename is `text.strip().lower().replace(" ", "_") + ".wav"`, the rule in `tts._get_voice_clip`. Same audio format as letters. Proposed loader change: check user packs' `content/voice/` before `VOICE_CLIPS_DIR`.

### content/pictures/<name>.json and <name>.png

```json
{ "name": "palm", "ops": [[43, 0, "#ffffff"], [44, 0, "#fefefe"]] }
```

`ops` is the `(x, y, hex)` paint-op list `tools/photo_to_art.py` generates, on the 132 by 25 Art canvas with the photo fitted and centered. `<name>.png` is the parent-facing preview at 10 px per cell, the same render `write_preview` produces. Studio's sizing is a line-for-line port of `fit_to_canvas` (checked against Python in `tests/art.test.ts`); the downsample is a box filter rather than Pillow's Lanczos, which differs by at most a shade at these ratios. Proposed loader change: whatever replaces `secret_photo.OPS` reads these files instead.

### content/<instrument>/<pitch>.wav

Sixty-seven files named by `music_constants.pitch_filename` (`C#4` becomes `cs4`), the same pitch set as `packs/core-sounds/content/marimba/`. Studio writes WAV, which `music_room._find_sound` already accepts as a fallback to `.ogg`, so no browser OGG encoder is needed. Every file is one source note resampled to the target pitch, like a one-shot sampler. Proposed loader change: add user-pack instrument directories to `INSTRUMENTS`.

### content/theme.json

```json
{
  "background": "#1e1033",
  "surface": "#2a1845",
  "keys": { "q": "#F2A5A5", "w": "#EE8D8D" }
}
```

`background` and `surface` are the two dark-theme colors registered in `purple_tui.py`. `keys` is the full letter-row map from `art_room.generate_row_gradient`, ported byte for byte, with the parent's hue per row. The number row is intentionally absent: it stays grayscale so the keycap stickers keep matching. Proposed loader change: none planned; this exists so a future theme loader has a concrete file to read.
