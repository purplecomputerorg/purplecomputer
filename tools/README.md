# Purple Computer Tools

Development tools for Purple Computer. Run these inside the VM (requires Linux/evdev).

## Setup

```bash
# Create tools/.env with your API key
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > tools/.env

# Install dependencies
source .venv/bin/activate
pip install cairosvg
```

## AI Drawing Tool (`doodle_ai.py`)

Uses Claude vision to generate drawings in Doodle mode with a visual feedback loop.

**How it works:**
1. Starts Purple Computer in dev mode
2. Takes screenshots via F8 (SVG)
3. Sends screenshot to Claude vision
4. Claude sees the canvas and generates drawing actions
5. Executes actions via real keypresses
6. Repeats for N iterations

**Usage:**
```bash
source .venv/bin/activate
python tools/doodle_ai.py --goal "a tree on a green hill" --iterations 5
python tools/doodle_ai.py --goal "sunset with orange and purple sky" --iterations 8
python tools/doodle_ai.py --goal "simple house with red roof" --iterations 3
```

**Output:**
- `doodle_ai_output/screenshots/` - SVG screenshots from each iteration
- `doodle_ai_output/actions.json` - All actions taken
- `doodle_ai_output/generated_demo.py` - Demo script for Purple Computer

**Options:**
- `--goal` (required): What to draw
- `--iterations`: Number of feedback loops (default: 5)
- `--output`: Output directory (default: `doodle_ai_output`)

## Environment Variables

Create `tools/.env` (gitignored):
```
ANTHROPIC_API_KEY=sk-ant-...
```

Or export directly:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```
