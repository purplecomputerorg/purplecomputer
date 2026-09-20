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
# Same voice and pinned hash as the golden image (festvox serves plain http only).
FLITE_VOICE=cmu_us_lnh.flitevox
FLITE_VOICE_URL=http://festvox.org/flite/packed/flite-2.3/voices/$FLITE_VOICE
FLITE_VOICE_SHA=d3fb6b1c4f781fc5c9b1ea5efdc8c46c1ce5e74cf349cd78c1fae3c0e19d7c9f
PYTHON_PATTERN='cpython-3\\.12.*x86_64-unknown-linux-gnu-install_only_stripped'

fetch() { [ -s "$1" ] || curl -fsSL -o "$1" "$2"; }

# The Quick voice. ChromeOS has no flite, and a binary linked against a newer glibc than the
# Chromebook's will not run there, so it is built static. flite's makefiles break under make -j.
build_flite() {
    local work build='./configure --with-audio=none --disable-shared LDFLAGS=-static >/dev/null && make >/dev/null'
    work="$(mktemp -d)"
    git clone -q --depth 1 https://github.com/festvox/flite.git "$work"
    if command -v nix-shell >/dev/null; then
        (cd "$work" && nix-shell -p gcc gnumake glibc.static --run "$build")
    else
        (cd "$work" && sh -c "$build")
    fi
    strip -o "$DEST/flite" "$work/bin/flite"
    rm -rf "$work"
}

mkdir -p "$DEST/wheels" "$DEST/voice"
cp "$SRC"/*.sh "$SRC/probe.py" "$REPO/purple_tui/canvas/kms.py" "$DEST/"
rm "$DEST/build-bundle.sh"
gcc -shared -fPIC -O2 -o "$DEST/libf128shim.so" "$SRC/f128shim.c"
tar -czf "$DEST/purple-app.tar.gz" -C "$REPO" --exclude=__pycache__ --exclude='*.purplepack' purple_tui packs

# pygame-ce, not pygame: see the guide. Versions are pinned because `just` eats "numpy<2" as a redirect.
# evdev-binary is python-evdev prebuilt (evdev itself is sdist only); it needs glibc 2.2.5.
# rich: play_eval validates its markup with it, and without it every answer falls back to letter blocks.
(cd "$REPO" && just python -m pip download --only-binary=:all: \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    --platform manylinux1_x86_64 --python-version 3.12 --implementation cp --abi cp312 --abi none \
    -d "$DEST/wheels" pygame-ce==2.5.8 numpy==1.26.4 piper-tts==1.3.0 evdev-binary==2.0.0 rich==14.2.0)

if [ ! -s "$DEST/python-x86_64.tar.gz" ]; then
    python_url=$(gh api repos/astral-sh/python-build-standalone/releases/latest \
        --jq ".assets[] | select(.name|test(\"$PYTHON_PATTERN\")) | .browser_download_url")
    fetch "$DEST/python-x86_64.tar.gz" "$python_url"
fi
fetch "$DEST/NotoColorEmoji.ttf" "$EMOJI_URL"
fetch "$DEST/voice/$FLITE_VOICE" "$FLITE_VOICE_URL"
echo "$FLITE_VOICE_SHA  $DEST/voice/$FLITE_VOICE" | sha256sum -c --quiet -
[ -x "$DEST/flite" ] || build_flite
for suffix in "" .json; do
    fetch "$DEST/voice/$VOICE$suffix" "$VOICE_URL$suffix"
done
du -sh "$DEST"
