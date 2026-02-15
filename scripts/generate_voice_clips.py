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
    """Convert a phrase to a safe filename."""
    return phrase.replace(" ", "_") + ".wav"


def _fix_pronunciation(text: str) -> str:
    """Replace words Piper mispronounces with phonetic respellings."""
    import re
    for word, replacement in PRONUNCIATION_MAP.items():
        text = re.sub(rf'\b{word}\b', replacement, text, flags=re.IGNORECASE)
    return text


def generate_clip(voice, phrase: str, output_path: Path) -> bool:
    """Generate a single voice clip."""
    from piper.config import SynthesisConfig

    config = SynthesisConfig(speaker_id=VOICE_SPEAKER)

    # Fix pronunciation before synthesis
    synth_text = _fix_pronunciation(phrase)

    # Pad with pauses to prevent clipping (same as tts.py)
    audio_chunks = list(voice.synthesize(f"... {synth_text} ...", config))
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


def _stub_ui_modules():
    """Stub out textual/rich/pygame so we can import SimpleEvaluator without UI deps.

    SimpleEvaluator is pure computation (no textual dependency), but it lives
    in explore_mode.py which imports textual at module level for the UI classes.
    The modes/__init__.py also imports all modes, pulling in their dependencies.
    """
    import types

    class _StubMeta(type):
        """Metaclass that allows _StubClass to return itself for class-level attribute access."""
        def __getattr__(cls, name):
            return cls

    class _StubClass(metaclass=_StubMeta):
        """Dummy class that accepts any args and returns itself for chaining."""
        def __init__(self, *args, **kwargs):
            pass

        def __init_subclass__(cls, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, name):
            return _StubClass()

    class _PygameError(Exception):
        """Stub for pygame.error so it can be caught."""
        pass

    class _PygameMixer:
        """Stub for pygame.mixer module."""
        @staticmethod
        def init(*args, **kwargs):
            raise _PygameError("stubbed")

        @staticmethod
        def get_init():
            return None

        @staticmethod
        def set_num_channels(*args):
            pass

        Sound = _StubClass
        Channel = _StubClass

    class _PygameModule(types.ModuleType):
        """Stub for pygame with working error exception."""
        error = _PygameError
        mixer = _PygameMixer

        def __getattr__(self, name):
            return _StubClass

    class _StubModule(types.ModuleType):
        """Module that returns a dummy class for any attribute lookup."""
        def __getattr__(self, name):
            return _StubClass

    stub_modules = [
        # textual
        'textual', 'textual.widgets', 'textual.widget', 'textual.containers',
        'textual.app', 'textual.events', 'textual.message', 'textual.strip',
        'textual.reactive', 'textual.css', 'textual.css.query',
        'textual.binding', 'textual.theme', 'textual.screen',
        # rich
        'rich', 'rich.segment', 'rich.style', 'rich.text', 'rich.highlighter',
        # pygame
        'pygame', 'pygame.mixer',
    ]

    for mod_name in stub_modules:
        if mod_name not in sys.modules:
            if mod_name == 'pygame':
                sys.modules[mod_name] = _PygameModule(mod_name)
            elif mod_name == 'pygame.mixer':
                sys.modules[mod_name] = _PygameMixer
            else:
                sys.modules[mod_name] = _StubModule(mod_name)


def _collect_all_actions() -> list:
    """Collect all demo actions from composition segments and fallback script."""
    sys.path.insert(0, str(PROJECT_ROOT))

    from purple_tui.demo.script import TypeText
    import importlib
    import json

    actions = []

    # Try composition segments first (demo.json)
    demo_json = PROJECT_ROOT / "purple_tui" / "demo" / "demo.json"
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

    Looks for TypeText actions containing ! (speech trigger).
    Evaluates the expression and converts to speakable text.
    """
    sys.path.insert(0, str(PROJECT_ROOT))
    _stub_ui_modules()

    from purple_tui.demo.script import TypeText
    from purple_tui.modes.explore_mode import SimpleEvaluator

    evaluator = SimpleEvaluator()
    phrases = []

    for action in _collect_all_actions():
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
