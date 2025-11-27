"""
Purple Computer - Music Mode
A simple keyboard-as-instrument mode where each key plays a musical note.
"""

import sys
import tty
import termios
import math
import wave
import tempfile
import subprocess
from pathlib import Path


# Musical keyboard layout - C major scale spanning octaves
# Low notes on left, high notes on right
# Maps keyboard keys to (frequency, note_name, display_key)
NOTE_MAP = {
    # Bottom row - LOW notes (lower octave)
    'z': (130.81, 'C', 'z→C'),
    'x': (146.83, 'D', 'x→D'),
    'c': (164.81, 'E', 'c→E'),
    'v': (174.61, 'F', 'v→F'),
    'b': (196.00, 'G', 'b→G'),
    'n': (220.00, 'A', 'n→A'),
    'm': (246.94, 'B', 'm→B'),

    # Middle row - MIDDLE notes (middle octave)
    'a': (261.63, 'C', 'a→C'),
    's': (293.66, 'D', 's→D'),
    'd': (329.63, 'E', 'd→E'),
    'f': (349.23, 'F', 'f→F'),
    'g': (392.00, 'G', 'g→G'),
    'h': (440.00, 'A', 'h→A'),
    'j': (493.88, 'B', 'j→B'),
    'k': (523.25, 'C', 'k→C'),
    'l': (587.33, 'D', 'l→D'),

    # Top row - HIGH notes (higher octave)
    'q': (523.25, 'C', 'q→C'),
    'w': (587.33, 'D', 'w→D'),
    'e': (659.25, 'E', 'e→E'),
    'r': (698.46, 'F', 'r→F'),
    't': (783.99, 'G', 't→G'),
    'y': (880.00, 'A', 'y→A'),
    'u': (987.77, 'B', 'u→B'),
    'i': (1046.50, 'C', 'i→C'),
    'o': (1174.66, 'D', 'o→D'),
    'p': (1318.51, 'E', 'p→E'),
}


def generate_tone(frequency, duration=0.3, sample_rate=44100, amplitude=0.25):
    """
    Generate a warm, fun-sounding tone with harmonics.

    Args:
        frequency: Frequency in Hz
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        amplitude: Volume (0.0 to 1.0)

    Returns:
        Path to temporary WAV file
    """
    num_samples = int(sample_rate * duration)

    # Generate samples with harmonics for a warmer, more musical sound
    samples = []
    for i in range(num_samples):
        t = i / sample_rate

        # Fundamental frequency (main note)
        sample = math.sin(2 * math.pi * frequency * t)

        # Add harmonics for richness (like a real instrument)
        sample += 0.3 * math.sin(2 * math.pi * frequency * 2 * t)  # 2nd harmonic
        sample += 0.15 * math.sin(2 * math.pi * frequency * 3 * t)  # 3rd harmonic

        # ADSR envelope for musical sound
        # Attack (fade in quickly)
        if i < num_samples * 0.05:
            envelope = i / (num_samples * 0.05)
        # Sustain
        elif i < num_samples * 0.7:
            envelope = 1.0
        # Release (fade out smoothly)
        else:
            envelope = (num_samples - i) / (num_samples * 0.3)

        sample *= envelope * amplitude

        # Normalize and convert to 16-bit integer
        sample_int = int(sample * 32767 / 1.45)  # Normalize for harmonics
        samples.append(sample_int)

    # Write to temporary WAV file
    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_path = temp_file.name
    temp_file.close()

    with wave.open(temp_path, 'w') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample (16-bit)
        wav_file.setframerate(sample_rate)

        # Write samples as bytes
        for sample in samples:
            wav_file.writeframes(sample.to_bytes(2, byteorder='little', signed=True))

    return temp_path


def play_sound(wav_path):
    """
    Play a WAV file using available audio player.
    Falls back to other players if primary is not available.
    """
    import os
    import platform

    # Different players for different systems
    players = {
        'Darwin': [['afplay', wav_path]],  # macOS - afplay doesn't support -q flag
        'Linux': [['aplay', '-q', wav_path], ['paplay', wav_path]],
        'Windows': [['start', '/min', wav_path]]
    }

    # Get appropriate players for this platform
    system = platform.system()
    player_commands = players.get(system, [['afplay', wav_path], ['aplay', '-q', wav_path]])

    for cmd in player_commands:
        try:
            # Run player in background, suppress output
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return
        except (FileNotFoundError, OSError):
            continue

    # If no player found, just silently continue
    pass


def get_key():
    """
    Get a single keypress without waiting for Enter.
    Returns the character pressed.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def show_keyboard_visual(last_key='', last_note_info=None):
    """
    Display a colorful, fun keyboard for kids!
    """
    # ANSI color codes
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    # Clear screen and hide cursor
    print("\033[2J\033[H\033[?25l", end='')

    # Fun colorful header - centered for ~100 char width
    print()
    print()
    print(f"                     {PURPLE}{BOLD}╔═══════════════════════════════════════╗{RESET}")
    print(f"                     {PURPLE}{BOLD}║                                       ║{RESET}")
    print(f"                     {PURPLE}{BOLD}║{RESET}              {CYAN}{BOLD}MUSIC MODE{RESET}              {PURPLE}{BOLD}║{RESET}")
    print(f"                     {PURPLE}{BOLD}║                                       ║{RESET}")
    print(f"                     {PURPLE}{BOLD}╚═══════════════════════════════════════╝{RESET}")
    print()
    print(f"                      {YELLOW}🎹 Press keys to make music! 🎹{RESET}")
    print(f"                           {GREEN}ESC to exit{RESET}")
    print()
    print()

    # Keyboard layout with labels
    all_keys = [
        ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
        ['z', 'x', 'c', 'v', 'b', 'n', 'm']
    ]

    row_labels = ['HIGH', 'MID', 'LOW']

    # Colors for different rows
    row_colors = [RED, GREEN, BLUE]

    # Draw keyboard
    for idx, row in enumerate(all_keys):
        label = row_labels[idx]
        label_color = row_colors[idx]

        # Top border
        print(f"                ", end='')
        for key in row:
            if key in NOTE_MAP:
                freq, note_name, display = NOTE_MAP[key]
                if key == last_key:
                    print(f"  {BOLD}{YELLOW}┌──────┐{RESET}", end='')
                else:
                    color = row_colors[idx]
                    print(f"  {color}┌──────┐{RESET}", end='')
        print()

        # Middle with key labels - row label goes here (vertically centered)
        print(f"       {label_color}{BOLD}{label:>4}{RESET}     ", end='')
        for key in row:
            if key in NOTE_MAP:
                freq, note_name, display = NOTE_MAP[key]
                if key == last_key:
                    print(f"  {BOLD}{YELLOW}│{display:^6}│{RESET}", end='')
                else:
                    color = row_colors[idx]
                    print(f"  {color}│{display:^6}│{RESET}", end='')
        print()

        # Bottom border
        print(f"                ", end='')
        for key in row:
            if key in NOTE_MAP:
                if key == last_key:
                    print(f"  {BOLD}{YELLOW}└──────┘{RESET}", end='')
                else:
                    color = row_colors[idx]
                    print(f"  {color}└──────┘{RESET}", end='')
        print()
        print()

    print()

    # Now playing with fun emojis
    if last_note_info:
        display_key, note_name = last_note_info
        print(f"                      {CYAN}{BOLD}♪ ♫ ♪  {display_key} = {note_name} note!  ♪ ♫ ♪{RESET}")
    else:
        print(f"                          {CYAN}(Try pressing keys!){RESET}")
    print()
    print()

    # Flush output
    sys.stdout.flush()


def activate():
    """
    Main entry point for Music Mode.
    This function is called when the mode is activated.
    """
    # Pre-generate tones for faster playback
    print("\nGenerating sounds...", flush=True)
    tone_cache = {}
    for key, (freq, note_name, display) in NOTE_MAP.items():
        tone_cache[key] = generate_tone(freq, duration=0.3)

    last_key = ''
    last_note_info = None

    try:
        # Switch to alternate screen buffer (like vim)
        # This prevents polluting the scrollback
        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J")      # Clear it
        sys.stdout.write("\033[H")       # Move cursor to top
        sys.stdout.write("\033[?25l")    # Hide cursor
        sys.stdout.flush()

        # Show initial screen
        show_keyboard_visual(last_key, last_note_info)

        while True:
            # Get a keypress
            key = get_key()

            # Check for ESC (ASCII 27) or Ctrl+C (ASCII 3)
            if ord(key) == 27:  # ESC
                break
            elif ord(key) == 3:  # Ctrl+C
                raise KeyboardInterrupt

            # Play sound if it's a mapped key
            if key.lower() in tone_cache:
                last_key = key.lower()
                freq, note_name, display_key = NOTE_MAP[last_key]
                last_note_info = (display_key, note_name)
                play_sound(tone_cache[last_key])
                # Redraw with highlighted key
                show_keyboard_visual(last_key, last_note_info)
            else:
                last_key = ''
                last_note_info = None
                # Redraw without highlight
                show_keyboard_visual(last_key, last_note_info)

    except KeyboardInterrupt:
        pass

    finally:
        # Show cursor and switch back to main screen buffer
        sys.stdout.write("\033[?25h")    # Show cursor
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()

        # Clean up temporary files
        for temp_file in tone_cache.values():
            try:
                Path(temp_file).unlink()
            except:
                pass

        print("✨ Exiting Music Mode...\n")

    return ""  # Return empty string so IPython doesn't print anything


# For IPython mode system compatibility
def mode():
    """
    Wrapper for IPython mode system.
    Returns an object that activates the mode when accessed.
    """
    activate()
    return ""


# If run directly (for testing)
if __name__ == '__main__':
    activate()
