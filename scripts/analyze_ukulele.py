#!/usr/bin/env python3
"""
Analyze a real ukulele recording to extract synthesis parameters.

Downloads a ukulele single-note sample from Freesound, then measures:
- Relative amplitudes of each harmonic partial
- Decay rates for each partial over time
- Attack transient shape
- Body resonance peaks

Output: concrete numbers we can plug into generate_ukulele().
"""

import sys
import wave
import math
import struct
import tempfile
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# We'll use the Freesound sample or generate a reference tone
# For now, let's analyze what we have vs what a real uke should sound like


def read_wav(path: str) -> tuple[list[float], int]:
    """Read a WAV file, return (samples_as_floats, sample_rate)."""
    with wave.open(path, 'r') as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        rate = w.getframerate()
        n_frames = w.getnframes()
        raw = w.readframes(n_frames)

    if sampwidth == 2:
        fmt = f'<{n_frames * n_channels}h'
        int_samples = struct.unpack(fmt, raw)
    elif sampwidth == 1:
        int_samples = [b - 128 for b in raw]
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    # Take first channel if stereo
    if n_channels > 1:
        int_samples = int_samples[::n_channels]

    peak = max(abs(s) for s in int_samples) or 1
    return [s / peak for s in int_samples], rate


def measure_harmonic_amplitude(samples: list[float], rate: int,
                               fundamental: float, harmonic: int,
                               start_time: float, window_dur: float) -> float:
    """
    Measure amplitude of a specific harmonic using Goertzel-like correlation.
    More precise than FFT for known frequencies.
    """
    freq = fundamental * harmonic
    start = int(start_time * rate)
    length = int(window_dur * rate)
    end = min(start + length, len(samples))

    if end <= start:
        return 0.0

    # Correlate with sine and cosine at target frequency
    sin_sum = 0.0
    cos_sum = 0.0
    for i in range(start, end):
        t = i / rate
        s = samples[i]
        sin_sum += s * math.sin(2 * math.pi * freq * t)
        cos_sum += s * math.cos(2 * math.pi * freq * t)

    n = end - start
    amplitude = 2 * math.sqrt(sin_sum**2 + cos_sum**2) / n
    return amplitude


def analyze_note(samples: list[float], rate: int, fundamental: float,
                 n_harmonics: int = 10):
    """Analyze a single plucked note."""

    print(f"\nFundamental: {fundamental:.1f} Hz")
    print(f"Duration: {len(samples)/rate:.2f}s ({len(samples)} samples at {rate} Hz)")

    # Measure harmonic amplitudes at different time windows
    # to get both initial spectrum and decay rates
    time_windows = [
        (0.01, 0.05),   # right after attack (10-60ms)
        (0.05, 0.10),   # early sustain
        (0.15, 0.10),   # mid sustain
        (0.30, 0.10),   # late sustain
        (0.50, 0.10),   # tail
    ]

    print(f"\n{'Harmonic':>10} | ", end="")
    for start, dur in time_windows:
        print(f" {start:.2f}s", end="  ")
    print(" | Decay rate")
    print("-" * 80)

    for h in range(1, n_harmonics + 1):
        freq = fundamental * h
        if freq > rate / 2:
            break

        amps = []
        for start, dur in time_windows:
            amp = measure_harmonic_amplitude(samples, rate, fundamental, h, start, dur)
            amps.append(amp)

        # Normalize to fundamental's initial amplitude
        label = f"H{h} ({freq:.0f}Hz)"
        print(f"{label:>16} | ", end="")
        for amp in amps:
            print(f" {amp:.4f}", end=" ")

        # Estimate decay rate from amplitude envelope
        # amp(t) = A * exp(-decay * t), so decay = -ln(amp2/amp1) / (t2-t1)
        if amps[0] > 0.001 and amps[-1] > 0.0001:
            t1 = time_windows[0][0] + time_windows[0][1] / 2
            t2 = time_windows[-1][0] + time_windows[-1][1] / 2
            decay = -math.log(amps[-1] / amps[0]) / (t2 - t1)
            print(f" | {decay:.1f}/s")
        else:
            print(f" | (too quiet)")

    # Relative amplitudes at early sustain (characteristic timbre)
    print("\n\nRelative amplitudes (early sustain, 50-150ms):")
    ref_amp = measure_harmonic_amplitude(samples, rate, fundamental, 1, 0.05, 0.10)
    if ref_amp < 0.0001:
        print("  Fundamental too quiet to measure")
        return

    for h in range(1, n_harmonics + 1):
        freq = fundamental * h
        if freq > rate / 2:
            break
        amp = measure_harmonic_amplitude(samples, rate, fundamental, h, 0.05, 0.10)
        ratio = amp / ref_amp
        bar = "#" * int(ratio * 50)
        print(f"  H{h:2d} ({freq:6.0f} Hz): {ratio:.3f}  {bar}")


def analyze_our_generated():
    """Analyze our current generated ukulele sound for comparison."""
    # Convert one of our OGG files to WAV for analysis
    ogg_path = PROJECT_ROOT / "packs/core-sounds/content/ukulele/f.ogg"
    if not ogg_path.exists():
        print(f"Generated ukulele sound not found at {ogg_path}")
        return

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name

    subprocess.run(
        ['ffmpeg', '-y', '-i', str(ogg_path), tmp_path],
        capture_output=True, check=True,
    )

    samples, rate = read_wav(tmp_path)
    Path(tmp_path).unlink()

    # F note in middle row = 261.63 Hz (C4)
    print("=" * 80)
    print("OUR GENERATED UKULELE (F key = 261.63 Hz)")
    print("=" * 80)
    analyze_note(samples, rate, 261.63)


def analyze_reference():
    """
    Download and analyze a real ukulele sample.
    Uses Freesound preview (no auth needed for previews).
    """
    # Freesound sound 173122 is a single ukulele note by _steef
    # Preview URLs don't need authentication
    preview_url = "https://freesound.org/data/previews/173/173122_1080263-lq.mp3"

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_mp3:
        mp3_path = tmp_mp3.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
        wav_path = tmp_wav.name

    try:
        print("Downloading real ukulele sample from Freesound...")
        result = subprocess.run(
            ['curl', '-sL', '-o', mp3_path, preview_url],
            capture_output=True, timeout=15,
        )
        if result.returncode != 0:
            print("  Download failed, skipping reference analysis")
            return

        # Check we got actual audio, not an error page
        import os
        size = os.path.getsize(mp3_path)
        if size < 5000:
            print(f"  Downloaded file too small ({size} bytes), may not be audio")
            print("  Skipping reference analysis")
            return

        subprocess.run(
            ['ffmpeg', '-y', '-i', mp3_path, '-ar', '44100', '-ac', '1', wav_path],
            capture_output=True, check=True,
        )

        samples, rate = read_wav(wav_path)
        print(f"  Got {len(samples)/rate:.2f}s of audio at {rate} Hz")

        # This sample might be a chord or strum, let's look at spectrum
        # Try to detect fundamental via autocorrelation
        fundamental = detect_fundamental(samples, rate)

        print("=" * 80)
        print(f"REAL UKULELE SAMPLE (detected fundamental: {fundamental:.1f} Hz)")
        print("=" * 80)
        analyze_note(samples, rate, fundamental)

    except Exception as e:
        print(f"  Reference analysis failed: {e}")
    finally:
        Path(mp3_path).unlink(missing_ok=True)
        Path(wav_path).unlink(missing_ok=True)


def detect_fundamental(samples: list[float], rate: int,
                       min_freq: float = 80, max_freq: float = 1000) -> float:
    """Detect fundamental frequency via autocorrelation on first 100ms."""
    # Use samples from 10ms to 100ms (skip attack transient)
    start = int(0.01 * rate)
    end = int(0.10 * rate)
    chunk = samples[start:end]

    min_lag = int(rate / max_freq)
    max_lag = int(rate / min_freq)

    best_corr = 0
    best_lag = min_lag

    for lag in range(min_lag, min(max_lag, len(chunk) // 2)):
        corr = sum(chunk[i] * chunk[i + lag] for i in range(len(chunk) - lag))
        corr /= (len(chunk) - lag)
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    return rate / best_lag


def main():
    analyze_our_generated()
    print("\n")
    analyze_reference()

    print("\n\n" + "=" * 80)
    print("REFERENCE: What real ukulele partials typically look like")
    print("=" * 80)
    print("""
Based on acoustic research (Physics 406, UIUC) and plucked string theory:

Real ukulele characteristics vs typical additive synthesis:
- Fundamental dominates strongly (nylon strings have fewer overtones than steel)
- 2nd harmonic: ~0.3-0.5x fundamental (warm, not bright)
- 3rd harmonic: ~0.1-0.2x (adds just a bit of character)
- 4th+: drops off rapidly, < 0.05x
- Decay: fundamental rings 0.5-1.5s, higher partials die 2-3x faster
- Attack: soft pluck ~5-10ms, no hard transient
- Body resonance: broad peak around 400-600 Hz (small body)
- Key difference from guitar: MUCH less high-frequency content
  (nylon + small body + short scale = warm and round)
- Slight inharmonicity from string stiffness (partials ~0.1-0.3% sharp)
""")


if __name__ == "__main__":
    main()
