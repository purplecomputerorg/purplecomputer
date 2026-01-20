#!/bin/bash
# PurpleOS Factory Installer
# Runs from Gate 2 confirmation script (purple-confirm.sh)
#
# TWO-GATE SAFETY MODEL:
#   Gate 1 (initramfs): Checks purple.install=1, sets /run/purple/armed marker
#   Gate 2 (systemd): Shows confirmation screen, requires ENTER to proceed
#   This script: Only runs AFTER user confirms in Gate 2
#
# This script:
# 1. Detects the internal disk (excluding USB/removable devices)
# 2. Wipes the partition table
# 3. Writes the pre-built golden image (purple-os.img.zst)
# 4. Sets up UEFI boot with multi-layer fallback strategy
# 5. Returns to caller (which handles reboot)

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Loud logging to console for debugging
log() {
    echo -e "${GREEN}[PURPLE]${NC} $1" >&2
    echo "[PURPLE] $1" >/dev/console 2>/dev/null || true
}
warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
    echo "[PURPLE WARN] $1" >/dev/console 2>/dev/null || true
}
error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    echo "[PURPLE ERROR] $1" >/dev/console 2>/dev/null || true
    exit 1
}

# Golden image path - set by hook via PURPLE_PAYLOAD_DIR
GOLDEN_IMAGE="${PURPLE_PAYLOAD_DIR:-/purple}/purple-os.img.zst"

# Spawn emergency shell on tty2 (user can access with Alt+F2)
if [ -c /dev/tty2 ]; then
    log "Emergency shell available on tty2 (Alt+F2)"
    setsid bash </dev/tty2 >/dev/tty2 2>&1 &
fi

# Display splash screen
show_splash() {
    clear
    echo ""
    echo -e "${PURPLE}=================================================${NC}"
    echo -e "${PURPLE}                                                 ${NC}"
    echo -e "${PURPLE}          Purple Computer Installer              ${NC}"
    echo -e "${PURPLE}                                                 ${NC}"
    echo -e "${PURPLE}=================================================${NC}"
    echo ""
    echo ""
}

# Find target disk (exclude USB/removable devices and the boot device)
find_target() {
    log "Detecting internal disk..."

    # In casper live environment, we need to identify and exclude the boot device
    local boot_dev=""

    # Method 1: Check /proc/cmdline for boot device hints from casper
    if grep -q "boot=casper" /proc/cmdline 2>/dev/null; then
        # Casper stores boot device info
        if [ -f /run/casper/rootfs.list ]; then
            log "  Found casper rootfs info"
        fi
    fi

    # Method 2: Find the device containing the live filesystem
    # The ISO volume is labeled PURPLE_INSTALLER
    local iso_dev=""
    iso_dev=$(blkid -L PURPLE_INSTALLER 2>/dev/null | sed 's/[0-9]*$//' || true)
    if [ -n "$iso_dev" ]; then
        boot_dev=$(basename "$iso_dev")
        log "  Boot device (ISO): $boot_dev"
    fi

    # Iterate through all block devices
    for disk in /sys/block/*; do
        [ -d "$disk" ] || continue
        local name=$(basename "$disk")

        # Skip loop, ram, rom devices
        case "$name" in
            loop*|ram*|sr*|dm-*) continue ;;
        esac

        # Skip the boot device
        if [ "$name" = "$boot_dev" ]; then
            log "  Skipping $name (boot device)"
            continue
        fi

        # Skip removable devices
        if [ -f "$disk/removable" ] && [ "$(cat $disk/removable)" = "1" ]; then
            log "  Skipping $name (removable)"
            continue
        fi

        # Check transport - skip USB
        local transport=""
        if [ -f "$disk/device/transport" ]; then
            transport=$(cat "$disk/device/transport" 2>/dev/null || echo "")
        fi
        # Also check via udevadm for more reliable detection
        if [ -z "$transport" ]; then
            transport=$(udevadm info --query=property --name=/dev/$name 2>/dev/null | grep "^ID_BUS=" | cut -d= -f2 || echo "")
        fi

        if [ "$transport" = "usb" ]; then
            log "  Skipping $name (USB transport)"
            continue
        fi

        # This appears to be an internal disk
        log "  Found internal disk: $name"
        echo "$name"
        return 0
    done

    return 1
}

# Get disk size in human-readable format
get_disk_size() {
    local disk="$1"
    local size_bytes=$(cat /sys/block/$disk/size 2>/dev/null || echo 0)
    local size_gb=$((size_bytes * 512 / 1024 / 1024 / 1024))
    echo "${size_gb}GB"
}

# Main installation routine
main() {
    show_splash

    log "Purple Computer Factory Installer"
    log "=================================="
    log ""

    # Find target disk
    TARGET=$(find_target) || error "No target disk found. Is there an internal disk?"

    TARGET_SIZE=$(get_disk_size "$TARGET")
    log "Target disk: /dev/$TARGET ($TARGET_SIZE)"

    # Safety check: Verify device exists and is a block device
    if [ ! -b "/dev/$TARGET" ]; then
        error "Device /dev/$TARGET is not a valid block device"
    fi

    # Check minimum disk size (need at least 16GB for golden image)
    local size_bytes=$(cat /sys/block/$TARGET/size 2>/dev/null || echo 0)
    local size_gb=$((size_bytes * 512 / 1024 / 1024 / 1024))
    if [ "$size_gb" -lt 16 ]; then
        error "Disk too small: ${size_gb}GB (minimum 16GB required)"
    fi

    log ""
    log "WARNING: This will ERASE ALL DATA on /dev/$TARGET"
    log ""
    sleep 3

    # Verify golden image exists
    if [ ! -f "$GOLDEN_IMAGE" ]; then
        error "Golden image not found: $GOLDEN_IMAGE"
    fi

    # Write golden image directly to disk
    log "Writing Purple Computer to disk..."
    log "  Source: $GOLDEN_IMAGE"
    log "  Target: /dev/$TARGET"
    log "  This will take approximately 10-15 minutes..."
    log ""

    # Use pv for progress if available, otherwise dd with status=progress
    if command -v pv >/dev/null 2>&1; then
        zstd -dc "$GOLDEN_IMAGE" | pv -s $(zstd -l "$GOLDEN_IMAGE" 2>/dev/null | tail -1 | awk '{print $5}' || echo "2G") | dd of=/dev/$TARGET bs=4M conv=fsync
    else
        zstd -dc "$GOLDEN_IMAGE" | dd of=/dev/$TARGET bs=4M status=progress conv=fsync
    fi

    # Force kernel to re-read partition table from the new image
    log "Reloading partition table..."
    sync
    blockdev --rereadpt /dev/$TARGET || true
    sleep 2

    log "Verifying partitions..."
    ls -la /dev/${TARGET}* 2>/dev/null || warn "Partition devices not visible yet"

    # ==========================================================================
    # UEFI BOOT SETUP - See CLAUDE.md "UEFI Boot and Hardware Compatibility"
    # ==========================================================================
    # Multiple EFI paths for hardware compatibility:
    # 1. /EFI/BOOT/BOOTX64.EFI - UEFI spec fallback (all firmware)
    # 2. /EFI/Microsoft/Boot/bootmgfw.efi - Surface, HP firmware bias
    # 3. /EFI/purple/grubx64.efi - vendor path for NVRAM entry
    # 4. NVRAM Boot#### entry - bonus for compliant firmware
    # Plus: Update grub.cfg with actual UUID for deterministic boot
    # ==========================================================================

    log "Setting up UEFI boot..."

    # Determine partition device names
    case "$TARGET" in
        nvme*|mmcblk*)
            EFI_PART="/dev/${TARGET}p1"
            ROOT_PART="/dev/${TARGET}p2"
            ;;
        *)
            EFI_PART="/dev/${TARGET}1"
            ROOT_PART="/dev/${TARGET}2"
            ;;
    esac

    # Get root UUID for deterministic boot (critical fix for multi-disk systems)
    ROOT_UUID=$(blkid -s UUID -o value "$ROOT_PART" 2>/dev/null || true)
    if [ -n "$ROOT_UUID" ]; then
        log "  Root UUID: $ROOT_UUID"
    else
        warn "  Could not get root UUID, falling back to label-based boot"
    fi

    if [ -b "$EFI_PART" ]; then
        mkdir -p /mnt/efi /mnt/root
        if mount "$EFI_PART" /mnt/efi 2>/dev/null; then

            # Layer 1: Standard fallback path (already in golden image)
            if [ -f /mnt/efi/EFI/BOOT/BOOTX64.EFI ]; then
                log "  Layer 1: /EFI/BOOT/BOOTX64.EFI present"
            else
                warn "  Layer 1: BOOTX64.EFI missing!"
            fi

            # Layer 2: Vendor path for NVRAM entry
            mkdir -p /mnt/efi/EFI/purple
            cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/purple/grubx64.efi 2>/dev/null || true
            log "  Layer 2: /EFI/purple/grubx64.efi"

            # Layer 3: Microsoft path (Surface, HP need this)
            # Check for existing Windows first
            WINDOWS_DETECTED=0
            if [ -f /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi ]; then
                MS_SIZE=$(stat -c%s /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi 2>/dev/null || echo 0)
                # Windows bootmgfw.efi is ~1.5-2.5MB, our GRUB is ~3-6MB
                if [ "$MS_SIZE" -gt 1000000 ] && [ "$MS_SIZE" -lt 2800000 ]; then
                    log "  Layer 3: Windows detected, preserving bootmgfw.efi"
                    WINDOWS_DETECTED=1
                fi
            fi
            if [ "$WINDOWS_DETECTED" -eq 0 ]; then
                mkdir -p /mnt/efi/EFI/Microsoft/Boot
                cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi
                log "  Layer 3: /EFI/Microsoft/Boot/bootmgfw.efi"
            fi

            # Layer 4: NVRAM entry (bonus, not required)
            if command -v efibootmgr >/dev/null 2>&1; then
                # Remove existing PurpleOS entries
                for bootnum in $(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9A-Fa-f]+" | sed 's/Boot//' || true); do
                    efibootmgr -b "$bootnum" -B 2>/dev/null || true
                done

                if efibootmgr -c -d "/dev/$TARGET" -p 1 -L "PurpleOS" -l '\EFI\purple\grubx64.efi' 2>/dev/null; then
                    log "  Layer 4: NVRAM entry created"
                    # Set boot order
                    PURPLE_BOOTNUM=$(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9A-Fa-f]+" | head -1 | sed 's/Boot//')
                    if [ -n "$PURPLE_BOOTNUM" ]; then
                        CURRENT_ORDER=$(efibootmgr 2>/dev/null | grep "BootOrder:" | sed 's/BootOrder: //')
                        NEW_ORDER="$PURPLE_BOOTNUM"
                        for entry in $(echo "$CURRENT_ORDER" | tr ',' ' '); do
                            [ "$entry" != "$PURPLE_BOOTNUM" ] && NEW_ORDER="$NEW_ORDER,$entry"
                        done
                        efibootmgr -o "$NEW_ORDER" 2>/dev/null || true
                    fi
                else
                    log "  Layer 4: NVRAM entry failed (fallback paths will work)"
                fi
            fi

            umount /mnt/efi 2>/dev/null || true
        else
            warn "Could not mount EFI partition"
        fi

        # Layer 5: Update grub.cfg with UUID (critical for multi-disk reliability)
        if [ -n "$ROOT_UUID" ] && mount "$ROOT_PART" /mnt/root 2>/dev/null; then
            if [ -f /mnt/root/boot/grub/grub.cfg ]; then
                # Replace label-based with UUID-based
                sed -i "s|root=LABEL=PURPLE_ROOT|root=UUID=$ROOT_UUID|g" /mnt/root/boot/grub/grub.cfg
                sed -i "s|search --no-floppy --label PURPLE_ROOT|search --no-floppy --fs-uuid $ROOT_UUID|g" /mnt/root/boot/grub/grub.cfg
                log "  Layer 5: Updated grub.cfg with UUID"
            fi
            umount /mnt/root 2>/dev/null || true
        fi

        rmdir /mnt/efi /mnt/root 2>/dev/null || true
        log "UEFI boot setup complete"
    else
        warn "EFI partition not found"
    fi

    log ""
    log "============================================"
    log "Installation complete!"
    log "============================================"

    # Return success - the initramfs hook handles reboot/user interaction
    # This keeps install.sh focused on disk operations only
    exit 0
}

main "$@"
