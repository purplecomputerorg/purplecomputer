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


# Note frequencies for a simple chromatic scale (Hz)
# Maps keyboard keys to (frequency, note_name)
NOTE_MAP = {
    # Top row
    'q': (261.63, 'C'),
    'w': (293.66, 'D'),
    'e': (329.63, 'E'),
    'r': (349.23, 'F'),
    't': (392.00, 'G'),
    'y': (440.00, 'A'),
    'u': (493.88, 'B'),
    'i': (523.25, 'C'),
    'o': (587.33, 'D'),
    'p': (659.25, 'E'),
    # Middle row
    'a': (261.63, 'C'),
    's': (293.66, 'D'),
    'd': (329.63, 'E'),
    'f': (349.23, 'F'),
    'g': (392.00, 'G'),
    'h': (440.00, 'A'),
    'j': (493.88, 'B'),
    'k': (523.25, 'C'),
    'l': (587.33, 'D'),
    # Bottom row
    'z': (329.63, 'E'),
    'x': (349.23, 'F'),
    'c': (392.00, 'G'),
    'v': (440.00, 'A'),
    'b': (493.88, 'B'),
    'n': (523.25, 'C'),
    'm': (587.33, 'D'),
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

    # Move cursor to home position (top-left)
    print("\033[H", end='')

    # Fun colorful header
    print()
    print()
    print(f"            {PURPLE}{BOLD}╔═══════════════════════════════════════╗{RESET}")
    print(f"            {PURPLE}{BOLD}║                                       ║{RESET}")
    print(f"            {PURPLE}{BOLD}║{RESET}     {CYAN}🎹  MUSIC MODE  🎹{RESET}            {PURPLE}{BOLD}║{RESET}")
    print(f"            {PURPLE}{BOLD}║                                       ║{RESET}")
    print(f"            {PURPLE}{BOLD}╚═══════════════════════════════════════╝{RESET}")
    print()
    print(f"                {YELLOW}Press keys to make music!{RESET}")
    print(f"                  {GREEN}ESC to exit{RESET}")
    print()
    print()

    # Simple keyboard layout
    all_keys = [
        ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
        ['z', 'x', 'c', 'v', 'b', 'n', 'm']
    ]

    # Colors for different keys (make it rainbow-like)
    key_colors = {
        'q': RED, 'w': RED, 'e': YELLOW, 'r': YELLOW, 't': YELLOW,
        'y': GREEN, 'u': GREEN, 'i': CYAN, 'o': CYAN, 'p': BLUE,
        'a': RED, 's': RED, 'd': YELLOW, 'f': YELLOW, 'g': GREEN,
        'h': GREEN, 'j': CYAN, 'k': CYAN, 'l': BLUE,
        'z': RED, 'x': YELLOW, 'c': YELLOW, 'v': GREEN,
        'b': GREEN, 'n': CYAN, 'm': BLUE
    }

    # Draw keyboard
    for row in all_keys:
        print("              ", end='')
        for key in row:
            if key == last_key:
                print(f"  {BOLD}{YELLOW}┌─────┐{RESET}", end='')
            else:
                color = key_colors.get(key, RESET)
                print(f"  {color}┌─────┐{RESET}", end='')
        print()

        print("              ", end='')
        for key in row:
            if key == last_key:
                print(f"  {BOLD}{YELLOW}│  {key.upper()}  │{RESET}", end='')
            else:
                color = key_colors.get(key, RESET)
                print(f"  {color}│  {key}  │{RESET}", end='')
        print()

        print("              ", end='')
        for key in row:
            if key == last_key:
                print(f"  {BOLD}{YELLOW}└─────┘{RESET}", end='')
            else:
                color = key_colors.get(key, RESET)
                print(f"  {color}└─────┘{RESET}", end='')
        print()
        print()

    print()

    # Now playing with fun emojis
    if last_note_info:
        note_name, freq = last_note_info
        print(f"                  {CYAN}{BOLD}♪ ♫ ♪  Playing: {note_name}  ♪ ♫ ♪{RESET}")
    else:
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
    for key, (freq, note_name) in NOTE_MAP.items():
        tone_cache[key] = generate_tone(freq, duration=0.3)

    last_key = ''
    last_note_info = None

    try:
        # Switch to alternate screen buffer (like vim)
        # This prevents polluting the scrollback
        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J")      # Clear it
        sys.stdout.write("\033[H")       # Move cursor to top
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
                freq, note_name = NOTE_MAP[last_key]
                last_note_info = (note_name, freq)
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
        # Switch back to main screen buffer
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
