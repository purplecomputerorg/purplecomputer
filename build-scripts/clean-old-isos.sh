#!/usr/bin/env bash
# Delete stale ISOs from /opt/purple-installer/output/, along with their
# .sha256 and .version sidecars.
#
# Keeps the newest few builds and drops everything older. A build is one stem
# (purple-installer-YYYYMMDD), so its .iso, .debug.iso and .with-backup.iso
# variants count as one build between them, not three.
#
# corrupt-test ISOs go at any age: each is a full ~9GB copy of a build's
# with-backup ISO with a few KiB deliberately damaged (just corrupt-test-iso),
# only useful for the flash session it was made for, and regenerable from the
# parent ISO. Four scenarios per build adds up fast.
#
# Usage:
#   ./clean-old-isos.sh              # keep the newest 3 builds (default)
#   ./clean-old-isos.sh 5            # keep the newest 5 builds
#   ./clean-old-isos.sh --dry-run    # show what would be deleted (keeping 3)
#   ./clean-old-isos.sh --dry-run 5  # show what would be deleted (keeping 5)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"

DRY_RUN=false
KEEP_BUILDS=3

for arg in "$@"; do
    if [ "$arg" = "--dry-run" ]; then
        DRY_RUN=true
    elif [[ "$arg" =~ ^[0-9]+$ ]]; then
        KEEP_BUILDS="$arg"
    else
        echo "Usage: $0 [--dry-run] [KEEP]"
        echo "  KEEP: how many recent builds to keep (default: 3)"
        exit 1
    fi
done

if [ ! -d "$OUTPUT_DIR" ]; then
    echo "No output directory at $OUTPUT_DIR"
    exit 0
fi

# An ISO and its sidecars are always cleaned together, so every pass matches
# the same three name patterns.
ISO_FILES=(-name "*.iso" -o -name "*.iso.sha256" -o -name "*.iso.version")

# Newest builds first, collapsing each build's variants to a single stem.
mapfile -t KEEP_STEMS < <(list_build_isos \
    | sed -E 's|.*/||; s/\.(with-backup|debug)?\.?iso$//' \
    | awk '!seen[$0]++' \
    | head -n "$KEEP_BUILDS")

KEEP_ARGS=()
for stem in "${KEEP_STEMS[@]}"; do
    KEEP_ARGS+=(! -name "$stem.*")
done

mapfile -t OLD_FILES < <({
    find "$OUTPUT_DIR" -maxdepth 1 -name "*corrupt-test*" \( "${ISO_FILES[@]}" \)
    find "$OUTPUT_DIR" -maxdepth 1 ! -name "*corrupt-test*" \( "${ISO_FILES[@]}" \) "${KEEP_ARGS[@]}"
} | sort)

if [ ${#OLD_FILES[@]} -eq 0 ]; then
    echo "Nothing to clean in $OUTPUT_DIR (${#KEEP_STEMS[@]} build(s) kept, no corrupt-test ISOs)."
    exit 0
fi

if [ ${#KEEP_STEMS[@]} -gt 0 ]; then
    echo "Keeping the newest ${#KEEP_STEMS[@]} build(s):"
    printf '  %s\n' "${KEEP_STEMS[@]}"
    echo
fi

echo "Deleting every older build, plus all corrupt-test ISOs:"
TOTAL_SIZE=0
for f in "${OLD_FILES[@]}"; do
    SIZE=$(stat --format=%s "$f" 2>/dev/null || echo 0)
    TOTAL_SIZE=$((TOTAL_SIZE + SIZE))
    SIZE_MB=$((SIZE / 1024 / 1024))
    echo "  $(basename "$f")  (${SIZE_MB}MB)"
done
TOTAL_MB=$((TOTAL_SIZE / 1024 / 1024))
echo
echo "${#OLD_FILES[@]} file(s), ${TOTAL_MB}MB total."

if [ "$DRY_RUN" = true ]; then
    echo "(dry run, nothing deleted)"
    exit 0
fi

echo
for f in "${OLD_FILES[@]}"; do
    sudo rm -f "$f"
    echo "  deleted $(basename "$f")"
done

echo
echo "Done. Freed ~${TOTAL_MB}MB."
