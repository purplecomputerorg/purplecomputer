#!/usr/bin/env python3
"""
Generate pre-recorded voice clips for Purple Computer

Uses Piper TTS to generate commonly spoken phrases as WAV files.
These are loaded at runtime instead of generating speech on the fly.

Automatically extracts phrases from the demo script by looking for
text with ! (which triggers speech in Play mode).
"""

import os
import sys
import wave
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VOICE_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content" / "voice"
sys.path.insert(0, str(PROJECT_ROOT))

# Voice model configuration (same as tts.py)
VOICE_MODEL = "en_US-libritts-high"
VOICE_SPEAKER = 166  # p6006
_SYNTH_PARAMS = {
    "noise_scale": 0.3,
    "noise_w": 0.3,
    "noise_w_scale": 0.3,
    "length_scale": 1.0,
}

# Pronunciation overrides (same as tts.py)
PRONUNCIATION_MAP = {
    "dinos": "dyenoze",
}

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
    """Convert a phrase to the filename the app looks the clip up under."""
    from purple_tui.tts import voice_clip_filename
    return voice_clip_filename(phrase)


def _fix_pronunciation(text: str) -> str:
    """Replace words Piper mispronounces with phonetic respellings."""
    import re
    for word, replacement in PRONUNCIATION_MAP.items():
        text = re.sub(rf'\b{word}\b', replacement, text, flags=re.IGNORECASE)
    return text


def _make_synth_config():
    """Build a SynthesisConfig using only parameters the installed version accepts."""
    from piper.config import SynthesisConfig
    import dataclasses
    valid = {f.name for f in dataclasses.fields(SynthesisConfig)}
    kwargs = {k: v for k, v in _SYNTH_PARAMS.items() if k in valid}
    kwargs["speaker_id"] = VOICE_SPEAKER
    return SynthesisConfig(**kwargs)


def _trim_silence(samples, sample_rate, threshold_db=-40.0):
    """Trim leading and trailing silence using windowed RMS."""
    if not samples:
        return samples
    threshold = 32767 * (10 ** (threshold_db / 20.0))
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


def _apply_fade(samples, sample_rate, fade_ms=10.0):
    """Apply fade-in and fade-out to eliminate clicks."""
    import array as _array
    if not samples:
        return samples
    fade_len = min(int(sample_rate * fade_ms / 1000.0), len(samples) // 2)
    if fade_len < 1:
        return samples
    result = _array.array('h', samples)
    for i in range(fade_len):
        scale = i / fade_len
        result[i] = int(result[i] * scale)
        result[-(i + 1)] = int(result[-(i + 1)] * scale)
    return result


def generate_clip(voice, phrase: str, output_path: Path) -> bool:
    """Generate a single voice clip with deterministic parameters."""
    import array

    config = _make_synth_config()

    # Fix pronunciation before synthesis
    synth_text = _fix_pronunciation(phrase)

    audio_chunks = list(voice.synthesize(synth_text, config))
    if not audio_chunks:
        return False

    first_chunk = audio_chunks[0]

    # Collect all raw samples for post-processing
    raw = b''.join(chunk.audio_int16_bytes for chunk in audio_chunks)
    samples = array.array('h')
    samples.frombytes(raw)

    # Trim, fade, normalize
    samples = _trim_silence(samples, first_chunk.sample_rate)
    samples = _apply_fade(samples, first_chunk.sample_rate)

    if samples:
        peak = max(abs(s) for s in samples)
        if peak > 0:
            target = 32767 * (10 ** (-3.0 / 20.0))
            scale = target / peak
            normalized = array.array('h')
            for s in samples:
                normalized.append(max(-32768, min(32767, int(s * scale))))
            samples = normalized

    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(first_chunk.sample_channels)
        wav_file.setsampwidth(first_chunk.sample_width)
        wav_file.setframerate(first_chunk.sample_rate)
        wav_file.writeframes(samples.tobytes())

    return True


def _stub_ui_modules():
    """The evaluator lives in purple_tui.play_eval with no UI dependencies now; nothing to stub."""
def _collect_all_actions() -> list:
    """Collect all demo actions from composition segments and fallback script."""
    import importlib
    import json

    actions = []

    # Scan the active composition (PURPLE_DEMO_COMPOSITION selects ad.json etc.)
    composition = os.environ.get("PURPLE_DEMO_COMPOSITION", "demo.json")
    demo_json = PROJECT_ROOT / "purple_tui" / "demo" / composition
    if demo_json.exists():
        entries = json.loads(demo_json.read_text())
        for entry in entries:
            name = entry["segment"]
            mod = importlib.import_module(
                f"purple_tui.demo.segments.{name}"
            )
            actions.extend(mod.SEGMENT)

    # Also scan the default script as fallback
    from purple_tui.demo.default_script import DEMO_SCRIPT
    actions.extend(DEMO_SCRIPT)

    return actions


def extract_demo_phrases() -> list[str]:
    """Extract speakable phrases from demo segments and default script.

    Uses the Play room's own speech-trigger and speakable logic, so a
    `repeat N ...` line yields the per-item phrases the room looks up.
    Demo mode disables live TTS, so every spoken line needs a matching
    pre-generated clip or it records silent.
    """
    _stub_ui_modules()

    from purple_tui.demo.script import TypeText
    from purple_tui.play_eval import (
        SimpleEvaluator, parse_speech_trigger, speakables_for,
    )

    evaluator = SimpleEvaluator()
    phrases = []

    for action in _collect_all_actions():
        if not isinstance(action, TypeText):
            continue

        speaks, eval_text = parse_speech_trigger(action.text)
        if not speaks or not eval_text:
            continue

        for speakable in speakables_for(evaluator, eval_text):
            if speakable not in phrases:
                phrases.append(speakable)
                print(f"  Found: '{eval_text}' -> '{speakable}'")

    return phrases


def main():
    """Generate all voice clips."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate pre-recorded voice clips")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Regenerate all clips even if they exist")
    parser.add_argument("--variants", type=int, default=0, metavar="N",
                        help="Generate N variants of each new clip (for auditioning)")
    args = parser.parse_args()

    print("Scanning demo segments for speech phrases...")
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

    if not to_generate and args.variants <= 0:
        print("All voice clips already exist. Use --force to regenerate.")
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

    # Generate standard clips
    if to_generate:
        print(f"Generating {len(to_generate)} voice clips...")
        print()
        for phrase, output_path in to_generate:
            if generate_clip(voice, phrase, output_path):
                print(f"  Created {output_path.name}")
            else:
                print(f"  FAILED: {output_path.name}")
        print()

    # Generate variants (for auditioning)
    if args.variants > 0:
        # Generate variants for new demo phrases only (not static UI phrases)
        variant_phrases = demo_phrases if demo_phrases else all_phrases
        print(f"Generating {args.variants} variants for {len(variant_phrases)} phrases...")
        print()
        for phrase in variant_phrases:
            base = phrase_to_filename(phrase).removesuffix(".wav")
            for i in range(1, args.variants + 1):
                output_path = VOICE_DIR / f"{base}_v{i}.wav"
                if generate_clip(voice, phrase, output_path):
                    print(f"  Created {output_path.name}")
                else:
                    print(f"  FAILED: {output_path.name}")
        print()
        print("Listen to each variant and copy the best one:")
        for phrase in variant_phrases:
            final_name = phrase_to_filename(phrase)
            base = final_name.removesuffix(".wav")
            print(f"  cp {VOICE_DIR}/{base}_v?.wav {VOICE_DIR}/{final_name}")

    print()
    print(f"Done! Voice clips saved to {VOICE_DIR}")
    return 0


if __name__ == "__main__":
    exit(main())
