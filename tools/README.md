# Purple Computer Tools

Development tools for Purple Computer. Run these inside the VM (requires Linux/evdev).

## Setup

```bash
# Create tools/.env with your API key
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > tools/.env

# Dependencies are auto-installed on first run, or install manually:
pip install -r tools/requirements.txt
```

## AI Drawing Tool (`doodle_ai.py`)

Uses Claude vision to generate drawings in Doodle mode with a visual feedback loop.

**How it works:**
1. Starts Purple Computer in dev mode (`PURPLE_DEV_MODE=1`)
2. Controls the app via file-based commands (bypasses evdev keyboard)
3. Takes screenshots via file trigger
4. Converts SVG to PNG, sends to Claude vision
5. Claude sees the canvas and generates drawing actions
6. Executes actions, repeats for N iterations

**Usage:**
```bash
./tools/doodle-ai "a tree on a green hill"
./tools/doodle-ai "sunset with orange and purple sky" --iterations 8
./tools/doodle-ai "simple house with red roof" --iterations 3
```

**Output:**
- `doodle_ai_output/screenshots/` - SVG screenshots from each iteration
- `doodle_ai_output/actions.json` - All actions taken
- `doodle_ai_output/generated_demo.py` - Demo script for Purple Computer

**Options:**
- `--goal` (required): What to draw
- `--iterations`: Number of feedback loops (default: 5)
- `--output`: Output directory (default: `doodle_ai_output`)

## Dev Mode API

When `PURPLE_DEV_MODE=1` is set, the app enables file-based control:

**Screenshot trigger:** Create a file `$PURPLE_SCREENSHOT_DIR/trigger` and the app
will take a screenshot and save the path to `$PURPLE_SCREENSHOT_DIR/latest.txt`.

**Command trigger:** Write JSON commands to `$PURPLE_SCREENSHOT_DIR/command`:
```json
{"action": "mode", "value": "doodle"}
{"action": "key", "value": "a"}
{"action": "key", "value": "up"}
{"action": "key", "value": "enter"}
```

Supported actions:
- `mode`: Switch to a mode (explore, play, doodle)
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
