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
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
VOICE_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content" / "voice"
sys.path.insert(0, str(PROJECT_ROOT))

from purple_tui.tts import (  # noqa: E402
    _fix_pronunciation, find_voice_model, load_voice, synthesize_to_file, voice_clip_filename,
)

# Static phrases (UI feedback, etc.)
STATIC_PHRASES = [
    "talking on",
    "talking off",
]


def generate_clip(voice, phrase: str, output_path: Path) -> bool:
    return synthesize_to_file(voice, _fix_pronunciation(phrase), str(output_path))


def _stub_ui_modules():
    """Stub out textual/rich/pygame so we can import SimpleEvaluator without UI deps.

    SimpleEvaluator is pure computation (no textual dependency), but it lives
    in play_room.py which imports textual at module level for the UI classes.
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

    import importlib.abc
    import importlib.machinery

    class _StubLoader(importlib.abc.Loader):
        def create_module(self, spec):
            return _StubModule(spec.name)

        def exec_module(self, module):
            pass

    class _StubFinder(importlib.abc.MetaPathFinder):
        """Stub any submodule of these UI packages on demand.

        Enumerating submodules by hand kept breaking whenever a new one
        (e.g. rich.markup) got imported, so match by top-level package.
        """
        _purple_stub = True
        prefixes = ("textual", "rich")

        def find_spec(self, name, path, target=None):
            if name.split(".")[0] in self.prefixes:
                return importlib.machinery.ModuleSpec(name, _StubLoader())
            return None

    if not any(getattr(f, "_purple_stub", False) for f in sys.meta_path):
        sys.meta_path.insert(0, _StubFinder())

    if "pygame" not in sys.modules:
        sys.modules["pygame"] = _PygameModule("pygame")
    if "pygame.mixer" not in sys.modules:
        sys.modules["pygame.mixer"] = _PygameMixer


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
    from purple_tui.rooms.play_room import (
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
        filename = voice_clip_filename(phrase)
        output_path = VOICE_DIR / filename
        if args.force or not output_path.exists():
            to_generate.append((phrase, output_path))

    if not to_generate and args.variants <= 0:
        print("All voice clips already exist. Use --force to regenerate.")
        return 0

    try:
        voice = load_voice()
    except (ImportError, FileNotFoundError) as e:
        print(f"ERROR: {e}")
        return 1
    print(f"Using voice model: {find_voice_model()}")
    print()

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
            base = voice_clip_filename(phrase).removesuffix(".wav")
            for i in range(1, args.variants + 1):
                output_path = VOICE_DIR / f"{base}_v{i}.wav"
                if generate_clip(voice, phrase, output_path):
                    print(f"  Created {output_path.name}")
                else:
                    print(f"  FAILED: {output_path.name}")
        print()
        print("Listen to each variant and copy the best one:")
        for phrase in variant_phrases:
            final_name = voice_clip_filename(phrase)
            base = final_name.removesuffix(".wav")
            print(f"  cp {VOICE_DIR}/{base}_v?.wav {VOICE_DIR}/{final_name}")

    print()
    print(f"Done! Voice clips saved to {VOICE_DIR}")
    return 0


if __name__ == "__main__":
    exit(main())
