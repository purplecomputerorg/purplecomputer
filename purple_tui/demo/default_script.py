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
    # -------------------------------------------------------------------------
    # SECTION 1: Ask Mode (F1) - Math, Emoji, Speech
    # -------------------------------------------------------------------------
    Comment("=== ASK MODE: Math and Emoji REPL ==="),

    SwitchMode("ask"),
    Pause(0.5),

    # Start with a friendly greeting (speech!)
    Comment("Greeting with speech"),
    TypeText("Hello World!"),
    PressKey("enter", pause_after=1.5),

    # Simple math
    Comment("Basic math"),
    TypeText("2 + 3"),
    PressKey("enter", pause_after=1.0),

    # Math with words
    Comment("Math with emoji words"),
    TypeText("2 + 3 apples"),
    PressKey("enter", pause_after=1.2),

    # More complex emoji math
    TypeText("rabbits + 7 carrots"),
    PressKey("enter", pause_after=1.2),

    # Color mixing!
    Comment("Color mixing"),
    TypeText("blue + 2 yellows"),
    PressKey("enter", pause_after=1.5),

    # Another color mix
    TypeText("red + yellow"),
    PressKey("enter", pause_after=1.2),

    # Bigger math
    Comment("Multiple numbers"),
    TypeText("5 + 3 + 2"),
    PressKey("enter", pause_after=1.0),

    # Personal statement with speech
    Comment("Statement with speech"),
    TypeText("My name is Purple!"),
    PressKey("enter", pause_after=1.5),

    # Fun question
    TypeText("What is 10 cats + 5 dogs?"),
    PressKey("enter", pause_after=1.5),

    section_pause(1.0),

    # -------------------------------------------------------------------------
    # SECTION 2: Play Mode (F2) - Music and Colors
    # -------------------------------------------------------------------------
    Comment("=== PLAY MODE: Music and Art Grid ==="),

    SwitchMode("play"),
    Pause(0.8),

    # Play a simple ascending scale
    Comment("Simple melody on top row"),
    PlayKeys(
        sequence=['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        tempo_bpm=180,
        pause_after=0.5,
    ),

    # Play a descending scale
    Comment("Descending"),
    PlayKeys(
        sequence=['p', 'o', 'i', 'u', 'y', 't', 'r', 'e', 'w', 'q'],
        tempo_bpm=200,
        pause_after=0.5,
    ),

    # Play a fun pattern
    Comment("Fun rhythmic pattern"),
    PlayKeys(
        sequence=[
            'a', 's', 'a', 's', 'd', 'f', 'd', 'f',
            'g', 'h', 'g', 'h', 'j', 'k', 'l', ';',
        ],
        tempo_bpm=240,
        pause_after=0.5,
    ),

    # Play some chords (simultaneous keys)
    Comment("Chords"),
    PlayKeys(
        sequence=[
            ['q', 'e', 't'],  # Chord 1
            None,            # Rest
            ['w', 'r', 'y'],  # Chord 2
            None,
            ['e', 't', 'u'],  # Chord 3
            None,
            ['q', 'e', 't', 'u'],  # Big chord
        ],
        tempo_bpm=90,
        pause_after=0.8,
    ),

    # Numbers row for variety
    Comment("Number row sounds"),
    PlayKeys(
        sequence=['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
        tempo_bpm=200,
        pause_after=0.5,
    ),

    section_pause(1.0),

    # -------------------------------------------------------------------------
    # SECTION 3: Write Mode (F3) - Text and Drawing
    # -------------------------------------------------------------------------
    Comment("=== WRITE MODE: Text Canvas with Paint ==="),

    SwitchMode("write"),
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
    # FINALE: Back to Ask mode with a closing message
    # -------------------------------------------------------------------------
    Comment("=== FINALE ==="),

    SwitchMode("ask"),
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
    Comment("=== QUICK DEMO ==="),

    # Ask mode highlights
    SwitchMode("ask"),
    TypeText("Hello!"),
    PressKey("enter", pause_after=0.8),
    TypeText("2 + 3"),
    PressKey("enter", pause_after=0.8),
    TypeText("cats + dogs"),
    PressKey("enter", pause_after=0.8),

    # Play mode
    SwitchMode("play"),
    PlayKeys(
        sequence=['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        tempo_bpm=200,
    ),

    # Write mode
    SwitchMode("write"),
    TypeText("Purple!", delay_per_char=0.1),
    DrawPath(directions=['right', 'right', 'down', 'down'], color_key='r'),

    # End
    SwitchMode("ask"),
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
