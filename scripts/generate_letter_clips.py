#!/usr/bin/env python3
"""
Generate pre-recorded letter name clips for Music Mode's Letters sub-mode.

Speaks each letter (A-Z) and digit (0-9) in Kokoro, Studio's room voice
(scripts/studio_bundle.py fetches it), on the same espeak-ng phonemes,
respellings and leveling as Purple's live Piper speech.

Output directory: packs/core-sounds/content/letters/

Usage:
    python scripts/generate_letter_clips.py
    python scripts/generate_letter_clips.py --force   # regenerate all
"""

import array
import json
import string
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
LETTERS_DIR = PROJECT_ROOT / "packs" / "core-sounds" / "content" / "letters"

sys.path.insert(0, str(PROJECT_ROOT))
from purple_tui.tts import _prepare_text, _write_wav, postprocess_samples  # noqa: E402
from scripts.studio_bundle import KOKORO, OUT, fetch_kokoro  # noqa: E402

KOKORO_DIR = OUT.parent / "voice" / "kokoro"
STYLE = 256


class Kokoro:
    def __init__(self):
        import numpy as np
        import onnxruntime
        from piper.phonemize_espeak import EspeakPhonemizer
        fetch_kokoro()
        self.vocab = json.loads((KOKORO_DIR / "kokoro.json").read_text())["vocab"]
        self.styles = np.fromfile(KOKORO_DIR / f"{KOKORO['voice']}.bin", dtype="<f4").reshape(-1, STYLE)
        self.session = onnxruntime.InferenceSession(str(KOKORO_DIR / KOKORO["model"]))
        self.espeak = EspeakPhonemizer()

    def speak_to_file(self, text: str, wav_path: Path) -> bool:
        import numpy as np
        ids = [self.vocab[p] for s in self.espeak.phonemize("en-us", _prepare_text(text)) for p in s if p in self.vocab]
        if not ids:
            return False
        audio = self.session.run(None, {
            "tokens": np.array([[0, *ids, 0]], dtype=np.int64),
            "style": self.styles[len(ids)][None],
            "speed": np.array([1.0], dtype=np.float32),
        })[0].reshape(-1)
        samples = array.array("h", (np.clip(audio / max(float(np.abs(audio).max()), 1e-8), -1, 1) * 32767).astype(np.int16).tobytes())
        _write_wav(str(wav_path), postprocess_samples(samples, KOKORO["rate"]), KOKORO["rate"])
        return True


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
        voice = Kokoro()
    except (ImportError, OSError) as e:
        print(f"ERROR: {e}")
        return 1
    print(f"Using voice model: {KOKORO['model']} ({KOKORO['voice']})")
    print()

    print(f"Generating {len(to_generate)} clips...")
    print()
    for letter, output_path in to_generate:
        if voice.speak_to_file(letter, output_path):
            print(f"  {letter} -> {output_path.name}")
        else:
            print(f"  FAILED: {letter}")

    print()
    print(f"Done! Letter clips saved to {LETTERS_DIR}")
    return 0


if __name__ == "__main__":
    exit(main())
