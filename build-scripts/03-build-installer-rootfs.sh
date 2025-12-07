#!/usr/bin/env bash
# Build installer rootfs
# This is the environment that runs install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
ROOTFS_DIR="${BUILD_DIR}/installer-rootfs"
ROOTFS_IMG="${BUILD_DIR}/installer.ext4"
GOLDEN_COMPRESSED="${BUILD_DIR}/purple-os.img.zst"

GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

main() {
    log_info "Building installer rootfs..."

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    if [ ! -f "$GOLDEN_COMPRESSED" ]; then
        echo "ERROR: Golden image not found at $GOLDEN_COMPRESSED"
        echo "Run 01-build-golden-image.sh first"
        exit 1
    fi

    mkdir -p "$BUILD_DIR"
    rm -rf "$ROOTFS_DIR"

    # Build minimal rootfs with installation tools
    log_info "Creating installer environment with debootstrap..."
    debootstrap \
        --arch=amd64 \
        --variant=minbase \
        --include=zstd,gdisk,grub-efi-amd64-bin,dosfstools,e2fsprogs \
        noble \
        "$ROOTFS_DIR" \
        http://archive.ubuntu.com/ubuntu

    # Copy install script
    log_info "Installing install.sh..."
    cp "$SCRIPT_DIR/install.sh" "$ROOTFS_DIR/"
    chmod +x "$ROOTFS_DIR/install.sh"

    # Copy golden image
    log_info "Embedding PurpleOS golden image..."
    cp "$GOLDEN_COMPRESSED" "$ROOTFS_DIR/"

    # Create filesystem image
    log_info "Creating ext4 filesystem..."
    ROOTFS_SIZE=$(du -sm "$ROOTFS_DIR" | cut -f1)
    ROOTFS_SIZE_PADDED=$((ROOTFS_SIZE + 500))  # Add 500MB padding

    dd if=/dev/zero of="$ROOTFS_IMG" bs=1M count="$ROOTFS_SIZE_PADDED" status=progress
    mkfs.ext4 -L PURPLE_INSTALLER "$ROOTFS_IMG"

    # Copy rootfs to image
    log_info "Copying installer rootfs to filesystem..."
    MOUNT_DIR="${BUILD_DIR}/mnt-installer"
    mkdir -p "$MOUNT_DIR"
    mount "$ROOTFS_IMG" "$MOUNT_DIR"
    cp -a "$ROOTFS_DIR"/* "$MOUNT_DIR/"
    sync
    umount "$MOUNT_DIR"

    log_info "✓ Installer rootfs ready: $ROOTFS_IMG"
    log_info "  Size: $(du -h $ROOTFS_IMG | cut -f1)"
}

main "$@"
