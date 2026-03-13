#!/usr/bin/env python3
"""
Test different phonetic respellings for letters that Piper mispronounces.

Generates WAV files for each candidate so you can listen and pick the best one.

Usage:
    python scripts/test_letter_pronunciations.py

Output: /tmp/letter-tests/*.wav
"""

import array
import sys
import wave
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_letter_clips import (
    find_voice_model, _make_synth_config,
    _trim_silence, _apply_fade, _normalize_peak,
)

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
    """Generate a single candidate pronunciation clip."""
    config = _make_synth_config()

    audio_chunks = list(voice.synthesize(text, config))
    if not audio_chunks:
        return False

    first_chunk = audio_chunks[0]
    raw = b''.join(chunk.audio_int16_bytes for chunk in audio_chunks)
    samples = array.array('h')
    samples.frombytes(raw)

    samples = _trim_silence(samples, first_chunk.sample_rate)
    samples = _apply_fade(samples, first_chunk.sample_rate)
    samples = _normalize_peak(samples)

    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(first_chunk.sample_channels)
        wav_file.setsampwidth(first_chunk.sample_width)
        wav_file.setframerate(first_chunk.sample_rate)
        wav_file.writeframes(samples.tobytes())

    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model_path = find_voice_model()
    if model_path is None:
        print("ERROR: Piper voice model not found.")
        return 1

    try:
        from piper import PiperVoice
    except ImportError:
        print("ERROR: piper-tts not installed.")
        return 1

    voice = PiperVoice.load(str(model_path))

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
