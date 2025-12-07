#!/usr/bin/env bash
# Build minimal initramfs with busybox
# This replaces live-boot entirely with a 50-line init script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
INITRAMFS_DIR="${BUILD_DIR}/initramfs"
OUTPUT="${BUILD_DIR}/initrd.img"

GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

main() {
    log_info "Building minimal initramfs..."

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    mkdir -p "$BUILD_DIR"
    rm -rf "$INITRAMFS_DIR"
    mkdir -p "$INITRAMFS_DIR"/{bin,sbin,dev,proc,sys,mnt,etc}

    # Copy busybox
    log_info "Installing busybox..."
    cp /bin/busybox "$INITRAMFS_DIR/bin/"

    # Create busybox symlinks
    chroot "$INITRAMFS_DIR" /bin/busybox --install -s

    # Create init script
    log_info "Creating init script..."
    cat > "$INITRAMFS_DIR/init" <<'EOF'
#!/bin/busybox sh
# Minimal init: mount ISO, loop-mount installer.ext4, run install.sh

# Mount pseudo-filesystems
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sys /sys
/bin/busybox mount -t devtmpfs dev /dev

# Wait for devices to settle
/bin/busybox sleep 2

# Mount the ISO (CD-ROM)
/bin/busybox echo "Mounting ISO..."
/bin/busybox mkdir -p /cdrom
/bin/busybox mount -t iso9660 -o ro LABEL=PURPLE_INSTALLER /cdrom || {
    /bin/busybox echo "ERROR: Cannot find ISO with label PURPLE_INSTALLER"
    /bin/busybox sh
}

# Loop-mount the installer rootfs from within the ISO
/bin/busybox echo "Mounting installer rootfs..."
/bin/busybox mkdir -p /mnt
/bin/busybox mount -o ro,loop /cdrom/boot/installer.ext4 /mnt || {
    /bin/busybox echo "ERROR: Cannot mount installer.ext4"
    /bin/busybox sh
}

# Switch to installer rootfs and run install script
/bin/busybox echo "Starting PurpleOS installer..."
exec /bin/busybox switch_root /mnt /install.sh
EOF

    chmod +x "$INITRAMFS_DIR/init"

    # Pack initramfs
    log_info "Packing initramfs..."
    (cd "$INITRAMFS_DIR" && find . | cpio -H newc -o | gzip -9) > "$OUTPUT"

    log_info "✓ Initramfs ready: $OUTPUT"
    log_info "  Size: $(du -h $OUTPUT | cut -f1)"
}

main "$@"
