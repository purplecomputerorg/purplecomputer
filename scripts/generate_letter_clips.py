#!/usr/bin/env python3
"""
Generate pre-recorded letter name clips for Play Mode's Letters sub-mode.

Uses Piper TTS to generate a spoken clip of each letter (A-Z).
These are loaded at runtime by PlayGrid instead of using live TTS.

Output directory: packs/core-sounds/content/letters/

Usage:
    python scripts/generate_letter_clips.py
    python scripts/generate_letter_clips.py --force   # regenerate all
"""

import string
import sys
import wave
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
LETTERS_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content" / "letters"

# Reuse voice config from generate_voice_clips.py
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166  # p6006


def get_voice_search_paths() -> list[Path]:
    """Get list of paths to search for voice model."""
    import os
    paths = [
        Path.home() / ".local" / "share" / "piper-voices",
        Path.home() / ".cache" / "piper",
        Path("/opt/purple/piper-voices"),
        Path("/opt/piper"),
    ]
    try:
        import pwd
        real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        paths.insert(0, real_home / ".local" / "share" / "piper-voices")
    except (ImportError, KeyError):
        pass
    return paths


def find_voice_model() -> Path | None:
    """Find the Piper voice model."""
    for base_path in get_voice_search_paths():
        candidate = base_path / f"{VOICE_MODEL}.onnx"
        if candidate.exists():
            return candidate
    return None


def generate_letter_clip(voice, letter: str, output_path: Path) -> bool:
    """Generate a single letter name clip."""
    from piper.config import SynthesisConfig

    config = SynthesisConfig(speaker_id=VOICE_SPEAKER)

    # Pad with pauses to prevent clipping (same as tts.py)
    audio_chunks = list(voice.synthesize(f"... {letter} ...", config))
    if not audio_chunks:
        return False

    first_chunk = audio_chunks[0]
    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(first_chunk.sample_channels)
        wav_file.setsampwidth(first_chunk.sample_width)
        wav_file.setframerate(first_chunk.sample_rate)
        for chunk in audio_chunks:
            wav_file.writeframes(chunk.audio_int16_bytes)

    return True


def main():
    """Generate letter name clips for A-Z."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate letter name clips for Play Mode")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Regenerate all clips even if they exist")
    args = parser.parse_args()

    LETTERS_DIR.mkdir(parents=True, exist_ok=True)

    # Find which letters need generating
    to_generate = []
    for letter in string.ascii_uppercase:
        output_path = LETTERS_DIR / f"{letter.lower()}.wav"
        if args.force or not output_path.exists():
            to_generate.append((letter, output_path))

    if not to_generate:
        print("All letter clips already exist. Use --force to regenerate.")
        return 0

    # Find voice model
    model_path = find_voice_model()
    if model_path is None:
        print("ERROR: Piper voice model not found.")
        print("Searched in:")
        for path in get_voice_search_paths():
            print(f"  {path / f'{VOICE_MODEL}.onnx'}")
        print()
        print("Please install the voice model first.")
        return 1

    print(f"Using voice model: {model_path}")
    print()

    # Load Piper
    try:
        from piper import PiperVoice
    except ImportError:
        print("ERROR: piper-tts not installed.")
        print("Install with: pip install piper-tts")
        return 1

    voice = PiperVoice.load(str(model_path))

    print(f"Generating {len(to_generate)} letter clips...")
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
