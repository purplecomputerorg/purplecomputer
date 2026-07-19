#!/usr/bin/env bash
# Copy an ISO and deliberately corrupt golden image copies inside it, to test
# install.sh's backup-copy fallback and the corrupt-Key error screen end to
# end on real hardware or a VM. The output flashes normally (its .sha256
# sidecar matches the corrupted bytes) and boots normally; only the chosen
# copy fails its zstd integrity check during install.
#
# corrupt-test ISOs are never auto-picked by find_latest_iso; flash them by
# explicit path: just flash <output.iso>
set -euo pipefail

usage() {
    echo "Usage: $0 <iso> [primary|backup|both]"
    echo ""
    echo "  primary  Corrupt /purple/purple-os.img.zst (default). On a"
    echo "           with-backup ISO the install should recover via the backup."
    echo "  backup   Corrupt /purple/purple-os-backup.img.zst only."
    echo "  both     Corrupt both copies; the install should show the"
    echo "           damaged-Purple-Key error screen."
}

ISO="${1:-}"
WHICH="${2:-primary}"
if [[ -z "$ISO" || ! -f "$ISO" ]]; then
    usage
    exit 1
fi
OUT="${ISO%.iso}.corrupt-test.iso"

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
        | dd of="$OUT" bs=64K seek="$off" oflag=seek_bytes conv=notrunc status=none
    echo "Corrupted 64KiB of $path at byte offset $off"
}

echo "Copying $(basename "$ISO") -> $(basename "$OUT")..."
cp --reflink=auto -f "$ISO" "$OUT"

case "$WHICH" in
    primary) corrupt /purple/purple-os.img.zst ;;
    backup)  corrupt /purple/purple-os-backup.img.zst ;;
    both)    corrupt /purple/purple-os.img.zst
             corrupt /purple/purple-os-backup.img.zst ;;
    *)       usage; exit 1 ;;
esac

sha256sum "$OUT" > "${OUT}.sha256"
[[ -f "${ISO}.version" ]] && cp -f "${ISO}.version" "${OUT}.version"

echo ""
echo "Done. Flash it with:  just flash $OUT"
