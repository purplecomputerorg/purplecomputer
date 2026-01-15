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
    # Clear all state for a fresh start
    ClearAll(),

    # -------------------------------------------------------------------------
    # SECTION 1: Explore Mode (F1) - Math, Emoji, Speech
    # -------------------------------------------------------------------------
    Comment("=== EXPLORE MODE: Math and Emoji REPL ==="),

    SwitchMode("explore"),
    Pause(0.5),

    # Start with a friendly greeting (speech!)
    Comment("Greeting with speech"),
    TypeText("Hello World!"),
    PressKey("enter", pause_after=1.5),

    # Simple math
    Comment("Basic math"),
    TypeText("2+3"),
    PressKey("enter", pause_after=1.0),

    # Math with words
    Comment("Math with emoji words"),
    TypeText("2+3 apples"),
    PressKey("enter", pause_after=1.2),

    # More complex emoji math
    TypeText("rabbits+7 carrots"),
    PressKey("enter", pause_after=1.2),

    # Color mixing!
    Comment("Color mixing"),
    TypeText("blue+2 yellows"),
    PressKey("enter", pause_after=1.5),

    # Another color mix
    TypeText("red+yellow"),
    PressKey("enter", pause_after=1.2),

    # Bigger math
    Comment("Multiple numbers"),
    TypeText("5+3+2"),
    PressKey("enter", pause_after=1.0),

    # Personal statement with speech
    Comment("Statement with speech"),
    TypeText("My name is Purple!"),
    PressKey("enter", pause_after=1.5),

    # Fun question
    TypeText("What is 10 cats+5 dogs?"),
    PressKey("enter", pause_after=1.5),

    section_pause(1.0),

    # -------------------------------------------------------------------------
    # SECTION 2: Play Mode (F2) - Music and Colors (draws a heart!)
    # -------------------------------------------------------------------------
    Comment("=== PLAY MODE: Music and Art Grid ==="),

    SwitchMode("play"),
    Pause(0.8),

    # Draw a heart shape with pretty music (max 2 keys at a time for realism)
    # The heart pattern on the 10x4 grid:
    #     . 2 3 . . . 7 8 . .
    #     Q W E R . Y U I O .
    #     . S D F G H J K . .
    #     . . C V B N M . . .

    # Start with gentle melody: left side of heart top
    Comment("Draw heart: left top curve"),
    PlayKeys(
        sequence=['q', 'w', '2', '3', 'e', 'r'],
        tempo_bpm=140,
        pause_after=0.3,
    ),

    # Right side of heart top (harmonizes with left)
    Comment("Draw heart: right top curve"),
    PlayKeys(
        sequence=['y', 'u', '7', '8', 'i', 'o'],
        tempo_bpm=140,
        pause_after=0.3,
    ),

    # Middle section with gentle 2-note harmonies
    Comment("Draw heart: middle with harmonies"),
    PlayKeys(
        sequence=[
            's', 'd',
            ['f', 'h'],  # harmony
            'g',
            ['j', 'k'],  # harmony
        ],
        tempo_bpm=120,
        pause_after=0.3,
    ),

    # Bottom of heart converging to point
    Comment("Draw heart: bottom point"),
    PlayKeys(
        sequence=[
            'c', 'v',
            ['b', 'n'],  # converging harmony
            'm',
            'b',  # the heart's point (press again to change color)
        ],
        tempo_bpm=100,
        pause_after=0.5,
    ),

    # Finish with a sweet arpeggio along the heart outline
    Comment("Sweet melody along the heart"),
    PlayKeys(
        sequence=[
            'q', 'w', 'e', 'r',  # left top
            'f', 'v', 'b',       # down to point
            'n', 'j', 'o',       # up right side
            'i', 'u', 'y',       # right top
            None,                # rest
            ['q', 'o'],          # final harmony
        ],
        tempo_bpm=160,
        pause_after=0.8,
    ),

    section_pause(1.0),

    # -------------------------------------------------------------------------
    # SECTION 3: Doodle Mode (F3) - Text and Drawing
    # -------------------------------------------------------------------------
    Comment("=== DOODLE MODE: Drawing Canvas with Paint ==="),

    SwitchMode("doodle"),
    Pause(0.8),

    # Type some text
    Comment("Type a greeting"),
    TypeText("Hello!"),
    Pause(0.3),

    # Move down and type more
    PressKey("enter"),
    TypeText("Purple Computer"),
    Pause(0.5),

    # Move to draw area
    PressKey("enter"),
    PressKey("enter"),

    # Draw a simple shape (horizontal line)
    Comment("Draw with space+arrows"),
    DrawPath(
        directions=['right', 'right', 'right', 'right', 'right'],
        steps_per_direction=1,
        delay_per_step=0.15,
        color_key='g',  # Green from G row
    ),

    # Move and draw another line
    PressKey("down"),
    PressKey("left"),
    PressKey("left"),
    PressKey("left"),

    # Draw vertical line
    DrawPath(
        directions=['down', 'down', 'down'],
        steps_per_direction=1,
        delay_per_step=0.15,
        color_key='r',  # Red from R row
    ),

    # Draw a trunk (brown-ish)
    PressKey("down"),
    DrawPath(
        directions=['down', 'down'],
        steps_per_direction=1,
        delay_per_step=0.15,
        color_key='b',  # Blue-ish
    ),

    Pause(1.0),

    # Type more text
    PressKey("right"),
    PressKey("right"),
    PressKey("right"),
    TypeText(" Art!", delay_per_char=0.12),

    section_pause(1.5),

    # -------------------------------------------------------------------------
    # FINALE: Back to Explore mode with a closing message
    # -------------------------------------------------------------------------
    Comment("=== FINALE ==="),

    SwitchMode("explore"),
    Pause(0.5),

    # Clear and show final message
    TypeText("Thanks for watching!"),
    PressKey("enter", pause_after=2.0),

    Comment("Demo complete!"),
]


# =============================================================================
# SHORTER DEMO (quick showcase, ~30 seconds)
# =============================================================================

DEMO_SCRIPT_SHORT = [
    # Clear all state for a fresh start
    ClearAll(),

    Comment("=== QUICK DEMO ==="),

    # Explore mode highlights
    SwitchMode("explore"),
    TypeText("Hello!"),
    PressKey("enter", pause_after=0.8),
    TypeText("2+3"),
    PressKey("enter", pause_after=0.8),
    TypeText("cats+dogs"),
    PressKey("enter", pause_after=0.8),

    # Play mode
    SwitchMode("play"),
    PlayKeys(
        sequence=['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        tempo_bpm=200,
    ),

    # Doodle mode
    SwitchMode("doodle"),
    TypeText("Purple!", delay_per_char=0.1),
    DrawPath(directions=['right', 'right', 'down', 'down'], color_key='r'),

    # End
    SwitchMode("explore"),
    TypeText("Bye!"),
    PressKey("enter", pause_after=1.0),
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
