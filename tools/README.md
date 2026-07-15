# Purple Computer Tools

Development tools for Purple Computer. Run these inside the VM (requires Linux/evdev).

## Setup

```bash
# Create tools/.env with your API key
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > tools/.env

# Dependencies are auto-installed on first run, or install manually:
pip install -r tools/requirements.txt
```

## AI Drawing Tool (`art_ai.py`)

Uses Claude vision to generate drawings in the Art room with a visual feedback loop.

**How it works:**
1. Starts Purple Computer in dev mode (`PURPLE_DEV_MODE=1`)
2. Controls the app via file-based commands (bypasses evdev keyboard)
3. Takes screenshots via file trigger
4. Converts SVG to PNG, sends to Claude vision
5. Claude sees the canvas and generates drawing actions
6. Executes actions, repeats for N iterations

**Usage:**
```bash
./tools/art-ai "a tree on a green hill"
./tools/art-ai "sunset with orange and purple sky" --iterations 8
./tools/art-ai --from art_ai_output/TIMESTAMP --instruction "add a bird"
```

**Output (per run, in `art_ai_output/TIMESTAMP/`):**
- `screenshots/` - screenshots from each iteration
- `plan.json` and `iteration_scripts.json` - plan and per-iteration actions, consumed by `./tools/install-art-demo`
- `debug/` - debug output

**Options:**
- `--goal` (or positional): What to draw (required unless using `--from`)
- `--from` + `--instruction`: Continue from a previous run's output dir or screenshot
- `--iterations`: Number of feedback loops (default: 5)
- `--output`: Output directory (default: auto-generated `art_ai_output/TIMESTAMP`)

## AI Music Tool (`music_ai.py`)

AI composition tool for the Music room.

**Usage:**
```bash
./tools/music-ai "smiley face that sounds happy"
./tools/music-ai "heart" --no-review
./tools/music-ai "rainstorm" --json
./tools/music-ai "happy birthday" --save birthday
```

**Options:**
- `--no-review`: Skip the review pass (Pass 2)
- `--json`: Print raw JSON output
- `--save NAME`: Save as a named demo segment

For how generated segments compose into demos, see `guides/demo-system.md`.

## Dev Mode API

When `PURPLE_DEV_MODE=1` is set, the app enables file-based control:

**Screenshot trigger:** Create a file `$PURPLE_SCREENSHOT_DIR/trigger` and the app
will take a screenshot and save the path to `$PURPLE_SCREENSHOT_DIR/latest.txt`.

**Command trigger:** Write JSON commands to `$PURPLE_SCREENSHOT_DIR/command`:
```json
{"action": "mode", "value": "art"}
{"action": "key", "value": "a"}
{"action": "key", "value": "up"}
{"action": "key", "value": "enter"}
```

Supported actions:
- `mode`: Switch to a room (play, music, art)
- `key`: Send a keypress (letters, arrows, enter, escape, space, backspace, tab)

**Disable real keyboard:** Set `PURPLE_NO_EVDEV=1` to disable evdev keyboard input.
This prevents the physical keyboard from interfering with programmatic control.
The AI tool sets this automatically.

## Environment Variables

Create `tools/.env` (gitignored):
```
ANTHROPIC_API_KEY=sk-ant-...
```

Or export directly:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```
