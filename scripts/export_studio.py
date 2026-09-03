#!/usr/bin/env python3
"""Export the Purple facts Studio depends on, so its TypeScript never carries a hand copy.

Writes studio/src/purple/export.json (constants the app imports) and
studio/tests/golden.json (reference renders the synth port is checked against).
tests/test_studio_export.py fails when either file is stale.

Usage: just studio-fixtures
"""

import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from purple_tui import synth  # noqa: E402
from purple_tui.art_config import CANVAS_HEIGHT, CANVAS_WIDTH  # noqa: E402
from purple_tui.constants import VIEWPORT_HEIGHT, VIEWPORT_WIDTH  # noqa: E402
from purple_tui.music_constants import (  # noqa: E402
    DEFAULT_ROOT_INDEX, FRIENDLY_KEYS, GRID_KEYS, INSTRUMENTS, pitch_filename, pitch_for,
)
from purple_tui.rooms.art_room import (  # noqa: E402
    APP_BG_DARK, DEFAULT_BG_DARK, DEFAULT_BG_LIGHT, GUTTER_BG_DARK_A, GUTTER_BG_DARK_B, KEY_COLORS,
)
from purple_tui.rooms.music_room import _SPEAKABLE_KEYS  # noqa: E402
from purple_tui.tts import voice_clip_filename  # noqa: E402
from scripts.generate_sounds import reachable_pitches  # noqa: E402
from tools.photo_to_art import CELL_ASPECT, fit_to_canvas  # noqa: E402

EXPORT_PATH = ROOT / "studio" / "src" / "purple" / "export.json"
GOLDEN_PATH = ROOT / "studio" / "tests" / "golden.json"

FIT_SIZES = [(4032, 3024), (3024, 4032), (1000, 1000), (1920, 1080), (100, 2000), (2000, 100), (1, 1), (132, 50), (264, 50), (50, 25)]
CLIP_EXAMPLES = ["  Hello There ", "It's Purple Computer", "hi", "5 times 5 ducks equals 25 ducks"]
# Golden renders: two pitches at the defaults, then one short varied render per instrument.
GOLDEN_FREQS = [261.63, 880.0]
GOLDEN_VARIED = {
    "marimba": {"duration": 0.3, "wood": 0.9, "tube": 0.4, "mallet": 0.5, "attack_ms": 20},
    "ukulele": {"duration": 0.3, "damping": 0.99, "warmth": 0.7, "softness": 1, "pluck_pos": 0.4, "body_mix": 0.8},
    "accordion": {"duration": 0.3, "detune": 8, "harmonics": 4, "rolloff": 2500, "trem_depth": 0.1},
    "glockenspiel": {"duration": 0.4, "ring": 0.5, "bell": 1.2, "shimmer": 1.8, "ping": 0.6},
}
GOLDEN_HEAD = 2000
GOLDEN_STRIDE = 97


def build_export() -> dict:
    letters_dir = ROOT / "packs" / "core-sounds" / "content" / "letters"
    with wave.open(str(letters_dir / "a.wav")) as w:
        clip_rate, clip_channels = w.getframerate(), w.getnchannels()
    pitches = [
        {"file": pitch_filename(n, o), "note": n, "octave": o} for n, o in reachable_pitches()
    ]
    grid_pitches = {
        f"{row},{col}": "{}{}".format(*pitch_for(row, col, FRIENDLY_KEYS[DEFAULT_ROOT_INDEX], 0))
        for row in range(3) for col in range(10)
    }
    return {
        "generated_by": "scripts/export_studio.py; do not edit",
        "art": {
            "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
            "canvas": [CANVAS_WIDTH, CANVAS_HEIGHT],
            "cell_aspect": CELL_ASPECT,
            "key_colors": {k: v for k, v in KEY_COLORS.items() if k not in ("÷", "×")},
            "app_bg": APP_BG_DARK,
            "bg_dark": DEFAULT_BG_DARK,
            "bg_light": DEFAULT_BG_LIGHT,
            "gutter": [GUTTER_BG_DARK_A, GUTTER_BG_DARK_B],
            "fit": {f"{w}x{h}": list(fit_to_canvas(w, h)) for w, h in FIT_SIZES},
        },
        "music": {
            "grid_rows": [[k.lower() for k in row] for row in GRID_KEYS[1:]],
            "percussion_row": [k for k in GRID_KEYS[0]],
            "instruments": [d for d, _ in INSTRUMENTS],
            "pitches": pitches,
            "grid_pitches": grid_pitches,
        },
        "voice": {
            "letter_keys": sorted(k.lower() for k in _SPEAKABLE_KEYS),
            "sample_rate": clip_rate,
            "channels": clip_channels,
            "clip_filenames": {text: voice_clip_filename(text) for text in CLIP_EXAMPLES},
        },
        "synth": {"sample_rate": synth.SAMPLE_RATE, "defaults": synth.DEFAULTS},
    }


def build_golden() -> list[dict]:
    out = []
    for name, gen in synth.GENERATORS.items():
        cases = [(f, {}) for f in GOLDEN_FREQS] + [(GOLDEN_FREQS[0], GOLDEN_VARIED[name])]
        for freq, params in cases:
            samples = gen(freq, **params)
            out.append({
                "base": name, "freq": freq, "params": params, "length": len(samples),
                "head": samples[:GOLDEN_HEAD], "stride": GOLDEN_STRIDE, "strided": samples[::GOLDEN_STRIDE],
            })
    return out


def dumps(value) -> str:
    return json.dumps(value, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    EXPORT_PATH.write_text(dumps(build_export()))
    GOLDEN_PATH.write_text(dumps(build_golden()))
    print(f"wrote {EXPORT_PATH.relative_to(ROOT)} and {GOLDEN_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
