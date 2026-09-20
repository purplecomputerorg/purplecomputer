#!/bin/bash
# Builds the Chromebook probe stick bundle (~175 MB of downloads) into a folder outside the repo.
# Usage: scripts/chromebook-probe/build-bundle.sh [dest]   (default ~/purple-chromebook-probe)
# Then copy the folder to a FAT32 stick. Run steps: guides/chromebook-dev-mode-plan.md
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/purple-chromebook-probe}"
VOICE=en_US-libritts_r-medium.onnx
VOICE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/$VOICE
PYTHON_PATTERN='cpython-3\\.12.*x86_64-unknown-linux-gnu-install_only_stripped'

mkdir -p "$DEST/wheels" "$DEST/voice"
cp "$SRC/probe.sh" "$SRC/probe.py" "$DEST/"
gcc -shared -fPIC -O2 -o "$DEST/libf128shim.so" "$SRC/f128shim.c"

# pygame-ce, not pygame: see the guide. Versions are pinned because `just` eats "numpy<2" as a redirect.
(cd "$SRC/../.." && just python -m pip download --only-binary=:all: \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    --python-version 3.12 --implementation cp --abi cp312 --abi none \
    -d "$DEST/wheels" pygame-ce==2.5.8 numpy==1.26.4 piper-tts==1.3.0)

python_url=$(gh api repos/astral-sh/python-build-standalone/releases/latest \
    --jq ".assets[] | select(.name|test(\"$PYTHON_PATTERN\")) | .browser_download_url")
curl -fsSL -o "$DEST/python-x86_64.tar.gz" "$python_url"
for suffix in "" .json; do
    curl -fsSL -o "$DEST/voice/$VOICE$suffix" "$VOICE_URL$suffix"
done
du -sh "$DEST"
