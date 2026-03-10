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
import random
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
    print()
    print("  RAPID-FIRE TESTS (overlap stress tests):")
    print("  r1) Marimba OGG rapid-fire (10 hits, 0.05s apart)")
    print("  r2) Marimba WAV rapid-fire (10 hits, 0.05s apart)")
    print("  r3) All instruments OGG rapid-fire")
    print("  r4) Mixed instruments simultaneously (like real usage)")
    print("  r5) Marimba OGG with set_volume(0.5) vs set_volume(0.3)")
    print("  r6) Buffer size test: reinit mixer with larger buffer")
    print("  r7) Channel count test: 8 vs 16 vs 32 channels")
    print()
    print("  q) Quit")
    print()

    # Preload all sounds with set_volume matching current music_room.py
    sounds = []
    for path, label in tests:
        try:
            s = pygame.mixer.Sound(path)
            s.set_volume(0.5)
            sounds.append(s)
        except Exception as e:
            print(f"  Could not load {label}: {e}")
            sounds.append(None)

    # Also make raw (no set_volume) versions for comparison
    sounds_raw = []
    for path, label in tests:
        try:
            sounds_raw.append(pygame.mixer.Sound(path))
        except Exception:
            sounds_raw.append(None)

    # Load all 4 instruments as OGG for mixed test
    inst_oggs = {}
    for name, gen_func in [("marimba", generate_marimba), ("xylophone", generate_xylophone),
                           ("ukulele", generate_ukulele), ("musicbox", generate_music_box)]:
        notes = []
        for note, freq in [("C", 261.63), ("E", 329.63), ("G", 392.00), ("A", 440.00)]:
            raw = gen_func(freq)
            peak = max(abs(s) for s in raw) or 1
            scaled = [int(s / peak * 0.7 * 32767) for s in raw]
            p = str(tmp / f"{name}_{note}.ogg")
            write_wav(p.replace('.ogg', '.wav'), scaled)
            wav_to_ogg(p.replace('.ogg', '.wav'), p, quality=3)
            s = pygame.mixer.Sound(p)
            s.set_volume(0.5)
            notes.append(s)
        inst_oggs[name] = notes

    while True:
        choice = input("\nPick a number (or a/r1-r7/q): ").strip().lower()
        if choice == 'q':
            break
        elif choice == 'a':
            for i, (path, label) in enumerate(tests):
                print(f"  Playing {i + 1}: {label}")
                if sounds[i]:
                    sounds[i].play()
                    time.sleep(1.5)

        elif choice == 'r1':
            print("  Marimba OGG rapid-fire: 10 hits, 0.05s apart (set_volume=0.5)")
            s = sounds[1]
            if s:
                for i in range(10):
                    s.play()
                    time.sleep(0.05)
                time.sleep(1)

        elif choice == 'r2':
            print("  Marimba WAV rapid-fire: 10 hits, 0.05s apart (set_volume=0.5)")
            s = sounds[0]
            if s:
                for i in range(10):
                    s.play()
                    time.sleep(0.05)
                time.sleep(1)

        elif choice == 'r3':
            print("  All instruments OGG rapid-fire (5 hits each, 0.05s apart):")
            for name, notes in inst_oggs.items():
                print(f"    {name}...")
                for i in range(5):
                    notes[i % len(notes)].play()
                    time.sleep(0.05)
                time.sleep(1)

        elif choice == 'r4':
            print("  Mixed instruments, simulating real kid usage:")
            print("  (different notes from different instruments overlapping)")
            all_notes = []
            for notes in inst_oggs.values():
                all_notes.extend(notes)
            for i in range(20):
                random.choice(all_notes).play()
                time.sleep(random.uniform(0.03, 0.15))
            time.sleep(1)

        elif choice == 'r5':
            print("  Comparing set_volume levels on rapid-fire OGG:")
            s = pygame.mixer.Sound(tests[1][0])  # marimba OGG

            for vol in [0.3, 0.5, 0.7, 1.0]:
                s.set_volume(vol)
                print(f"    set_volume({vol}): 8 hits, 0.05s apart")
                for i in range(8):
                    s.play()
                    time.sleep(0.05)
                time.sleep(1.5)

        elif choice == 'r6':
            print("  Testing different mixer buffer sizes:")
            s_path = tests[1][0]  # marimba OGG path

            for buf in [1024, 2048, 4096]:
                pygame.mixer.quit()
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=buf)
                pygame.mixer.set_num_channels(16)
                s = pygame.mixer.Sound(s_path)
                s.set_volume(0.5)
                print(f"    buffer={buf}: 10 hits, 0.05s apart")
                for i in range(10):
                    s.play()
                    time.sleep(0.05)
                time.sleep(1.5)

            # Restore default
            pygame.mixer.quit()
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.set_num_channels(16)
            print("  (mixer restored to buffer=2048)")

        elif choice == 'r7':
            print("  Testing different channel counts:")
            s_path = tests[1][0]

            for ch in [8, 16, 32]:
                pygame.mixer.set_num_channels(ch)
                s = pygame.mixer.Sound(s_path)
                s.set_volume(0.5)
                print(f"    {ch} channels: 10 hits, 0.05s apart")
                for i in range(10):
                    s.play()
                    time.sleep(0.05)
                time.sleep(1.5)

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
