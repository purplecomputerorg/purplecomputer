#!/bin/bash
# PurpleOS Factory Installer
# Dead-simple disk reimaging: wipe, write image, install bootloader, reboot

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[PURPLE]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Find target disk (anything except the boot disk)
find_target() {
    log "Detecting boot disk..."
    log "PURPLE_INSTALLER_DEV env var: ${PURPLE_INSTALLER_DEV:-NOT SET}"

    local boot_disk

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

    # Ensure pseudo-filesystems are mounted (needed for findmnt, lsblk, etc.)
    [ ! -d /proc/mounts ] && mount -t proc proc /proc 2>/dev/null || true
    [ ! -d /sys/dev ] && mount -t sysfs sys /sys 2>/dev/null || true

    TARGET=$(find_target)
    if [ -z "$TARGET" ]; then
        error "No target disk found"
    fi

    log "Target disk: /dev/$TARGET"
    log "WARNING: This will WIPE /dev/$TARGET"
    sleep 3

    # Wipe partition table
    log "Wiping disk..."
    sgdisk -Z /dev/$TARGET

    # Create partitions
    log "Creating partitions..."
    sgdisk -n 1:0:+512M -t 1:ef00 -c 1:"EFI" /dev/$TARGET
    sgdisk -n 2:0:0 -t 2:8300 -c 2:"PURPLE_ROOT" /dev/$TARGET

    # Write PurpleOS image to root partition
    log "Writing PurpleOS image (this takes ~10 min)..."
    zstd -dc /purple-os.img.zst | dd of=/dev/${TARGET}2 bs=4M status=progress

    # Mount partitions
    log "Installing bootloader..."
    mkdir -p /target
    mount /dev/${TARGET}2 /target
    mkdir -p /target/boot/efi
    mount /dev/${TARGET}1 /target/boot/efi

    # Install GRUB
    grub-install \
        --target=x86_64-efi \
        --efi-directory=/target/boot/efi \
        --boot-directory=/target/boot \
        --bootloader-id=PURPLE \
        /dev/$TARGET

    # Cleanup
    sync
    umount /target/boot/efi
    umount /target

    log "✓ Installation complete!"
    log "Rebooting in 3 seconds..."
    sleep 3
    reboot -f
}

main "$@"
