#!/usr/bin/env python3
"""Zip Purple itself for Studio's in-browser Purple: purple_tui, its fonts, the core packs, and
the emoji font when this machine has one. Unpacked into Pyodide's file system as is.

Also fetches the Pyodide wheels Purple needs (pygame-ce and friends) once, since the page may
only load files from its own site.

Writes studio/.cache/purple.zip, studio/.cache/pyodide/*.whl, and studio/.cache/poster-<room>.png:
a screenshot of each room from Purple's headless preview, shown while the live one starts.
Usage: just studio-bundle
"""

import json
import os
import subprocess
import urllib.request
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "studio" / ".cache" / "purple.zip"
TRACKED = ["purple_tui", "packs/core-emoji", "packs/core-sounds"]
SKIP = ("purple_tui/tests/",)
WHEELS = ["pygame-ce", "fonttools", "rich", "wcwidth"]
LOCK = ROOT / "studio" / "node_modules" / "pyodide" / "pyodide-lock.json"
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


def take_posters() -> None:
    shots = OUT.parent / "shots"
    for room in ("play", "music", "art", "blocks"):
        env = {**os.environ, "PURPLE_SCREENSHOT_DIR": str(shots)}
        subprocess.run([sys.executable, str(ROOT / "scripts" / "preview.py"), room], cwd=ROOT, env=env, check=True, capture_output=True)
        (shots / f"{room}.png").replace(OUT.parent / f"poster-{room}.png")
    shots.rmdir()


def main() -> None:
    fetch_wheels()
    take_posters()
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
