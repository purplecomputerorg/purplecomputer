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
        --include=linux-image-generic,initramfs-tools,systemd,systemd-sysv,sudo,vim-tiny,less \
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

    # We skip grub-install and update-grub entirely - they create complex configs that
    # don't work well with our standalone GRUB. Instead we use grub-mkstandalone for
    # the bootloader and create our own minimal grub.cfg.

    # Create minimal grub.cfg for the installed system
    # This is what gets loaded when our standalone BOOTX64.EFI calls configfile
    log_info "Creating minimal GRUB configuration..."
    mkdir -p "$MOUNT_DIR/boot/grub"
    cat > "$MOUNT_DIR/boot/grub/grub.cfg" <<'EOF'
# PurpleOS minimal GRUB configuration
set timeout=3
set default=0

menuentry "PurpleOS" {
    search --no-floppy --label PURPLE_ROOT --set=root
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro quiet console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}

menuentry "PurpleOS (recovery mode)" {
    search --no-floppy --label PURPLE_ROOT --set=root
    linux /boot/vmlinuz root=LABEL=PURPLE_ROOT ro single console=tty0 console=ttyS0,115200n8
    initrd /boot/initrd.img
}
EOF

    # Create symlinks to actual kernel/initrd (Ubuntu installs versioned files)
    # This makes our grub.cfg work regardless of kernel version
    KERNEL_VERSION=$(ls "$MOUNT_DIR/boot/" | grep "vmlinuz-" | head -1 | sed 's/vmlinuz-//')
    if [ -n "$KERNEL_VERSION" ]; then
        ln -sf "vmlinuz-$KERNEL_VERSION" "$MOUNT_DIR/boot/vmlinuz"
        ln -sf "initrd.img-$KERNEL_VERSION" "$MOUNT_DIR/boot/initrd.img"
        log_info "  Kernel version: $KERNEL_VERSION"
    fi

    # Create fallback bootloader using grub-mkstandalone for maximum hardware compatibility
    # Ubuntu's grubx64.efi may not have all modules (e.g., serial) built in
    # grub-mkstandalone ensures we have all modules needed for debugging and boot
    log_info "Creating UEFI fallback bootloader with grub-mkstandalone..."
    mkdir -p "$MOUNT_DIR/boot/efi/EFI/BOOT"

    # Create the grub.cfg that will be embedded in the standalone EFI binary
    cat > /tmp/grub-standalone.cfg <<'EOF'
# GRUB standalone fallback bootloader for PurpleOS
# Using grub-mkstandalone avoids prefix/UUID mismatch issues with copied grubx64.efi

# Enable console output first (before serial, so we see something even if serial fails)
terminal_output console
set debug=all
set pager=0

# Setup serial console for debugging
serial --unit=0 --speed=115200
terminal_input console serial
terminal_output console serial

echo "GRUB: PurpleOS standalone bootloader starting..."

search --no-floppy --label PURPLE_ROOT --set=root

if [ -z "$root" ]; then
    echo "ERROR: Could not find PURPLE_ROOT partition"
    echo "Listing available devices:"
    ls
    sleep 30
else
    echo "SUCCESS: Found root=$root"
    set prefix=($root)/boot/grub
    echo "Loading config from $prefix/grub.cfg"
    configfile ($root)/boot/grub/grub.cfg
fi
EOF

    # Generate standalone GRUB EFI with all required modules
    grub-mkstandalone \
        --format=x86_64-efi \
        --output="$MOUNT_DIR/boot/efi/EFI/BOOT/BOOTX64.EFI" \
        --modules="part_gpt part_msdos fat ext2 normal linux configfile search search_label efi_gop efi_uga all_video video video_bochs video_cirrus video_fb gfxterm gfxterm_background terminal terminfo font echo test serial" \
        --locales="" \
        "boot/grub/grub.cfg=/tmp/grub-standalone.cfg"

    rm -f /tmp/grub-standalone.cfg

    # Cleanup
    log_info "Cleaning up..."
    sync
    umount "$MOUNT_DIR/boot/efi"
    umount "$MOUNT_DIR"
    kpartx -dv "$LOOP_DEV"
    losetup -d "$LOOP_DEV"

    # Compress golden image
    log_info "Compressing golden image..."
    zstd -19 -T0 -f "$GOLDEN_IMAGE" -o "$GOLDEN_COMPRESSED"

    log_info "✓ Golden image ready: $GOLDEN_COMPRESSED"
    log_info "  Original size: $(du -h $GOLDEN_IMAGE | cut -f1)"
    log_info "  Compressed: $(du -h $GOLDEN_COMPRESSED | cut -f1)"

    # Delete uncompressed image to save space
    rm -f "$GOLDEN_IMAGE"
}

main "$@"
