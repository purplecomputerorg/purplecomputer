#!/bin/bash
# diagnose-boot.sh - Quick UEFI boot health check for PurpleOS
# Run on a booted system to verify boot configuration

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
info() { echo "  $1"; }

echo ""
echo "=== Purple Computer Boot Diagnostics ==="
echo ""

# 1. Boot mode
if [ -d /sys/firmware/efi ]; then
    pass "UEFI mode"
else
    fail "BIOS mode (expected UEFI)"
fi

# 2. Root identification method
CMDLINE=$(cat /proc/cmdline)
if echo "$CMDLINE" | grep -q "root=UUID="; then
    pass "Root by UUID (reliable)"
elif echo "$CMDLINE" | grep -q "root=LABEL="; then
    warn "Root by LABEL (less reliable)"
else
    warn "Root by device path (may change between boots)"
fi

# 3. NVRAM entry
if command -v efibootmgr >/dev/null 2>&1; then
    if efibootmgr 2>/dev/null | grep -qi purple; then
        pass "NVRAM entry exists"
    else
        warn "No NVRAM entry (relying on fallback paths)"
    fi
fi

# 4. EFI paths
EFI_MOUNT=$(findmnt -n -o TARGET /boot/efi 2>/dev/null || echo "/boot/efi")
if [ -d "$EFI_MOUNT/EFI" ]; then
    [ -f "$EFI_MOUNT/EFI/BOOT/BOOTX64.EFI" ] && pass "/EFI/BOOT/BOOTX64.EFI" || fail "/EFI/BOOT/BOOTX64.EFI missing"
    [ -f "$EFI_MOUNT/EFI/purple/grubx64.efi" ] && pass "/EFI/purple/grubx64.efi" || warn "/EFI/purple/grubx64.efi missing"
    [ -f "$EFI_MOUNT/EFI/Microsoft/Boot/bootmgfw.efi" ] && pass "/EFI/Microsoft/Boot/bootmgfw.efi" || warn "/EFI/Microsoft/Boot/ missing"
else
    warn "EFI partition not mounted at $EFI_MOUNT"
fi

# 5. GRUB config
if [ -f /boot/grub/grub.cfg ]; then
    if grep -q "search.*--fs-uuid" /boot/grub/grub.cfg; then
        pass "grub.cfg uses UUID search"
    elif grep -q "search.*--label" /boot/grub/grub.cfg; then
        warn "grub.cfg uses label search"
    fi

    if grep -q "root=UUID=" /boot/grub/grub.cfg; then
        pass "grub.cfg passes UUID to kernel"
    elif grep -q "root=LABEL=" /boot/grub/grub.cfg; then
        warn "grub.cfg passes LABEL to kernel"
    fi
fi

# 6. Duplicate labels
PURPLE_COUNT=$(blkid 2>/dev/null | grep -c 'LABEL="PURPLE_ROOT"' || echo 0)
if [ "$PURPLE_COUNT" -gt 1 ]; then
    fail "Multiple PURPLE_ROOT partitions ($PURPLE_COUNT) - boot may be non-deterministic!"
elif [ "$PURPLE_COUNT" -eq 1 ]; then
    pass "Single PURPLE_ROOT partition"
fi

# 7. Hardware info
VENDOR=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null || echo "Unknown")
PRODUCT=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "Unknown")
info "Hardware: $VENDOR $PRODUCT"

echo ""
