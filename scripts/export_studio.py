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
from purple_tui import palette as P  # noqa: E402
from purple_tui.constants import ART_COLS, ART_ROWS, CANVAS_COLS, CANVAS_ROWS  # noqa: E402
from purple_tui.music_constants import (  # noqa: E402
    DEFAULT_ROOT_INDEX, FRIENDLY_KEYS, GRID_KEYS, INSTRUMENTS, PERCUSSION, pitch_filename, pitch_for, reachable_pitches,
)
from purple_tui.canvas.rooms.art_room import CANVAS_ALT, CANVAS_BG  # noqa: E402
from purple_tui.canvas.rooms.family_room import TEXT_MAX  # noqa: E402
from purple_tui.palette import KEY_COLORS  # noqa: E402
from purple_tui.canvas.sounds import CLIP_NAMES, SAMPLE_VOLUME  # noqa: E402
from purple_tui.roomkit.purple import H as ROOM_H, W as ROOM_W  # noqa: E402
from purple_tui.tts import VOICE_MODEL, VOICE_SPEAKER, _SYNTH_PARAMS, voice_clip_filename  # noqa: E402
from tools.photo_to_art import fit_to_canvas  # noqa: E402

EXPORT_PATH = ROOT / "studio" / "sdk" / "src" / "purple" / "export.json"
GOLDEN_PATH = ROOT / "studio" / "tests" / "golden.json"
PACK_FORMATS_PATH = ROOT / "studio" / "pack_formats.json"

PALETTE_NAMES = ("BG", "SURFACE", "TILE", "FIELD", "HAIR", "LINE", "PRIMARY", "ON_PRIMARY", "ACCENT", "TEXT", "MUTED", "DIM", "CARET", "DANGER", "GOOD")
FIT_SIZES = [(4032, 3024), (3024, 4032), (1000, 1000), (1920, 1080), (100, 2000), (2000, 100), (1, 1), (132, 50), (264, 50), (50, 25)]
CLIP_EXAMPLES = ["  Hello There ", "It's Purple Computer", "hi", "5 times 5 ducks equals 25 ducks"]
# The espeak-ng files Piper reads for English (en-us is lang/gmw/en-US on top of lang/gmw/en).
ESPEAK_DATA = ["en_dict", "intonations", "phondata", "phonindex", "phontab", "lang/gmw/en", "lang/gmw/en-US"]
# Golden renders: two pitches at the defaults, then one short varied render per instrument.
GOLDEN_FREQS = [261.63, 880.0]
GOLDEN_VARIED = {
    "marimba": {"duration": 0.3, "wood": 0.9, "tube": 0.4, "mallet": 0.5, "attack_ms": 20},
    "ukulele": {"duration": 0.3, "damping": 0.99, "warmth": 0.7, "softness": 1, "pluck_pos": 0.4, "body_mix": 0.8},
    "accordion": {"duration": 0.3, "detune": 8, "harmonics": 4, "rolloff": 2500, "trem_depth": 0.1, "breath": 1, "scoop": 40},
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
    ledger = json.loads(PACK_FORMATS_PATH.read_text())
    return {
        "generated_by": "scripts/export_studio.py; do not edit",
        "pack_formats": [{k: f[k] for k in ("format", "date", "needs")} for f in ledger["formats"]],
        "pack_skipped": ledger.get("skipped", []),
        "screen": {
            "viewport": [CANVAS_COLS, CANVAS_ROWS],
            "palette": {name.lower(): getattr(P, name) for name in PALETTE_NAMES},
        },
        "art": {
            "canvas": [ART_COLS, ART_ROWS],
            "cell_aspect": 1,
            "key_colors": {k: v for k, v in KEY_COLORS.items() if k not in ("÷", "×")},
            "canvas_bg": CANVAS_BG,
            "canvas_alt": CANVAS_ALT,
            "fit": {f"{w}x{h}": list(fit_to_canvas(w, h, ART_COLS, ART_ROWS, 1)) for w, h in FIT_SIZES},
        },
        "music": {
            "grid_rows": [[k.lower() for k in row] for row in GRID_KEYS[1:]],
            "percussion_row": [k for k in GRID_KEYS[0]],
            "instruments": [d for d, _ in INSTRUMENTS],
            "pitches": pitches,
            "grid_pitches": grid_pitches,
            "sample_volume": SAMPLE_VOLUME,
        },
        "voice": {
            "letter_files": {k.lower(): name for k, name in CLIP_NAMES.items()},
            "sample_rate": clip_rate,
            "channels": clip_channels,
            "clip_filenames": {text: voice_clip_filename(text) for text in CLIP_EXAMPLES},
            # Studio's Piper: the model input "scales" is noise, length, noise_w.
            "piper": {"model": VOICE_MODEL, "speaker": VOICE_SPEAKER,
                      "scales": [_SYNTH_PARAMS[k] for k in ("noise_scale", "length_scale", "noise_w")],
                      "word_gap": _SYNTH_PARAMS["word_gap"],
                      "espeak_data": ESPEAK_DATA},
        },
        "synth": {"sample_rate": synth.SAMPLE_RATE, "defaults": synth.DEFAULTS},
        "room": {
            "grid": [ROOM_W, ROOM_H],
            "keys": ["space", "enter", "backspace", "up", "down", "left", "right"],
            "drums": sorted(set(PERCUSSION.values())),
            "drum_keys": PERCUSSION,
            "say_max": TEXT_MAX,
        },
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
