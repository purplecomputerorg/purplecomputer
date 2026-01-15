"""Default demo script showcasing Purple Computer's features.

This script runs through all three modes with engaging examples.
Designed to be ~45 seconds.

Edit this file to customize the demo for your screencast!

IMPORTANT: Understanding Play mode behavior
-------------------------------------------
Play mode has a 10x4 grid matching the keyboard:

    1 2 3 4 5 6 7 8 9 0
    Q W E R T Y U I O P
    A S D F G H J K L ;
    Z X C V B N M , . /

Each key press CYCLES the color: off → purple → blue → red → off
Colors PERSIST until cycled again. This means you can "draw" pictures
by pressing keys strategically. For a smiley face:
- Eyes: 4 and 6 (row 0, percussion)
- Nose: T (row 1)
- Smile corners: D and J (row 2, UP)
- Smile bottom: C, V, B, N, M (row 3, DOWN)

Avoid pressing the same key twice in one demo section, or it will
cycle to the next color instead of staying the same.
"""

from .script import (
    TypeText,
    PressKey,
    SwitchMode,
    Pause,
    Clear,
    ClearAll,
    PlayKeys,
    DrawPath,
    Comment,
    type_and_enter,
    section_pause,
)


# =============================================================================
# THE DEMO SCRIPT
# =============================================================================
#
# Flow: Explore (quick) → Play (draw smiley) → Doodle (art + text) → Explore (color mix)
#

DEMO_SCRIPT = [
    ClearAll(),

    # -------------------------------------------------------------------------
    # 1. QUICK GREETING (Explore) - 3s
    # Start with something fun that plays sound
    # -------------------------------------------------------------------------
    Comment("=== GREETING ==="),
    # Already in Explore mode by default
    Pause(0.3),
    TypeText("hello!", delay_per_char=0.12),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # 2. MUSICAL SMILEY (Play) - 10s
    # Draw a smiley face while playing music!
    #
    # The grid:
    #     Col:  0 1 2 3 4 5 6 7 8 9
    #     Row 0: 1 2 3 4 5 6 7 8 9 0    <- 4 and 6 are eyes
    #     Row 1: Q W E R T Y U I O P    <- T is nose
    #     Row 2: A S D F G H J K L ;    <- D and J are smile CORNERS (UP)
    #     Row 3: Z X C V B N M , . /    <- C V B N M is smile BOTTOM (DOWN)
    #
    # Corners UP (D, J) + bottom DOWN (CVBNM) = upward-curving smile!
    # -------------------------------------------------------------------------
    Comment("=== MUSICAL SMILEY ==="),
    SwitchMode("play"),
    Pause(0.4),

    # Eyes: 4 and 6 (percussion - blink blink!)
    PlayKeys(
        sequence=['4', None, '6'],
        tempo_bpm=90,
        pause_after=0.3,
    ),

    # Nose: T (high marimba, cute boop!)
    PlayKeys(
        sequence=['t'],
        tempo_bpm=100,
        pause_after=0.3,
    ),

    # Smile corners: D and J (mid-range, these are UP)
    PlayKeys(
        sequence=['d', None, 'j'],
        tempo_bpm=100,
        pause_after=0.3,
    ),

    # Smile bottom: C V B N M (low notes, ascending melody, this is DOWN)
    PlayKeys(
        sequence=['c', 'v', 'b', 'n', 'm'],
        tempo_bpm=140,
        pause_after=0.8,
    ),

    # -------------------------------------------------------------------------
    # 3. COLOR MAGIC (Explore) - 5s
    # Show color mixing!
    # -------------------------------------------------------------------------
    Comment("=== COLOR MAGIC ==="),
    SwitchMode("explore"),
    Pause(0.3),
    TypeText("pink+indigo"),
    PressKey("enter", pause_after=1.8),

    # -------------------------------------------------------------------------
    # 4. CREATIVE DRAWING (Doodle) - 15s
    # Show paint mode: color mixing, drawing, and text together
    # -------------------------------------------------------------------------
    Comment("=== CREATIVE DRAWING ==="),
    SwitchMode("doodle"),
    Pause(0.3),

    # First draw a sun (yellow circle-ish) in top left
    # Yellow keys are on ASDF row: a, s, d, f, g, h, j, k, l
    PressKey("down"),
    DrawPath(
        directions=['right', 'right', 'right'],
        delay_per_step=0.08,
        color_key='f',  # Yellow
    ),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(
        directions=['right', 'right', 'right', 'right'],
        delay_per_step=0.08,
        color_key='d',  # Slightly different yellow
    ),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(
        directions=['right', 'right', 'right'],
        delay_per_step=0.08,
        color_key='f',
    ),
    Pause(0.3),

    # Now mix colors: draw blue over part of it to show mixing
    PressKey("up"),
    PressKey("left"),
    DrawPath(
        directions=['down', 'down'],
        delay_per_step=0.1,
        color_key='c',  # Blue (ZXCV row)
    ),
    Pause(0.4),

    # Switch to text mode and write "Purple!"
    PressKey("tab"),  # Exit paint mode
    Pause(0.2),
    # Move to a good spot for text
    PressKey("right"),
    PressKey("right"),
    PressKey("right"),
    PressKey("right"),
    PressKey("up"),
    TypeText("Purple!", delay_per_char=0.1),
    Pause(0.6),

    # -------------------------------------------------------------------------
    # 5. EMOJI FUN (Explore) - 4s
    # Quick emoji math to end
    # -------------------------------------------------------------------------
    Comment("=== EMOJI FUN ==="),
    SwitchMode("explore"),
    Pause(0.2),
    TypeText("3+2 cats"),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # 6. MUSICAL FINALE (Play) - 6s
    # End with a musical flourish, then hold on the smiley!
    # -------------------------------------------------------------------------
    Comment("=== FINALE ==="),
    SwitchMode("play"),
    Pause(0.2),

    # Play a descending scale on keys we haven't used
    # This adds color accents around the smiley
    PlayKeys(
        sequence=['5', '3', '2', '1', ['z', '/', 'm']],
        tempo_bpm=160,
        pause_after=0.5,
    ),

    # Hold on the finished smiley so viewers can admire it!
    Pause(2.0),

    Comment("Demo complete!"),
]


# =============================================================================
# SHORTER DEMO (~20 seconds)
# =============================================================================

DEMO_SCRIPT_SHORT = [
    ClearAll(),

    Comment("=== QUICK DEMO ==="),

    # Quick greeting
    TypeText("hi!"),
    PressKey("enter", pause_after=1.0),

    # Draw a quick smiley: eyes (4 6), nose (T), corners UP (D J), bottom DOWN (CVBNM)
    SwitchMode("play"),
    PlayKeys(
        sequence=['4', '6', 't', 'd', 'j', 'c', 'v', 'b', 'n', 'm'],
        tempo_bpm=180,
        pause_after=0.3,
    ),

    # Color mix
    SwitchMode("explore"),
    TypeText("pink+indigo"),
    PressKey("enter", pause_after=1.2),

    # Quick doodle
    SwitchMode("doodle"),
    DrawPath(directions=['right', 'right', 'down', 'down'], color_key='f', delay_per_step=0.06),
    PressKey("tab"),
    TypeText("Fun!"),
    Pause(0.5),
]


# =============================================================================
# HELPERS FOR CUSTOM SCRIPTS
# =============================================================================

def make_melody(notes: str, tempo: int = 150) -> PlayKeys:
    """Helper to create a melody from a string of keys.

    Usage:
        make_melody("qwerty", tempo=180)
    """
    return PlayKeys(
        sequence=list(notes),
        tempo_bpm=tempo,
    )


def make_smiley() -> list:
    """Create a smiley face in Play mode.

    Returns a list of actions that draw:
    - Eyes at 4 and 6 (row 0)
    - Nose at T (row 1)
    - Smile corners at D and J (row 2, UP)
    - Smile bottom at C, V, B, N, M (row 3, DOWN)

    The corners are ABOVE the bottom, creating an upward-curving smile!
    """
    return [
        PlayKeys(sequence=['4', None, '6'], tempo_bpm=90),
        PlayKeys(sequence=['t'], tempo_bpm=100),
        PlayKeys(sequence=['d', None, 'j'], tempo_bpm=100),
        PlayKeys(sequence=['c', 'v', 'b', 'n', 'm'], tempo_bpm=140),
    ]
