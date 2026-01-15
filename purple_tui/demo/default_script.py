"""Default demo script showcasing Purple Computer's features.

This script runs through all three modes with engaging examples.
Designed to be 30 seconds to 3 minutes depending on timing.

Edit this file to customize the demo for your screencast!
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
# Modify this list to change what the demo does!
# Each action happens in sequence at human-readable pace.
#

DEMO_SCRIPT = [
    # ==========================================================================
    # DYNAMIC DEMO: ~50 seconds, bouncing between modes, showing off the magic!
    # ==========================================================================
    ClearAll(),

    # -------------------------------------------------------------------------
    # 1. MUSICAL HELLO (Play) - 4s
    # Quick ascending flourish to grab attention
    # -------------------------------------------------------------------------
    Comment("=== MUSICAL HELLO ==="),
    SwitchMode("play"),
    Pause(0.3),
    PlayKeys(
        sequence=['a', 's', 'd', 'f', 'g'],
        tempo_bpm=220,
        pause_after=0.4,
    ),

    # -------------------------------------------------------------------------
    # 2. COLOR MAGIC (Explore) - 7s
    # The wow moment: mixing colors!
    # -------------------------------------------------------------------------
    Comment("=== COLOR MAGIC ==="),
    SwitchMode("explore"),
    Pause(0.3),
    TypeText("red+blue"),
    PressKey("enter", pause_after=1.8),  # Purple appears!

    # -------------------------------------------------------------------------
    # 3. DRAW A TREE (Doodle) - 10s
    # Simple tree: leafy top + trunk
    # -------------------------------------------------------------------------
    Comment("=== DRAW A TREE ==="),
    SwitchMode("doodle"),
    Pause(0.3),

    # Position for tree top (move down a bit first)
    PressKey("down"),
    PressKey("down"),

    # Draw leafy crown (green-ish) - a small triangle/blob
    DrawPath(
        directions=['right', 'right', 'right', 'right'],
        delay_per_step=0.1,
        color_key='g',
    ),
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    DrawPath(
        directions=['right', 'right'],
        delay_per_step=0.1,
        color_key='g',
    ),

    # Draw trunk (reddish-brown)
    PressKey("down"),
    DrawPath(
        directions=['down', 'down'],
        delay_per_step=0.12,
        color_key='r',
    ),
    Pause(0.4),

    # -------------------------------------------------------------------------
    # 4. MUSICAL SMILEY (Play) - 8s
    # Draw a smiley face with sounds! Eyes + smile
    # Grid:  R . . . I   <- eyes
    #        D . . . K   <- mouth corners
    #        . F G H .   <- smile
    # -------------------------------------------------------------------------
    Comment("=== MUSICAL SMILEY ==="),
    SwitchMode("play"),
    Pause(0.3),

    # Eyes (with a little pause between)
    PlayKeys(
        sequence=['r', None, 'i'],
        tempo_bpm=100,
        pause_after=0.2,
    ),

    # Smile curve
    PlayKeys(
        sequence=['f', 'g', 'h', ['d', 'k']],  # smile + corners together
        tempo_bpm=140,
        pause_after=0.5,
    ),

    # -------------------------------------------------------------------------
    # 5. EMOJI MATH (Explore) - 6s
    # Fun with emoji arithmetic
    # -------------------------------------------------------------------------
    Comment("=== EMOJI MATH ==="),
    SwitchMode("explore"),
    Pause(0.3),
    TypeText("3 cats+2 dogs"),
    PressKey("enter", pause_after=1.5),

    # -------------------------------------------------------------------------
    # 6. QUICK SIGNATURE (Doodle) - 6s
    # Type "Purple!" on the canvas
    # -------------------------------------------------------------------------
    Comment("=== SIGNATURE ==="),
    SwitchMode("doodle"),
    Pause(0.2),
    PressKey("enter"),
    PressKey("enter"),
    PressKey("enter"),
    TypeText("Purple!", delay_per_char=0.1),
    Pause(0.6),

    # -------------------------------------------------------------------------
    # 7. ONE MORE COLOR MIX (Explore) - 5s
    # Another color magic moment
    # -------------------------------------------------------------------------
    Comment("=== MORE COLOR MAGIC ==="),
    SwitchMode("explore"),
    Pause(0.2),
    TypeText("blue+yellow"),
    PressKey("enter", pause_after=1.2),

    # -------------------------------------------------------------------------
    # 8. MUSICAL GOODBYE (Play) - 4s
    # Descending flourish to end
    # -------------------------------------------------------------------------
    Comment("=== GOODBYE ==="),
    SwitchMode("play"),
    Pause(0.2),
    PlayKeys(
        sequence=['j', 'h', 'g', 'f', 'd', ['a', 's']],  # descending + final chord
        tempo_bpm=180,
        pause_after=0.8,
    ),

    Comment("Demo complete!"),
]


# =============================================================================
# SHORTER DEMO (quick showcase, ~30 seconds)
# =============================================================================

DEMO_SCRIPT_SHORT = [
    # Quick ~20 second demo, same bouncy style
    ClearAll(),

    Comment("=== QUICK DEMO ==="),

    # Musical hello
    SwitchMode("play"),
    PlayKeys(sequence=['a', 's', 'd', 'f'], tempo_bpm=240, pause_after=0.2),

    # Color magic
    SwitchMode("explore"),
    TypeText("red+blue"),
    PressKey("enter", pause_after=1.2),

    # Quick draw
    SwitchMode("doodle"),
    TypeText("Hi!"),
    DrawPath(directions=['right', 'right', 'down'], color_key='g', delay_per_step=0.08),

    # Emoji fun
    SwitchMode("explore"),
    TypeText("cats+dogs"),
    PressKey("enter", pause_after=1.0),

    # Musical goodbye
    SwitchMode("play"),
    PlayKeys(sequence=['g', 'f', 'd', 's', 'a'], tempo_bpm=200, pause_after=0.5),
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


def type_and_say(text: str, pause: float = 1.0):
    """Type text ending with ! (which triggers speech) and press enter."""
    if not text.endswith('!'):
        text = text + '!'
    return [
        TypeText(text),
        PressKey("enter", pause_after=pause),
    ]
