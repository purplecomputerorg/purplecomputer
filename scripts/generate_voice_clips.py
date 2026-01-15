#!/usr/bin/env python3
"""
Generate pre-recorded voice clips for Purple Computer

Uses Piper TTS to generate commonly spoken phrases as WAV files.
These are loaded at runtime instead of generating speech on the fly.

Automatically extracts phrases from the demo script by looking for
text with ! (which triggers speech in Explore mode).
"""

import sys
import wave
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VOICE_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content" / "voice"

# Voice model configuration (same as tts.py)
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166  # p6006

# Static phrases (UI feedback, etc.)
STATIC_PHRASES = [
    "talking on",
    "talking off",
]


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


def phrase_to_filename(phrase: str) -> str:
    """Convert a phrase to a safe filename."""
    return phrase.replace(" ", "_") + ".wav"


def generate_clip(voice, phrase: str, output_path: Path) -> bool:
    """Generate a single voice clip."""
    from piper.config import SynthesisConfig

    config = SynthesisConfig(speaker_id=VOICE_SPEAKER)

    # Pad with pauses to prevent clipping (same as tts.py)
    audio_chunks = list(voice.synthesize(f"... {phrase} ...", config))
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


def extract_demo_phrases() -> list[str]:
    """Extract speakable phrases from the demo script.

    Looks for TypeText actions containing ! (speech trigger).
    Evaluates the expression and converts to speakable text.
    """
    # Add project root to path for imports
    sys.path.insert(0, str(PROJECT_ROOT))

    from purple_tui.demo.default_script import DEMO_SCRIPT
    from purple_tui.demo.script import TypeText
    from purple_tui.modes.explore_mode import SimpleEvaluator

    evaluator = SimpleEvaluator()
    phrases = []

    for action in DEMO_SCRIPT:
        if not isinstance(action, TypeText):
            continue

        text = action.text

        # Check for ! anywhere (speech trigger)
        if '!' not in text:
            continue

        # Strip ! and clean up
        eval_text = text.replace('!', '').strip()
        if not eval_text:
            continue

        # Evaluate to get the result
        result = evaluator.evaluate(eval_text)

        # Convert to speakable text
        speakable = evaluator._make_speakable(eval_text, result)

        if speakable and speakable not in phrases:
            phrases.append(speakable)
            print(f"  Found: '{eval_text}' -> '{speakable}'")

    return phrases


def main():
    """Generate all voice clips."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate pre-recorded voice clips")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Regenerate all clips even if they exist")
    args = parser.parse_args()

    print("Scanning demo script for speech phrases...")
    demo_phrases = extract_demo_phrases()

    all_phrases = STATIC_PHRASES + demo_phrases

    if not all_phrases:
        print("No phrases to generate.")
        return 0

    # Check which clips need generating
    VOICE_DIR.mkdir(parents=True, exist_ok=True)

    to_generate = []
    for phrase in all_phrases:
        filename = phrase_to_filename(phrase)
        output_path = VOICE_DIR / filename
        if args.force or not output_path.exists():
            to_generate.append((phrase, output_path))

    if not to_generate:
        print("All voice clips already exist. Use --force to regenerate.")
        return 0

    print()
    print(f"Generating {len(to_generate)} voice clips...")
    print()

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

    # Generate clips
    print("Generating voice clips:")
    for phrase, output_path in to_generate:
        if generate_clip(voice, phrase, output_path):
            print(f"  Created {output_path.name}")
        else:
            print(f"  FAILED: {output_path.name}")

    print()
    print(f"Done! Voice clips saved to {VOICE_DIR}")
    return 0


if __name__ == "__main__":
    exit(main())
