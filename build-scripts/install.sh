#!/bin/bash
# PurpleOS Factory Installer
# Dead-simple disk reimaging: wipe, write image, install bootloader, reboot

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[PURPLE]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Find target disk (first non-USB disk)
find_target() {
    # Get first internal disk (skip USB)
    lsblk -dno NAME,TYPE,TRAN | awk '$2=="disk" && $3!="usb" {print $1; exit}'
}

main() {
    log "PurpleOS Factory Installer"
    log "=========================="

    # Ensure /sys is mounted (needed for lsblk)
    if [ ! -d /sys/dev ]; then
        mount -t sysfs sys /sys 2>/dev/null || true
    fi

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
