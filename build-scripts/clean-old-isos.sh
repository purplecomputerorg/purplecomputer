#!/usr/bin/env bash
# Delete local ISOs older than a given age from /opt/purple-installer/output/.
#
# Usage:
#   ./clean-old-isos.sh              # delete ISOs older than 7 days (default)
#   ./clean-old-isos.sh 3            # delete ISOs older than 3 days
#   ./clean-old-isos.sh --dry-run    # show what would be deleted (7 days)
#   ./clean-old-isos.sh --dry-run 3  # show what would be deleted (3 days)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

DRY_RUN=false
MAX_AGE_DAYS=7

for arg in "$@"; do
    if [ "$arg" = "--dry-run" ]; then
        DRY_RUN=true
    elif [[ "$arg" =~ ^[0-9]+$ ]]; then
        MAX_AGE_DAYS="$arg"
    else
        echo "Usage: $0 [--dry-run] [DAYS]"
        echo "  DAYS: delete ISOs older than this many days (default: 7)"
        exit 1
    fi
done

if [ ! -d "$OUTPUT_DIR" ]; then
    echo "No output directory at $OUTPUT_DIR"
    exit 0
fi

# Find .iso and .sha256 files older than MAX_AGE_DAYS
mapfile -t OLD_FILES < <(find "$OUTPUT_DIR" -maxdepth 1 \( -name "*.iso" -o -name "*.iso.sha256" \) -mtime +"$MAX_AGE_DAYS" | sort)

if [ ${#OLD_FILES[@]} -eq 0 ]; then
    echo "No ISOs older than $MAX_AGE_DAYS days in $OUTPUT_DIR."
    exit 0
fi

echo "ISOs older than $MAX_AGE_DAYS days:"
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
