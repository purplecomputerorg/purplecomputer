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
import wave
import array
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Voice config (same as tts.py)
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166
_SYNTH_PARAMS = {
    "noise_scale": 0.3,
    "noise_w": 0.3,
    "noise_w_scale": 0.3,
    "length_scale": 1.0,
}

LETTER_PRONUNCIATION = {
    "A": "ay", "B": "bee", "C": "see", "D": "dee", "E": "ee",
    "F": "ef", "G": "jee", "H": "aitch", "I": "eye", "J": "jay",
    "K": "kay", "L": "el", "M": "em", "N": "en", "O": "oh",
    "P": "pee", "Q": "cue", "R": "ar", "S": "es", "T": "tee",
    "U": "you", "V": "vee", "W": "double you", "X": "ex",
    "Y": "why", "Z": "zee",
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# Test phrases
TEST_PHRASES = [
    "A", "B", "C", "D", "E",
    "cat",
    "purple",
    "seven",
    "2 plus 2 equals 4",
]


def get_voice_search_paths() -> list[Path]:
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
    for base_path in get_voice_search_paths():
        candidate = base_path / f"{VOICE_MODEL}.onnx"
        if candidate.exists():
            return candidate
    return None


def prepare_text(text: str) -> str:
    """Same logic as tts._prepare_text()."""
    stripped = text.strip()
    if len(stripped) == 1 and stripped.upper() in LETTER_PRONUNCIATION:
        stripped = LETTER_PRONUNCIATION[stripped.upper()]
    if len(stripped) < 4:
        stripped = stripped + "."
    return stripped


def trim_silence(samples: array.array, sample_rate: int) -> array.array:
    if not samples:
        return samples
    threshold = 32767 * (10 ** (-40.0 / 20.0))
    threshold_sq = threshold * threshold
    window = max(1, int(sample_rate * 0.005))

    def _rms_above(idx):
        end = min(idx + window, len(samples))
        if end <= idx:
            return False
        return (sum(s * s for s in samples[idx:end]) / (end - idx)) > threshold_sq

    start = 0
    for i in range(0, len(samples) - window, window):
        if _rms_above(i):
            start = max(0, i - int(sample_rate * 0.01))
            break
    end = len(samples)
    for i in range(len(samples) - window, -1, -window):
        if _rms_above(i):
            end = min(len(samples), i + window + int(sample_rate * 0.02))
            break
    return samples[start:end]


def apply_fade(samples: array.array, sample_rate: int, fade_ms: float = 10.0) -> array.array:
    if not samples:
        return samples
    fade_len = min(int(sample_rate * fade_ms / 1000.0), len(samples) // 2)
    if fade_len < 1:
        return samples
    result = array.array('h', samples)
    for i in range(fade_len):
        scale = i / fade_len
        result[i] = int(result[i] * scale)
        result[-(i + 1)] = int(result[-(i + 1)] * scale)
    return result


def normalize_peak(samples: array.array) -> array.array:
    if not samples:
        return samples
    peak = max(abs(s) for s in samples)
    if peak == 0:
        return samples
    target = 32767 * (10 ** (-3.0 / 20.0))
    scale = target / peak
    result = array.array('h')
    for s in samples:
        result.append(max(-32768, min(32767, int(s * scale))))
    return result


def _make_synth_config():
    from piper.config import SynthesisConfig
    import dataclasses
    valid = {f.name for f in dataclasses.fields(SynthesisConfig)}
    kwargs = {k: v for k, v in _SYNTH_PARAMS.items() if k in valid}
    kwargs["speaker_id"] = VOICE_SPEAKER
    return SynthesisConfig(**kwargs)


def synthesize(voice, text: str, output_path: Path) -> bool:
    """Synthesize text to WAV with deterministic parameters and post-processing."""
    config = _make_synth_config()

    prepared = prepare_text(text)
    audio_chunks = list(voice.synthesize(prepared, config))
    if not audio_chunks:
        return False

    first_chunk = audio_chunks[0]
    raw = b''.join(chunk.audio_int16_bytes for chunk in audio_chunks)
    samples = array.array('h')
    samples.frombytes(raw)

    samples = trim_silence(samples, first_chunk.sample_rate)
    samples = apply_fade(samples, first_chunk.sample_rate)
    samples = normalize_peak(samples)

    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(first_chunk.sample_channels)
        wav_file.setsampwidth(first_chunk.sample_width)
        wav_file.setframerate(first_chunk.sample_rate)
        wav_file.writeframes(samples.tobytes())

    return True


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

    model_path = find_voice_model()
    if model_path is None:
        print("ERROR: Piper voice model not found.")
        print("Searched in:")
        for path in get_voice_search_paths():
            print(f"  {path / f'{VOICE_MODEL}.onnx'}")
        return 1

    print(f"Voice model: {model_path}")
    print(f"Output dir:  {output_dir}")
    print()

    try:
        from piper import PiperVoice
    except ImportError:
        print("ERROR: piper-tts not installed.")
        return 1

    voice = PiperVoice.load(str(model_path))

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
