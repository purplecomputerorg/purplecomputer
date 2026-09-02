#!/usr/bin/env python3
"""
Debug script to verify deterministic TTS output.

Generates WAV files for a set of test phrases, then repeats and confirms
the second run produces byte-identical files.

Usage:
    python scripts/debug_tts.py
    python scripts/debug_tts.py --output-dir /tmp/tts-debug
"""

import hashlib
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))
from purple_tui.tts import _prepare_text, find_voice_model, load_voice, synthesize_to_file  # noqa: E402

# Test phrases
TEST_PHRASES = [
    "A", "B", "C", "D", "E",
    "cat",
    "purple",
    "seven",
    "2 plus 2 equals 4",
]


def synthesize(voice, text: str, output_path: Path) -> bool:
    return synthesize_to_file(voice, _prepare_text(text), str(output_path))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_filename(text: str) -> str:
    return text.lower().replace(" ", "_")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Debug: verify deterministic TTS")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: temp dir)")
    args = parser.parse_args()

    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="tts-debug-"))
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        voice = load_voice()
    except (ImportError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return 1
    print(f"Voice model: {find_voice_model()}")
    print(f"Output dir:  {output_dir}")
    print()

    # Run 1: generate all test phrases
    print("=== Run 1: Generating WAV files ===")
    run1_hashes = {}
    for phrase in TEST_PHRASES:
        name = safe_filename(phrase)
        out = output_dir / f"{name}_run1.wav"
        if synthesize(voice, phrase, out):
            h = file_hash(out)
            run1_hashes[phrase] = h
            print(f"  {phrase:30s} -> {out.name}  sha256={h[:16]}...")
        else:
            print(f"  FAILED: {phrase}")
            return 1

    print()

    # Run 2: regenerate and compare
    print("=== Run 2: Verifying determinism ===")
    all_match = True
    for phrase in TEST_PHRASES:
        name = safe_filename(phrase)
        out = output_dir / f"{name}_run2.wav"
        if synthesize(voice, phrase, out):
            h = file_hash(out)
            match = h == run1_hashes[phrase]
            status = "MATCH" if match else "MISMATCH"
            print(f"  {phrase:30s} -> {status}  sha256={h[:16]}...")
            if not match:
                all_match = False
        else:
            print(f"  FAILED: {phrase}")
            all_match = False

    print()
    if all_match:
        print("All files are byte-identical across runs. TTS is deterministic.")
        return 0
    else:
        print("SOME FILES DIFFER. TTS is NOT deterministic.")
        return 1


if __name__ == "__main__":
    exit(main())
