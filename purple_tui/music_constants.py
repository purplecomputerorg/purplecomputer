"""Music mode constants: grid layout, colors, frequencies, percussion.

Pure data with no side effects. Importable from anywhere without triggering
pygame initialization or ALSA setup.
"""

# 10x4 grid matching keyboard layout
GRID_KEYS = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';'],
    ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/'],
]

# All keys in a flat list for indexing
ALL_KEYS = [key for row in GRID_KEYS for key in row]

# Color cycle: keycap (sticker color) -> opposite (RYB complement) -> purple -> off.
# "keycap" / "opposite" are sentinel values; MusicGrid.get_color() resolves them
# per-key via art_room.KEY_COLORS / KEY_OPPOSITES so what you see on the screen
# matches the physical sticker on the keycap.
COLOR_KEYCAP = "keycap"
COLOR_OPPOSITE = "opposite"
COLORS = [COLOR_KEYCAP, COLOR_OPPOSITE, "#5a3875", None]

# Instruments: (directory_name, display_name)
# Enter cycles through these in Music mode
INSTRUMENTS = [
    ("marimba", "Marimba"),
    ("xylophone", "Xylophone"),
    ("ukulele", "Ukulele"),
    ("musicbox", "Music Box"),
]

# Common short names that map to instrument IDs
INSTRUMENT_ALIASES = {
    "uke": "ukulele",
}

# Musical frequencies (G major scale across 3 octaves)
NOTE_FREQUENCIES = {
    # Top row: bright but not shrill (392-988 Hz)
    'Q': 392.00, 'W': 440.00, 'E': 493.88, 'R': 523.25, 'T': 587.33,
    'Y': 659.25, 'U': 739.99, 'I': 783.99, 'O': 880.00, 'P': 987.77,
    # Middle row: warm middle (196-494 Hz)
    'A': 196.00, 'S': 220.00, 'D': 246.94, 'F': 261.63, 'G': 293.66,
    'H': 329.63, 'J': 369.99, 'K': 392.00, 'L': 440.00, 'semicolon': 493.88,
    # Bottom row: rich low end (98-247 Hz)
    'Z': 98.00, 'X': 110.00, 'C': 123.47, 'V': 130.81, 'B': 146.83,
    'N': 164.81, 'M': 185.00, 'comma': 196.00, 'period': 220.00, 'slash': 246.94,
}

# Note names for grid display (G major: G A B C D E F#)
# Each column plays the same note across octaves
NOTE_NAMES = {
    'Q': 'G', 'W': 'A', 'E': 'B', 'R': 'C', 'T': 'D',
    'Y': 'E', 'U': 'F#', 'I': 'G', 'O': 'A', 'P': 'B',
    'A': 'G', 'S': 'A', 'D': 'B', 'F': 'C', 'G': 'D',
    'H': 'E', 'J': 'F#', 'K': 'G', 'L': 'A', ';': 'B',
    'Z': 'G', 'X': 'A', 'C': 'B', 'V': 'C', 'B': 'D',
    'N': 'E', 'M': 'F#', ',': 'G', '.': 'A', '/': 'B',
}

# --- Chromatic / key-shift support -----------------------------------------
#
# The grid plays a major scale starting from a chosen root note. The kid can
# shift root note (Left/Right) and octave (Up/Down) at runtime. Pre-rendered
# samples cover every reachable pitch.

CHROMATIC_NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#',
                         'G', 'G#', 'A', 'A#', 'B']

# Major scale: semitone offsets from the root for scale degrees 0..6
MAJOR_SCALE_SEMITONES = [0, 2, 4, 5, 7, 9, 11]

# Five "no wrong notes" keys cycled by Left/Right. Stored as semitone indices
# (0=C, 2=D, 5=F, 7=G, 9=A). G is the default for backward compatibility with
# the original NOTE_FREQUENCIES table above.
FRIENDLY_KEYS = [0, 2, 5, 7, 9]
DEFAULT_ROOT_INDEX = FRIENDLY_KEYS.index(7)  # G

# Vertical row → base octave for scale degree 0 in that row (G major default
# already maps row 0 to G4, row 1 to G3, row 2 to G2).
ROW_OCTAVE_BASE = {0: 4, 1: 3, 2: 2}


def pitch_filename(note_name: str, octave: int) -> str:
    """Pitch-based sample filename, e.g. ('C#', 4) -> 'cs4'.

    Uses 's' instead of '#' so filenames are shell-safe.
    """
    return note_name.lower().replace('#', 's') + str(octave)


def pitch_for(row: int, col: int, root: int, octave_shift: int) -> tuple[str, int]:
    """Return (note_name, octave) for the cell at (row, col) given current state.

    row: 0=top (Q-P), 1=middle (A-;), 2=bottom (Z-/)
    col: 0..9 (scale degree, with col 7..9 wrapping into next octave)
    root: 0..11 semitone index (0=C, 7=G default)
    octave_shift: integer offset applied to all rows (typically -1, 0, +1)
    """
    row_octave = ROW_OCTAVE_BASE[row] + octave_shift
    deg = col
    semitone_offset = MAJOR_SCALE_SEMITONES[deg % 7] + 12 * (deg // 7)
    abs_st = root + 12 * row_octave + semitone_offset
    return CHROMATIC_NOTE_NAMES[abs_st % 12], abs_st // 12


# Percussion display names for number row cells
PERCUSSION_NAMES = {
    '1': 'kick', '2': 'snare', '3': 'hat', '4': 'clap', '5': 'bell',
    '6': 'wood', '7': 'tri', '8': 'tamb', '9': 'bongo', '0': 'gong',
}

# Percussion instruments (number row)
PERCUSSION = {
    '0': 'gong',
    '1': 'kick',
    '2': 'snare',
    '3': 'hi-hat',
    '4': 'clap',
    '5': 'cowbell',
    '6': 'woodblock',
    '7': 'triangle',
    '8': 'tambourine',
    '9': 'bongo',
}
