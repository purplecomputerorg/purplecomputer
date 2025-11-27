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
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich import box


# Musical keyboard layout - C major scale spanning octaves
# Low notes on left, high notes on right
# Maps keyboard keys to (frequency, note_name, display_key, instrument)
NOTE_MAP = {
    # Bottom row - LOW notes (lower octave)
    'z': (130.81, 'C', 'z→C', 'piano'),
    'x': (146.83, 'D', 'x→D', 'piano'),
    'c': (164.81, 'E', 'c→E', 'piano'),
    'v': (174.61, 'F', 'v→F', 'piano'),
    'b': (196.00, 'G', 'b→G', 'piano'),
    'n': (220.00, 'A', 'n→A', 'piano'),
    'm': (246.94, 'B', 'm→B', 'piano'),

    # Middle row - MIDDLE notes (middle octave)
    'a': (261.63, 'C', 'a→C', 'piano'),
    's': (293.66, 'D', 's→D', 'piano'),
    'd': (329.63, 'E', 'd→E', 'piano'),
    'f': (349.23, 'F', 'f→F', 'piano'),
    'g': (392.00, 'G', 'g→G', 'piano'),
    'h': (440.00, 'A', 'h→A', 'piano'),
    'j': (493.88, 'B', 'j→B', 'piano'),
    'k': (523.25, 'C', 'k→C', 'piano'),
    'l': (587.33, 'D', 'l→D', 'piano'),

    # Top row - HIGH notes (higher octave)
    'q': (523.25, 'C', 'q→C', 'piano'),
    'w': (587.33, 'D', 'w→D', 'piano'),
    'e': (659.25, 'E', 'e→E', 'piano'),
    'r': (698.46, 'F', 'r→F', 'piano'),
    't': (783.99, 'G', 't→G', 'piano'),
    'y': (880.00, 'A', 'y→A', 'piano'),
    'u': (987.77, 'B', 'u→B', 'piano'),
    'i': (1046.50, 'C', 'i→C', 'piano'),
    'o': (1174.66, 'D', 'o→D', 'piano'),
    'p': (1318.51, 'E', 'p→E', 'piano'),
}

# Arrow keys with different instruments
# up=highest, down=lowest, left/right=middle range
ARROW_MAP = {
    'up': (1046.50, 'C6', '↑→Flute', 'flute'),      # High flute
    'right': (523.25, 'C5', '→→Bell', 'bell'),       # Mid-high bell
    'left': (261.63, 'C4', '←→Strings', 'strings'),  # Mid-low strings
    'down': (130.81, 'C3', '↓→Bass', 'bass'),        # Low bass
}


def generate_tone(frequency, duration=0.3, sample_rate=44100, amplitude=0.25, instrument='piano'):
    """
    Generate a warm, fun-sounding tone with harmonics.

    Args:
        frequency: Frequency in Hz
        duration: Duration in seconds
        sample_rate: Sample rate in Hz
        amplitude: Volume (0.0 to 1.0)
        instrument: Type of instrument sound ('piano', 'flute', 'bell', 'strings', 'bass')

    Returns:
        Path to temporary WAV file
    """
    num_samples = int(sample_rate * duration)

    # Generate samples with harmonics for a warmer, more musical sound
    samples = []
    for i in range(num_samples):
        t = i / sample_rate

        # Different waveforms for different instruments
        if instrument == 'piano':
            # Piano: strong fundamental with harmonics
            sample = math.sin(2 * math.pi * frequency * t)
            sample += 0.3 * math.sin(2 * math.pi * frequency * 2 * t)
            sample += 0.15 * math.sin(2 * math.pi * frequency * 3 * t)

        elif instrument == 'flute':
            # Flute: pure tone with minimal harmonics
            sample = math.sin(2 * math.pi * frequency * t)
            sample += 0.08 * math.sin(2 * math.pi * frequency * 2 * t)
            # Very subtle breathiness
            import random
            sample += 0.01 * (random.random() - 0.5)

        elif instrument == 'bell':
            # Bell: metallic sound with inharmonic overtones
            sample = math.sin(2 * math.pi * frequency * t)
            sample += 0.4 * math.sin(2 * math.pi * frequency * 2.5 * t)  # Inharmonic
            sample += 0.3 * math.sin(2 * math.pi * frequency * 3.7 * t)
            sample += 0.2 * math.sin(2 * math.pi * frequency * 5.2 * t)

        elif instrument == 'strings':
            # Strings: rich harmonics with vibrato
            vibrato = 1 + 0.02 * math.sin(2 * math.pi * 5 * t)  # 5 Hz vibrato
            sample = math.sin(2 * math.pi * frequency * vibrato * t)
            sample += 0.4 * math.sin(2 * math.pi * frequency * 2 * vibrato * t)
            sample += 0.3 * math.sin(2 * math.pi * frequency * 3 * vibrato * t)
            sample += 0.2 * math.sin(2 * math.pi * frequency * 4 * vibrato * t)

        elif instrument == 'bass':
            # Bass: strong fundamental, deep harmonics
            sample = math.sin(2 * math.pi * frequency * t)
            sample += 0.5 * math.sin(2 * math.pi * frequency * 2 * t)
            sample += 0.3 * math.sin(2 * math.pi * frequency * 3 * t)
            # Add a bit of rumble
            sample += 0.2 * math.sin(2 * math.pi * frequency * 0.5 * t)

        else:
            # Default to piano
            sample = math.sin(2 * math.pi * frequency * t)
            sample += 0.3 * math.sin(2 * math.pi * frequency * 2 * t)
            sample += 0.15 * math.sin(2 * math.pi * frequency * 3 * t)

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
    Returns the character pressed, or special strings for arrow keys.
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)

        # Check for escape sequences (arrow keys)
        if ord(ch) == 27:  # ESC
            # Read the next two characters to check for arrow keys
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return 'arrow_up'
                elif ch3 == 'B':
                    return 'arrow_down'
                elif ch3 == 'C':
                    return 'arrow_right'
                elif ch3 == 'D':
                    return 'arrow_left'
            # If not an arrow key, return ESC
            return chr(27)

        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def show_keyboard_visual(console, last_key='', last_note_info=None):
    """
    Display a colorful, fun keyboard for kids using rich!
    """
    console.clear()

    # Header with emoji
    title = Text("🎵 MUSIC MODE 🎵", style="bold cyan")
    subtitle = Text("Press keys to make music!", style="bold yellow")
    instructions = Text("(ESC to exit)", style="dim green")

    header_panel = Panel(
        Align.center(title),
        box=box.HEAVY,
        style="magenta",
        padding=(0, 2)
    )
    console.print(Align.center(header_panel))
    console.print()
    console.print(Align.center(subtitle))
    console.print(Align.center(instructions))
    console.print()
    console.print()

    # Keyboard layout
    all_keys = [
        ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
        ['z', 'x', 'c', 'v', 'b', 'n', 'm']
    ]

    row_labels = [' HIGH ', '  MID ', '  LOW ']
    row_colors = ['red', 'green', 'blue']
    row_emojis = ['🔴', '🟢', '🔵']

    # Draw each keyboard row with boxes
    for idx, row in enumerate(all_keys):
        label = row_labels[idx]
        color = row_colors[idx]
        emoji = row_emojis[idx]

        # Build the row as Text objects with boxes
        row_text = Text()
        row_text.append(f"{emoji} {label}", style=f"bold {color}")

        for key in row:
            if key in NOTE_MAP:
                freq, note_name, display, instrument = NOTE_MAP[key]
                # Box around each key
                simple_display = f"{key.upper()}:{note_name}"
                if key == last_key:
                    row_text.append(f" [{simple_display:^5}] ", style="bold black on yellow")
                else:
                    row_text.append(f" [{simple_display:^5}] ", style=f"bold {color}")

        console.print(Align.center(row_text))
        console.print()  # Extra spacing between rows

    console.print()

    # Arrow keys section with emoji
    arrow_title = Text("🎹 Arrow Keys - Different Instruments 🎹", style="bold yellow")
    arrow_panel = Panel(
        Align.center(arrow_title),
        box=box.HEAVY,
        style="magenta",
        padding=(0, 1)
    )
    console.print(Align.center(arrow_panel))
    console.print()

    # Arrow keys display - bigger boxes
    up_style = "bold black on yellow" if last_key == 'arrow_up' else "bold white on blue"
    down_style = "bold black on yellow" if last_key == 'arrow_down' else "bold white on blue"
    left_style = "bold black on yellow" if last_key == 'arrow_left' else "bold white on blue"
    right_style = "bold black on yellow" if last_key == 'arrow_right' else "bold white on blue"

    # Up
    up_text = Text(f"[ ↑ FLUTE 🎶 ]", style=up_style)
    console.print(Align.center(up_text))
    console.print()

    # Left and Right on same line
    lr_text = Text()
    lr_text.append(f"[ ← STRINGS 🎻 ]", style=left_style)
    lr_text.append("      ")
    lr_text.append(f"[ → BELL 🔔 ]", style=right_style)
    console.print(Align.center(lr_text))
    console.print()

    # Down
    down_text = Text(f"[ ↓ BASS 🎸 ]", style=down_style)
    console.print(Align.center(down_text))

    console.print()
    console.print()

    # Now playing - bigger and more fun
    if last_note_info:
        display_key, note_name = last_note_info
        msg = Text(f"🎵 Playing: {note_name} note! 🎵", style="bold cyan")
    else:
        msg = Text("✨ Try pressing keys! ✨", style="bold green")

    console.print(Align.center(msg))


def activate():
    """
    Main entry point for Music Mode.
    This function is called when the mode is activated.
    """
    # Create rich console
    console = Console()

    # Pre-generate tones for faster playback
    console.print("\n[yellow]Generating sounds...[/yellow]")
    tone_cache = {}

    # Generate piano tones for regular keys
    for key, (freq, note_name, display, instrument) in NOTE_MAP.items():
        tone_cache[key] = generate_tone(freq, duration=0.3, instrument=instrument)

    # Generate instrument tones for arrow keys
    for arrow_key, (freq, note_name, display, instrument) in ARROW_MAP.items():
        tone_cache[arrow_key] = generate_tone(freq, duration=0.3, instrument=instrument)

    last_key = ''
    last_note_info = None

    try:
        # Hide cursor
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

        # Show initial screen
        show_keyboard_visual(console, last_key, last_note_info)

        while True:
            # Get a keypress
            key = get_key()

            # Check for ESC or Ctrl+C
            if key == chr(27):  # ESC (when not an arrow key)
                break
            elif isinstance(key, str) and len(key) == 1 and ord(key) == 3:  # Ctrl+C
                raise KeyboardInterrupt

            # Check if it's an arrow key
            if key.startswith('arrow_'):
                arrow_name = key.replace('arrow_', '')
                if arrow_name in ARROW_MAP:
                    last_key = key
                    freq, note_name, display_key, instrument = ARROW_MAP[arrow_name]
                    last_note_info = (display_key, note_name)
                    play_sound(tone_cache[arrow_name])
                    show_keyboard_visual(console, last_key, last_note_info)
            # Play sound if it's a regular mapped key
            elif key.lower() in tone_cache:
                last_key = key.lower()
                freq, note_name, display_key, instrument = NOTE_MAP[last_key]
                last_note_info = (display_key, note_name)
                play_sound(tone_cache[last_key])
                # Redraw with highlighted key
                show_keyboard_visual(console, last_key, last_note_info)
            else:
                last_key = ''
                last_note_info = None
                # Redraw without highlight
                show_keyboard_visual(console, last_key, last_note_info)

    except KeyboardInterrupt:
        pass

    finally:
        # Show cursor
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

        # Clean up temporary files
        for temp_file in tone_cache.values():
            try:
                Path(temp_file).unlink()
            except:
                pass

        console.print("\n[green]✨ Exiting Music Mode...[/green]\n")

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
