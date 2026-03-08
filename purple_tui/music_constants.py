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

# Color cycle: purple -> blue -> red -> default (off)
# Tinted variants: subtle color over dark background (less eye strain)
COLORS = ["#5a3875", "#2d4f6e", "#5a2d2d", None]

# Instruments: (directory_name, display_name)
# Enter cycles through these in Music mode
INSTRUMENTS = [
    ("marimba", "Marimba"),
    ("xylophone", "Xylophone"),
    ("ukulele", "Ukulele"),
    ("musicbox", "Music Box"),
]

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
