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

# 4. EFI paths (signed boot chain: shim + GRUB in each directory)
EFI_MOUNT=$(findmnt -n -o TARGET /boot/efi 2>/dev/null || echo "/boot/efi")
if [ -d "$EFI_MOUNT/EFI" ]; then
    # Layer 1: UEFI spec fallback (shim + signed GRUB)
    [ -f "$EFI_MOUNT/EFI/BOOT/BOOTX64.EFI" ] && pass "/EFI/BOOT/BOOTX64.EFI (shim)" || fail "/EFI/BOOT/BOOTX64.EFI missing"
    [ -f "$EFI_MOUNT/EFI/BOOT/grubx64.efi" ] && pass "/EFI/BOOT/grubx64.efi (signed GRUB)" || fail "/EFI/BOOT/grubx64.efi missing"
    # Search config (signed GRUB loads this via its compiled-in prefix)
    [ -f "$EFI_MOUNT/EFI/ubuntu/grub.cfg" ] && pass "/EFI/ubuntu/grub.cfg (search config)" || fail "/EFI/ubuntu/grub.cfg missing"
    # Layer 2: Vendor path for NVRAM
    [ -f "$EFI_MOUNT/EFI/purple/shimx64.efi" ] && pass "/EFI/purple/shimx64.efi" || warn "/EFI/purple/shimx64.efi missing"
    [ -f "$EFI_MOUNT/EFI/purple/grubx64.efi" ] && pass "/EFI/purple/grubx64.efi" || warn "/EFI/purple/grubx64.efi missing"
    # Layer 3: Microsoft path (Surface, HP)
    [ -f "$EFI_MOUNT/EFI/Microsoft/Boot/bootmgfw.efi" ] && pass "/EFI/Microsoft/Boot/bootmgfw.efi (shim)" || warn "/EFI/Microsoft/Boot/ missing"
    [ -f "$EFI_MOUNT/EFI/Microsoft/Boot/grubx64.efi" ] && pass "/EFI/Microsoft/Boot/grubx64.efi" || warn "/EFI/Microsoft/Boot/grubx64.efi missing"
else
    warn "EFI partition not mounted at $EFI_MOUNT"
fi

# 5. GRUB config (root partition)
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

# 5b. EFI search config (loaded by signed GRUB)
if [ -d "$EFI_MOUNT/EFI" ] && [ -f "$EFI_MOUNT/EFI/ubuntu/grub.cfg" ]; then
    if grep -q "search.*--fs-uuid" "$EFI_MOUNT/EFI/ubuntu/grub.cfg"; then
        pass "EFI search config uses UUID"
    elif grep -q "search.*--label" "$EFI_MOUNT/EFI/ubuntu/grub.cfg"; then
        warn "EFI search config uses label (not updated with UUID)"
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
