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
from purple_tui.music_constants import (
    CHROMATIC_NOTE_NAMES, FRIENDLY_KEYS, pitch_filename, pitch_for,
)


def reachable_pitches() -> list[tuple[str, int]]:
    """Every (note_name, octave) the grid can actually play.

    Enumerates all (row, col, root, octave_shift) cells and unions the
    pitch_for outputs. The 5 FRIENDLY_KEYS × major scale geometry covers
    11 of 12 chromatic notes; the missing one depends on which roots are
    in the cycle.
    """
    seen = set()
    for row in (0, 1, 2):
        for col in range(10):
            for root in FRIENDLY_KEYS:
                for shift in (-1, 0, 1):
                    seen.add(pitch_for(row, col, root, shift))
    return sorted(seen, key=lambda p: (p[1], CHROMATIC_NOTE_NAMES.index(p[0])))


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


def loudness_compensated_peak(freq: float, base: float = 0.7) -> float:
    """Push low-pitched samples closer to digital ceiling.

    The ear is much less sensitive below ~500Hz (Fletcher-Munson / ISO 226).
    Even on good speakers, a 100Hz note at the same digital level as a
    1kHz note sounds substantially quieter. Compensate by letting low
    samples normalize hotter — up to ~+2.5dB at the lowest octaves.
    """
    if freq >= 500:
        return base
    boost = 1.0 + 0.4 * (1 - max(freq, 80) / 500)
    return min(0.95, base * boost)


def low_freq_partial_boost(freq: float) -> float:
    """Scale upper-partial amplitudes for low-pitched notes.

    A low note's upper partials sit in the ear's most sensitive band
    (1–4kHz). Boosting them adds perceived loudness without changing pitch
    or smearing the fundamental. Returns 1.0 for notes above 250Hz.
    """
    if freq >= 250:
        return 1.0
    return min(2.5, 250 / max(freq, 80))


def finalize_samples(samples: list[float], peak_level: float = 0.75,
                     freq: float | None = None) -> list[int]:
    """Normalize and convert to int16.

    If freq is provided, scale peak_level via loudness_compensated_peak so
    low-frequency samples normalize hotter to offset ear insensitivity.
    """
    if freq is not None:
        peak_level = loudness_compensated_peak(freq, base=peak_level)
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


def generate_marimba(frequency: float, duration: float = 0.55) -> list[int]:
    """
    Crisp marimba: rosewood bar + tuned tube resonator at the fundamental.

    Real marimba bars are tuned so the second mode lands ~2 octaves above the
    fundamental (4:1) — that's the woody character. The tube resonator
    reinforces only the fundamental. Earlier versions stacked a 0.5x
    sub-octave sine and three tube partials, which produced a muddy clash
    against the bar fundamental and a low rumble that smeared the pitch.
    """
    sample_rate = 44100
    nyquist = sample_rate / 2
    num_samples = int(sample_rate * duration)

    # (ratio, amp, decay_rate). 4.0 is the defining marimba partial — the
    # woody "knock" that makes a marimba sound like itself rather than a
    # low sine. For low-pitched notes the upper partials get extra gain
    # because the fundamental sits below the ear's sensitive band.
    boost = low_freq_partial_boost(frequency)
    bar_partials = [
        (1.0, 1.0, 5.5),
        (4.0, 0.5 * boost, 11.0),
        (9.2, 0.08 * boost, 18.0),
    ]

    samples = []
    fade_out_duration = 0.18
    fade_out_start = duration - fade_out_duration

    # Soft mallet noise burst — adds the "thock" without muddying sustain.
    random.seed(int(frequency * 1000))

    for i in range(num_samples):
        t = i / sample_rate
        sample = 0.0

        if t < 0.008:
            attack = t / 0.008
        else:
            attack = 1.0

        for ratio, amp, decay_rate in bar_partials:
            f = frequency * ratio
            if f >= nyquist:
                continue
            sample += amp * math.exp(-t * decay_rate) * math.sin(2 * math.pi * f * t)

        # Tuned tube resonator: fundamental only, slow attack, fast decay.
        # Quieter and shorter than the bar so it adds body without smearing
        # pitch into the bar's own fundamental.
        tube_env = (1 - math.exp(-t * 30)) * math.exp(-t * 6.0)
        sample += 0.25 * tube_env * math.sin(2 * math.pi * frequency * t)

        # Mallet "thock": noise burst, ~6ms, lowpassed by the bar.
        if t < 0.01:
            mallet = (random.random() * 2 - 1) * 0.25 * math.exp(-t * 400)
            sample += mallet

        sample *= attack

        if t > fade_out_start:
            fade_progress = (t - fade_out_start) / fade_out_duration
            sample *= 0.5 * (1 + math.cos(math.pi * fade_progress))

        samples.append(sample)

    return finalize_samples(samples, peak_level=0.7, freq=frequency)


def generate_accordion(frequency: float, duration: float = 0.55) -> list[int]:
    """
    Accordion: two detuned reed voices summed, with a gentle tremolo.

    Real accordions sound the way they do because each note plays through
    *two* reeds tuned slightly apart — that's what produces the swimmy
    "musette" beating. Each reed is close to a sawtooth waveform (rich in
    harmonics) but rolled off at the top so it reads as reedy rather than
    buzzy. We synthesize two band-limited sawtooths a few cents apart,
    sum them, and modulate the amplitude at ~6Hz to suggest the bellows
    breathing in and out.
    """
    sample_rate = 44100
    nyquist = sample_rate / 2
    num_samples = int(sample_rate * duration)
    samples = []
    fade_out_duration = 0.12
    fade_out_start = duration - fade_out_duration

    # Two reeds, ~8 cents apart. The chorus beat rate at low pitch is a
    # few Hz, which is what gives accordion its characteristic "wobble."
    detune_cents = 4.0
    f1 = frequency
    f2 = frequency * (2 ** (detune_cents / 1200.0))

    # Band-limited sawtooth via Fourier series. Lower rolloff (2kHz) tames
    # the buzzy reed edge — pushes the timbre toward harmonium/shruti box
    # rather than carnival accordion.
    rolloff_hz = 2000.0
    harmonic_cap = 20
    max_n = min(harmonic_cap, int(nyquist / max(frequency, 1.0)))

    trem_rate = 6.0
    trem_depth = 0.04

    for i in range(num_samples):
        t = i / sample_rate
        # 30ms attack — bellows take a moment to engage.
        if t < 0.03:
            attack = t / 0.03
        else:
            attack = 1.0

        s = 0.0
        for f in (f1, f2):
            for n in range(1, max_n + 1):
                fn = f * n
                if fn >= nyquist:
                    break
                amp = 1.0 / n
                if fn > rolloff_hz:
                    amp *= rolloff_hz / fn
                s += amp * math.sin(2 * math.pi * fn * t)

        trem = 1.0 + trem_depth * math.sin(2 * math.pi * trem_rate * t)
        s *= attack * trem

        if t > fade_out_start:
            fade_progress = (t - fade_out_start) / fade_out_duration
            s *= 0.5 * (1 + math.cos(math.pi * fade_progress))

        samples.append(s)

    return finalize_samples(samples, peak_level=0.55, freq=frequency)


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

    return finalize_samples(samples, peak_level=0.7, freq=frequency)


def generate_glockenspiel(frequency: float, duration: float = 1.2) -> list[int]:
    """Glockenspiel: bright metal bell with long shimmery ring.

    Distinguishes from marimba by three things:
    1. Long sustain — fundamental decays slowly so notes ring out for a
       full second+ rather than the marimba's ~0.5s woody knock.
    2. Weak fundamental, dominant 2nd partial — real glock bars are too
       small to vibrate strongly at the fundamental, so the 2.8x partial
       carries the perceived "bell" character.
    3. Bright metallic ping at onset — short ~4kHz sine burst suggests a
       hard mallet on metal, vs marimba's woody noise thock.

    Tuning note: the 2.8x inharmonic partial creates a false autocorrelation
    peak ~85 cents below the fundamental. The fundamental itself is correct
    (verify with DFT, not autocorrelation).
    """
    sample_rate = 44100
    nyquist = sample_rate / 2
    num_samples = int(sample_rate * duration)
    fade_out = 0.18
    fade_start = duration - fade_out
    boost = low_freq_partial_boost(frequency)
    # Inharmonic ratios with the 2nd partial louder than the fundamental.
    # Decay rates roughly halved vs the older marimba-shaped version so the
    # bell rings out instead of knocking.
    partials = [
        (1.0, 0.6, 0.8),
        (2.8, 0.9 * boost, 2.0),
        (5.42, 0.45 * boost, 3.0),
        (8.6, 0.22 * boost, 5.0),
        (11.7, 0.12 * boost, 7.0),
    ]
    ping_freq = 4000.0
    ping_duration = 0.005
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        if t < 0.002:
            attack = t / 0.002
        else:
            attack = 1.0
        s = 0.0
        for ratio, amp, dec in partials:
            f = frequency * ratio
            if f >= nyquist:
                continue
            s += amp * math.exp(-t * dec) * math.sin(2 * math.pi * f * t)
        if t < ping_duration and ping_freq < nyquist:
            ping_env = math.exp(-t / (ping_duration / 4))
            s += 0.35 * ping_env * math.sin(2 * math.pi * ping_freq * t)
        s *= attack
        if t > fade_start:
            p = (t - fade_start) / fade_out
            s *= 0.5 * (1 + math.cos(math.pi * p))
        samples.append(s)
    return finalize_samples(samples, peak_level=0.7, freq=frequency)



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
            # MIDI: C0=12, so semitone = 12*(octave+1) + note_idx
            # We use scientific pitch (A4=440) → freq = 440 * 2^((midi-69)/12)
            note_idx = CHROMATIC_NOTE_NAMES.index(note_name)
            midi = 12 * (octave + 1) + note_idx
            freq = 440.0 * (2 ** ((midi - 69) / 12))
            samples = generator(freq)
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
