#!/usr/bin/env python3
"""
Generate pre-recorded letter name clips for Music Mode's Letters sub-mode.

Uses Piper TTS to generate a spoken clip of each letter (A-Z).
These are loaded at runtime by MusicGrid instead of using live TTS.

Same synthesis and leveling as live speech (purple_tui.tts), so a
clip and a live letter sound identical.

Output directory: packs/core-sounds/content/letters/

Usage:
    python scripts/generate_letter_clips.py
    python scripts/generate_letter_clips.py --force   # regenerate all
"""

import string
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
LETTERS_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content" / "letters"

sys.path.insert(0, str(PROJECT_ROOT))
from purple_tui.tts import _prepare_text, find_voice_model, load_voice, synthesize_to_file  # noqa: E402


def generate_letter_clip(voice, letter: str, output_path: Path) -> bool:
    return synthesize_to_file(voice, _prepare_text(letter), str(output_path))


def main():
    """Generate letter (A-Z) and number (0-9) name clips."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate letter and number name clips for Music Mode")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Regenerate all clips even if they exist")
    args = parser.parse_args()

    LETTERS_DIR.mkdir(parents=True, exist_ok=True)

    # Find which clips need generating (letters A-Z + digits 0-9)
    all_keys = list(string.ascii_uppercase) + list(string.digits)
    to_generate = []
    for key in all_keys:
        output_path = LETTERS_DIR / f"{key.lower()}.wav"
        if args.force or not output_path.exists():
            to_generate.append((key, output_path))

    if not to_generate:
        print("All letter clips already exist. Use --force to regenerate.")
        return 0

    try:
        voice = load_voice()
    except (ImportError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return 1
    print(f"Using voice model: {find_voice_model()}")
    print()

    print(f"Generating {len(to_generate)} clips...")
    print()
    for letter, output_path in to_generate:
        if generate_letter_clip(voice, letter, output_path):
            print(f"  {letter} -> {output_path.name}")
        else:
            print(f"  FAILED: {letter}")

    print()
    print(f"Done! Letter clips saved to {LETTERS_DIR}")
    return 0


if __name__ == "__main__":
    exit(main())
