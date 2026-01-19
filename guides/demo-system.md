# Demo System Architecture

This guide explains how the demo playback system works and the key behaviors of each mode that affect demo scripting.

## Overview

The demo system (`purple_tui/demo/`) plays back scripted sequences of keyboard actions to showcase Purple Computer's features. The demo player dispatches synthetic keyboard actions through the same handler as real keyboard input.

**Key files:**
- `demo/script.py`: Action types (TypeText, PlayKeys, DrawPath, etc.)
- `demo/default_script.py`: The actual demo script
- `demo/player.py`: Executes scripts by dispatching actions

## Mode Behaviors (Critical for Scripting)

### Play Mode

**How it works:**
- Displays a 10x4 grid matching the keyboard layout
- Each key has a color state: -1 (off), 0 (purple), 1 (blue), 2 (red)
- Pressing a key **cycles** to the next color (purple → blue → red → off → purple...)
- Colors **persist** until cycled again or reset

**The key insight:** Persistent colors ARE the feature! By pressing keys strategically,
you can "draw pictures" on the keyboard grid while playing music. For example,
pressing E, I (eyes) then C, V, B, N (smile) creates a smiley face.

**The grid layout:**
```
1 2 3 4 5 6 7 8 9 0
Q W E R T Y U I O P
A S D F G H J K L ;
Z X C V B N M , . /
```

**Demo strategy:** Plan your key sequences to create recognizable shapes:
- Smiley: E, I (eyes) + A, L (corners) + C, V, B, N (smile curve)
- Heart: Design keys that form a heart shape
- Avoid pressing the same key twice (it cycles to next color)

```python
# Example: Draw a smiley face
PlayKeys(sequence=['e', None, 'i'], tempo_bpm=90)      # Eyes
PlayKeys(sequence=['a', None, 'l'], tempo_bpm=100)    # Corners
PlayKeys(sequence=['c', 'v', 'b', 'n'], tempo_bpm=140)  # Smile
```

### Doodle Mode

**Two sub-modes:**
1. **Text mode** (default): Typing letters places them on the canvas
2. **Paint mode**: Letters select brush colors and stamp colored blocks

**How to switch:** Press Tab to toggle between text and paint mode.

**Paint mode behavior:**
- Letter keys (a-z) select brush color based on keyboard row:
  - QWERTY row: Red family
  - ASDF row: Yellow/gold family
  - ZXCV row: Blue family
- Number keys (0-9) select grayscale
- Lowercase: Select color AND stamp at cursor, then advance
- Shift+letter: Select color only (no stamp)
- Space+arrows: Draw lines (hold space while moving)

**Common mistake:** Using `DrawPath` without entering paint mode first. The demo player now automatically enters paint mode before drawing.

```python
# DrawPath execution:
# 1. Check if in paint mode, if not: press Tab
# 2. Press Shift+color_key to select brush (no stamp)
# 3. Hold Space + move in directions to paint line
# 4. Release Space
```

### Explore Mode

**How it works:**
- Text input field for questions/expressions
- Results appear below after pressing Enter
- History scrolls up

**For demos:** Just use `TypeText` + `PressKey("enter")`. No special considerations.

## Demo Script Actions

### TypeText
Types characters one at a time. Works in any mode.
```python
TypeText("hello", delay_per_char=0.08)
```

### PressKey
Presses special keys (enter, tab, space, arrows, etc).
```python
PressKey("enter", pause_after=0.5)
PressKey("space", count=2)  # Toggle paint mode in Doodle
```

### PlayKeys
Plays a sequence of keys with musical timing. In Play mode, lights up keys.
```python
PlayKeys(
    sequence=['a', 's', 'd', ['f', 'g']],  # Last item is a chord
    tempo_bpm=120,
)
```
- Single key: `'a'`
- Chord (simultaneous): `['a', 's']`
- Rest (silence): `None`

### DrawPath
Draws colored lines in Doodle mode's paint mode.
```python
DrawPath(
    directions=['right', 'right', 'down', 'down'],
    color_key='g',  # Green (ASDF row)
    delay_per_step=0.1,
)
```
**Note:** Automatically enters paint mode if not already in it.

### SwitchMode
Changes to a different mode.
```python
SwitchMode("play")    # F2
SwitchMode("explore") # F1
SwitchMode("doodle")  # F3
```

### Pause
Wait for a duration.
```python
Pause(1.5)  # Wait 1.5 seconds
```

### ClearAll
Clears all state across all modes. Use at start of demo.
```python
ClearAll()
```

## Color Reference

### Play Mode Colors
| Index | Color   | Hex       |
|-------|---------|-----------|
| -1    | Off     | (default) |
| 0     | Purple  | #da77f2   |
| 1     | Blue    | #4dabf7   |
| 2     | Red     | #ff6b6b   |

### Doodle Mode Brush Colors
| Row    | Keys          | Color Family |
|--------|---------------|--------------|
| Number | 1-0           | Grayscale    |
| QWERTY | q,w,e,r,t,y,u,i,o,p | Red family   |
| ASDF   | a,s,d,f,g,h,j,k,l   | Yellow family |
| ZXCV   | z,x,c,v,b,n,m       | Blue family   |

Within each row, colors go from light (left) to dark (right).

## Demo Player Callbacks

The demo player accepts callbacks for mode state:

```python
DemoPlayer(
    dispatch_action=app._dispatch_keyboard_action,
    clear_all=app.clear_all_state,
    set_play_key_color=app._set_play_key_color,      # Direct color control (optional)
    is_doodle_paint_mode=app._is_doodle_paint_mode,  # Check if in paint mode
)
```

The `is_doodle_paint_mode` callback lets DrawPath check if we're already in paint mode
before pressing Tab (avoids toggling back to text mode).

## Example: Good Demo Sequence

```python
DEMO_SCRIPT = [
    ClearAll(),

    # Quick greeting in Explore mode
    TypeText("hello!"),
    PressKey("enter", pause_after=1.0),

    # Play mode: draw a smiley face while playing music
    SwitchMode("play"),
    PlayKeys(sequence=['e', None, 'i'], tempo_bpm=90),      # Eyes
    PlayKeys(sequence=['a', None, 'l'], tempo_bpm=100),     # Corners
    PlayKeys(sequence=['c', 'v', 'b', 'n'], tempo_bpm=140), # Smile

    # Explore mode: show color mixing
    SwitchMode("explore"),
    TypeText("red+blue"),
    PressKey("enter", pause_after=1.5),

    # Doodle mode: draw with colors and add text
    SwitchMode("doodle"),
    DrawPath(directions=['right', 'right', 'down'], color_key='f'),  # Yellow
    DrawPath(directions=['down', 'left'], color_key='c'),            # Blue (mixes!)
    PressKey("tab"),  # Switch to text mode
    TypeText("Purple!"),
]
```

## Troubleshooting

**Problem:** Play mode shows a blob instead of a recognizable shape.
**Cause:** Keys pressed randomly without considering grid positions.
**Fix:** Plan your key sequence to form a picture. Use the grid reference above.

**Problem:** Play mode colors keep changing on same keys.
**Cause:** Pressing the same key multiple times cycles it through colors.
**Fix:** Avoid pressing the same key twice. Each key should only be pressed once per picture.

**Problem:** Doodle mode shows typed letters instead of colored paint.
**Cause:** Drawing while in text mode instead of paint mode.
**Fix:** DrawPath auto-enters paint mode. For manual drawing, press Tab first.

**Problem:** Colors are wrong or missing in Doodle.
**Cause:** Using wrong key for color (see color reference above).
**Fix:** Use keys from the correct keyboard row for desired color family.
