"""Alternative demo scripts to compare.

Run with: PURPLE_DEMO_SCRIPT=option1 python -m purple_tui

Each demo showcases different aspects of Purple Computer.
"""

from .script import (
    TypeText,
    PressKey,
    SwitchMode,
    Pause,
    ClearAll,
    PlayKeys,
    DrawPath,
    Comment,
)


# =============================================================================
# OPTION 1: "THE MAGIC SHOW"
# =============================================================================
# Theme: Color mixing is MAGIC! Show it in Explore, then prove it in Doodle.
# Duration: ~60 seconds
# Highlights: Color mixing wow moments, speech, paint mixing demo

DEMO_OPTION_1 = [
    ClearAll(),
    Comment("=== THE MAGIC SHOW ==="),

    # -------------------------------------------------------------------------
    # ACT 1: The Question (Explore) - 8s
    # Start with curiosity, build anticipation
    # -------------------------------------------------------------------------
    Pause(0.5),
    TypeText("What happens when you mix colors?", delay_per_char=0.06),
    PressKey("enter", pause_after=2.0),

    # -------------------------------------------------------------------------
    # ACT 2: The First Trick (Explore) - 12s
    # Red + Blue = Purple - the classic magic trick!
    # -------------------------------------------------------------------------
    TypeText("Red + Blue", delay_per_char=0.08),
    PressKey("enter", pause_after=2.5),  # Let them see the purple!

    TypeText("Blue + Yellow", delay_per_char=0.08),
    PressKey("enter", pause_after=2.5),  # Green appears!

    TypeText("Red + Yellow", delay_per_char=0.08),
    PressKey("enter", pause_after=2.5),  # Orange!

    # -------------------------------------------------------------------------
    # ACT 3: Musical Interlude (Play) - 10s
    # Celebratory melody while drawing a star pattern
    # -------------------------------------------------------------------------
    Comment("=== CELEBRATION ==="),
    SwitchMode("play"),
    Pause(0.3),

    # Draw a simple star/diamond pattern
    # Center column: 5, T, G, B
    # Plus arms: 4, 6, R, Y, F, H
    PlayKeys(
        sequence=['5', 't', 'g', 'b'],  # Vertical line
        tempo_bpm=140,
        pause_after=0.2,
    ),
    PlayKeys(
        sequence=['4', '6', 'r', 'y', 'f', 'h'],  # Arms
        tempo_bpm=160,
        pause_after=0.5,
    ),

    # -------------------------------------------------------------------------
    # ACT 4: Prove the Magic (Doodle) - 20s
    # Actually MIX colors on canvas - yellow + blue = green!
    # -------------------------------------------------------------------------
    Comment("=== PROVING THE MAGIC ==="),
    SwitchMode("doodle"),
    Pause(0.3),

    # Position: move to good starting spot
    PressKey("down"),
    PressKey("down"),
    PressKey("right"),
    PressKey("right"),

    # Draw a yellow sun (ASDF row = yellow)
    DrawPath(
        directions=['right', 'right', 'right', 'right', 'right'],
        color_key='f',
        delay_per_step=0.06,
    ),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(
        directions=['right', 'right', 'right', 'right', 'right', 'right', 'right'],
        color_key='d',
        delay_per_step=0.06,
    ),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(
        directions=['right', 'right', 'right', 'right', 'right'],
        color_key='f',
        delay_per_step=0.06,
    ),
    Pause(0.4),

    # Now draw BLUE through it - watch it turn GREEN!
    PressKey("up"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(
        directions=['down', 'down', 'down'],
        color_key='c',  # Blue from ZXCV row
        delay_per_step=0.15,  # Slower so they can see the mixing
    ),
    Pause(0.8),

    # Add text label
    PressKey("tab"),  # Exit paint mode
    PressKey("right"),
    PressKey("right"),
    PressKey("right"),
    PressKey("right"),
    PressKey("up"),
    TypeText("Magic!", delay_per_char=0.1),
    Pause(0.8),

    # -------------------------------------------------------------------------
    # ACT 5: Grand Finale (Play) - 8s
    # Triumphant chord sequence
    # -------------------------------------------------------------------------
    Comment("=== FINALE ==="),
    SwitchMode("play"),
    Pause(0.2),
    PlayKeys(
        sequence=[['a', 'd', 'g'], None, ['s', 'f', 'h'], None, ['a', 'd', 'g', 'k']],
        tempo_bpm=90,
        pause_after=1.0,
    ),

    Comment("Demo complete!"),
]


# =============================================================================
# OPTION 2: "SMILEY SYMPHONY"
# =============================================================================
# Theme: Draw a smiley face in Play mode while making music!
# Duration: ~55 seconds
# Highlights: Play mode picture-drawing, emoji fun, expressive

DEMO_OPTION_2 = [
    ClearAll(),
    Comment("=== SMILEY SYMPHONY ==="),

    # -------------------------------------------------------------------------
    # INTRO: Set the mood (Explore) - 5s
    # -------------------------------------------------------------------------
    Pause(0.3),
    TypeText("Let's make a smiley!", delay_per_char=0.07),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # MAIN EVENT: Draw smiley in Play mode - 20s
    # Grid reminder:
    #   1 2 3 4 5 6 7 8 9 0
    #   Q W E R T Y U I O P   <- E and I are perfect eye positions
    #   A S D F G H J K L ;   <- smile corners at A and L
    #   Z X C V B N M , . /   <- smile curve C V B N
    # -------------------------------------------------------------------------
    Comment("=== DRAWING THE SMILEY ==="),
    SwitchMode("play"),
    Pause(0.5),

    # Eyes first - high notes, happy sound!
    # E and I with dramatic pause between
    PlayKeys(
        sequence=['e', None, None, 'i'],
        tempo_bpm=80,  # Slow, dramatic
        pause_after=0.5,
    ),

    # Smile corners - descending to set up the curve
    PlayKeys(
        sequence=['a', None, 'l'],
        tempo_bpm=100,
        pause_after=0.3,
    ),

    # The smile curve - ascending melody, left to right!
    # C V B N makes a nice ascending low phrase
    PlayKeys(
        sequence=['c', 'v', 'b', 'n'],
        tempo_bpm=130,
        pause_after=0.8,
    ),

    # Add some sparkle - press number keys for percussion accents
    # This adds dots around the smiley
    PlayKeys(
        sequence=['3', None, '8'],  # Above the eyes
        tempo_bpm=120,
        pause_after=0.3,
    ),

    # Final accent - bottom corners
    PlayKeys(
        sequence=[['z', '/']],  # Chord at bottom corners
        tempo_bpm=100,
        pause_after=1.0,
    ),

    # -------------------------------------------------------------------------
    # REACTION: Emoji celebration (Explore) - 10s
    # -------------------------------------------------------------------------
    Comment("=== CELEBRATION ==="),
    SwitchMode("explore"),
    Pause(0.3),
    TypeText("5 happy cats!", delay_per_char=0.08),
    PressKey("enter", pause_after=2.0),

    TypeText("3 + 2 stars", delay_per_char=0.08),
    PressKey("enter", pause_after=2.0),

    # -------------------------------------------------------------------------
    # DOODLE: Add a signature - 12s
    # -------------------------------------------------------------------------
    Comment("=== SIGNATURE ==="),
    SwitchMode("doodle"),
    Pause(0.3),

    # Move to bottom area
    PressKey("down"),
    PressKey("down"),
    PressKey("down"),
    PressKey("down"),
    PressKey("down"),

    # Draw a little rainbow line
    DrawPath(directions=['right', 'right'], color_key='r', delay_per_step=0.08),
    DrawPath(directions=['right', 'right'], color_key='f', delay_per_step=0.08),
    DrawPath(directions=['right', 'right'], color_key='c', delay_per_step=0.08),
    Pause(0.3),

    # Add text
    PressKey("tab"),
    PressKey("right"),
    PressKey("right"),
    TypeText("Purple Computer", delay_per_char=0.08),
    Pause(0.8),

    # -------------------------------------------------------------------------
    # OUTRO: Musical goodbye - 6s
    # -------------------------------------------------------------------------
    Comment("=== GOODBYE ==="),
    SwitchMode("play"),
    Pause(0.2),
    # Descending arpeggio
    PlayKeys(
        sequence=['p', 'i', 'u', 'y', 't', 'r', 'e', 'w', 'q'],
        tempo_bpm=200,
        pause_after=0.8,
    ),

    Comment("Demo complete!"),
]


# =============================================================================
# OPTION 3: "RAINBOW EXPLORER"
# =============================================================================
# Theme: Explore ALL the colors in every mode
# Duration: ~70 seconds
# Highlights: Full color palette showcase, gradients, mixing

DEMO_OPTION_3 = [
    ClearAll(),
    Comment("=== RAINBOW EXPLORER ==="),

    # -------------------------------------------------------------------------
    # INTRO: Color question (Explore) - 6s
    # -------------------------------------------------------------------------
    Pause(0.3),
    TypeText("How many colors can we make?", delay_per_char=0.06),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # PRIMARY COLORS (Explore) - 12s
    # -------------------------------------------------------------------------
    Comment("=== PRIMARY COLORS ==="),
    TypeText("Red", delay_per_char=0.1),
    PressKey("enter", pause_after=1.0),
    TypeText("Yellow", delay_per_char=0.1),
    PressKey("enter", pause_after=1.0),
    TypeText("Blue", delay_per_char=0.1),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # MIXING MAGIC (Explore) - 12s
    # -------------------------------------------------------------------------
    Comment("=== MIXING ==="),
    TypeText("Red + Yellow", delay_per_char=0.08),
    PressKey("enter", pause_after=1.5),
    TypeText("Yellow + Blue", delay_per_char=0.08),
    PressKey("enter", pause_after=1.5),
    TypeText("Blue + Red", delay_per_char=0.08),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # PLAY MODE: Color rows (Play) - 15s
    # Show that each row is a different color!
    # -------------------------------------------------------------------------
    Comment("=== KEYBOARD RAINBOW ==="),
    SwitchMode("play"),
    Pause(0.4),

    # Top row - percussion party
    PlayKeys(
        sequence=['1', '2', '3', '4', '5'],
        tempo_bpm=180,
        pause_after=0.3,
    ),

    # QWERTY row - red tones, high notes
    PlayKeys(
        sequence=['q', 'w', 'e', 'r', 't'],
        tempo_bpm=160,
        pause_after=0.3,
    ),

    # ASDF row - yellow tones, mid notes
    PlayKeys(
        sequence=['a', 's', 'd', 'f', 'g'],
        tempo_bpm=160,
        pause_after=0.3,
    ),

    # ZXCV row - blue tones, low notes
    PlayKeys(
        sequence=['z', 'x', 'c', 'v', 'b'],
        tempo_bpm=160,
        pause_after=0.8,
    ),

    # -------------------------------------------------------------------------
    # DOODLE: Paint a gradient (Doodle) - 18s
    # Show light-to-dark within a row
    # -------------------------------------------------------------------------
    Comment("=== GRADIENT PAINTING ==="),
    SwitchMode("doodle"),
    Pause(0.3),

    # Position
    PressKey("down"),
    PressKey("down"),

    # Red gradient (QWERTY row: Q=light, P=dark)
    DrawPath(directions=['right', 'right'], color_key='q', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='e', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='t', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='u', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='o', delay_per_step=0.06),
    Pause(0.3),

    # Move down for yellow gradient
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),

    # Yellow gradient (ASDF row)
    DrawPath(directions=['right', 'right'], color_key='a', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='d', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='g', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='j', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='l', delay_per_step=0.06),
    Pause(0.3),

    # Move down for blue gradient
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),

    # Blue gradient (ZXCV row)
    DrawPath(directions=['right', 'right'], color_key='z', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='c', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='b', delay_per_step=0.06),
    DrawPath(directions=['right', 'right'], color_key='m', delay_per_step=0.06),
    Pause(0.5),

    # Label
    PressKey("tab"),
    PressKey("right"),
    PressKey("right"),
    PressKey("up"),
    PressKey("up"),
    TypeText("Rainbow!", delay_per_char=0.1),
    Pause(0.8),

    # -------------------------------------------------------------------------
    # FINALE: Full chord (Play) - 5s
    # -------------------------------------------------------------------------
    Comment("=== FINALE ==="),
    SwitchMode("play"),
    Pause(0.2),
    PlayKeys(
        sequence=[['z', 'a', 'q', '1'], None, ['m', 'l', 'p', '0']],
        tempo_bpm=80,
        pause_after=1.0,
    ),

    Comment("Demo complete!"),
]


# =============================================================================
# OPTION 4: "STORY TIME"
# =============================================================================
# Theme: Tell a little story with speech, emojis, and illustrations
# Duration: ~65 seconds
# Highlights: Speech, narrative flow, emoji expressions

DEMO_OPTION_4 = [
    ClearAll(),
    Comment("=== STORY TIME ==="),

    # -------------------------------------------------------------------------
    # CHAPTER 1: Once upon a time... (Explore) - 15s
    # -------------------------------------------------------------------------
    Pause(0.5),
    TypeText("Once upon a time!", delay_per_char=0.07),
    PressKey("enter", pause_after=2.0),

    TypeText("There were 3 cats", delay_per_char=0.07),
    PressKey("enter", pause_after=1.5),

    TypeText("And 2 dogs", delay_per_char=0.07),
    PressKey("enter", pause_after=1.5),

    TypeText("3 cats + 2 dogs", delay_per_char=0.07),
    PressKey("enter", pause_after=2.0),

    # -------------------------------------------------------------------------
    # CHAPTER 2: They played music! (Play) - 15s
    # Draw a house while playing a tune
    # -------------------------------------------------------------------------
    Comment("=== THEY PLAYED MUSIC ==="),
    SwitchMode("play"),
    Pause(0.4),

    # Draw a simple house shape:
    #     4 5 6
    #   R T Y U
    #   F G H J
    # Roof: 4, 5, 6 (top)
    # Walls: R, U (sides), T, Y (under roof)
    # Base: F, G, H, J (bottom)

    # Roof (percussion for "building" sound)
    PlayKeys(
        sequence=['4', '5', '6'],
        tempo_bpm=140,
        pause_after=0.2,
    ),

    # Upper walls
    PlayKeys(
        sequence=['r', 't', 'y', 'u'],
        tempo_bpm=150,
        pause_after=0.2,
    ),

    # Lower walls and base
    PlayKeys(
        sequence=['f', 'g', 'h', 'j'],
        tempo_bpm=150,
        pause_after=0.5,
    ),

    # Door (make it blue - press twice)
    PlayKeys(
        sequence=['g', 'g'],  # Press twice = blue!
        tempo_bpm=120,
        pause_after=0.3,
    ),

    # Windows (make them red - press 3 times)
    PlayKeys(
        sequence=['t', 't', 't', 'y', 'y', 'y'],  # 3 times each = red!
        tempo_bpm=180,
        pause_after=0.8,
    ),

    # -------------------------------------------------------------------------
    # CHAPTER 3: They painted together! (Doodle) - 20s
    # -------------------------------------------------------------------------
    Comment("=== THEY PAINTED ==="),
    SwitchMode("doodle"),
    Pause(0.3),

    # Draw a sun (yellow)
    PressKey("down"),
    PressKey("right"),
    PressKey("right"),
    DrawPath(directions=['right', 'right', 'right'], color_key='f', delay_per_step=0.08),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(directions=['right', 'right', 'right', 'right', 'right'], color_key='d', delay_per_step=0.08),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(directions=['right', 'right', 'right'], color_key='f', delay_per_step=0.08),
    Pause(0.3),

    # Draw grass (blue + yellow = green!)
    PressKey("down"),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),

    # First yellow layer
    DrawPath(directions=['right'] * 12, color_key='d', delay_per_step=0.04),
    # Go back and add blue to make green
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(directions=['right'] * 12, color_key='c', delay_per_step=0.04),
    Pause(0.5),

    # -------------------------------------------------------------------------
    # CHAPTER 4: The End! (Explore) - 10s
    # -------------------------------------------------------------------------
    Comment("=== THE END ==="),
    SwitchMode("explore"),
    Pause(0.3),
    TypeText("The End!", delay_per_char=0.1),
    PressKey("enter", pause_after=2.0),

    TypeText("5 stars!", delay_per_char=0.08),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # CREDITS: Musical outro (Play) - 5s
    # -------------------------------------------------------------------------
    SwitchMode("play"),
    Pause(0.2),
    PlayKeys(
        sequence=['c', 'e', 'g', ['c', 'e', 'g']],  # Happy major chord arpeggio
        tempo_bpm=120,
        pause_after=1.0,
    ),

    Comment("Demo complete!"),
]


# =============================================================================
# OPTION 5: "QUICK & PUNCHY" (shorter, high-impact)
# =============================================================================
# Theme: Maximum wow in minimum time
# Duration: ~35 seconds
# Highlights: Fast-paced, impressive moments only

DEMO_OPTION_5 = [
    ClearAll(),
    Comment("=== QUICK & PUNCHY ==="),

    # Instant wow: color mixing (5s)
    TypeText("Red + Blue!", delay_per_char=0.06),
    PressKey("enter", pause_after=2.0),

    # Play mode: fast smiley (8s)
    SwitchMode("play"),
    PlayKeys(
        sequence=['e', 'i', 'a', 'l', 'c', 'v', 'b', 'n'],
        tempo_bpm=180,
        pause_after=0.5,
    ),

    # Another color mix (5s)
    SwitchMode("explore"),
    TypeText("Blue + Yellow!", delay_per_char=0.06),
    PressKey("enter", pause_after=2.0),

    # Quick doodle with mixing (10s)
    SwitchMode("doodle"),
    DrawPath(directions=['right'] * 6, color_key='f', delay_per_step=0.05),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(directions=['right'] * 6, color_key='c', delay_per_step=0.05),  # Mix!
    PressKey("tab"),
    PressKey("right"),
    PressKey("right"),
    TypeText("Wow!", delay_per_char=0.08),
    Pause(0.5),

    # Finale chord (4s)
    SwitchMode("play"),
    PlayKeys(
        sequence=[['a', 's', 'd', 'f', 'g']],
        tempo_bpm=100,
        pause_after=1.0,
    ),

    Comment("Demo complete!"),
]


# =============================================================================
# COMPARISON TABLE
# =============================================================================
"""
| Option | Name             | Duration | Focus                    | Best For           |
|--------|------------------|----------|--------------------------|---------------------|
| 1      | The Magic Show   | ~60s     | Color mixing magic       | Science-minded kids |
| 2      | Smiley Symphony  | ~55s     | Play mode drawing        | Music lovers        |
| 3      | Rainbow Explorer | ~70s     | Full color palette       | Comprehensive demo  |
| 4      | Story Time       | ~65s     | Narrative + speech       | Younger kids        |
| 5      | Quick & Punchy   | ~35s     | Fast highlights          | Short attention     |

Recommended for website/marketing: Option 1 or 5
Recommended for in-depth showcase: Option 3
Recommended for cute factor: Option 4
Recommended for music focus: Option 2
"""
