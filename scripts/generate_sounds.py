#!/usr/bin/env python3
"""
Generate fun sounds for Purple Computer Music Mode

Creates vibrant, kid-friendly sounds:
- Marimba: warm, woody, percussive (default)
- Accordion: sustained, two detuned reed voices with gentle tremolo
- Ukulele: warm, plucky, cheerful
- Glockenspiel: bright, metallic, inharmonic bell with long ring
- Percussion: kick, snare, hi-hat, etc. (shared across instruments)
"""

import sys
import wave
import math
import random
import subprocess
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOUNDS_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content"

sys.path.insert(0, str(PROJECT_ROOT))
from purple_tui.music_constants import (  # noqa: F401  reachable_pitches re-exported for older scripts
    note_frequency, pitch_filename, reachable_pitches,
)
from purple_tui.synth import (  # noqa: F401  re-exported for the clip analysis scripts
    finalize_samples, generate_accordion, generate_glockenspiel, generate_marimba, generate_ukulele,
    loudness_compensated_peak, low_freq_partial_boost,
)


def write_sound(filename: str, samples: list[int], sample_rate: int = 44100,
                subdir: str | None = None):
    """Write samples as an OGG file (via WAV temp file + ffmpeg)."""
    if subdir:
        target = SOUNDS_DIR / subdir
        target.mkdir(parents=True, exist_ok=True)
    else:
        target = SOUNDS_DIR
    ogg_name = filename.replace('.wav', '.ogg')
    ogg_path = target / ogg_name

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name
        with wave.open(tmp_path, 'w') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for sample in samples:
                sample = max(-32767, min(32767, sample))
                wav_file.writeframes(sample.to_bytes(2, byteorder='little', signed=True))

    subprocess.run(
        ['ffmpeg', '-y', '-i', tmp_path, '-c:a', 'libvorbis', '-q:a', '3',
         str(ogg_path)],
        capture_output=True, check=True,
    )
    Path(tmp_path).unlink()

    label = f"{subdir}/{ogg_name}" if subdir else ogg_name
    print(f"  Created {label}")


def generate_piano_tone(frequency: float, duration: float = 0.4) -> list[int]:
    """
    Original bright, vibrant piano-like tone.
    Rich harmonics + sparkle + nice envelope.
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate

        sample = math.sin(2 * math.pi * frequency * t)
        sample += 0.5 * math.sin(2 * math.pi * frequency * 2 * t)
        sample += 0.35 * math.sin(2 * math.pi * frequency * 3 * t)
        sample += 0.2 * math.sin(2 * math.pi * frequency * 4 * t)
        sample += 0.1 * math.sin(2 * math.pi * frequency * 5 * t)

        shimmer = 0.05 * math.sin(2 * math.pi * frequency * 8 * t)
        shimmer *= math.exp(-t * 8)
        sample += shimmer

        attack_time = 0.02
        decay_time = 0.1
        sustain_level = 0.7
        release_start = duration - 0.15

        if t < attack_time:
            envelope = (t / attack_time) * 1.1
        elif t < attack_time + decay_time:
            decay_progress = (t - attack_time) / decay_time
            envelope = 1.1 - (0.4 * decay_progress)
        elif t < release_start:
            envelope = sustain_level
        else:
            release_progress = (t - release_start) / (duration - release_start)
            envelope = sustain_level * (1 - release_progress)

        sample *= envelope * 0.3
        samples.append(int(sample * 32767))

    return samples


def generate_rich_tone(frequency: float, duration: float = 0.5) -> list[int]:
    """
    Bright, playful tone - like a toy piano or xylophone.
    Punchy attack, clear tone, fun for kids.
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)

    samples = []
    fade_out_start = duration - 0.04

    for i in range(num_samples):
        t = i / sample_rate

        if t < 0.005:
            attack = (t / 0.005) * 1.3
        elif t < 0.03:
            attack = 1.3 - 0.3 * ((t - 0.005) / 0.025)
        else:
            attack = 1.0

        sample = math.sin(2 * math.pi * frequency * t)
        sample += 0.5 * math.sin(2 * math.pi * frequency * 2 * t)
        sample += 0.4 * math.sin(2 * math.pi * frequency * 4 * t)
        sample += 0.15 * math.sin(2 * math.pi * frequency * 6 * t)

        envelope = math.exp(-t * 4)
        sample = sample * attack * envelope

        if t > fade_out_start:
            sample *= 1 - (t - fade_out_start) / 0.04

        samples.append(sample)

    return finalize_samples(samples)


# Percussion is peak-normalized through finalize_samples just like the
# pitched instruments, so a runtime set_volume(0.4) lands every sample at
# the same perceived loudness.
PERCUSSION_PEAK = 0.7


def generate_kick_drum() -> list[int]:
    """Punchy kick drum - tuned for laptop speakers"""
    sample_rate = 44100
    duration = 0.35
    num_samples = int(sample_rate * duration)
    samples = []

    fade_in_samples = int(sample_rate * 0.002)

    for i in range(num_samples):
        t = i / sample_rate
        freq = 180 * math.exp(-t * 20) + 60
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        click = math.exp(-t * 80) * 0.25
        sample += click
        envelope = math.exp(-t * 7)

        if i < fade_in_samples:
            fade = i / fade_in_samples
        else:
            fade = 1.0

        samples.append(sample * envelope * fade)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_snare() -> list[int]:
    """Crispy snare drum"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(42)
    for i in range(num_samples):
        t = i / sample_rate
        tone = math.sin(2 * math.pi * 200 * t) * math.exp(-t * 20)
        noise = (random.random() * 2 - 1) * math.exp(-t * 15)
        sample = tone * 0.4 + noise * 0.6
        envelope = math.exp(-t * 10)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_hihat() -> list[int]:
    """Bright hi-hat cymbal"""
    sample_rate = 44100
    duration = 0.15
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(123)
    for i in range(num_samples):
        t = i / sample_rate
        noise = random.random() * 2 - 1
        tone = math.sin(2 * math.pi * 8000 * t) * 0.3
        tone += math.sin(2 * math.pi * 10000 * t) * 0.2
        sample = noise * 0.7 + tone
        envelope = math.exp(-t * 30)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_gong() -> list[int]:
    """Deep gong hit"""
    sample_rate = 44100
    duration = 1.0
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        freq = 120
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.6 * math.sin(2 * math.pi * freq * 2.01 * t)
        sample += 0.4 * math.sin(2 * math.pi * freq * 3.02 * t)
        sample += 0.2 * math.sin(2 * math.pi * freq * 4.5 * t)
        wobble = 1 + 0.1 * math.sin(2 * math.pi * 3 * t)
        sample *= wobble
        envelope = math.exp(-t * 2)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_cowbell() -> list[int]:
    """Classic cowbell - more cowbell!"""
    sample_rate = 44100
    duration = 0.3
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        freq1 = 800
        freq2 = 540
        sample = math.sin(2 * math.pi * freq1 * t)
        sample += 0.7 * math.sin(2 * math.pi * freq2 * t)
        sample += 0.3 * math.sin(2 * math.pi * freq1 * 2 * t)
        envelope = math.exp(-t * 8)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_clap() -> list[int]:
    """Hand clap sound"""
    sample_rate = 44100
    duration = 0.2
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(321)
    for i in range(num_samples):
        t = i / sample_rate
        burst1 = math.exp(-((t - 0.005) ** 2) * 50000)
        burst2 = math.exp(-((t - 0.015) ** 2) * 40000)
        burst3 = math.exp(-((t - 0.025) ** 2) * 30000)
        bursts = burst1 + burst2 * 0.8 + burst3 * 0.6
        noise = (random.random() * 2 - 1) * bursts
        envelope = math.exp(-t * 15)
        samples.append(noise * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_woodblock() -> list[int]:
    """Hollow wood block tick"""
    sample_rate = 44100
    duration = 0.15
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        freq = 800
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.5 * math.sin(2 * math.pi * freq * 2.3 * t)
        sample += 0.3 * math.sin(2 * math.pi * freq * 4.1 * t)
        envelope = math.exp(-t * 25)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_triangle() -> list[int]:
    """Triangle ding"""
    sample_rate = 44100
    duration = 0.6
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        freq = 1500
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        sample += 0.15 * math.sin(2 * math.pi * freq * 3 * t)
        vibrato = 1 + 0.002 * math.sin(2 * math.pi * 6 * t)
        sample *= vibrato
        envelope = math.exp(-t * 4)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_tambourine() -> list[int]:
    """Jingly tambourine shake"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    random.seed(654)
    for i in range(num_samples):
        t = i / sample_rate
        noise = (random.random() * 2 - 1)
        jingle = math.sin(2 * math.pi * 6000 * t) * 0.3
        jingle += math.sin(2 * math.pi * 8500 * t) * 0.2
        jingle += math.sin(2 * math.pi * 11000 * t) * 0.1
        sample = noise * 0.5 + jingle
        envelope = math.exp(-t * 12)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def generate_bongo() -> list[int]:
    """Bongo drum hit"""
    sample_rate = 44100
    duration = 0.25
    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate
        freq = 400 * math.exp(-t * 30) + 180
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.4 * math.sin(2 * math.pi * freq * 1.5 * t)
        envelope = math.exp(-t * 15)
        samples.append(sample * envelope)

    return finalize_samples(samples, peak_level=PERCUSSION_PEAK)

def main():
    """Generate all sounds"""
    print("Generating Purple Computer sounds...")
    print()

    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    # Instrument generators: (directory_name, generator_function)
    instruments = [
        ("marimba", generate_marimba),
        ("accordion", generate_accordion),
        ("ukulele", generate_ukulele),
        ("glockenspiel", generate_glockenspiel),
    ]

    for inst_dir, generator in instruments:
        print(f"{inst_dir} tones:")
        inst_path = SOUNDS_DIR / inst_dir
        # Wipe stale per-key files (q.ogg, a.ogg, etc.) from the previous
        # naming scheme so the runtime can't fall back to them.
        if inst_path.exists():
            for old in inst_path.glob("*.ogg"):
                old.unlink()
        for note_name, octave in reachable_pitches():
            samples = generator(note_frequency(note_name, octave))
            fname = pitch_filename(note_name, octave) + ".wav"
            write_sound(fname, samples, subdir=inst_dir)
        print()

    print("Percussion (0-9):")

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
        write_sound(f"{num}.wav", samples)
        print(f"    {num} = {name}")

    print()
    print(f"Done! Sounds saved to {SOUNDS_DIR}")

if __name__ == "__main__":
    main()
