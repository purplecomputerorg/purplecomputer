#!/usr/bin/env python3
"""Zip Purple itself for Studio's in-browser Purple: purple_tui, its fonts, the core packs, and
Noto's emoji as pictures (the ones Purple's own words use). Unpacked into Pyodide's file system as is.
The core sounds go beside it in studio/.cache/core-sounds/, leaving empty files of the same names in the zip,
and studio/scripts/pyc.mjs adds Pyodide's bytecode for purple_tui.

The emoji come from the Noto Color Emoji package Purple's ISO installs (Ubuntu noble-updates), pulled
out of the font as PNGs (purple_tui/canvas/emoji_pictures.py) since no emoji font format draws in
every browser. Studio's pages show the same pictures, from studio/.cache/emoji/.

Also fetches the Pyodide wheels Purple needs (pygame-ce and friends) and Purple's Piper voice once,
since the page may only load files from its own site.

Writes studio/.cache/purple.zip (stored, not compressed: Studio's build brotlis it whole),
studio/.cache/pyodide/*.whl and python_stdlib-<version>.zip, studio/.cache/voice/ (the voice model
and the espeak-ng English data it phonemizes with, and in voice/kokoro/ the room voice Make a Room
speaks a room's fixed lines in), and studio/.cache/purple-room-check.pyz, the room checker
(purple_tui/roomkit/check.py) as one file anyone with Python 3 can run.
Usage: just studio-bundle
"""

import ast
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
WHEELS = ["pygame-ce", "rich", "wcwidth"]
LOCK = ROOT / "studio" / "node_modules" / "pyodide" / "pyodide-lock.json"
EXPORT = ROOT / "studio" / "sdk" / "src" / "purple" / "export.json"
# Purple's voice, pinned where the shell builds read it: the VOICE_EN lines of scripts/voice_model.sh.
VOICE_PINS = dict(line.split("=", 1) for line in (ROOT / "scripts" / "voice_model.sh").read_text().splitlines() if line.startswith("VOICE_EN"))
# The room voice (studio/src/roomvoice.ts): Kokoro, Apache-2.0. int8 is the faster build under WebAssembly.
# Slowed by stretching (tempo) rather than Kokoro's speed: below 1.0 its first word gains a leading "a" ("a blue").
KOKORO_FILES = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
KOKORO_CONFIG = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/config.json"
KOKORO_LICENSE = "https://www.apache.org/licenses/LICENSE-2.0.txt"
KOKORO = {"model": "kokoro-v1.0.int8.onnx", "voice": "af_heart", "tempo": 0.75, "rate": 24000}
# What the room checker imports: the pack rules and the room library, all standard library.
CHECKER = ["purple_tui/__init__.py", "purple_tui/content.py", "purple_tui/i18n.py", "purple_tui/pack_manager.py", "purple_tui/synth.py",
           "purple_tui/constants.py", "purple_tui/roomkit/purple.py", "purple_tui/roomkit/runner.py",
           "purple_tui/roomkit/limits.py", "purple_tui/roomkit/check.py"]
FONTS = "purple_tui/canvas/fonts/"
# Purple draws only its own icons from this one, so the zip carries just those.
TRIMMED_FONTS = {FONTS + "SymbolsNerdFontMono-Regular.ttf"}
# Each font's characters, for the browser's glyph check (studio/src/live/browser.py).
CMAPS = "font-cmaps.json"
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


def store_stdlib() -> None:
    """Pyodide's standard library zip with its files stored, so Studio's build can brotli it whole
    (studio/vite.config.ts). Named for its Pyodide version, so the build never pairs it with another."""
    version = json.loads((LOCK.parent / "package.json").read_text())["version"]
    with zipfile.ZipFile(LOCK.parent / "python_stdlib.zip") as src, zipfile.ZipFile(OUT.parent / "pyodide" / f"python_stdlib-{version}.zip", "w") as out:
        for info in src.infolist():
            data = src.read(info)
            info.compress_type = zipfile.ZIP_STORED
            out.writestr(info, data)


def fetch_voice() -> None:
    """Purple's model with float16 weights (half the download, the same voice) and its config, from R2;
    the espeak-ng data from the piper package."""
    import piper
    spec = json.loads(EXPORT.read_text())["voice"]["piper"]
    out = OUT.parent / "voice"
    out.mkdir(parents=True, exist_ok=True)
    model = VOICE_PINS["VOICE_EN"]
    for name, hosted, sha in ((f"{model}.onnx", f"{model}.half.onnx", VOICE_PINS["VOICE_EN_HALF_SHA256"]),
                              (f"{model}.onnx.json", f"{model}.onnx.json", VOICE_PINS["VOICE_EN_JSON_SHA256"])):
        dest = out / name
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha:
            continue
        # Cloudflare turns away urllib's own user agent.
        request = urllib.request.Request(f"{VOICE_PINS['VOICE_EN_BASE']}/{hosted}", headers={"User-Agent": "purple-studio-bundle"})
        dest.write_bytes(urllib.request.urlopen(request).read())
        if hashlib.sha256(dest.read_bytes()).hexdigest() != sha:
            sys.exit(f"{hosted} doesn't match scripts/voice_model.sh")
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


def bundled_text(files: list[str]) -> str:
    """What the zip's fonts and emoji must cover: Purple's words and source, the browser's own Python, each
    string literal as it reads at run time ("\\uf001" as the icon), and every string Purple's modules hold
    once imported, so an icon built from its code point counts too. Rebuilt from source on every bundle."""
    text = [loaded_strings()]
    for f in files + sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "studio/src/live").glob("*.py")):
        if f.endswith((".py", ".json", ".txt")):
            text.append((ROOT / f).read_text(errors="ignore"))
            if f.endswith(".py"):
                text += [n.value for n in ast.walk(ast.parse(text[-1])) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return "".join(text)


def loaded_strings() -> str:
    import importlib
    import os
    import pkgutil
    import purple_tui

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    found: list[str] = []

    def walk(value, depth: int) -> None:
        if isinstance(value, str):
            found.append(value)
        elif depth and isinstance(value, dict):
            for item in value.items():
                walk(item, depth - 1)
        elif depth and isinstance(value, (tuple, list, set, frozenset)):
            for item in value:
                walk(item, depth - 1)
        elif depth and isinstance(value, type) and value.__module__.startswith("purple_tui."):
            walk(list(vars(value).values()), depth - 1)

    for module in pkgutil.walk_packages(purple_tui.__path__, "purple_tui."):
        if ".tests" not in module.name:
            walk(list(vars(importlib.import_module(module.name)).values()), 4)
    return "".join(found)


def trimmed_font(path: Path, text: str) -> bytes:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    subsetter = subset.Subsetter()
    subsetter.populate(unicodes={ord(c) for c in text} & set(font.getBestCmap()))
    subsetter.subset(font)
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def cmap_bounds(data: bytes) -> list[int]:
    """The font's characters as sorted half-open run bounds: a character is in it when bisect_right lands odd."""
    from fontTools.ttLib import TTFont

    bounds: list[int] = []
    for c in sorted(TTFont(io.BytesIO(data)).getBestCmap()):
        if bounds and bounds[-1] == c:
            bounds[-1] = c + 1
        else:
            bounds += [c, c + 1]
    return bounds


def bundled_emoji(text: str) -> list[Path]:
    """map.json and the pictures for the emoji Purple's vocabulary and its own files use; the browser
    fetches any other emoji's pictures the first time it draws one (studio/src/live/browser.py)."""
    from purple_tui.canvas.emoji_pictures import EmojiPictures
    from purple_tui.canvas.gfx import _ONE_EMOJI_RE

    pictures = EmojiPictures(EMOJI)
    glyphs = {g for m in _ONE_EMOJI_RE.finditer(text) for g in pictures.glyphs_for(m[0]) if len(pictures.glyphs[g]) == 3}
    return [EMOJI / "map.json", *(pictures.dir / f"{g}.png" for g in sorted(glyphs))]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build_checker(OUT.parent / "purple-room-check.pyz")
    fetch_wheels()
    store_stdlib()
    fetch_voice()
    fetch_kokoro()
    build_emoji()
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", *TRACKED], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split()
    shutil.rmtree(CORE_SOUNDS, ignore_errors=True)
    text = bundled_text(files)
    cmaps = {}
    with zipfile.ZipFile(OUT, "w") as z:
        for f in files:
            if f.startswith(SKIP) or not (ROOT / f).is_file():
                continue
            if f.startswith(SOUNDS) and f.endswith((".ogg", ".wav")):
                # Served on its own and played by the page (studio/src/live/sound.ts); the zip keeps the name.
                (CORE_SOUNDS / f.removeprefix(SOUNDS)).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / f, CORE_SOUNDS / f.removeprefix(SOUNDS))
                z.writestr(f, b"")
            else:
                data = trimmed_font(ROOT / f, text) if f in TRIMMED_FONTS else (ROOT / f).read_bytes()
                if f.startswith(FONTS) and f.endswith((".ttf", ".otf")):
                    cmaps[Path(f).name] = cmap_bounds(data)
                z.writestr(f, data)
        z.writestr(CMAPS, json.dumps(cmaps, separators=(",", ":")))
        for f in bundled_emoji(text):
            z.write(f, f.relative_to(OUT.parent).as_posix())
    subprocess.run(["node", "scripts/pyc.mjs", str(OUT)], cwd=ROOT / "studio", check=True)
    print(f"{OUT} ({OUT.stat().st_size // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
