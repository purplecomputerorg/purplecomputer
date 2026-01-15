# Purple Computer Mode Reference

A comprehensive guide to how each mode works, including all the mechanics, tricks, and techniques for creating engaging demos.

---

## Table of Contents
1. [Play Mode (F2)](#play-mode-f2)
2. [Doodle Mode (F3)](#doodle-mode-f3)
3. [Explore Mode (F1)](#explore-mode-f1)
4. [Demo Scripting Reference](#demo-scripting-reference)

---

# Play Mode (F2)

## The Grid

A 10×4 grid that mirrors the keyboard layout:

```
Row 0:  1   2   3   4   5   6   7   8   9   0
Row 1:  Q   W   E   R   T   Y   U   I   O   P
Row 2:  A   S   D   F   G   H   J   K   L   ;
Row 3:  Z   X   C   V   B   N   M   ,   .   /
```

Each cell displays its key character and can be colored.

## Color Cycling

**Every key press cycles through 4 states:**

| Press # | Color  | Hex       | Index |
|---------|--------|-----------|-------|
| Start   | Off    | (default) | -1    |
| 1st     | Purple | #da77f2   | 0     |
| 2nd     | Blue   | #4dabf7   | 1     |
| 3rd     | Red    | #ff6b6b   | 2     |
| 4th     | Off    | (default) | -1    |
| 5th     | Purple | (repeats) | 0     |

**Key insight**: Colors PERSIST. Press a key once = purple. Press again = blue. Press again = red. Press again = off.

**To draw a picture**: Press each key exactly ONCE to make it purple. Avoid pressing the same key twice unless you want a different color.

**To make multi-colored patterns**:
- Press some keys once (purple)
- Press other keys twice (blue)
- Press other keys three times (red)

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
- `L` = 494 Hz (highest on row)

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

## Demo Tricks for Play Mode

### Drawing Shapes

To draw a **smiley face**:
```
. . . . . . . . . .
. . E . . . . I . .   ← Press E, I (eyes)
A . . . . . . . . L   ← Press A, L (corners)
. . C V B N . . . .   ← Press C, V, B, N (smile)
```

Keys to press (in order for nice melody): `E`, `I`, `A`, `L`, `C`, `V`, `B`, `N`

To draw a **heart**:
```
. 2 3 . . . 8 9 .
Q . . R T Y . . O P
. S . . . . . K . .
. . X C . N M . . .
. . . . B . . . . .
```

### Multi-Color Patterns

To make alternating colors:
- Press row 1 keys once (purple eyes)
- Press row 3 keys twice each (blue smile)

### Musical Sequences

**Ascending scale** (sounds good): `Z`, `X`, `C`, `V`, `B`, `N`, `M`
**Descending scale**: `M`, `N`, `B`, `V`, `C`, `X`, `Z`

**Chord** (multiple keys at once): Any keys pressed rapidly together blend into a chord.

**Melodic patterns**:
- Arpeggios: `A`, `D`, `G`, `K` (skipping keys)
- Octave jumps: `A` then `Q` (same column, different row)

### Clearing the Grid

Switch away from Play mode and back, or use `ClearAll()` in demo script to reset all colors to off.

---

# Doodle Mode (F3)

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

**Double-tap Space** (in text mode): Also toggles to paint mode.

## Color System

### Keyboard Row → Color Family

| Row      | Keys                | Color Family | Tint (text mode) | Paint colors |
|----------|---------------------|--------------|------------------|--------------|
| Numbers  | 1 2 3 4 5 6 7 8 9 0 | **Grayscale**| None             | White → Black |
| QWERTY   | Q W E R T Y U I O P | **Red**      | Dark red         | Light red → Dark red |
| ASDF     | A S D F G H J K L   | **Yellow**   | Gold/mustard     | Light gold → Dark gold |
| ZXCV     | Z X C V B N M       | **Blue**     | Dark blue        | Light blue → Dark blue |

### Within Each Row: Light to Dark Gradient

Left keys = lighter, right keys = darker:

**QWERTY (Red family)**:
- `Q` = #BF6C6C (light salmon)
- `T` = #A32C2C (medium red)
- `P` = #801C1C (dark burgundy)

**ASDF (Yellow family)**:
- `A` = #BFAF40 (light gold)
- `F` = #AA7F40 (medium gold)
- `L` = #875F40 (dark brown-gold)

**ZXCV (Blue family)**:
- `Z` = #6C8CBF (light periwinkle)
- `V` = #3C5CAA (medium blue)
- `M` = #1C3495 (dark navy)

**Number row (Grayscale)**:
```
1: #FFFFFF (white)     6: #606060
2: #E0E0E0             7: #404040
3: #C0C0C0             8: #202020
4: #A0A0A0             9: #101010
5: #808080 (gray)      0: #000000 (black)
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

# Explore Mode (F1)

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

Same Kubelka-Munk algorithm as Doodle mode:

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
- Press **Space** to accept suggestion
- Shows both emoji icon and color swatch for words like "orange" (both 🍊 and color)

## Demo Tricks for Explore Mode

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
PressKey("tab")      # Toggle paint mode in Doodle
PressKey("space")    # Accept autocomplete or type space
PressKey("up")       # Navigate/scroll
```

### PlayKeys
```python
PlayKeys(
    sequence=['e', 'i', 'a', 'l', 'c', 'v', 'b', 'n'],
    tempo_bpm=120,
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

### SwitchMode
```python
SwitchMode("play")    # F2
SwitchMode("explore") # F1
SwitchMode("doodle")  # F3
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

### Play Mode Pictures

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

### Doodle Mode Art

1. **Position first**: Use multiple PressKey("down")/("right") to get to starting position
2. **Draw shapes**: Use DrawPath with directions
3. **Mix colors**: Draw overlapping paths with different color_keys
4. **Add text**: PressKey("tab") to exit paint mode, then TypeText

### Explore Mode Wow Moments

The most impressive demos:
1. Color mixing (`red + blue` → purple)
2. Emoji math with visualization (`5 * 3 cats`)
3. Speech (`hello!` with sound)

### Timing

- `tempo_bpm=120` = 0.5 seconds per note
- `tempo_bpm=180` = 0.33 seconds per note
- `tempo_bpm=90` = 0.67 seconds per note

### Multi-Color Play Mode Patterns

To get different colors on different keys:
```python
# First set of keys: press once (purple)
PlayKeys(sequence=['e', 'i'], tempo_bpm=100)

# Second set: press twice (blue)
PlayKeys(sequence=['a', 'a', 'l', 'l'], tempo_bpm=150)

# Third set: press three times (red)
PlayKeys(sequence=['c', 'c', 'c', 'n', 'n', 'n'], tempo_bpm=200)
```

### Doodle Color Mixing Demo

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

### Play Mode Grid
```
1 2 3 4 5 6 7 8 9 0   ← Percussion sounds
Q W E R T Y U I O P   ← High marimba (392-988 Hz)
A S D F G H J K L ;   ← Mid marimba (196-494 Hz)
Z X C V B N M , . /   ← Low marimba (98-247 Hz)
```

### Doodle Color Keys
```
1-0: Grayscale (white to black)
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

### Mode Shortcuts
```
F1: Explore mode
F2: Play mode
F3: Doodle mode
Tab (in Doodle): Toggle text/paint mode
```
