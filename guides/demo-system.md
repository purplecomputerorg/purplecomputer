# Demo System

How to create, generate, and compose demo screencasts for Purple Computer.

## Table of Contents

- [Quick Start](#quick-start)
- [Composing a Demo](#composing-a-demo)
  - [demo.json](#demojson)
  - [Reordering and Editing](#reordering-and-editing)
  - [Removing a Segment](#removing-a-segment)
  - [Per-Segment Speed](#per-segment-speed)
- [Generating Segments](#generating-segments)
  - [Play Mode Segment (play-ai)](#play-mode-segment-play-ai)
  - [Doodle Segment (doodle-ai)](#doodle-segment-doodle-ai)
  - [Writing a Segment by Hand](#writing-a-segment-by-hand)
- [Fallback Chain](#fallback-chain)
- [How It Works](#how-it-works)
  - [Architecture](#architecture)
  - [Segment Format](#segment-format)
  - [SetSpeed Action](#setspeed-action)
  - [Demo Player Callbacks](#demo-player-callbacks)
- [Mode Behaviors (for Scripting)](#mode-behaviors-for-scripting)
  - [Play Mode](#play-mode)
  - [Doodle Mode](#doodle-mode)
  - [Explore Mode](#explore-mode)
- [Action Reference](#action-reference)
- [Color Reference](#color-reference)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Generate a Play Mode segment
./tools/play-ai "smiley face" --save smiley

# Generate a Doodle segment
./tools/doodle-ai --goal "palm tree"
./tools/install-doodle-demo --from doodle_ai_output/TIMESTAMP --save palm_tree

# Run it
make run-demo
```

Each `--save` creates a segment file in `purple_tui/demo/segments/` and adds it to `demo.json`. The demo plays all segments in order.

---

## Composing a Demo

### demo.json

The file `purple_tui/demo/demo.json` lists which segments to play and in what order:

```json
[
  {"segment": "smiley"},
  {"segment": "palm_tree", "speed": 8.0}
]
```

Each entry names a Python module in `purple_tui/demo/segments/`. The `speed` field is optional.

You don't need to create this file manually. `--save` builds it up as you generate segments. To start over, delete the file.

### Reordering and Editing

Just edit the JSON array:

```json
[
  {"segment": "palm_tree", "speed": 8.0},
  {"segment": "smiley"}
]
```

### Removing a Segment

Delete its line from `demo.json`. You can also delete the segment file from `purple_tui/demo/segments/` if you no longer need it.

### Per-Segment Speed

Speed controls how fast a segment plays back. Higher = faster.

Three places can set it, checked in this order:

1. `"speed"` in `demo.json` (highest priority)
2. `SPEED_MULTIPLIER` in the segment file
3. Default: `1.0`

The player inserts a `SetSpeed` action before each segment, so different segments can run at different speeds.

---

## Generating Segments

### Play Mode Segment (play-ai)

Generates a Play Mode composition (music + colored grid art) from a text prompt:

```bash
./tools/play-ai "smiley face" --save smiley
./tools/play-ai "heart" --save heart
./tools/play-ai "rainstorm" --save rainstorm --no-review
```

Options:
- `--save NAME`: save as a named segment and add to `demo.json`
- `--no-review`: skip the AI review pass (faster, less accurate)
- `--json`: print raw JSON instead of Python code

Without `--save`, it just prints the generated code to stdout.

### Doodle Segment (doodle-ai)

Two steps: generate the drawing, then install it as a segment.

**Step 1: Generate the drawing**

```bash
./tools/doodle-ai --goal "palm tree"
```

This creates a timestamped folder like `doodle_ai_output/20260202_143022/` with screenshots of each iteration.

**Step 2: Review the results**

Check the screenshots to pick your favorite:

```
doodle_ai_output/20260202_143022/screenshots/
  iteration_0_blank.svg
  iteration_0_blank_cropped.png
  iteration_1.svg
  iteration_1_cropped.png
  iteration_2.svg
  ...
```

The `_cropped.png` files show exactly what the AI saw. Or trust the AI's judgment (stored in `best_iteration.json`).

**Step 3: Install as a segment**

```bash
# Use best iteration (default)
./tools/install-doodle-demo --from doodle_ai_output/20260202_143022 --save palm_tree

# From a specific screenshot
./tools/install-doodle-demo --from doodle_ai_output/20260202_143022/screenshots/iteration_2b_refinement_cropped.png --save palm_tree

# Pick iteration and duration
./tools/install-doodle-demo --from doodle_ai_output/20260202_143022 --iteration 3 --duration 15 --save palm_tree
```

Options:
- `--save NAME`: save as a named segment and add to `demo.json`
- `--iteration X`: use a specific iteration instead of the best
- `--duration N`: target playback duration in seconds (default: 10)

Without `--save`, it writes to `ai_generated_script.py` (legacy behavior).

### Writing a Segment by Hand

Create a Python file in `purple_tui/demo/segments/`:

```python
# purple_tui/demo/segments/greeting.py
from ..script import SwitchMode, TypeText, PressKey, Pause

SEGMENT = [
    SwitchMode("explore"),
    TypeText("hello!"),
    PressKey("enter", pause_after=1.0),
    Pause(1.5),
]
```

Rules:
- Export a `SEGMENT` list of `DemoAction` objects
- Each segment should include its own `SwitchMode` at the start
- Optionally export `SPEED_MULTIPLIER` (float, default 1.0)

Then add it to `demo.json` manually or with:

```python
# From tools/ directory
from ai_utils import append_to_demo_json
append_to_demo_json("greeting")
```

---

## Fallback Chain

The demo system checks these in order:

1. **`demo.json`** exists: load composed segments
2. **`ai_generated_script.py`** exists: use the monolithic AI script (legacy)
3. **`default_script.py`**: the hand-crafted default

Delete `demo.json` to fall back to option 2 or 3.

---

## How It Works

### Architecture

```
demo.json               (composition: which segments, in what order)
    |
    v
segments/smiley.py      (SEGMENT = [...], SPEED_MULTIPLIER = 1.0)
segments/palm_tree.py
    |
    v
get_demo_script()       (loads demo.json, imports segments, inserts SetSpeed)
    |
    v
DemoPlayer.play()       (dispatches actions as synthetic keyboard events)
    |
    v
handle_keyboard_action()  (same path as real keyboard input)
```

Key files:
- `purple_tui/demo/script.py`: action dataclasses (TypeText, PlayKeys, DrawPath, etc.)
- `purple_tui/demo/player.py`: executes scripts by dispatching actions
- `purple_tui/demo/__init__.py`: `get_demo_script()` and composition loading
- `purple_tui/demo/segments/`: one file per segment
- `purple_tui/demo/default_script.py`: the hand-crafted fallback

### Segment Format

Each segment file exports:

```python
SEGMENT: list[DemoAction]          # required
SPEED_MULTIPLIER: float = 1.0     # optional
```

The composition loader wraps each segment with a `SetSpeed` action, so segments don't need to manage speed themselves.

### SetSpeed Action

```python
@dataclass
class SetSpeed(DemoAction):
    multiplier: float = 1.0
```

Inserted automatically between segments during composition loading. Updates the player's speed multiplier on the fly. Higher values = faster playback.

### Demo Player Callbacks

```python
DemoPlayer(
    dispatch_action=app._dispatch_keyboard_action,
    speed_multiplier=1.0,
    clear_all=app.clear_all_state,
    set_play_key_color=app._set_play_key_color,
    is_doodle_paint_mode=app._is_doodle_paint_mode,
)
```

- `clear_all`: called by `ClearAll()` to reset all modes
- `set_play_key_color`: direct color control for Play Mode keys
- `is_doodle_paint_mode`: lets `DrawPath` check if Tab is needed

---

## Mode Behaviors (for Scripting)

### Play Mode

- 10x4 grid mapped to the keyboard
- Each key press **cycles** the color: off -> purple -> blue -> red -> off
- Colors **persist** until cycled again
- Every press plays a sound, so pressing a key 3x for red also plays 3 notes

The grid:
```
1 2 3 4 5 6 7 8 9 0   (percussion)
Q W E R T Y U I O P   (high marimba)
A S D F G H J K L ;   (mid marimba)
Z X C V B N M , . /   (low marimba)
```

Strategy: plan which keys to press to form a picture. Each key should be pressed exactly the right number of times for its target color.

```python
PlayKeys(sequence=['e', None, 'i'], seconds_between=0.67)       # Eyes (purple, 1 press)
PlayKeys(sequence=['a', None, 'l'], seconds_between=0.6)       # Corners (purple)
PlayKeys(sequence=['c', 'v', 'b', 'n'], seconds_between=0.43)  # Smile (purple)
```

### Doodle Mode

Two sub-modes:
1. **Text mode** (default): typing places letters on the canvas
2. **Paint mode** (Tab to toggle): letter keys select brush color and stamp

Paint mode colors by keyboard row:
- QWERTY row: red family (light to dark, left to right)
- ASDF row: yellow family
- ZXCV row: blue family
- Number row: grayscale

Drawing mechanics:
- Lowercase key: select color AND stamp, then advance cursor
- Shift+key: select color only (no stamp)
- Space+arrows: draw lines (hold space while moving)
- `DrawPath` handles all of this automatically

### Explore Mode

Text input with results below. Just use `TypeText` + `PressKey("enter")`.

```python
SwitchMode("explore"),
TypeText("red + blue"),
PressKey("enter", pause_after=1.5),
```

---

## Action Reference

### TypeText
```python
TypeText("hello!", delay_per_char=0.08, final_pause=0.3)
```

### PressKey
```python
PressKey("enter", pause_after=0.5)
PressKey("tab")
PressKey("space", hold_duration=0.5)  # hold then release
```
Keys: `enter`, `backspace`, `escape`, `tab`, `space`, `up`, `down`, `left`, `right`

### PlayKeys
```python
PlayKeys(sequence=['a', 's', ['d', 'f'], None], seconds_between=0.5, pause_after=0.5)
```
- `'a'`: single key
- `['d', 'f']`: chord (simultaneous)
- `None`: rest

### DrawPath
```python
DrawPath(directions=['right', 'right', 'down'], color_key='f', delay_per_step=0.1)
```
Automatically enters paint mode. Holds space while moving.

### MoveSequence
```python
MoveSequence(directions=['right', 'right', 'down'], delay_per_step=0.01)
```
Moves cursor without painting. For repositioning between draws.

### SwitchMode
```python
SwitchMode("play")     # F2
SwitchMode("explore")  # F1
SwitchMode("doodle")   # F3
```

### Pause
```python
Pause(1.5)
```

### ClearAll
```python
ClearAll()  # reset all modes
```

### SetSpeed
```python
SetSpeed(multiplier=2.0)  # 2x speed from here on
```
Normally inserted automatically by the composition loader.

---

## Color Reference

### Play Mode
| Presses | Color  | Hex     |
|---------|--------|---------|
| 0       | Off    | default |
| 1       | Purple | #da77f2 |
| 2       | Blue   | #4dabf7 |
| 3       | Red    | #ff6b6b |
| 4       | Off    | cycles  |

### Doodle Mode Brushes
| Row    | Keys                 | Colors       |
|--------|----------------------|--------------|
| 1-0    | number row           | Grayscale    |
| QWERTY | q,w,e,r,t,y,u,i,o,p | Red family   |
| ASDF   | a,s,d,f,g,h,j,k,l   | Yellow family|
| ZXCV   | z,x,c,v,b,n,m       | Blue family  |

Within each row, colors go light (left) to dark (right).

### Color Mixing (Doodle)
Overlapping paint strokes mix subtractively:
- Red + Blue = Purple
- Red + Yellow = Orange
- Blue + Yellow = Green

---

## Troubleshooting

**Play mode shows a blob instead of a shape.**
Plan your key sequence on the grid first. Mark which keys form the picture before writing code.

**Play mode colors are wrong.**
A key pressed N times lands on color (N % 4). Press once for purple, twice for blue, three times for red. Four presses cycle back to off.

**Doodle mode types letters instead of painting.**
You're in text mode. Press Tab to switch to paint mode. `DrawPath` does this automatically, but manual `PressKey` sequences don't.

**Doodle colors are wrong.**
Check which keyboard row the key is on (QWERTY=red, ASDF=yellow, ZXCV=blue).

**Demo doesn't use my segments.**
Check that `demo.json` exists in `purple_tui/demo/` and that the segment names match files in `purple_tui/demo/segments/`.

**Demo plays the old monolithic script.**
Delete `demo.json` to fall back to `ai_generated_script.py`, or delete both to fall back to `default_script.py`.

**Tempo reference:**
- 90 bpm = 0.67s per note
- 120 bpm = 0.5s per note
- 180 bpm = 0.33s per note
