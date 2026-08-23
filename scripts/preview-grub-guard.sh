#!/usr/bin/env bash
# Render the GRUB unsupported-computer screen (32-bit CPU, no i386 payload on
# the ISO) without building one: extract the router prelude from
# 01-remaster-iso.sh, boot it via grub-mkrescue in QEMU with a 32-bit CPU, and
# screendump to a PNG. The routing itself is checked by test-grub-router.sh.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${PURPLE_SCREENSHOT_DIR:-/tmp/screenshots}"
OUT="$OUT_DIR/grub-32bit-guard.png"

for cmd in grub-mkrescue qemu-system-x86_64; do
    command -v "$cmd" >/dev/null || { echo "ERROR: $cmd not installed" >&2; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/boot/grub" "$OUT_DIR"

awk '/^ROUTER$/{on=0} on{print} /<< .ROUTER.$/{on=1}' \
    "$REPO/build-scripts/01-remaster-iso.sh" > "$WORK/boot/grub/grub.cfg"
[ -s "$WORK/boot/grub/grub.cfg" ] || { echo "ERROR: router snippet not found in 01-remaster-iso.sh" >&2; exit 1; }
cp "$REPO/config/grub/purple-router.cfg" "$WORK/boot/grub/"

grub-mkrescue -o "$WORK/guard.iso" "$WORK" >/dev/null 2>&1

# pentium3 has no long mode, so cpuid -l fails and the guard screen shows
(sleep 8; echo "screendump $WORK/screen.ppm"; sleep 2; echo quit) | \
    qemu-system-x86_64 -cpu pentium3 -m 512 -cdrom "$WORK/guard.iso" \
        -display none -monitor stdio >/dev/null 2>&1

"$REPO/.venv/bin/python3" -c \
    "import sys; from PIL import Image; Image.open(sys.argv[1]).save(sys.argv[2])" \
    "$WORK/screen.ppm" "$OUT"
echo "$OUT"
