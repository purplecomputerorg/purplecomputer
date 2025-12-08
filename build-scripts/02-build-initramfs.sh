#!/usr/bin/env bash
# Build minimal initramfs for PurpleOS installer (module-free architecture)
#
# DESIGN CHANGES FROM OLD VERSION:
# - NO kernel modules (.ko files) - all drivers built into kernel
# - NO CD-ROM/isofs logic - boots directly from USB stick
# - NO insmod commands - kernel has everything built-in
# - Mounts installer.ext4 directly from USB partition, not from ISO
#
# This initramfs contains ONLY:
# - BusyBox (statically compiled)
# - init script (mounts USB, switches root)
# - Empty directory structure for kernel pseudo-filesystems

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
INITRAMFS_ROOT="${BUILD_DIR}/initramfs-root"
OUTPUT="${BUILD_DIR}/initrd.img"

GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

main() {
    log_info "Building minimal initramfs (module-free architecture)..."

    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run as root"
        exit 1
    fi

    mkdir -p "$BUILD_DIR"

    # Create clean initramfs root
    log_info "Creating initramfs directory structure..."
    rm -rf "$INITRAMFS_ROOT"
    mkdir -p "$INITRAMFS_ROOT"/{bin,sbin,dev,proc,sys,mnt,run,newroot}

    # Copy busybox (try multiple locations for Nix/Ubuntu compatibility)
    log_info "Installing BusyBox..."
    if [ -f /run/current-system/sw/bin/busybox ]; then
        # NixOS
        cp /run/current-system/sw/bin/busybox "$INITRAMFS_ROOT/bin/"
    elif command -v busybox >/dev/null 2>&1; then
        # In PATH (Ubuntu/Docker)
        cp $(which busybox) "$INITRAMFS_ROOT/bin/"
    elif [ -f /bin/busybox ]; then
        # Standard location
        cp /bin/busybox "$INITRAMFS_ROOT/bin/"
    else
        echo "ERROR: busybox not found. Install busybox-static package."
        echo "  Ubuntu/Debian: apt-get install busybox-static"
        echo "  NixOS: nix-shell -p busybox"
        exit 1
    fi

    # Verify busybox is statically linked
    if ldd "$INITRAMFS_ROOT/bin/busybox" 2>&1 | grep -q "not a dynamic executable"; then
        log_info "✓ BusyBox is statically compiled (good)"
    else
        echo "WARNING: BusyBox is dynamically linked - may not work in initramfs"
        echo "Install busybox-static instead of busybox"
    fi

    # Create busybox symlinks
    log_info "Creating BusyBox symlinks..."
    (cd "$INITRAMFS_ROOT" && bin/busybox --install -s)

    # Create minimal init script (NO module loading, NO CD-ROM logic)
    log_info "Creating init script..."
    cat > "$INITRAMFS_ROOT/init" <<'EOF'
#!/bin/busybox sh
# PurpleOS Installer Init Script (Module-Free Architecture)
# Mounts installer rootfs from USB stick and executes install.sh
#
# DESIGN: All drivers (USB, SATA, NVMe, ext4, vfat) are built into kernel.
# No runtime module loading. No CD-ROM dependency.

set -e

# Mount kernel pseudo-filesystems
echo "Mounting pseudo-filesystems..."
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sys /sys
/bin/busybox mount -t devtmpfs dev /dev

# Wait for devices to settle (USB enumeration, disk detection)
echo "Waiting for hardware initialization..."
/bin/busybox sleep 3

# Display detected block devices for debugging
echo "Detected block devices:"
/bin/busybox ls -l /dev/sd* /dev/nvme* /dev/vd* 2>/dev/null || echo "  (none yet)"

# Find installer USB stick or boot device
# Strategy: Look for partition labeled PURPLE_INSTALLER or containing /boot/installer.ext4
# Try both by-label (modern) and direct partition scan (fallback)

INSTALLER_DEV=""

# Method 1: Find by filesystem label (most reliable)
echo "Searching for PURPLE_INSTALLER partition..."
for dev in /dev/sd* /dev/nvme* /dev/vd*; do
    [ -b "$dev" ] || continue

    # Check if this partition has the PURPLE_INSTALLER label
    LABEL=$(/bin/busybox blkid -s LABEL -o value "$dev" 2>/dev/null || true)
    if [ "$LABEL" = "PURPLE_INSTALLER" ]; then
        INSTALLER_DEV="$dev"
        echo "✓ Found installer partition: $INSTALLER_DEV (by label)"
        break
    fi
done

# Method 2: Scan partitions for installer.ext4 (fallback)
if [ -z "$INSTALLER_DEV" ]; then
    echo "Label-based detection failed, scanning partitions..."
    for dev in /dev/sd* /dev/nvme* /dev/vd*; do
        [ -b "$dev" ] || continue

        # Skip whole disks, only check partitions
        # Partitions: sd*[0-9], vd*[0-9], nvme*n*p[0-9]
        case "$(basename "$dev")" in
            sd*[0-9]|vd*[0-9]) ;;  # SATA/virtio partition
            nvme*n*p[0-9]*) ;;     # NVMe partition (nvme0n1p1, etc)
            *) continue ;;          # Whole disk - skip
        esac

        # Try mounting and checking for installer.ext4
        if /bin/busybox mount -o ro "$dev" /mnt 2>/dev/null; then
            if [ -f /mnt/boot/installer.ext4 ]; then
                INSTALLER_DEV="$dev"
                echo "✓ Found installer partition: $INSTALLER_DEV (by content)"
                /bin/busybox umount /mnt
                break
            fi
            /bin/busybox umount /mnt
        fi
    done
fi

# Error handling: No installer found
if [ -z "$INSTALLER_DEV" ]; then
    echo ""
    echo "ERROR: Cannot find PurpleOS installer partition"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Is the USB stick properly inserted?"
    echo "  2. Did you write the ISO with: dd if=purple-installer.iso of=/dev/sdX bs=4M"
    echo "  3. Is the partition labeled PURPLE_INSTALLER?"
    echo ""
    echo "Available block devices:"
    /bin/busybox lsblk 2>/dev/null || /bin/busybox ls -l /dev/sd* /dev/nvme* 2>/dev/null
    echo ""
    echo "Dropping to emergency shell. Type 'exit' to reboot."
    exec /bin/busybox sh
fi

# Mount installer partition
echo "Mounting installer partition from $INSTALLER_DEV..."
/bin/busybox mount -o ro "$INSTALLER_DEV" /mnt || {
    echo "ERROR: Failed to mount $INSTALLER_DEV"
    echo "Dropping to emergency shell..."
    exec /bin/busybox sh
}

# Verify installer.ext4 exists
if [ ! -f /mnt/boot/installer.ext4 ]; then
    echo "ERROR: /boot/installer.ext4 not found on $INSTALLER_DEV"
    echo "USB stick may be corrupted or incomplete"
    /bin/busybox umount /mnt
    exec /bin/busybox sh
fi

# Loop-mount installer rootfs
echo "Mounting installer rootfs..."
/bin/busybox mount -o ro,loop /mnt/boot/installer.ext4 /newroot || {
    echo "ERROR: Cannot mount installer.ext4"
    /bin/busybox umount /mnt
    exec /bin/busybox sh
}

# Verify install.sh exists in installer rootfs
if [ ! -x /newroot/install.sh ]; then
    echo "ERROR: /install.sh not found or not executable in installer rootfs"
    /bin/busybox umount /newroot
    /bin/busybox umount /mnt
    exec /bin/busybox sh
fi

# Switch to installer rootfs and execute installation
echo ""
echo "========================================"
echo "  PurpleOS Installer Starting"
echo "========================================"
echo ""

# Export installer device so install.sh knows which disk to avoid
export PURPLE_INSTALLER_DEV="$INSTALLER_DEV"

# switch_root will:
# 1. Move /mnt to /newroot/mnt (keeps USB mounted for logging)
# 2. Change root to /newroot
# 3. Execute /install.sh with PURPLE_INSTALLER_DEV set
exec /bin/busybox switch_root /newroot /install.sh
EOF

    chmod +x "$INITRAMFS_ROOT/init"

    # Build initramfs archive
    log_info "Creating initramfs archive..."
    (cd "$INITRAMFS_ROOT" && \
     find . -print0 | \
     cpio --null -ov --format=newc 2>/dev/null | \
     gzip -9 > "$OUTPUT")

    # Display results
    log_info "✓ Initramfs built successfully!"
    log_info "  Output: $OUTPUT"
    log_info "  Size: $(du -h $OUTPUT | cut -f1)"
    echo
    log_info "Module-free architecture:"
    log_info "  - No kernel modules included"
    log_info "  - No insmod/modprobe needed"
    log_info "  - No CD-ROM/isofs dependency"
    log_info "  - Direct USB boot support"
}

main "$@"
