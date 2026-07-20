#!/usr/bin/env bash
# Copy an ISO and deliberately corrupt golden image copies inside it, to test
# install.sh's backup-copy fallback and the corrupt-Key error screen end to
# end on real hardware or a VM. The output flashes normally (its .sha256
# sidecar matches the corrupted bytes) and boots normally; only the chosen
# copy fails its zstd integrity check during install.
#
# corrupt-test ISOs are never auto-picked by find_latest_iso; flash them via
# just flash-corrupt (or an explicit path to just flash)
#
# Full walkthrough: guides/corruption-testing.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"

usage() {
    echo "Usage: $0 [iso] [primary|backup|both]"
    echo ""
    echo "  iso      ISO to copy and corrupt. Default: the newest build's"
    echo "           with-backup ISO (build one with PURPLE_WITH_BACKUP_ISO=1 just build)."
    echo "  primary  Corrupt /purple/purple-os.img.zst (default). On a"
    echo "           with-backup ISO the install should recover via the backup."
    echo "  backup   Corrupt /purple/purple-os-backup.img.zst only."
    echo "  both     Corrupt both copies; the install should show the"
    echo "           damaged-Purple-Key error screen."
}

ISO="" WHICH="primary"
for arg in "$@"; do
    case "$arg" in
        -h|--help)           usage; exit 0 ;;
        primary|backup|both) WHICH="$arg" ;;
        *)                   ISO="$arg" ;;
    esac
done

if [[ -z "$ISO" ]]; then
    ISO="$(find_latest_iso backup)"
    if [[ -z "$ISO" ]]; then
        echo "ERROR: the newest build has no with-backup ISO in $OUTPUT_DIR." >&2
        echo "Build one with: PURPLE_WITH_BACKUP_ISO=1 just build" >&2
        echo "Or pass an ISO path explicitly." >&2
        exit 1
    fi
    echo "Using newest with-backup ISO: $(basename "$ISO")"
fi
if [[ ! -f "$ISO" ]]; then
    echo "ERROR: ISO not found: $ISO" >&2
    usage
    exit 1
fi
OUT="${ISO%.iso}.corrupt-test-${WHICH}.iso"

corrupt() {
    local path="$1" lba
    lba="$(xorriso -indev "$OUT" -find "$path" -exec report_lba -- 2>/dev/null \
        | awk -F, '/File data lba/ {gsub(/ /, "", $2); print $2}')"
    if [[ -z "$lba" ]]; then
        echo "ERROR: $path not found in $OUT" >&2
        echo "(backup copies only exist in .with-backup.iso builds)" >&2
        exit 1
    fi
    # 8 MiB into the file: past the zstd header, early enough that the install
    # write fails within seconds instead of at 96%.
    local off=$(( lba * 2048 + 8*1024*1024 ))
    head -c 65536 /dev/zero | tr '\0' 'X' \
        | sudo dd of="$OUT" bs=64K seek="$off" oflag=seek_bytes conv=notrunc status=none
    echo "Corrupted 64KiB of $path at byte offset $off"
}

# The output dir is owned by the Docker build (nobody:nogroup), so all writes
# need sudo. Prompt once up front rather than mid-copy.
sudo -v

echo "Copying $(basename "$ISO") -> $(basename "$OUT")..."
sudo cp --reflink=auto -f "$ISO" "$OUT"

case "$WHICH" in
    primary) corrupt /purple/purple-os.img.zst
             echo "Scenario '$WHICH': expect the install to self-heal from the backup copy." ;;
    backup)  corrupt /purple/purple-os-backup.img.zst
             echo "Scenario '$WHICH': expect the install to succeed normally from the primary." ;;
    both)    corrupt /purple/purple-os.img.zst
             corrupt /purple/purple-os-backup.img.zst
             echo "Scenario '$WHICH': expect the install to show the damaged-Purple-Key screen." ;;
esac

sha256sum "$OUT" | sudo tee "${OUT}.sha256" >/dev/null
[[ -f "${ISO}.version" ]] && sudo cp -f "${ISO}.version" "${OUT}.version"

echo ""
echo "Done. Flash it with:  just flash-corrupt"
