# Headless UI Preview

Run Purple Computer headlessly on the server, take screenshots, and iterate on UI changes without a display or VM.

## Quick Start

```bash
just preview              # Play room (default)
just preview art          # Art room
just preview music        # Music room
```

Output is a PNG path printed to stdout (e.g. `/tmp/screenshots/preview_art.png`). If `rsvg-convert` is unavailable, falls back to SVG.

## Actions

Actions are extra arguments after the room name, processed left to right.

```bash
just preview [room] [action1] [action2] ...
```

### `type:TEXT`

Types each character one at a time into the active input.

```bash
just preview play type:cat              # Type "cat" into the Play prompt
just preview play type:5+3 key:enter    # Type "5+3" then press Enter
just preview art code_panel type:forward key:enter   # Type turtle command
```

### `key:KEY`

Presses a single key. Supported keys:

| Key name    | What it does |
|-------------|-------------|
| `enter`     | Submit/confirm |
| `tab`       | Switch tool/instrument |
| `space`     | Space character or tool action |
| `up`, `down`, `left`, `right` | Arrow navigation |
| `escape`    | Cancel/back |
| `backspace` | Delete character |
| `delete`    | Forward delete |
| Single char (e.g. `a`, `1`) | Type that character |

```bash
just preview music key:a key:b key:c     # Press keys on the music grid
just preview music key:tab               # Switch to next instrument
just preview art key:tab                  # Switch art tool
```

### `code_panel`

Opens the REPL/code panel at the bottom of the screen.

```bash
just preview art code_panel              # Art room with code panel
just preview music code_panel            # Music room with code panel
```

### `clear`

Clears the art canvas.

```bash
just preview art clear type:h type:i     # Clear canvas, then type "hi"
```

### `wait:SECONDS`

Pauses for N seconds between actions. Useful for letting animations or transitions settle.

```bash
just preview play type:hello wait:0.5 key:enter
```

## Examples

```bash
# See the Play room with a math result
just preview play type:5+3 key:enter

# See emoji autocomplete in action
just preview play type:cat

# Art room with code panel, run a turtle command
just preview art code_panel type:forward key:enter

# Art room after typing on canvas (write mode)
just preview art type:hello

# Music room with different instrument tab
just preview music key:tab

# Music room with a key highlighted
just preview music key:a
```

## How It Works

The preview script (`scripts/preview.py`) uses Textual's `run_test()` to render the app in memory at the correct viewport size (146x38) without needing a terminal or display.

Key environment variables set automatically:
- `PURPLE_NO_EVDEV=1`: skips hardware keyboard detection
- `SDL_AUDIODRIVER=dummy`: prevents pygame audio init failures
- `PURPLE_DEV_MODE=1`: enables dev command infrastructure

SVG screenshots are taken via Textual's `save_screenshot()`, then converted to PNG using `rsvg-convert` (pulled via `nix-shell -p librsvg`).

## Output Files

Screenshots are saved to `/tmp/screenshots/` with filenames derived from the room and actions:

```
/tmp/screenshots/preview_play.png
/tmp/screenshots/play_type_cat.png
/tmp/screenshots/art_code_panel.png
/tmp/screenshots/art_code_panel_type_forward_key_enter.png
```

Both the SVG source and PNG conversion are kept.

## Limitations

- No audio playback (pygame uses dummy driver)
- No evdev keyboard input (uses synthetic key dispatch)
- Some timing-dependent features (animations, debounced toggles) may not render identically to real hardware
- Emoji rendering depends on system fonts (Noto Color Emoji may not be installed on the server, so emoji may show as placeholder glyphs)
