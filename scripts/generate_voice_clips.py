#!/usr/bin/env python3
"""
Generate pre-recorded voice clips for Purple Computer

Uses Piper TTS to generate commonly spoken phrases as WAV files.
These are loaded at runtime instead of generating speech on the fly.
"""

import wave
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VOICE_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content" / "voice"

# Voice model configuration (same as tts.py)
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166  # p6006

# Phrases to pre-generate
PHRASES = [
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


def main():
    """Generate all voice clips."""
    print("Generating Purple Computer voice clips...")
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

    # Create output directory
    VOICE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate clips
    print("Generating voice clips:")
    for phrase in PHRASES:
        filename = phrase_to_filename(phrase)
        output_path = VOICE_DIR / filename

        if generate_clip(voice, phrase, output_path):
            print(f"  Created {filename}")
        else:
            print(f"  FAILED: {filename}")

    print()
    print(f"Done! Voice clips saved to {VOICE_DIR}")
    return 0


if __name__ == "__main__":
    exit(main())
