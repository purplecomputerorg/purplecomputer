#!/usr/bin/env bash
# Test the install.sh partition layout + BIOS grub-install against a loop-backed
# fake disk. Catches parted option-parsing bugs, bios_grub flag issues, and
# grub-install failures without rebuilding an ISO or touching real hardware.
#
# Run: sudo build-scripts/test-install-partitioning.sh
# Exit code: 0 = all pass, non-zero = first failing check.

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}PASS${NC}  $1"; }
fail() { echo -e "${RED}FAIL${NC}  $1"; exit 1; }
info() { echo -e "${YELLOW}....${NC}  $1"; }

IMG="${TMPDIR:-/tmp}/purple-partition-test.img"
SIZE_GB=120
LOOP=""

cleanup() {
    set +e
    [ -n "$LOOP" ] && losetup -d "$LOOP" 2>/dev/null
    rm -f "$IMG"
}
trap cleanup EXIT

[ "$EUID" -eq 0 ] || fail "must run as root (needs losetup / grub-install)"

for t in parted losetup grub-install mkfs.ext4 xxd; do
    command -v "$t" >/dev/null || fail "missing tool: $t"
done

# -----------------------------------------------------------------------------
# 1. Create fake disk
# -----------------------------------------------------------------------------
info "creating ${SIZE_GB}GB sparse disk at $IMG"
rm -f "$IMG"
truncate -s "${SIZE_GB}G" "$IMG"

# -----------------------------------------------------------------------------
# 2. Run the EXACT parted sequence from install.sh. Any mismatch here means
#    this test is out of sync with install.sh and should be updated.
# -----------------------------------------------------------------------------
info "running install.sh parted sequence"
parted -s "$IMG" mklabel gpt                                    || fail "mklabel gpt"
parted -s "$IMG" mkpart ESP fat32 1MiB 513MiB                   || fail "mkpart ESP"
parted -s "$IMG" set 1 esp on                                   || fail "set 1 esp on"
parted -s "$IMG" -- mkpart primary ext4 513MiB -2MiB            || fail "mkpart root (negative offset; missing '--'?)"
parted -s "$IMG" -- mkpart primary -2MiB 100%                   || fail "mkpart bios_grub (negative start)"
parted -s "$IMG" set 3 bios_grub on                             || fail "set 3 bios_grub on"

pass "parted sequence completed without errors"

# -----------------------------------------------------------------------------
# 3. Verify the resulting layout
# -----------------------------------------------------------------------------
PRINT=$(parted -s "$IMG" print)
echo "$PRINT" | sed 's/^/        /'

# Use machine-readable output: "N:start:end:size:fs:name:flags;"
# The filesystem column is empty until mkfs runs — that's expected here.
MACH=$(parted -sm "$IMG" unit MiB print)
awk -F: -v m="$MACH" 'BEGIN{split(m,L,"\n")}' # no-op syntactic check

get_field() { awk -F: -v n="$1" -v f="$2" '$1==n{gsub(/;$/,"",$f); print $f}' <<<"$MACH"; }

P1_NAME=$(get_field 1 6); P1_FLAGS=$(get_field 1 7)
P2_NAME=$(get_field 2 6)
P3_NAME=$(get_field 3 6); P3_FLAGS=$(get_field 3 7); P3_SIZE=$(get_field 3 4)

[ "$P1_NAME" = "ESP" ]                      || fail "p1 name is '$P1_NAME', expected 'ESP'"
[[ "$P1_FLAGS" == *esp* ]]                  || fail "p1 flags '$P1_FLAGS' missing 'esp'"
[ "$P2_NAME" = "primary" ]                  || fail "p2 name is '$P2_NAME', expected 'primary'"
[ "$P3_NAME" = "primary" ]                  || fail "p3 name is '$P3_NAME', expected 'primary'"
[[ "$P3_FLAGS" == *bios_grub* ]]            || fail "p3 flags '$P3_FLAGS' missing 'bios_grub'"
pass "3-partition layout present with correct names and flags"

# Sanity: p3 should be ~1-2MiB, not gigabytes (catches swapped offsets).
# Parted rounds to 1MiB-aligned boundaries so a `-2MiB` end can yield ~1MiB.
P3_INT=${P3_SIZE%.*}
[ "$P3_INT" -ge 1 ] && [ "$P3_INT" -le 3 ] || fail "p3 size is ${P3_SIZE}MiB, expected 1-3MiB"
pass "p3 size is ${P3_SIZE}MiB (within expected 1-3MiB)"

# -----------------------------------------------------------------------------
# 4. Attach loop device so partition block devs exist for grub-install
# -----------------------------------------------------------------------------
info "attaching loop device"
LOOP=$(losetup -fP --show "$IMG")
info "loop device: $LOOP (expect ${LOOP}p1, p2, p3)"
udevadm settle --timeout=5 2>/dev/null || true

for p in 1 2 3; do
    [ -b "${LOOP}p${p}" ] || fail "partition device ${LOOP}p${p} not created"
done
pass "partition block devices ${LOOP}p1/p2/p3 present"

# -----------------------------------------------------------------------------
# 5. Run grub-install --target=i386-pc exactly as install.sh Layer 6 does
# -----------------------------------------------------------------------------
info "formatting root and running grub-install --target=i386-pc"
mkfs.ext4 -q -F -L PURPLE_ROOT "${LOOP}p2"

ROOT_MNT=$(mktemp -d)
mount "${LOOP}p2" "$ROOT_MNT"
mkdir -p "$ROOT_MNT/boot/grub"

if grub-install --target=i386-pc \
                --boot-directory="$ROOT_MNT/boot" \
                --no-floppy \
                --recheck \
                "$LOOP" >/tmp/grub-bios-test.log 2>&1; then
    pass "grub-install --target=i386-pc succeeded"
else
    sed 's/^/        /' /tmp/grub-bios-test.log
    umount "$ROOT_MNT"; rmdir "$ROOT_MNT"
    fail "grub-install --target=i386-pc failed (see log above)"
fi

# core.img should exist in /boot/grub/i386-pc/
[ -f "$ROOT_MNT/boot/grub/i386-pc/core.img" ] || fail "core.img not copied to /boot/grub/i386-pc/"
pass "core.img present in /boot/grub/i386-pc/"

umount "$ROOT_MNT"; rmdir "$ROOT_MNT"

# -----------------------------------------------------------------------------
# 6. MBR should contain GRUB boot.img (non-zero first 446 bytes)
# -----------------------------------------------------------------------------
MBR_HEX=$(dd if="$LOOP" bs=446 count=1 2>/dev/null | xxd -p | tr -d '\n')
if [ "$MBR_HEX" = "$(printf '00%.0s' $(seq 1 446))" ]; then
    fail "MBR boot code is all zeros — grub-install did not write boot.img"
fi
# GRUB boot.img starts with an x86 jump (0xeb or 0xe9). Catches "something was
# written but it's not GRUB" (e.g. wrong --target).
FIRST_BYTE="${MBR_HEX:0:2}"
[ "$FIRST_BYTE" = "eb" ] || [ "$FIRST_BYTE" = "e9" ] \
    || fail "MBR first byte is 0x$FIRST_BYTE, expected 0xeb or 0xe9 (x86 jump / GRUB boot.img)"
pass "MBR contains x86 boot code (first byte 0x$FIRST_BYTE)"

echo
echo -e "${GREEN}All checks passed.${NC} The install.sh partition layout + BIOS"
echo "grub-install path is working against a loop-backed fake disk."
