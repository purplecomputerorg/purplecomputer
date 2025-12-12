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
    'H': 440.00, 'J': 493.88, 'K': 523.25, 'L': 587.33, 'semicolon': 659.25,
    # Bottom row - warm low notes (continues into next octave)
    'Z': 130.81, 'X': 146.83, 'C': 164.81, 'V': 174.61, 'B': 196.00,
    'N': 220.00, 'M': 246.94, 'comma': 261.63, 'period': 293.66, 'slash': 329.63,
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

def generate_kick_drum() -> list[int]:
    """Punchy kick drum - tuned for laptop speakers"""
    sample_rate = 44100
    duration = 0.35
    num_samples = int(sample_rate * duration)
    samples = []

    # Short fade-in to prevent click (2ms)
    fade_in_samples = int(sample_rate * 0.002)

    for i in range(num_samples):
        t = i / sample_rate
        # Higher min freq (60 Hz vs 40 Hz) for better laptop speaker reproduction
        freq = 180 * math.exp(-t * 20) + 60
        sample = math.sin(2 * math.pi * freq * t)
        # Second harmonic helps laptop speakers reproduce the low end
        sample += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        # Softer click at the start
        click = math.exp(-t * 80) * 0.25
        sample += click
        envelope = math.exp(-t * 7)

        # Apply fade-in
        if i < fade_in_samples:
            fade = i / fade_in_samples
        else:
            fade = 1.0

        samples.append(int(sample * envelope * fade * 0.5 * 32767))

    return samples

def generate_snare() -> list[int]:
    """Crispy snare drum"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(42)
    for i in range(num_samples):
        t = i / sample_rate
        # Body tone
        tone = math.sin(2 * math.pi * 200 * t) * math.exp(-t * 20)
        # Snare rattle (filtered noise)
        noise = (random.random() * 2 - 1) * math.exp(-t * 15)
        sample = tone * 0.4 + noise * 0.6
        envelope = math.exp(-t * 10)
        samples.append(int(sample * envelope * 0.5 * 32767))

    return samples

def generate_hihat() -> list[int]:
    """Bright hi-hat cymbal"""
    sample_rate = 44100
    duration = 0.15
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(123)
    for i in range(num_samples):
        t = i / sample_rate
        # High frequency noise for metallic sound
        noise = random.random() * 2 - 1
        # Add some high tones
        tone = math.sin(2 * math.pi * 8000 * t) * 0.3
        tone += math.sin(2 * math.pi * 10000 * t) * 0.2
        sample = noise * 0.7 + tone
        envelope = math.exp(-t * 30)
        samples.append(int(sample * envelope * 0.35 * 32767))

    return samples

def generate_gong() -> list[int]:
    """Deep gong hit"""
    sample_rate = 44100
    duration = 1.0
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Low fundamental with beating harmonics
        freq = 120
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.6 * math.sin(2 * math.pi * freq * 2.01 * t)  # Slight detune for shimmer
        sample += 0.4 * math.sin(2 * math.pi * freq * 3.02 * t)
        sample += 0.2 * math.sin(2 * math.pi * freq * 4.5 * t)
        # Slow amplitude wobble
        wobble = 1 + 0.1 * math.sin(2 * math.pi * 3 * t)
        sample *= wobble
        envelope = math.exp(-t * 2)
        samples.append(int(sample * envelope * 0.4 * 32767))

    return samples

def generate_cowbell() -> list[int]:
    """Classic cowbell - more cowbell!"""
    sample_rate = 44100
    duration = 0.3
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Two slightly detuned tones for metallic character
        freq1 = 800
        freq2 = 540
        sample = math.sin(2 * math.pi * freq1 * t)
        sample += 0.7 * math.sin(2 * math.pi * freq2 * t)
        # Add harmonics
        sample += 0.3 * math.sin(2 * math.pi * freq1 * 2 * t)
        envelope = math.exp(-t * 8)
        samples.append(int(sample * envelope * 0.4 * 32767))

    return samples

def generate_clap() -> list[int]:
    """Hand clap sound"""
    sample_rate = 44100
    duration = 0.2
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(321)
    for i in range(num_samples):
        t = i / sample_rate
        # Multiple short bursts for realistic clap
        burst1 = math.exp(-((t - 0.005) ** 2) * 50000)
        burst2 = math.exp(-((t - 0.015) ** 2) * 40000)
        burst3 = math.exp(-((t - 0.025) ** 2) * 30000)
        bursts = burst1 + burst2 * 0.8 + burst3 * 0.6
        noise = (random.random() * 2 - 1) * bursts
        envelope = math.exp(-t * 15)
        samples.append(int(noise * envelope * 0.5 * 32767))

    return samples

def generate_woodblock() -> list[int]:
    """Hollow wood block tick"""
    sample_rate = 44100
    duration = 0.15
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Hollow resonant tone
        freq = 800
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.5 * math.sin(2 * math.pi * freq * 2.3 * t)
        sample += 0.3 * math.sin(2 * math.pi * freq * 4.1 * t)
        envelope = math.exp(-t * 25)
        samples.append(int(sample * envelope * 0.45 * 32767))

    return samples

def generate_triangle() -> list[int]:
    """Triangle ding"""
    sample_rate = 44100
    duration = 0.6
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # High pure tone with slight shimmer
        freq = 1500
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        sample += 0.15 * math.sin(2 * math.pi * freq * 3 * t)
        # Subtle vibrato
        vibrato = 1 + 0.002 * math.sin(2 * math.pi * 6 * t)
        sample *= vibrato
        envelope = math.exp(-t * 4)
        samples.append(int(sample * envelope * 0.35 * 32767))

    return samples

def generate_tambourine() -> list[int]:
    """Jingly tambourine shake"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(654)
    for i in range(num_samples):
        t = i / sample_rate
        # Jingles - high metallic noise
        noise = (random.random() * 2 - 1)
        # Add some high pitched tones for jingles
        jingle = math.sin(2 * math.pi * 6000 * t) * 0.3
        jingle += math.sin(2 * math.pi * 8500 * t) * 0.2
        jingle += math.sin(2 * math.pi * 11000 * t) * 0.1
        sample = noise * 0.5 + jingle
        envelope = math.exp(-t * 12)
        samples.append(int(sample * envelope * 0.4 * 32767))

    return samples

def generate_bongo() -> list[int]:
    """Bongo drum hit"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        # Higher pitched than kick, with quick pitch drop
        freq = 400 * math.exp(-t * 30) + 180
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.4 * math.sin(2 * math.pi * freq * 1.5 * t)
        envelope = math.exp(-t * 15)
        samples.append(int(sample * envelope * 0.45 * 32767))

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

    # Number sounds - percussion kit
    silly_sounds = [
        ("0", generate_gong, "gong"),
        ("1", generate_kick_drum, "kick"),
        ("2", generate_snare, "snare"),
        ("3", generate_hihat, "hi-hat"),
        ("4", generate_clap, "clap"),
        ("5", generate_cowbell, "cowbell"),
        ("6", generate_woodblock, "woodblock"),
        ("7", generate_triangle, "triangle"),
        ("8", generate_tambourine, "tambourine"),
        ("9", generate_bongo, "bongo"),
    ]

    for num, generator, name in silly_sounds:
        samples = generator()
        write_wav(f"{num}.wav", samples)
        print(f"    {num} = {name}")

    print()
    print(f"Done! Sounds saved to {SOUNDS_DIR}")

if __name__ == "__main__":
    main()
