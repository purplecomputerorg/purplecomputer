#!/usr/bin/env python3
"""
Generate fun sounds for Purple Computer Play Mode

Creates vibrant, kid-friendly sounds:
- Letters: Bright piano-like tones (fun and exhilarating)
- Numbers: Silly sounds (boing, drum, pop, giggle, etc.)
"""

import wave
import math
import random
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOUNDS_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content"

# Musical frequencies (C major scale, spread across octaves for fun range)
NOTE_FREQUENCIES = {
    # Top row - sparkly high notes
    'Q': 523.25, 'W': 587.33, 'E': 659.25, 'R': 698.46, 'T': 783.99,
    'Y': 880.00, 'U': 987.77, 'I': 1046.50, 'O': 1174.66, 'P': 1318.51,
    # Middle row - bright middle range
    'A': 261.63, 'S': 293.66, 'D': 329.63, 'F': 349.23, 'G': 392.00,
    'H': 440.00, 'J': 493.88, 'K': 523.25, 'L': 587.33,
    # Bottom row - warm low notes
    'Z': 130.81, 'X': 146.83, 'C': 164.81, 'V': 174.61, 'B': 196.00,
    'N': 220.00, 'M': 246.94,
}

def write_wav(filename: str, samples: list[int], sample_rate: int = 44100):
    """Write samples to a WAV file"""
    filepath = SOUNDS_DIR / filename
    with wave.open(str(filepath), 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for sample in samples:
            # Clamp to valid range
            sample = max(-32767, min(32767, sample))
            wav_file.writeframes(sample.to_bytes(2, byteorder='little', signed=True))
    print(f"  Created {filename}")

def generate_piano_tone(frequency: float, duration: float = 0.4) -> list[int]:
    """
    Generate a bright, vibrant piano-like tone.
    Rich harmonics + sparkle + nice envelope = fun for kids!
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate

        # Rich harmonic series (piano-like)
        sample = math.sin(2 * math.pi * frequency * t)  # Fundamental
        sample += 0.5 * math.sin(2 * math.pi * frequency * 2 * t)  # 2nd harmonic
        sample += 0.35 * math.sin(2 * math.pi * frequency * 3 * t)  # 3rd harmonic
        sample += 0.2 * math.sin(2 * math.pi * frequency * 4 * t)  # 4th harmonic
        sample += 0.1 * math.sin(2 * math.pi * frequency * 5 * t)  # 5th harmonic

        # Add a bit of sparkle (high frequency shimmer)
        shimmer = 0.05 * math.sin(2 * math.pi * frequency * 8 * t)
        shimmer *= math.exp(-t * 8)  # Quick decay on shimmer
        sample += shimmer

        # ADSR envelope - quick attack, nice sustain, gentle release
        attack_time = 0.02
        decay_time = 0.1
        sustain_level = 0.7
        release_start = duration - 0.15

        if t < attack_time:
            # Quick attack with slight overshoot
            envelope = (t / attack_time) * 1.1
        elif t < attack_time + decay_time:
            # Decay to sustain
            decay_progress = (t - attack_time) / decay_time
            envelope = 1.1 - (0.4 * decay_progress)
        elif t < release_start:
            # Sustain
            envelope = sustain_level
        else:
            # Release
            release_progress = (t - release_start) / (duration - release_start)
            envelope = sustain_level * (1 - release_progress)

        sample *= envelope * 0.3
        samples.append(int(sample * 32767))

    return samples

def generate_boing() -> list[int]:
    """Silly boing sound - frequency drops quickly"""
    sample_rate = 44100
    duration = 0.5
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Frequency drops from high to low
        freq = 800 * math.exp(-t * 6) + 100
        sample = math.sin(2 * math.pi * freq * t)
        # Add some wobble
        sample += 0.3 * math.sin(2 * math.pi * freq * 1.5 * t)
        # Envelope
        envelope = math.exp(-t * 3)
        samples.append(int(sample * envelope * 0.4 * 32767))

    return samples

def generate_drum() -> list[int]:
    """Fun drum hit"""
    sample_rate = 44100
    duration = 0.3
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(42)  # Consistent drum
    for i in range(num_samples):
        t = i / sample_rate
        # Low thump
        thump = math.sin(2 * math.pi * 80 * t) * math.exp(-t * 15)
        # Snappy attack
        snap = (random.random() * 2 - 1) * math.exp(-t * 30)
        sample = thump * 0.7 + snap * 0.5
        envelope = math.exp(-t * 8)
        samples.append(int(sample * envelope * 0.5 * 32767))

    return samples

def generate_pop() -> list[int]:
    """Bubbly pop sound"""
    sample_rate = 44100
    duration = 0.2
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Quick frequency sweep up then down
        if t < 0.05:
            freq = 200 + (t / 0.05) * 800
        else:
            freq = 1000 * math.exp(-(t - 0.05) * 20)
        sample = math.sin(2 * math.pi * freq * t)
        envelope = math.exp(-t * 15)
        samples.append(int(sample * envelope * 0.4 * 32767))

    return samples

def generate_giggle() -> list[int]:
    """Silly giggle-like sound"""
    sample_rate = 44100
    duration = 0.6
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Wobbling frequency
        wobble = math.sin(t * 25) * 100
        freq = 400 + wobble
        sample = math.sin(2 * math.pi * freq * t)
        # Add harmonics for richness
        sample += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        envelope = math.exp(-t * 3) * (0.5 + 0.5 * math.sin(t * 20))
        samples.append(int(sample * envelope * 0.35 * 32767))

    return samples

def generate_whoosh() -> list[int]:
    """Swooshy whoosh sound"""
    sample_rate = 44100
    duration = 0.4
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(123)
    for i in range(num_samples):
        t = i / sample_rate
        # Filtered noise that sweeps
        noise = random.random() * 2 - 1
        # Frequency sweep for filter effect
        sweep = math.sin(t * math.pi / duration)
        sample = noise * sweep
        envelope = math.sin(t * math.pi / duration)
        samples.append(int(sample * envelope * 0.4 * 32767))

    return samples

def generate_ding() -> list[int]:
    """Bright ding/bell sound"""
    sample_rate = 44100
    duration = 0.5
    num_samples = int(sample_rate * duration)
    samples = []

    freq = 1200
    for i in range(num_samples):
        t = i / sample_rate
        # Bell-like harmonics
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.5 * math.sin(2 * math.pi * freq * 2.4 * t)
        sample += 0.25 * math.sin(2 * math.pi * freq * 5.95 * t)
        envelope = math.exp(-t * 5)
        samples.append(int(sample * envelope * 0.3 * 32767))

    return samples

def generate_bonk() -> list[int]:
    """Cartoon bonk sound"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Two quick tones
        freq1 = 300 * math.exp(-t * 20)
        freq2 = 150 * math.exp(-t * 15)
        sample = math.sin(2 * math.pi * freq1 * t) + 0.7 * math.sin(2 * math.pi * freq2 * t)
        envelope = math.exp(-t * 12)
        samples.append(int(sample * envelope * 0.4 * 32767))

    return samples

def generate_spring() -> list[int]:
    """Springy boing (different from boing)"""
    sample_rate = 44100
    duration = 0.7
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Multiple bounces
        freq = 300 + 200 * abs(math.sin(t * 15)) * math.exp(-t * 2)
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.4 * math.sin(2 * math.pi * freq * 2 * t)
        envelope = math.exp(-t * 2)
        samples.append(int(sample * envelope * 0.35 * 32767))

    return samples

def generate_quack() -> list[int]:
    """Duck-like quack"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Nasal-sounding frequency modulation
        freq = 350 + 100 * math.sin(t * 60)
        sample = math.sin(2 * math.pi * freq * t)
        # Nasally harmonics
        sample += 0.6 * math.sin(2 * math.pi * freq * 2 * t)
        sample += 0.4 * math.sin(2 * math.pi * freq * 3 * t)
        envelope = math.exp(-t * 8)
        samples.append(int(sample * envelope * 0.35 * 32767))

    return samples

def generate_zap() -> list[int]:
    """Electric zap sound"""
    sample_rate = 44100
    duration = 0.3
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(456)
    for i in range(num_samples):
        t = i / sample_rate
        # Descending tone with noise
        freq = 2000 * math.exp(-t * 10) + 100
        tone = math.sin(2 * math.pi * freq * t)
        noise = (random.random() * 2 - 1) * 0.3 * math.exp(-t * 15)
        sample = tone + noise
        envelope = math.exp(-t * 8)
        samples.append(int(sample * envelope * 0.35 * 32767))

    return samples

def main():
    """Generate all sounds"""
    print("Generating Purple Computer sounds...")
    print()

    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate piano tones for letters
    print("Piano tones (A-Z):")
    for letter, freq in NOTE_FREQUENCIES.items():
        samples = generate_piano_tone(freq)
        write_wav(f"{letter.lower()}.wav", samples)

    print()
    print("Silly sounds (0-9):")

    # Number sounds - all different silly sounds
    silly_sounds = [
        ("0", generate_boing, "boing"),
        ("1", generate_drum, "drum"),
        ("2", generate_pop, "pop"),
        ("3", generate_giggle, "giggle"),
        ("4", generate_whoosh, "whoosh"),
        ("5", generate_ding, "ding"),
        ("6", generate_bonk, "bonk"),
        ("7", generate_spring, "spring"),
        ("8", generate_quack, "quack"),
        ("9", generate_zap, "zap"),
    ]

    for num, generator, name in silly_sounds:
        samples = generator()
        write_wav(f"{num}.wav", samples)
        print(f"    {num} = {name}")

    print()
    print(f"Done! Sounds saved to {SOUNDS_DIR}")

if __name__ == "__main__":
    main()
