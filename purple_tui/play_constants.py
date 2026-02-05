"""Play mode constants: grid layout, colors, frequencies, percussion.

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
COLORS = ["#da77f2", "#4dabf7", "#ff6b6b", None]

# Musical frequencies (C major scale, balanced range)
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
