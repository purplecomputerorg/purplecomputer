#!/bin/bash
# PurpleOS Factory Installer
# Called from the parent menu's install option (parent_menu.py)
#
# This script:
# 1. Detects the internal disk (excluding USB/removable devices)
# 2. Wipes the partition table
# 3. Writes the pre-built golden image (purple-os.img.zst)
# 4. Sets up UEFI boot with multi-layer fallback strategy
# 5. Returns to caller (which handles reboot)

set -eo pipefail

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

    # Decompress and write, teeing the decompressed stream to sha256sum so we
    # can verify the disk contents afterwards without decompressing again.
    # The tee sends the same bytes to both dd (disk write) and sha256sum (checksum).
    WRITE_SHA256_FILE="/tmp/purple-write-sha256"
    WRITE_SIZE_FILE="/tmp/purple-write-size"
    if command -v pv >/dev/null 2>&1; then
        zstd -dc "$GOLDEN_IMAGE" \
            | tee >(sha256sum | awk '{print $1}' > "$WRITE_SHA256_FILE") \
            | tee >(wc -c > "$WRITE_SIZE_FILE") \
            | pv -s $(zstd -l "$GOLDEN_IMAGE" 2>/dev/null | tail -1 | awk '{print $5}' || echo "2G") \
            | dd of=/dev/$TARGET bs=4M conv=fsync
    else
        zstd -dc "$GOLDEN_IMAGE" \
            | tee >(sha256sum | awk '{print $1}' > "$WRITE_SHA256_FILE") \
            | tee >(wc -c > "$WRITE_SIZE_FILE") \
            | dd of=/dev/$TARGET bs=4M status=progress conv=fsync
    fi

    # Force kernel to re-read partition table from the new image
    log "Reloading partition table..."
    sync

    # Post-write verification: read back from disk and compare to what we wrote.
    # This catches silent write failures (bad sectors, firmware lies, etc.).
    if [ -f "$WRITE_SHA256_FILE" ] && [ -s "$WRITE_SHA256_FILE" ] && [ -f "$WRITE_SIZE_FILE" ] && [ -s "$WRITE_SIZE_FILE" ]; then
        WRITE_SHA256=$(cat "$WRITE_SHA256_FILE")
        WRITE_SIZE=$(cat "$WRITE_SIZE_FILE" | tr -d ' ')
        log "Verifying disk write (this takes a few minutes)..."

        # Flush hardware write caches before reading back
        blockdev --flushbufs /dev/$TARGET 2>/dev/null || true
        hdparm -F /dev/$TARGET 2>/dev/null || true
        sleep 5

        # Drop page cache, then read back with O_DIRECT
        echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
        DISK_SHA256=$(dd if=/dev/$TARGET bs=4M count="$WRITE_SIZE" iflag=direct,count_bytes status=none 2>/dev/null | sha256sum | awk '{print $1}')

        if [ "$WRITE_SHA256" = "$DISK_SHA256" ]; then
            log "Disk verification passed (SHA256 match)"
        else
            warn "Disk verification: SHA256 mismatch"
            warn "  Expected: $WRITE_SHA256"
            warn "  Got:      $DISK_SHA256"
            error "Disk write verification failed. The installation may be corrupt."
        fi
        rm -f "$WRITE_SHA256_FILE" "$WRITE_SIZE_FILE"
    else
        warn "Could not capture write checksum, skipping verification"
    fi

    # Retry partition re-read: the kernel sometimes needs a moment after dd
    for attempt in 1 2 3 4 5; do
        blockdev --rereadpt /dev/$TARGET 2>/dev/null && break
        log "  Partition re-read attempt $attempt/5, retrying..."
        sleep 2
    done

    # Wait for partition devices to appear
    log "Waiting for partition devices..."
    for attempt in 1 2 3 4 5 6; do
        case "$TARGET" in
            nvme*|mmcblk*) PROBE_PART="/dev/${TARGET}p1" ;;
            *)             PROBE_PART="/dev/${TARGET}1" ;;
        esac
        [ -b "$PROBE_PART" ] && break
        log "  Waiting for $PROBE_PART (attempt $attempt/6)..."
        sleep 2
    done

    if [ ! -b "$PROBE_PART" ]; then
        error "Partition devices did not appear after writing disk image. The install may have failed."
    fi

    log "Partitions ready."

    # ==========================================================================
    # UEFI BOOT SETUP - See CLAUDE.md "UEFI Boot and Hardware Compatibility"
    # ==========================================================================
    # Signed boot chain: shim (Microsoft-signed) → GRUB (Canonical-signed) → kernel
    # Multiple EFI paths for hardware compatibility:
    # 1. /EFI/BOOT/BOOTX64.EFI (shim) + grubx64.efi - UEFI spec fallback
    # 2. /EFI/Microsoft/Boot/bootmgfw.efi (shim) + grubx64.efi - Surface, HP
    # 3. /EFI/purple/shimx64.efi + grubx64.efi - vendor path for NVRAM entry
    # 4. NVRAM Boot#### entry - bonus for compliant firmware
    # Plus: /EFI/ubuntu/grub.cfg has search config (signed GRUB's prefix)
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
        if mount "$EFI_PART" /mnt/efi; then

            # Layer 1: Standard fallback path (already in golden image)
            # shim (BOOTX64.EFI) loads grubx64.efi from same directory
            if [ -f /mnt/efi/EFI/BOOT/BOOTX64.EFI ] && [ -f /mnt/efi/EFI/BOOT/grubx64.efi ]; then
                log "  Layer 1: /EFI/BOOT/ shim + GRUB present"
            else
                warn "  Layer 1: signed boot files missing!"
            fi

            # Layer 2: Vendor path for NVRAM entry (shim + GRUB)
            mkdir -p /mnt/efi/EFI/purple
            cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/purple/shimx64.efi 2>/dev/null || true
            cp /mnt/efi/EFI/BOOT/grubx64.efi /mnt/efi/EFI/purple/grubx64.efi 2>/dev/null || true
            log "  Layer 2: /EFI/purple/ shim + GRUB"

            # Layer 3: Microsoft path (Surface, HP need this)
            # shim as bootmgfw.efi + grubx64.efi in same directory
            WINDOWS_DETECTED=0
            if [ -f /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi ]; then
                MS_SIZE=$(stat -c%s /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi 2>/dev/null || echo 0)
                # Windows bootmgfw.efi is ~1.5-2.5MB, our shim is smaller (~1.2MB)
                if [ "$MS_SIZE" -gt 1500000 ] && [ "$MS_SIZE" -lt 2800000 ]; then
                    log "  Layer 3: Windows detected, preserving bootmgfw.efi"
                    WINDOWS_DETECTED=1
                fi
            fi
            if [ "$WINDOWS_DETECTED" -eq 0 ]; then
                mkdir -p /mnt/efi/EFI/Microsoft/Boot
                cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi
                cp /mnt/efi/EFI/BOOT/grubx64.efi /mnt/efi/EFI/Microsoft/Boot/grubx64.efi
                log "  Layer 3: /EFI/Microsoft/Boot/ shim + GRUB"
            fi

            # Layer 4: NVRAM entry (bonus, not required)
            # Points to shim, which chain-loads grubx64.efi
            if command -v efibootmgr >/dev/null 2>&1; then
                # Remove existing PurpleOS entries
                for bootnum in $(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9A-Fa-f]+" | sed 's/Boot//' || true); do
                    efibootmgr -b "$bootnum" -B 2>/dev/null || true
                done

                if efibootmgr -c -d "/dev/$TARGET" -p 1 -L "PurpleOS" -l '\EFI\purple\shimx64.efi' 2>/dev/null; then
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

            # Layer 5 (EFI part): Update search config with UUID
            if [ -n "$ROOT_UUID" ] && [ -f /mnt/efi/EFI/ubuntu/grub.cfg ]; then
                sed -i "s|search --no-floppy --label PURPLE_ROOT|search --no-floppy --fs-uuid $ROOT_UUID|g" /mnt/efi/EFI/ubuntu/grub.cfg
                log "  Layer 5: Updated EFI search config with UUID"
            fi

            umount /mnt/efi 2>/dev/null || true
        else
            warn "Could not mount EFI partition"
        fi

        # Layer 5 (root part): Update grub.cfg with UUID
        if [ -n "$ROOT_UUID" ]; then
            if mount "$ROOT_PART" /mnt/root 2>/dev/null; then
                if [ -f /mnt/root/boot/grub/grub.cfg ]; then
                    sed -i "s|root=LABEL=PURPLE_ROOT|root=UUID=$ROOT_UUID|g" /mnt/root/boot/grub/grub.cfg
                    sed -i "s|search --no-floppy --label PURPLE_ROOT|search --no-floppy --fs-uuid $ROOT_UUID|g" /mnt/root/boot/grub/grub.cfg
                    log "  Layer 5: Updated root grub.cfg with UUID"
                fi
                umount /mnt/root 2>/dev/null || true
            fi
        fi

        rmdir /mnt/efi /mnt/root 2>/dev/null || true
        log "UEFI boot setup complete"
    else
        error "EFI partition not found at $EFI_PART. Cannot set up boot."
    fi

    log ""
    log "============================================"
    log "Installation complete!"
    log "============================================"

    # Sentinel file so the TUI can detect completion even if proc.returncode
    # never gets set (can happen when a background child holds the process alive)
    touch /run/purple-install-complete

    # Return success - the initramfs hook handles reboot/user interaction
    # This keeps install.sh focused on disk operations only
    exit 0
}

main "$@"
