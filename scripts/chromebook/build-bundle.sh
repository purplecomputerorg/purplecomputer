#!/bin/bash
# Builds the Chromebook stick bundle (~190 MB of downloads) into a folder outside the repo:
# the probe, and Purple itself for the stage 1 install. Downloads already there are kept.
# Usage: scripts/chromebook/build-bundle.sh [dest]   (default ~/purple-chromebook)
# Then copy the folder to a FAT32 stick. Run steps: guides/chromebook-dev-mode-plan.md
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
REPO="$SRC/../.."
DEST="${1:-$HOME/purple-chromebook}"
VOICE=en_US-libritts_r-medium.onnx
VOICE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/$VOICE
EMOJI_URL=https://github.com/googlefonts/noto-emoji/raw/main/2D/fonts/NotoColorEmoji.ttf
PYTHON_PATTERN='cpython-3\\.12.*x86_64-unknown-linux-gnu-install_only_stripped'

fetch() { [ -s "$1" ] || curl -fsSL -o "$1" "$2"; }

mkdir -p "$DEST/wheels" "$DEST/voice"
cp "$SRC"/*.sh "$SRC/probe.py" "$REPO/purple_tui/canvas/kms.py" "$DEST/"
rm "$DEST/build-bundle.sh"
gcc -shared -fPIC -O2 -o "$DEST/libf128shim.so" "$SRC/f128shim.c"
tar -czf "$DEST/purple-app.tar.gz" -C "$REPO" --exclude=__pycache__ --exclude='*.purplepack' purple_tui packs

# pygame-ce, not pygame: see the guide. Versions are pinned because `just` eats "numpy<2" as a redirect.
# evdev-binary is python-evdev prebuilt (evdev itself is sdist only); it needs glibc 2.2.5.
(cd "$REPO" && just python -m pip download --only-binary=:all: \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    --platform manylinux1_x86_64 --python-version 3.12 --implementation cp --abi cp312 --abi none \
    -d "$DEST/wheels" pygame-ce==2.5.8 numpy==1.26.4 piper-tts==1.3.0 evdev-binary==2.0.0)

if [ ! -s "$DEST/python-x86_64.tar.gz" ]; then
    python_url=$(gh api repos/astral-sh/python-build-standalone/releases/latest \
        --jq ".assets[] | select(.name|test(\"$PYTHON_PATTERN\")) | .browser_download_url")
    fetch "$DEST/python-x86_64.tar.gz" "$python_url"
fi
fetch "$DEST/NotoColorEmoji.ttf" "$EMOJI_URL"
for suffix in "" .json; do
    fetch "$DEST/voice/$VOICE$suffix" "$VOICE_URL$suffix"
done
du -sh "$DEST"
