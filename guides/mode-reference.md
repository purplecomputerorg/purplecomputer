# Purple Computer Room Reference

A comprehensive guide to how each room works, including all the mechanics, tricks, and techniques for creating engaging demos.

---

## Table of Contents
1. [Music Room](#music-room)
2. [Art Room](#art-room)
3. [Play Room](#play-room)
4. [Demo Scripting Reference](#demo-scripting-reference)

Rooms are switched via the room picker (tap Escape), not F-keys.

---

# Music Room

## The Grid

A 10×4 grid that mirrors the keyboard layout:

```
Row 0:  1   2   3   4   5   6   7   8   9   0
Row 1:  Q   W   E   R   T   Y   U   I   O   P
Row 2:  A   S   D   F   G   H   J   K   L   ;
Row 3:  Z   X   C   V   B   N   M   ,   .   /
```

Each cell displays its key character and can be colored.

## Other Controls

- **Enter**: cycle the instrument (marimba, ukulele, accordion, glockenspiel).
- **Tab**: toggle Letters mode, which names each pressed letter aloud.
- **Left/Right**: shift the musical key (B♭ / F / C / G / D); **Up/Down**: shift octave.
- **Space**: loop station (record, loop, layer, double-tap to stop).

## Color Cycling

**Every key press cycles through 3 states** (`COLORS` in `music_constants.py`):

| Press # | Color           | Value           | Index |
|---------|-----------------|-----------------|-------|
| Start   | Off             | (default)       | -1    |
| 1st     | Keycap (sticker)| per-key, from KEY_COLORS | 0 |
| 2nd     | Purple          | #5a3875         | 1     |
| 3rd     | Off             | (default)       | -1    |
| 4th     | Keycap (repeats)| per-key         | 0     |

The first press lights the cell in its physical sticker color (resolved per-key
from `art_room.KEY_COLORS`), the second turns it purple, the third turns it off.

**Key insight**: Colors PERSIST. Press a key once = keycap color. Press again = purple. Press again = off.

**To draw a picture**: Press each key exactly ONCE to light it in its keycap color.

## Sound System

### Letter Keys (A-Z): Marimba Notes

**Pitch by row (frequency increases left to right within each row):**

| Row    | Keys              | Frequency Range | Character |
|--------|-------------------|-----------------|-----------|
| QWERTY | Q W E R T Y U I O P | 392-988 Hz     | Bright, high |
| ASDF   | A S D F G H J K L   | 196-494 Hz     | Warm, middle |
| ZXCV   | Z X C V B N M       | 98-247 Hz      | Rich, low    |

Within each row, left keys are lower pitch, right keys are higher:
- `A` = 196 Hz (lowest on row)
- `;` = 494 Hz (highest on row; `L` = 440 Hz)

**Sound character**: Full marimba with resonator tube harmonics, soft mallet attack.

### Number Keys (0-9): Percussion

| Key | Sound     | Character           |
|-----|-----------|---------------------|
| 0   | Gong      | Deep, sustained     |
| 1   | Kick drum | Punchy, low         |
| 2   | Snare     | Crispy, mid         |
| 3   | Hi-hat    | Bright, short       |
| 4   | Clap      | Hand-like           |
| 5   | Cowbell   | Metallic, fun       |
| 6   | Woodblock | Hollow tick         |
| 7   | Triangle  | Ding, sustain       |
| 8   | Tambourine| Jingly              |
| 9   | Bongo     | Mid-range drum      |

## Demo Tricks for Music Room

### Drawing Shapes

**Important**: The grid is only 10 wide × 4 tall. For a proper **smile** (curving UP),
the mouth's ENDS must be HIGHER (lower row number) than the CENTER.

To draw a **smiley face** (smile curves UP):
```
Col:  0 1 2 3 4 5 6 7 8 9
      . . . 4 . 6 . . . .   ← Row 0: Eyes (4 and 6)
      . . . . T . . . . .   ← Row 1: Nose (T)
      . . D . . . J . . .   ← Row 2: Smile CORNERS (UP)
      . . C V B N M . . .   ← Row 3: Smile BOTTOM (DOWN)
```

Keys to press: `4`, `6` (eyes), `T` (nose), `D`, `J` (smile corners), then `C`, `V`, `B`, `N`, `M` (smile bottom)

This creates an upward-curving smile because the corners (D, J) are ABOVE the bottom (CVBNM)!

To draw a **simple house**:
```
Col:  0 1 2 3 4 5 6 7 8 9
      . . . 4 5 6 . . . .   ← Row 0: Roof peak
      . . . R . Y . . . .   ← Row 1: Roof sides
      . . . F G H . . . .   ← Row 2: Upper walls
      . . . V B N . . . .   ← Row 3: Lower walls + door (B)
```

Keys: `4`, `5`, `6`, `R`, `Y`, `F`, `G`, `H`, `V`, `B`, `N`

Then press `B` once more to turn the door purple!

### Multi-Color Patterns

Each key has two lit looks: its keycap color (1st press) and purple (2nd press).
To mix the two:
- Press some keys once (keycap color)
- Press other keys twice (purple)

### Musical Sequences

**Ascending scale** (sounds good): `Z`, `X`, `C`, `V`, `B`, `N`, `M`
**Descending scale**: `M`, `N`, `B`, `V`, `C`, `X`, `Z`

**Chord** (multiple keys at once): Any keys pressed rapidly together blend into a chord.

**Melodic patterns**:
- Arpeggios: `A`, `D`, `G`, `K` (skipping keys)
- Octave jumps: `A` then `Q` (same column, different row)

### Clearing the Grid

Switch away from the Music room and back, or use `ClearAll()` in demo script to reset all colors to off.

---

# Art Room

## Two Sub-Modes

### Text Mode (Default)
- **Cursor**: Purple vertical bar `▌`
- **Typing**: Characters appear at cursor, cursor moves right
- **Auto-wrap**: At right edge, wraps to next line
- **Background**: Subtle tint based on keyboard row (15% strength)

### Paint Mode
- **Cursor**: 3×3 blinking ring of box-drawing characters
- **Typing**: Stamps colored blocks and advances cursor
- **Drawing**: Hold Space + arrows to draw lines
- **Toggle**: Press **Tab** to switch between modes

## Color System

### Keyboard Row → Color Family

| Row      | Keys                | Color Family | Tint (text mode) | Paint colors |
|----------|---------------------|--------------|------------------|--------------|
| Numbers  | 1 2 3 4 5 6 7 8 9 0 - = | **Grayscale**| None         | White → Black |
| QWERTY   | Q W E R T Y U I O P | **Red**      | Dark red         | Light red → Dark red |
| ASDF     | A S D F G H J K L   | **Yellow**   | Gold/mustard     | Light gold → Dark gold |
| ZXCV     | Z X C V B N M       | **Blue**     | Dark blue        | Light blue → Dark blue |

### Within Each Row: Light to Dark Gradient

Left keys = lighter, right keys = darker. Exact values are computed by `generate_row_gradient()` in `art_room.py` (HSL, saturation 0.75, lightness 0.80 down to 0.20 across the row). Samples:

**QWERTY (Red family)**:
- `Q` = #F2A5A5 (light red)
- `T` = #E44444 (medium red)
- `P` = #891313 (dark red)

**ASDF (Yellow family)**:
- `A` = #F2E5A5 (light gold)
- `F` = #E6CE55 (medium gold)
- `L` = #8E7A14 (dark gold)

**ZXCV (Blue family)**:
- `Z` = #A5BFF2 (light blue)
- `V` = #4C7FE5 (medium blue)
- `M` = #194CB2 (dark navy)

**Number row (Grayscale)** (`GRAYSCALE` in `art_room.py`; 1 = lightest, then darker rightward through `-` and `=`):
```
1: #FFFFFF (white)     6: #888888 (middle gray)
2: #E8E8E8             7: #707070
3: #D0D0D0             8: #585858
4: #B8B8B8             9: #404040
5: #A0A0A0             0: #282828
-: #101010 (near black)   = and +: #000000 (pure black)
```

## Color Mixing

### How It Works

When you paint OVER an existing painted cell, the colors MIX using realistic paint physics (Kubelka-Munk spectral mixing):

| First Color | Second Color | Result      |
|-------------|--------------|-------------|
| Yellow (F)  | Blue (C)     | **Green**   |
| Red (R)     | Blue (C)     | **Purple**  |
| Red (R)     | Yellow (F)   | **Orange**  |
| Any color   | Same color   | Same color  |

**To mix colors in a demo:**
1. Draw with first color (e.g., yellow `F`)
2. Draw OVER the same cells with second color (e.g., blue `C`)
3. The overlapping cells become green!

### Text Mode Background Tints

In text mode, backgrounds get subtle tints (15%) but don't mix. Typing over an existing cell replaces the tint.

## Cursor Movement

### Arrow Keys
- **Up/Down/Left/Right**: Move cursor one cell
- **Diagonal**: Hold two arrows simultaneously
- **Edge behavior**: Cursor stops at edges (no wrapping)

### Positioning the Cursor

**To get to the center of the canvas:**
```python
# Assuming ~80 wide × ~24 tall canvas
# Move right ~40 times and down ~12 times
for _ in range(40):
    PressKey("right")
for _ in range(12):
    PressKey("down")
```

**Or use a helper in the demo script to estimate center based on typical terminal size.**

### Enter Key
Moves down one row, keeps column position. Useful for vertical typing/drawing.

### Backspace
- **Single press**: Erase character, fade background 50%
- **Hold 1+ second**: Clear entire canvas

## Drawing Lines

### Space + Arrows

1. Enter paint mode (Tab)
2. Select a color (press a letter key with Shift to select without stamping)
3. Press and hold Space
4. While holding Space, press arrow keys to paint in that direction
5. Release Space to stop drawing

**Each arrow press while Space is held:**
- Moves cursor in that direction
- Paints the cell you moved INTO

### Directional Typing

Hold an arrow key while typing to advance in that direction instead of right:
- Hold **Left** + type → text goes leftward
- Hold **Down** + type → text goes downward

## Paint Mode Tricks

### Shift + Letter = Select Color Without Stamping

In paint mode:
- `G` = Select gold color AND stamp at cursor
- `Shift+G` = Select gold color, DON'T stamp

Use this to "load your brush" before drawing a line.

### The Brush Ring

The 3×3 blinking ring shows:
- **Your current brush color** (in the box-drawing characters)
- **What's under the cursor** (the center "hole")

### Combining Text and Paint

1. Paint a colorful background
2. Press Tab to switch to text mode
3. Type text over the painted area
4. Text appears with readable foreground on colored background

---

# Play Room

## Input Types

### Pure Math
```
2 + 2           → 4 (with dots: ••••)
3 * 4           → 12 (×4 displays as multiplication)
10 / 2          → 5 (÷2 displays as division)
(2 + 3) * 4     → 20 (parentheses work)
```

### Emoji Expressions
```
cat             → 🐱
3 cats          → 🐱🐱🐱
cats            → 🐱🐱 (bare plural = 2)
cat + dog       → 🐱 🐶
3 * 4 cats      → 12 🐱 (with label + 12 cats displayed)
```

### Color Mixing
```
red + blue      → Purple swatch (Kubelka-Munk mixing)
red + yellow    → Orange swatch
blue + yellow   → Green swatch
3 red + 1 blue  → Weighted mix (more red)
```

### Combined Expressions
```
2 + 3 cats      → 5 🐱 (math attaches to emoji)
red + 3 cats    → Red swatch + 3 🐱
what is 2 + 3   → "what is 5" (text preserved)
```

## Speech/Sound

### Triggers

| Input           | Effect                    |
|-----------------|---------------------------|
| `cat!`          | Shows 🐱, speaks "cat"    |
| `!cat`          | Same (! anywhere works)   |
| `say cat`       | Speaks "cat"              |
| `2 + 3!`        | Shows 5, speaks "2 plus 3 equals 5" |
| Enter (empty)   | Repeats last result aloud |

### What Gets Spoken

- **Simple word**: Just the word ("cat")
- **Math**: "input equals result" ("2 plus 3 equals 5")
- **Emoji math**: "3 times 4 cats equals 12 cats"
- **Colors**: The resulting color name ("purple")

## Color Mixing Details

Same Kubelka-Munk algorithm as the Art room:

| Mix               | Result  |
|-------------------|---------|
| red + blue        | Purple  |
| red + yellow      | Orange  |
| blue + yellow     | Green   |
| red + blue + yellow | Brown-ish |

**Weighted mixing**: `3 red + 1 blue` leans more red than `1 red + 1 blue`.

## Autocomplete

- Appears after typing 2+ characters
- Shows matching emojis and colors
- Press **Tab** to accept suggestion
- Shows both emoji icon and color swatch for words like "orange" (both 🍊 and color)

## Demo Tricks for Play Room

### Quick Impressive Queries
```
hello!              → Shows greeting, speaks it
red + blue          → Purple swatch (magic!)
3 + 2 cats          → 5 🐱🐱🐱🐱🐱
blue + yellow       → Green swatch
what is 5 * 5       → "what is 25" with 25 dots
```

### Color Mixing Showcase
```
red + blue          → Purple
blue + yellow       → Green (realistic paint mixing!)
red + yellow        → Orange
```

### Fun Emoji Math
```
3 cats + 2 dogs     → 🐱🐱🐱 🐶🐶
5 * 2 bananas       → 10 🍌 (with visualization)
(2 + 3) apples      → 5 🍎 (parentheses trigger label)
```

---

# Demo Scripting Reference

## Available Actions

### TypeText
```python
TypeText("hello!", delay_per_char=0.08)
```
Types characters one at a time. Works in any mode.

### PressKey
```python
PressKey("enter", pause_after=0.5)
PressKey("tab")      # Toggle paint mode (Art) or Letters mode (Music); accept autocomplete (Play)
PressKey("space")    # Type a space
PressKey("space", hold_duration=0.5)  # Hold to open Code Space (Music/Art)
PressKey("up")       # Navigate/scroll
```

### PlayKeys
```python
PlayKeys(
    sequence=['e', 'i', 'a', 'l', 'c', 'v', 'b', 'n'],
    seconds_between=0.5,
    pause_after=0.5,
)
```

Special sequence items:
- `'a'` = single key
- `['a', 's']` = chord (simultaneous)
- `None` = rest (silence)

### DrawPath
```python
DrawPath(
    directions=['right', 'right', 'down', 'down', 'left'],
    color_key='f',        # Yellow (ASDF row)
    delay_per_step=0.1,
)
```
Automatically enters paint mode if needed.

### SwitchRoom
```python
SwitchRoom("music")
SwitchRoom("play")
SwitchRoom("art")
```

### Pause
```python
Pause(1.5)  # Wait 1.5 seconds
```

### ClearAll
```python
ClearAll()  # Reset all modes to clean state
```

## Demo Design Tips

### Music Room Pictures

Plan your key sequence on paper first:
```
Grid planning:
1 2 3 4 5 6 7 8 9 0
Q W E R T Y U I O P
A S D F G H J K L ;
Z X C V B N M , . /

Mark which keys to press for your shape.
Assign colors by press count.
```

### Art Room Drawings

1. **Position first**: Use multiple PressKey("down")/("right") to get to starting position
2. **Draw shapes**: Use DrawPath with directions
3. **Mix colors**: Draw overlapping paths with different color_keys
4. **Add text**: Press Tab to exit paint mode, then TypeText

### Play Room Wow Moments

The most impressive demos:
1. Color mixing (`red + blue` → purple)
2. Emoji math with visualization (`5 * 3 cats`)
3. Speech (`hello!` with sound)

### Timing

`seconds_between` controls the gap between each key press:
- `seconds_between=0.5` = half a second per note
- `seconds_between=0.33` = fast
- `seconds_between=0.67` = slow, dramatic

### Multi-Color Music Room Patterns

To get different colors on different keys:
```python
# First set of keys: press once (keycap color)
PlayKeys(sequence=['e', 'i'], seconds_between=0.6)

# Second set: press twice (purple)
PlayKeys(sequence=['a', 'a', 'l', 'l'], seconds_between=0.4)
```

### Art Room Color Mixing Demo

```python
# Draw yellow square
DrawPath(directions=['right', 'right', 'right'], color_key='f')
PressKey("down")
PressKey("left")
PressKey("left")
PressKey("left")
DrawPath(directions=['right', 'right', 'right'], color_key='f')

# Draw blue stripe through it (creates green where they overlap!)
PressKey("up")
PressKey("left")
DrawPath(directions=['right', 'right', 'right', 'right'], color_key='c')
```

---

## Quick Reference Tables

### Music Room Grid
```
1 2 3 4 5 6 7 8 9 0   ← Percussion sounds
Q W E R T Y U I O P   ← High marimba (392-988 Hz)
A S D F G H J K L ;   ← Mid marimba (196-494 Hz)
Z X C V B N M , . /   ← Low marimba (98-247 Hz)
```

### Art Room Color Keys
```
1 through =: Grayscale (white to black)
QWERTY: Red family (light to dark)
ASDF: Yellow family (light to dark)
ZXCV: Blue family (light to dark)
```

### Color Mixing Results
```
Red + Blue = Purple
Red + Yellow = Orange
Blue + Yellow = Green
```

### Room Shortcuts
```
Esc (tap): Open room picker (Play, Music, Art)
Esc (hold 1s): Parent mode
Tab (in Art): Toggle text/paint mode
Tab (in Music): Toggle Letters mode
```
