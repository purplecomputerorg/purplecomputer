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
- Displays a 10x4 grid of keys
- Each key has a color state: -1 (off), 0 (purple), 1 (blue), 2 (red)
- Pressing a key **cycles** to the next color (purple → blue → red → off → purple...)
- Colors **persist** until cycled again or reset

**Common mistake:** Assuming keys light up while held and turn off on release (like a piano). They don't. Each press cycles the color and it stays.

**For demos:** The demo player uses `set_play_key_color` callback to directly set colors, enabling "flash" behavior where keys light up momentarily then turn off.

```python
# In PlayKeys, with flash enabled:
# 1. Set key to purple (index 0)
# 2. Play sound
# 3. Wait beat duration
# 4. Set key to off (index -1)
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

**Common mistake:** Using `DrawPath` without entering paint mode first. The demo player now automatically presses Tab to enter paint mode before drawing.

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
PressKey("tab")  # Toggle paint mode in Doodle
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

The demo player accepts callbacks for direct mode manipulation:

```python
DemoPlayer(
    dispatch_action=app._dispatch_keyboard_action,
    clear_all=app.clear_all_state,
    set_play_key_color=app._set_play_key_color,      # For flash effects
    is_doodle_paint_mode=app._is_doodle_paint_mode,  # Check paint mode
)
```

## Example: Good Demo Sequence

```python
DEMO_SCRIPT = [
    ClearAll(),

    # Play mode: flash keys in sequence
    SwitchMode("play"),
    PlayKeys(sequence=['a', 's', 'd', 'f'], tempo_bpm=180),

    # Explore mode: ask a question
    SwitchMode("explore"),
    TypeText("red+blue"),
    PressKey("enter", pause_after=1.5),

    # Doodle mode: draw a colored shape
    SwitchMode("doodle"),
    # DrawPath auto-enters paint mode
    DrawPath(directions=['right', 'right', 'down', 'down'], color_key='g'),
    DrawPath(directions=['left', 'left'], color_key='r'),
]
```

## Troubleshooting

**Problem:** Play mode keys stay lit as rectangles instead of flashing.
**Cause:** set_play_key_color callback not wired up, falling back to cycle behavior.
**Fix:** Ensure DemoPlayer receives the callback from PurpleApp.

**Problem:** Doodle mode shows typed letters instead of colored paint.
**Cause:** Drawing while in text mode instead of paint mode.
**Fix:** DrawPath now auto-enters paint mode. For manual drawing, send Tab first.

**Problem:** Colors are wrong or missing.
**Cause:** Using wrong key for color (see color reference above).
**Fix:** Use keys from the correct keyboard row for desired color family.
