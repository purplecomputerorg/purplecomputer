#!/usr/bin/env bash
# Build PurpleOS Golden Image
# This creates a complete, bootable PurpleOS system as a disk image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
GOLDEN_IMAGE="${BUILD_DIR}/purple-os.img"
GOLDEN_COMPRESSED="${BUILD_DIR}/purple-os.img.zst"
IMAGE_SIZE_MB=4096

# Colors
GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

main() {
    log_info "Building PurpleOS Golden Image..."

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    mkdir -p "$BUILD_DIR"

    # Create empty disk image
    log_info "Creating ${IMAGE_SIZE_MB}MB disk image..."
    dd if=/dev/zero of="$GOLDEN_IMAGE" bs=1M count="$IMAGE_SIZE_MB" status=progress

    # Create partition table
    log_info "Partitioning disk image..."
    parted -s "$GOLDEN_IMAGE" mklabel gpt
    parted -s "$GOLDEN_IMAGE" mkpart ESP fat32 1MiB 513MiB
    parted -s "$GOLDEN_IMAGE" set 1 esp on
    parted -s "$GOLDEN_IMAGE" mkpart primary ext4 513MiB 100%

    # Setup loop device with kpartx (more reliable in Docker)
    log_info "Setting up loop device..."
    LOOP_DEV=$(losetup -f --show "$GOLDEN_IMAGE")
    kpartx -av "$LOOP_DEV"

    # kpartx creates devices like /dev/mapper/loop0p1
    LOOP_NAME=$(basename "$LOOP_DEV")

    # Format partitions
    log_info "Formatting partitions..."
    mkfs.vfat -F32 "/dev/mapper/${LOOP_NAME}p1"
    mkfs.ext4 -L PURPLE_ROOT "/dev/mapper/${LOOP_NAME}p2"

    # Mount root partition
    MOUNT_DIR="${BUILD_DIR}/mnt-golden"
    mkdir -p "$MOUNT_DIR"
    mount "/dev/mapper/${LOOP_NAME}p2" "$MOUNT_DIR"
    mkdir -p "$MOUNT_DIR/boot/efi"
    mount "/dev/mapper/${LOOP_NAME}p1" "$MOUNT_DIR/boot/efi"

    # Install base system using debootstrap
    log_info "Installing base system with debootstrap..."
    debootstrap \
        --arch=amd64 \
        --variant=minbase \
        --include=linux-image-generic,grub-efi-amd64,systemd,sudo,vim-tiny,less \
        noble \
        "$MOUNT_DIR" \
        http://archive.ubuntu.com/ubuntu

    # Configure system
    log_info "Configuring PurpleOS..."

    # Set hostname
    echo "purplecomputer" > "$MOUNT_DIR/etc/hostname"

    # Create purple user
    chroot "$MOUNT_DIR" useradd -m -s /bin/bash purple
    chroot "$MOUNT_DIR" usermod -aG sudo purple
    echo "purple:purple" | chroot "$MOUNT_DIR" chpasswd

    # Bind mount necessary filesystems for grub-install
    log_info "Installing GRUB bootloader..."
    mount --bind /dev "$MOUNT_DIR/dev"
    mount --bind /proc "$MOUNT_DIR/proc"
    mount --bind /sys "$MOUNT_DIR/sys"

    chroot "$MOUNT_DIR" grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=PURPLE --no-nvram
    chroot "$MOUNT_DIR" update-grub

    # Unmount bind mounts
    umount "$MOUNT_DIR/dev"
    umount "$MOUNT_DIR/proc"
    umount "$MOUNT_DIR/sys"

    # Cleanup
    log_info "Cleaning up..."
    sync
    umount "$MOUNT_DIR/boot/efi"
    umount "$MOUNT_DIR"
    kpartx -dv "$LOOP_DEV"
    losetup -d "$LOOP_DEV"

    # Compress golden image
    log_info "Compressing golden image..."
    zstd -19 -T0 "$GOLDEN_IMAGE" -o "$GOLDEN_COMPRESSED"

    log_info "✓ Golden image ready: $GOLDEN_COMPRESSED"
    log_info "  Original size: $(du -h $GOLDEN_IMAGE | cut -f1)"
    log_info "  Compressed: $(du -h $GOLDEN_COMPRESSED | cut -f1)"
}

main "$@"
