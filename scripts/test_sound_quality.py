#!/usr/bin/env python3
"""
A/B test sound quality: WAV vs OGG at different settings.

Generates a marimba note in several formats and lets you play each one
with number keys. Uses pygame for playback (same as Purple Computer).

Run on the VM:  just python scripts/test_sound_quality.py
"""

import os
import sys
import wave
import time
import tempfile
import subprocess
from pathlib import Path

# Suppress pygame welcome
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_sounds import generate_marimba, generate_xylophone, generate_ukulele, generate_music_box

FREQ = 261.63  # Middle C


def write_wav(path: str, samples: list[int], sample_rate: int = 44100):
    with wave.open(path, 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        for s in samples:
            s = max(-32767, min(32767, s))
            f.writeframes(s.to_bytes(2, byteorder='little', signed=True))


def wav_to_ogg(wav_path: str, ogg_path: str, quality: int = 3):
    subprocess.run(
        ['ffmpeg', '-y', '-i', wav_path, '-c:a', 'libvorbis', '-q:a', str(quality),
         ogg_path],
        capture_output=True, check=True,
    )


def main():
    import pygame.mixer
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

    tmp = Path(tempfile.mkdtemp(prefix='purple_sound_test_'))

    # Generate raw samples for each instrument
    raw_marimba = generate_marimba(FREQ)
    raw_xylo = generate_xylophone(FREQ)
    raw_uke = generate_ukulele(FREQ)
    raw_mbox = generate_music_box(FREQ)

    # Helper to make both WAV and OGG versions
    def make_pair(name, samples, peak_level, ogg_quality=3):
        # Re-normalize to desired peak level
        peak = max(abs(s) for s in samples) or 1
        scaled = [int(s / peak * peak_level * 32767) for s in samples]
        wav_path = str(tmp / f"{name}.wav")
        ogg_path = str(tmp / f"{name}.ogg")
        write_wav(wav_path, scaled)
        wav_to_ogg(wav_path, ogg_path, quality=ogg_quality)
        return wav_path, ogg_path

    # Build test sounds
    tests = []

    # WAV vs OGG comparison at current level
    wav, ogg = make_pair("marimba_0.7_q3", raw_marimba, 0.7, 3)
    tests.append((wav, "Marimba WAV (peak 0.7)"))
    tests.append((ogg, "Marimba OGG q3 (peak 0.7) [CURRENT]"))

    # Higher OGG quality
    _, ogg = make_pair("marimba_0.7_q6", raw_marimba, 0.7, 6)
    tests.append((ogg, "Marimba OGG q6 (peak 0.7)"))

    _, ogg = make_pair("marimba_0.7_q10", raw_marimba, 0.7, 10)
    tests.append((ogg, "Marimba OGG q10 (peak 0.7)"))

    # Original peak level for comparison
    wav, ogg = make_pair("marimba_0.5_q3", raw_marimba, 0.5, 3)
    tests.append((wav, "Marimba WAV (peak 0.5) [ORIGINAL]"))
    tests.append((ogg, "Marimba OGG q3 (peak 0.5) [ORIGINAL]"))

    # Other instruments at current settings
    _, ogg = make_pair("xylo_0.7_q3", raw_xylo, 0.7, 3)
    tests.append((ogg, "Xylophone OGG q3 (peak 0.7)"))

    _, ogg = make_pair("uke_0.7_q3", raw_uke, 0.7, 3)
    tests.append((ogg, "Ukulele OGG q3 (peak 0.7)"))

    _, ogg = make_pair("mbox_0.7_q3", raw_mbox, 0.7, 3)
    tests.append((ogg, "Music Box OGG q3 (peak 0.7)"))

    # Existing repo file
    existing = PROJECT_ROOT / "packs/core-sounds/content/marimba/c.ogg"
    if existing.exists():
        tests.append((str(existing), "Existing repo marimba/c.ogg"))

    # Interactive playback
    print("=" * 60)
    print("  SOUND QUALITY A/B TEST")
    print("  Using pygame mixer (same as Purple Computer)")
    print("=" * 60)
    print()
    for i, (path, label) in enumerate(tests):
        print(f"  {i + 1:2d}) {label}")
    print()
    print("  a) Play ALL in sequence")
    print("  r) Rapid-fire test (3 notes quick, tests overlap)")
    print("  q) Quit")
    print()

    # Preload all sounds
    sounds = []
    for path, label in tests:
        try:
            sounds.append(pygame.mixer.Sound(path))
        except Exception as e:
            print(f"  Could not load {label}: {e}")
            sounds.append(None)

    while True:
        choice = input("\nPick a number (or a/r/q): ").strip().lower()
        if choice == 'q':
            break
        elif choice == 'a':
            for i, (path, label) in enumerate(tests):
                print(f"  Playing {i + 1}: {label}")
                if sounds[i]:
                    sounds[i].play()
                    time.sleep(1.5)
        elif choice == 'r':
            print("  Rapid-fire marimba (3 hits, 0.1s apart):")
            # Use whichever marimba is test #2 (current OGG)
            s = sounds[1]
            if s:
                for _ in range(3):
                    s.play()
                    time.sleep(0.1)
                time.sleep(1)
            # Now same with WAV
            print("  Rapid-fire WAV (3 hits, 0.1s apart):")
            s = sounds[0]
            if s:
                for _ in range(3):
                    s.play()
                    time.sleep(0.1)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(tests):
                    label = tests[idx][1]
                    print(f"  Playing: {label}")
                    if sounds[idx]:
                        sounds[idx].play()
                else:
                    print("  Invalid number")
            except ValueError:
                print("  Invalid input")

    pygame.mixer.quit()
    print(f"\nTest files saved in: {tmp}")


if __name__ == '__main__':
    main()
