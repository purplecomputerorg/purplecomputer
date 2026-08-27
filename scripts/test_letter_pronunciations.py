#!/usr/bin/env python3
"""
Test different phonetic respellings for letters that Piper mispronounces.

Generates WAV files for each candidate so you can listen and pick the best one.

Usage:
    python scripts/test_letter_pronunciations.py

Output: /tmp/letter-tests/*.wav
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from purple_tui.tts import load_voice, synthesize_to_file  # noqa: E402

OUTPUT_DIR = Path("/tmp/letter-tests")

# Candidates to try for each problem letter.
# The goal: find a short text that Piper reads as the letter name.
CANDIDATES = {
    "A": [
        "ay",           # current (sounds like "I")
        "ay.",          # with period
        "ehh",          # short "a" sound
        "aye",          # alternative spelling
        "hey",          # might drop the h?
        "a.",           # just the letter
        "the letter a", # carrier phrase
        "say a",        # carrier phrase, clip start
        "aay",          # elongated
        "eigh",         # like "eight" without t
        "ae",           # dipthong
    ],
    "F": [
        "ef",           # current (sounds like "e-f-f")
        "ef.",          # with period
        "eff",          # double f (comment says this spells out)
        "ehf",          # alternative
        "the letter f", # carrier phrase
        "say f",        # carrier phrase
        "eph",          # ph instead of ff
        "ehff",         # elongated
    ],
}


def generate_candidate(voice, text: str, output_path: Path) -> bool:
    return synthesize_to_file(voice, text, str(output_path))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        voice = load_voice()
    except (ImportError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return 1

    for letter, candidates in CANDIDATES.items():
        print(f"\n=== Letter {letter} ===")
        for i, text in enumerate(candidates):
            safe_name = text.replace(" ", "_").replace(".", "dot")
            filename = f"{letter}_{i:02d}_{safe_name}.wav"
            output_path = OUTPUT_DIR / filename

            if generate_candidate(voice, text, output_path):
                print(f"  {i:2d}. {text!r:25s} -> {filename}")
            else:
                print(f"  {i:2d}. {text!r:25s} -> FAILED")

    print(f"\nAll clips saved to {OUTPUT_DIR}/")
    print("Listen to them and pick the best pronunciation for each letter.")
    return 0


if __name__ == "__main__":
    exit(main())
