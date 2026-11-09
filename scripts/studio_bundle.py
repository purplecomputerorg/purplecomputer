#!/usr/bin/env python3
"""Zip Purple itself for Studio's in-browser Purple: purple_tui, its fonts, the core packs, and
Noto's emoji as pictures (the ones Purple's own words use). Unpacked into Pyodide's file system as is.
The core sounds go beside it in studio/.cache/core-sounds/, leaving empty files of the same names in the zip.

The emoji come from the Noto Color Emoji package Purple's ISO installs (Ubuntu noble-updates), pulled
out of the font as PNGs (purple_tui/canvas/emoji_pictures.py) since no emoji font format draws in
every browser. Studio's pages show the same pictures, from studio/.cache/emoji/.

Also fetches the Pyodide wheels Purple needs (pygame-ce and friends) and Purple's Piper voice once,
since the page may only load files from its own site.

Writes studio/.cache/purple.zip, studio/.cache/pyodide/*.whl, studio/.cache/voice/ (the voice model
and the espeak-ng English data it phonemizes with, and in voice/kokoro/ the room voice Make a Room
speaks a room's fixed lines in), and studio/.cache/purple-room-check.pyz, the room checker
(purple_tui/roomkit/check.py) as one file anyone with Python 3 can run.
Usage: just studio-bundle
"""

import hashlib
import io
import json
import lzma
import shutil
import subprocess
import urllib.request
import sys
import tarfile
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
# Slowed by stretching (tempo) rather than Kokoro's speed: below 1.0 its first word gains a leading "a" ("a blue").
KOKORO_FILES = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_CONFIG = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/config.json"
KOKORO_LICENSE = "https://www.apache.org/licenses/LICENSE-2.0.txt"
KOKORO = {"model": "kokoro-v1.0.int8.onnx", "voice": "af_heart", "tempo": 0.75, "rate": 24000}
# What the room checker imports: the pack rules and the room library, all standard library.
CHECKER = ["purple_tui/__init__.py", "purple_tui/content.py", "purple_tui/pack_manager.py", "purple_tui/synth.py",
           "purple_tui/constants.py", "purple_tui/roomkit/purple.py", "purple_tui/roomkit/runner.py",
           "purple_tui/roomkit/limits.py", "purple_tui/roomkit/check.py"]
EMOJI = OUT.parent / "emoji"
SOUNDS = "packs/core-sounds/content/"
CORE_SOUNDS = OUT.parent / "core-sounds"
UBUNTU = "http://archive.ubuntu.com/ubuntu"
# The pockets 00-build-golden-image.sh installs from, newest first.
NOTO_POCKETS = ["noble-updates", "noble"]
EMOJI_TEST = "https://unicode.org/Public/emoji/latest/emoji-test.txt"


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


def fetch_noto() -> tuple[Path, str]:
    """The font from the fonts-noto-color-emoji package Purple's ISO gets, and its version; the last
    one fetched when Ubuntu can't be reached."""
    cache = OUT.parent / "noto"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        package = next(filter(None, map(_noto_package, NOTO_POCKETS)))
    except OSError as e:
        cached = sorted(cache.glob("*.ttf"))
        if not cached:
            raise
        print(f"Couldn't reach Ubuntu ({e}); using {cached[-1].name}", file=sys.stderr)
        return cached[-1], cached[-1].stem
    font = cache / f"{package['Version']}.ttf"
    if not font.exists():
        deb = urllib.request.urlopen(f"{UBUNTU}/{package['Filename']}").read()
        if hashlib.sha256(deb).hexdigest() != package["SHA256"]:
            sys.exit(f"{package['Filename']} doesn't match Ubuntu's checksum")
        tar = subprocess.run(["dpkg-deb", "--fsys-tarfile", "/dev/stdin"], input=deb, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as t:
            member = next(m for m in t.getmembers() if m.name.endswith("/NotoColorEmoji.ttf"))
            font.write_bytes(t.extractfile(member).read())
    return font, package["Version"]


def _noto_package(pocket: str) -> dict | None:
    index = lzma.decompress(urllib.request.urlopen(f"{UBUNTU}/dists/{pocket}/main/binary-amd64/Packages.xz").read()).decode()
    for stanza in index.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in stanza.splitlines() if ": " in line and not line.startswith(" "))
        if fields.get("Package") == "fonts-noto-color-emoji":
            return fields
    return None


def build_emoji() -> None:
    """studio/.cache/emoji/: every emoji Unicode lists, as the pictures the ISO's Noto draws it with."""
    from purple_tui.canvas.emoji_pictures import build

    font, version = fetch_noto()
    if (EMOJI / version).is_dir() and (EMOJI / "map.json").exists():
        return
    listed = OUT.parent / "noto" / "emoji-test.txt"
    if not listed.exists():
        urllib.request.urlretrieve(EMOJI_TEST, listed)
    sequences = ["".join(chr(int(c, 16)) for c in line.split(";")[0].split())
                 for line in listed.read_text().splitlines() if ";" in line and not line.startswith("#")]
    shutil.rmtree(EMOJI, ignore_errors=True)
    build(font, EMOJI, sequences, version)


def bundled_emoji(files: list[str]) -> list[Path]:
    """map.json and the pictures for the emoji Purple's vocabulary and its own files use; the browser
    fetches any other emoji's pictures the first time it draws one (studio/src/live/browser.py)."""
    from purple_tui.canvas.emoji_pictures import EmojiPictures
    from purple_tui.canvas.gfx import _ONE_EMOJI_RE

    pictures = EmojiPictures(EMOJI)
    text = "".join((ROOT / f).read_text(errors="ignore") for f in files if f.endswith((".py", ".json", ".txt")))
    glyphs = {g for m in _ONE_EMOJI_RE.finditer(text) for g in pictures.glyphs_for(m[0]) if len(pictures.glyphs[g]) == 3}
    return [EMOJI / "map.json", *(pictures.dir / f"{g}.png" for g in sorted(glyphs))]


def main() -> None:
    build_checker(OUT.parent / "purple-room-check.pyz")
    fetch_wheels()
    fetch_voice()
    fetch_kokoro()
    build_emoji()
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", *TRACKED], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(CORE_SOUNDS, ignore_errors=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            if f.startswith(SKIP) or not (ROOT / f).is_file():
                continue
            if f.startswith(SOUNDS) and f.endswith((".ogg", ".wav")):
                # Served on its own and played by the page (studio/src/live/sound.ts); the zip keeps the name.
                (CORE_SOUNDS / f.removeprefix(SOUNDS)).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / f, CORE_SOUNDS / f.removeprefix(SOUNDS))
                z.writestr(f, b"")
            else:
                z.write(ROOT / f, f)
        for f in bundled_emoji(files):
            z.write(f, f.relative_to(OUT.parent).as_posix())
    print(f"{OUT} ({OUT.stat().st_size // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
