#!/bin/bash
# PurpleOS Factory Installer
# Dead-simple disk reimaging: wipe, write image, install bootloader, reboot

set -e

echo "[DEBUG] install.sh started, set -e active"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[PURPLE]${NC} $1" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# Find target disk (anything except the boot disk)
find_target() {
    echo "[DEBUG] find_target() entered" >&2
    log "Detecting boot disk..."
    echo "[DEBUG] About to check PURPLE_INSTALLER_DEV" >&2
    log "PURPLE_INSTALLER_DEV env var: ${PURPLE_INSTALLER_DEV:-NOT SET}"
    echo "[DEBUG] Declaring local boot_disk" >&2

    local boot_disk
    echo "[DEBUG] local boot_disk declared" >&2

    # The init script passed us the installer partition device
    if [ -n "$PURPLE_INSTALLER_DEV" ]; then
        log "Installer partition: $PURPLE_INSTALLER_DEV"

        # Strip partition number to get parent disk
        # Handle: /dev/sda2 -> sda, /dev/vda1 -> vda, /dev/nvme0n1p2 -> nvme0n1
        # Use basic sed without -E for better compatibility
        boot_disk=$(echo "$PURPLE_INSTALLER_DEV" | sed 's|/dev/||' | sed 's/p*[0-9]*$//')
        log "Boot disk: $boot_disk"
    else
        log "WARNING: PURPLE_INSTALLER_DEV not set, falling back to partition detection"

        # Fallback: assume the disk with partitions is the boot disk
        for disk in /sys/block/*; do
            local disk_name
            disk_name=$(basename "$disk")

            case "$disk_name" in
                loop*|ram*|sr*) continue ;;
            esac

            # Check if has partition subdirectories with "partition" file
            for part in "$disk"/*; do
                if [ -f "$part/partition" ]; then
                    boot_disk="$disk_name"
                    log "Boot disk: $boot_disk (has partitions - fallback method)"
                    break 2
                fi
            done
        done
    fi

    log "Boot disk identified as: $boot_disk"

    # Find first disk that isn't the boot disk
    for disk in /sys/block/*; do
        name=$(basename "$disk")

        # Skip loop, ram, rom devices
        case "$name" in
            loop*|ram*|sr*) continue ;;
        esac

        # Skip the boot disk
        if [ "$name" = "$boot_disk" ]; then
            log "Skipping $name (boot disk)"
            continue
        fi

        log "Selected target: $name"
        echo "$name"
        return 0
    done

    log "ERROR: No target disk found (only boot disk available)"
    return 1
}

main() {
    log "PurpleOS Factory Installer"
    log "=========================="

    log "About to call find_target..."
    set +e  # Temporarily disable exit-on-error
    TARGET=$(find_target)
    FIND_EXIT=$?
    set -e  # Re-enable exit-on-error
    log "find_target returned: $TARGET (exit code: $FIND_EXIT)"

    if [ $FIND_EXIT -ne 0 ] || [ -z "$TARGET" ]; then
        error "No target disk found"
    fi

    log "Target disk: /dev/$TARGET"

    # Debug: Check if device actually exists and is accessible
    log "Checking device /dev/$TARGET..."
    ls -la /dev/$TARGET || log "ERROR: Device node doesn't exist!"
    [ -b /dev/$TARGET ] && log "Device is a block device" || log "ERROR: Not a block device!"

    log "WARNING: This will WIPE /dev/$TARGET"
    sleep 3

    # Write PurpleOS golden image to entire disk
    # The image contains: GPT partition table + EFI partition + root partition + bootloader
    log "Writing PurpleOS image to disk (this takes ~10 min)..."
    zstd -dc /purple-os.img.zst | dd of=/dev/$TARGET bs=4M status=progress

    # Force kernel to re-read partition table from the new image
    log "Reloading partition table..."
    sync
    blockdev --rereadpt /dev/$TARGET || true
    sleep 2  # Give kernel time to recognize new partitions

    log "Verifying partitions..."
    ls -la /dev/${TARGET}* || log "Warning: partition devices not visible yet"

    # Register PurpleOS in UEFI boot order (required for Surface and some other laptops)
    log "Registering PurpleOS in UEFI boot menu..."

    # Determine EFI partition device name
    # For nvme: /dev/nvme0n1p1, for sata: /dev/sda1
    case "$TARGET" in
        nvme*) EFI_PART="/dev/${TARGET}p1" ;;
        *)     EFI_PART="/dev/${TARGET}1" ;;
    esac

    if [ -b "$EFI_PART" ]; then
        # Mount EFI partition temporarily (/mnt/efi created at build time)
        if mount "$EFI_PART" /mnt/efi 2>/dev/null; then
            if command -v efibootmgr >/dev/null 2>&1; then
                # Remove any existing PurpleOS entries first
                for bootnum in $(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9]+" | sed 's/Boot//'); do
                    efibootmgr -b "$bootnum" -B 2>/dev/null || true
                done

                # Create new boot entry pointing to our bootloader
                efibootmgr -c -d "/dev/$TARGET" -p 1 -L "PurpleOS" -l '\EFI\BOOT\BOOTX64.EFI' 2>/dev/null && \
                    log "Added PurpleOS to UEFI boot menu" || \
                    log "Warning: Could not add UEFI boot entry (may need manual setup)"
            else
                log "Warning: efibootmgr not available"
            fi
            umount /mnt/efi 2>/dev/null || true
        else
            log "Warning: Could not mount EFI partition"
        fi
    fi

    log "Installation complete!"
    log "Rebooting in 5 seconds... Remove USB drive now."
    sleep 5
    # Use busybox reboot or kernel reboot syscall
    /bin/busybox reboot -f || echo b > /proc/sysrq-trigger
}

main "$@"
