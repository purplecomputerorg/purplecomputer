#!/usr/bin/env python3
"""Zip Purple itself for Studio's in-browser Purple: purple_tui, its fonts, the core packs, and
the emoji font when this machine has one. Unpacked into Pyodide's file system as is.

Also fetches the Pyodide wheels Purple needs (pygame-ce and friends) and Purple's Piper voice once,
since the page may only load files from its own site.

Writes studio/.cache/purple.zip, studio/.cache/pyodide/*.whl, studio/.cache/voice/ (the voice model
and the espeak-ng English data it phonemizes with).
Usage: just studio-bundle
"""

import json
import shutil
import subprocess
import urllib.request
import sys
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


def main() -> None:
    fetch_wheels()
    fetch_voice()
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
