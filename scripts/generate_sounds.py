#!/usr/bin/env python3
"""
Generate fun sounds for Purple Computer Music Mode

Creates vibrant, kid-friendly sounds:
- Marimba: warm, woody, percussive (default)
- Xylophone: bright, clear, sparkly
- Ukulele: warm, plucky, cheerful
- Music Box: sparkly, bell-like, magical
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
from purple_tui.music_constants import NOTE_FREQUENCIES


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


def finalize_samples(samples: list[float], peak_level: float = 0.75) -> list[int]:
    """Normalize and convert to int16."""
    peak = max(abs(s) for s in samples) or 1
    return [int(s / peak * peak_level * 32767) for s in samples]


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


def generate_marimba(frequency: float, duration: float = 0.65) -> list[int]:
    """
    Full, resonant marimba with tube resonator simulation.
    Bar vibration + resonator tube = rich, room-filling sound.
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)

    bar_partials = [
        (1.0, 1.0, 2.5),
        (3.9, 0.15, 6.0),
        (9.2, 0.05, 12.0),
    ]

    tube_modes = [
        (1.0, 0.45, 1.5),
        (2.0, 0.2, 2.5),
        (3.0, 0.1, 3.5),
    ]

    samples = []
    fade_out_duration = 0.18
    fade_out_start = duration - fade_out_duration

    for i in range(num_samples):
        t = i / sample_rate
        sample = 0

        if t < 0.012:
            attack = t / 0.012
        elif t < 0.06:
            attack = 1.0 + 0.2 * math.sin(math.pi * (t - 0.012) / 0.048)
        else:
            attack = 1.0

        for ratio, amp, decay_rate in bar_partials:
            partial_decay = math.exp(-t * decay_rate)
            sample += amp * partial_decay * math.sin(2 * math.pi * frequency * ratio * t)

        for ratio, amp, decay_rate in tube_modes:
            tube_env = (1 - math.exp(-t * 25)) * math.exp(-t * decay_rate)
            sample += amp * tube_env * math.sin(2 * math.pi * frequency * ratio * t)

        sub_bass = 0.3 * math.exp(-t * 2.0) * math.sin(2 * math.pi * frequency * 0.5 * t)
        sample += sub_bass

        sample *= attack

        if t > fade_out_start:
            fade_progress = (t - fade_out_start) / fade_out_duration
            sample *= 0.5 * (1 + math.cos(math.pi * fade_progress))

        samples.append(sample)

    return finalize_samples(samples, peak_level=0.7)


def generate_xylophone(frequency: float, duration: float = 0.5) -> list[int]:
    """
    Bright, clear xylophone. Hard mallet on wooden/synthetic bars.
    Sharp attack, prominent high partials, quick decay.
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    samples = []
    fade_out_duration = 0.1
    fade_out_start = duration - fade_out_duration

    # Xylophone bar partials (slightly inharmonic, brighter than marimba)
    bar_partials = [
        (1.0, 1.0, 4.0),      # fundamental, strong, moderate decay
        (3.0, 0.45, 6.0),     # 3rd partial prominent (characteristic of xylophone)
        (6.0, 0.2, 10.0),     # high partial for brightness
        (9.9, 0.08, 16.0),    # sparkle partial, decays fast
    ]

    for i in range(num_samples):
        t = i / sample_rate
        sample = 0

        # Very sharp mallet attack with bright click
        if t < 0.003:
            attack = t / 0.003
        elif t < 0.015:
            # Brief overshoot for hard-mallet "click"
            attack = 1.0 + 0.25 * math.exp(-(t - 0.003) * 300)
        else:
            attack = 1.0

        for ratio, amp, decay_rate in bar_partials:
            partial_decay = math.exp(-t * decay_rate)
            sample += amp * partial_decay * math.sin(2 * math.pi * frequency * ratio * t)

        # High-frequency click transient (mallet impact)
        click = 0.15 * math.exp(-t * 80) * math.sin(2 * math.pi * frequency * 12 * t)
        sample += click

        sample *= attack

        if t > fade_out_start:
            fade_progress = (t - fade_out_start) / fade_out_duration
            sample *= 0.5 * (1 + math.cos(math.pi * fade_progress))

        samples.append(sample)

    return finalize_samples(samples, peak_level=0.7)


def generate_ukulele(frequency: float, duration: float = 0.9) -> list[int]:
    """
    Ukulele via Karplus-Strong physical modeling.

    Instead of additive synthesis (static sine waves), this uses a delay line
    with filtered feedback, which naturally produces the evolving harmonic
    interactions of a real plucked string. The key parameters that make it
    sound like a nylon-string ukulele rather than a steel guitar:

    - Warm initial excitation (lowpass-filtered noise, simulating finger pad)
    - High damping factor (nylon strings lose energy faster than steel)
    - Strong lowpass in the feedback loop (nylon has few high overtones)
    - Body resonance filter adds the small hollow-body character
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    fade_out_duration = 0.15
    fade_out_start = duration - fade_out_duration

    # Delay line length determines pitch
    period = sample_rate / frequency
    # Integer part + fractional allpass interpolation for accurate tuning
    N = int(period)
    frac = period - N

    # Allpass coefficient for fractional delay (keeps tuning accurate)
    allpass_coeff = (1 - frac) / (1 + frac)

    # Initialize delay line with filtered noise (the "pluck").
    # Lowpass filtering the initial noise simulates a soft finger pad pluck
    # (vs bright pick = unfiltered white noise).
    random.seed(int(frequency * 1000))  # deterministic per note
    raw_noise = [random.random() * 2 - 1 for _ in range(N)]

    # Two-pass smoothing: makes the initial spectrum warm (fewer high harmonics).
    # This is the main thing that distinguishes nylon uke from steel guitar.
    delay_line = raw_noise[:]
    for _ in range(3):  # 3 passes = very warm, finger-pluck character
        for j in range(1, N):
            delay_line[j] = 0.5 * delay_line[j] + 0.5 * delay_line[j - 1]

    # Pluck position filter: a real finger plucks ~1/4 to 1/3 along the string,
    # which suppresses harmonics at multiples of that position.
    # For ukulele plucked near the soundhole (~1/4 of string length),
    # this notches out the 4th harmonic, giving a rounder tone.
    pluck_pos = N // 4
    if pluck_pos > 0:
        for j in range(N):
            if j >= pluck_pos:
                delay_line[j] = delay_line[j] - 0.5 * delay_line[j - pluck_pos]

    # KS synthesis loop
    samples = [0.0] * num_samples
    buf = delay_line[:]
    write_pos = 0
    allpass_prev_in = 0.0
    allpass_prev_out = 0.0

    # Damping: nylon strings lose energy faster than steel.
    # This controls overall decay rate.
    damping = 0.996

    # Feedback filter state (one-pole lowpass in the delay loop).
    # Lower blend = warmer, more ukulele-like.
    # 0.4 means the feedback strongly favors the previous sample (warm).
    blend = 0.4
    prev_sample = 0.0

    for i in range(num_samples):
        # Read from delay line
        out = buf[write_pos]

        # One-pole lowpass filter in the feedback loop.
        # This is what makes higher harmonics decay faster than lower ones,
        # the hallmark of a plucked string sound.
        filtered = blend * out + (1 - blend) * prev_sample
        prev_sample = filtered

        # Allpass interpolation for fractional delay (pitch accuracy)
        allpass_out = allpass_coeff * filtered + allpass_prev_in - allpass_coeff * allpass_prev_out
        allpass_prev_in = filtered
        allpass_prev_out = allpass_out

        # Write back with damping
        buf[write_pos] = allpass_out * damping

        # Advance write position
        write_pos = (write_pos + 1) % N

        samples[i] = out

    # Body resonance: simple two-pole resonator at ~420 Hz.
    # Simulates the small hollow body of a ukulele adding warmth.
    body_freq = 420.0
    body_q = 3.0  # moderate Q, broad resonance
    # Biquad bandpass coefficients
    w0 = 2 * math.pi * body_freq / sample_rate
    alpha = math.sin(w0) / (2 * body_q)
    b0 = alpha
    b1 = 0.0
    b2 = -alpha
    a0 = 1 + alpha
    a1 = -2 * math.cos(w0)
    a2 = 1 - alpha
    # Normalize
    b0 /= a0; b1 /= a0; b2 /= a0; a1 /= a0; a2 /= a0

    body = [0.0] * num_samples
    x1 = x2 = y1 = y2 = 0.0
    for i in range(num_samples):
        x0 = samples[i]
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        body[i] = y0
        x2 = x1; x1 = x0; y2 = y1; y1 = y0

    # Mix: dry string + body resonance
    body_mix = 0.35
    for i in range(num_samples):
        samples[i] = samples[i] + body_mix * body[i]

    # Cosine fade-out
    fade_start_sample = int(fade_out_start * sample_rate)
    fade_samples = int(fade_out_duration * sample_rate)
    for i in range(fade_start_sample, num_samples):
        progress = (i - fade_start_sample) / fade_samples
        samples[i] *= 0.5 * (1 + math.cos(math.pi * progress))

    return finalize_samples(samples, peak_level=0.7)


def generate_music_box(frequency: float, duration: float = 0.55) -> list[int]:
    """
    Sparkly, bell-like music box. Inharmonic partials from metal comb physics.
    Bright "ping" attack, clear and punchy.
    """
    sample_rate = 44100
    num_samples = int(sample_rate * duration)
    samples = []
    fade_out_duration = 0.12
    fade_out_start = duration - fade_out_duration

    for i in range(num_samples):
        t = i / sample_rate
        sample = 0

        # Snappy ping attack
        if t < 0.002:
            attack = t / 0.002
        elif t < 0.01:
            attack = 1.0 + 0.3 * math.exp(-(t - 0.002) * 200)
        else:
            attack = 1.0

        # Inharmonic partials (metal comb physics)
        sample += 1.0 * math.sin(2 * math.pi * frequency * 1.0 * t)
        sample += 0.4 * math.sin(2 * math.pi * frequency * 2.76 * t)
        sample += 0.2 * math.sin(2 * math.pi * frequency * 5.4 * t)
        sample += 0.1 * math.sin(2 * math.pi * frequency * 8.93 * t)

        # High sparkle partial that decays fast
        sparkle = 0.15 * math.sin(2 * math.pi * frequency * 12.1 * t) * math.exp(-t * 20)
        sample += sparkle

        # Moderate decay, not too long
        envelope = math.exp(-t * 3.5)
        sample *= envelope * attack

        if t > fade_out_start:
            fade_progress = (t - fade_out_start) / fade_out_duration
            sample *= 0.5 * (1 + math.cos(math.pi * fade_progress))

        samples.append(sample)

    return finalize_samples(samples, peak_level=0.7)


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
        tone = math.sin(2 * math.pi * 200 * t) * math.exp(-t * 20)
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
        noise = random.random() * 2 - 1
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
        freq = 120
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.6 * math.sin(2 * math.pi * freq * 2.01 * t)
        sample += 0.4 * math.sin(2 * math.pi * freq * 3.02 * t)
        sample += 0.2 * math.sin(2 * math.pi * freq * 4.5 * t)
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
        freq1 = 800
        freq2 = 540
        sample = math.sin(2 * math.pi * freq1 * t)
        sample += 0.7 * math.sin(2 * math.pi * freq2 * t)
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
        freq = 1500
        sample = math.sin(2 * math.pi * freq * t)
        sample += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        sample += 0.15 * math.sin(2 * math.pi * freq * 3 * t)
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
        noise = (random.random() * 2 - 1)
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

    # Instrument generators: (directory_name, generator_function)
    instruments = [
        ("marimba", generate_marimba),
        ("xylophone", generate_xylophone),
        ("ukulele", generate_ukulele),
        ("musicbox", generate_music_box),
    ]

    for inst_dir, generator in instruments:
        print(f"{inst_dir} tones:")
        for letter, freq in NOTE_FREQUENCIES.items():
            samples = generator(freq)
            write_sound(f"{letter.lower()}.wav", samples, subdir=inst_dir)
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
