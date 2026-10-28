#!/usr/bin/env python3
"""Zip Purple itself for Studio's in-browser Purple: purple_tui, its fonts, the core packs, and
the emoji font when this machine has one. Unpacked into Pyodide's file system as is.

Also fetches the Pyodide wheels Purple needs (pygame-ce and friends) and Purple's Piper voice once,
since the page may only load files from its own site.

Writes studio/.cache/purple.zip, studio/.cache/pyodide/*.whl, studio/.cache/voice/ (the voice model
and the espeak-ng English data it phonemizes with, and in voice/kokoro/ the room voice Make a Room
speaks a room's fixed lines in), and studio/.cache/purple-room-check.pyz, the room checker
(purple_tui/roomkit/check.py) as one file anyone with Python 3 can run.
Usage: just studio-bundle
"""

import json
import shutil
import subprocess
import urllib.request
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "studio" / ".cache" / "purple.zip"
TRACKED = ["purple_tui", "packs/core-emoji", "packs/core-sounds"]
SKIP = ("purple_tui/tests/",)
WHEELS = ["pygame-ce", "fonttools", "rich", "wcwidth"]
LOCK = ROOT / "studio" / "node_modules" / "pyodide" / "pyodide-lock.json"
EXPORT = ROOT / "studio" / "sdk" / "src" / "purple" / "export.json"
VOICES_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium"
# The room voice (studio/src/roomvoice.ts): Kokoro, Apache-2.0. int8 is the faster build under WebAssembly.
# Below speed 1.0 a short line gains a leading "a" ("a blue").
KOKORO_FILES = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_CONFIG = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/config.json"
KOKORO_LICENSE = "https://www.apache.org/licenses/LICENSE-2.0.txt"
KOKORO = {"model": "kokoro-v1.0.int8.onnx", "voice": "af_heart", "speed": 1.0, "rate": 24000}
# What the room checker imports: the pack rules and the room library, all standard library.
CHECKER = ["purple_tui/__init__.py", "purple_tui/content.py", "purple_tui/pack_manager.py", "purple_tui/synth.py",
           "purple_tui/constants.py", "purple_tui/roomkit/purple.py", "purple_tui/roomkit/runner.py",
           "purple_tui/roomkit/limits.py", "purple_tui/roomkit/check.py"]
EMOJI_FONTS = [Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"), Path.home() / ".local/share/fonts/NotoColorEmoji.ttf"]


def fetch_wheels() -> None:
    version = json.loads((LOCK.parent / "package.json").read_text())["version"]
    packages = json.loads(LOCK.read_text())["packages"]
    out = OUT.parent / "pyodide"
    out.mkdir(parents=True, exist_ok=True)
    for name in WHEELS:
        wheel = out / packages[name]["file_name"]
        if not wheel.exists():
            urllib.request.urlretrieve(f"https://cdn.jsdelivr.net/pyodide/v{version}/full/{wheel.name}", wheel)


def fetch_voice() -> None:
    """The model from this machine's Purple voice when it has one, else from Piper's voices; the espeak-ng data from the piper package."""
    import piper
    from purple_tui.tts import find_voice_model
    spec = json.loads(EXPORT.read_text())["voice"]["piper"]
    out = OUT.parent / "voice"
    local = find_voice_model()
    for name in (f"{spec['model']}.onnx", f"{spec['model']}.onnx.json"):
        dest = out / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue
        if local:
            shutil.copyfile(local.parent / name, dest)
        else:
            urllib.request.urlretrieve(f"{VOICES_URL}/{name}", dest)
    data = Path(piper.__file__).parent / "espeak-ng-data"
    for name in spec["espeak_data"]:
        (out / "espeak-ng-data" / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(data / name, out / "espeak-ng-data" / name)


def fetch_kokoro() -> None:
    """The model, one voice's style vectors as raw float32, and kokoro.json: the settings and Kokoro's phoneme vocabulary."""
    import numpy as np
    out = OUT.parent / "voice" / "kokoro"
    out.mkdir(parents=True, exist_ok=True)
    for url, name in ((f"{KOKORO_FILES}/{KOKORO['model']}", KOKORO["model"]), (KOKORO_LICENSE, "LICENSE.txt")):
        if not (out / name).exists():
            urllib.request.urlretrieve(url, out / name)
    if not (out / f"{KOKORO['voice']}.bin").exists():
        with tempfile.TemporaryDirectory() as tmp:
            urllib.request.urlretrieve(f"{KOKORO_FILES}/voices-v1.0.bin", f"{tmp}/voices.bin")
            np.load(f"{tmp}/voices.bin")[KOKORO["voice"]].astype("<f4").tofile(out / f"{KOKORO['voice']}.bin")
    config = OUT.parent / "kokoro-config.json"
    if not config.exists():
        urllib.request.urlretrieve(KOKORO_CONFIG, config)
    vocab = json.loads(config.read_text())["vocab"]
    (out / "kokoro.json").write_text(json.dumps({**KOKORO, "vocab": vocab}, ensure_ascii=False))


def build_checker(out: Path) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        for f in CHECKER:
            (Path(tmp) / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / f, Path(tmp) / f)
        (Path(tmp) / "purple_tui/roomkit/__init__.py").touch()
        (Path(tmp) / "__main__.py").write_text("import sys\nfrom purple_tui.roomkit.check import main\nsys.exit(main())\n")
        zipapp.create_archive(tmp, out, interpreter="/usr/bin/env python3")
    return out


def main() -> None:
    build_checker(OUT.parent / "purple-room-check.pyz")
    fetch_wheels()
    fetch_voice()
    fetch_kokoro()
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", *TRACKED], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            if not f.startswith(SKIP) and (ROOT / f).is_file():
                z.write(ROOT / f, f)
        emoji = next((p for p in EMOJI_FONTS if p.exists()), None)
        if emoji:
            z.write(emoji, "fonts/NotoColorEmoji.ttf")
    print(f"{OUT} ({OUT.stat().st_size // 1024} KB, emoji font {'included' if emoji else 'missing'})", file=sys.stderr)


if __name__ == "__main__":
    main()
