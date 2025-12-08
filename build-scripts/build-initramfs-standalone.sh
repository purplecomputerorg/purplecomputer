#!/usr/bin/env bash
set -euo pipefail

UBUNTU_KERNEL="${1:-6.8.0-31-generic}"
WORK_DIR="work"
EXTRACT_DIR="$WORK_DIR/extracted"
INITRAMFS_ROOT="initramfs-root"
OUTPUT="initramfs.gz"

echo "Building initramfs for Ubuntu kernel: $UBUNTU_KERNEL"

# Parse kernel version components
KVER_BASE=$(echo "$UBUNTU_KERNEL" | sed 's/-generic$//')
UBUNTU_VERSION="24.04"
UBUNTU_CODENAME="noble"

# Construct package URLs
BASE_URL="http://archive.ubuntu.com/ubuntu/pool/main/l/linux"
SIGNED_URL="http://archive.ubuntu.com/ubuntu/pool/main/l/linux-signed"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "Downloading kernel packages..."

# First, fetch the package index to find the exact version
echo "Fetching package list..."
PACKAGE_LIST=$(wget -q -O - "${BASE_URL}/" | grep -o "linux-modules-${UBUNTU_KERNEL}_[^\"]*_amd64.deb" | head -1)

if [ -z "$PACKAGE_LIST" ]; then
    echo "ERROR: Could not find linux-modules package for ${UBUNTU_KERNEL}"
    exit 1
fi

# Extract the full version
FULL_VERSION=$(echo "$PACKAGE_LIST" | sed "s/linux-modules-${UBUNTU_KERNEL}_\(.*\)_amd64.deb/\1/")
echo "Found version: $FULL_VERSION"

# Download linux-modules package
wget -q -O linux-modules.deb "${BASE_URL}/linux-modules-${UBUNTU_KERNEL}_${FULL_VERSION}_amd64.deb" || {
    echo "ERROR: Failed to download linux-modules package"
    echo "URL: ${BASE_URL}/linux-modules-${UBUNTU_KERNEL}_${FULL_VERSION}_amd64.deb"
    exit 1
}

# Download linux-modules-extra package
wget -q -O linux-modules-extra.deb "${BASE_URL}/linux-modules-extra-${UBUNTU_KERNEL}_${FULL_VERSION}_amd64.deb" || {
    echo "WARNING: Could not download linux-modules-extra (may not be critical)"
}

cd ..

echo "Extracting packages..."
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"

dpkg-deb -x "$WORK_DIR/linux-modules.deb" "$EXTRACT_DIR"
if [ -f "$WORK_DIR/linux-modules-extra.deb" ]; then
    dpkg-deb -x "$WORK_DIR/linux-modules-extra.deb" "$EXTRACT_DIR"
fi

echo "Decompressing kernel modules..."
find "$EXTRACT_DIR/lib/modules" -name "*.ko.zst" -exec sh -c 'zstd -d "$0" -o "${0%.zst}" && rm "$0"' {} \;

echo "Creating initramfs root..."
rm -rf "$INITRAMFS_ROOT"
mkdir -p "$INITRAMFS_ROOT"/{bin,sbin,dev,proc,sys,mnt,lib/modules}

# Copy busybox (try multiple locations)
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
    exit 1
fi

# Create busybox symlinks
(cd "$INITRAMFS_ROOT" && bin/busybox --install -s)

# Copy kernel modules
cp -r "$EXTRACT_DIR/lib/modules/$UBUNTU_KERNEL" "$INITRAMFS_ROOT/lib/modules/"

# Create minimal init script
cat > "$INITRAMFS_ROOT/init" <<'EOF'
#!/bin/busybox sh
# Minimal init: mount ISO, loop-mount installer.ext4, run install.sh

# Mount pseudo-filesystems
/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sys /sys
/bin/busybox mount -t devtmpfs dev /dev

/bin/busybox sleep 2

# Load kernel modules for SATA CD-ROM
echo "Loading kernel modules..."
KVER=$(/bin/busybox uname -r)
MDIR="/lib/modules/$KVER/kernel/drivers"

# Load AHCI (SATA controller) - required for CD-ROM detection in QEMU/KVM
echo "Loading AHCI SATA driver..."
/bin/busybox insmod $MDIR/ata/ahci.ko || echo "ahci: failed or built-in"

# Load loop device for mounting installer.ext4
/bin/busybox insmod $MDIR/block/loop.ko 2>/dev/null || echo "loop: failed or built-in"

# Load isofs for mounting ISO
/bin/busybox insmod /lib/modules/$KVER/kernel/fs/isofs/isofs.ko 2>/dev/null || echo "isofs: failed or built-in"

echo "Modules loaded:"
/bin/busybox lsmod

# Wait for CD-ROM device to appear (up to 10 seconds)
echo "Waiting for CD-ROM device..."
CDROM_DEV=""
WAIT_COUNT=0
while [ $WAIT_COUNT -lt 10 ]; do
    for dev in /dev/sr0 /dev/sr1 /dev/cdrom; do
        if [ -b "$dev" ]; then
            CDROM_DEV="$dev"
            break 2
        fi
    done
    /bin/busybox sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ -z "$CDROM_DEV" ]; then
    echo "ERROR: No CD-ROM device found after 10 seconds"
    echo "Available block devices:"
    /bin/busybox ls -l /dev/sr* /dev/sd* /dev/cdrom 2>/dev/null || true
    echo ""
    echo "Loaded modules:"
    /bin/busybox lsmod 2>/dev/null || true
    exec /bin/busybox sh
fi

# Mount the ISO (CD-ROM)
echo "Mounting ISO from $CDROM_DEV..."
/bin/busybox mkdir -p /cdrom
/bin/busybox mount -t iso9660 -o ro "$CDROM_DEV" /cdrom || {
    echo "ERROR: Cannot mount CD-ROM"
    exec /bin/busybox sh
}

# Loop-mount the installer rootfs from within the ISO
echo "Mounting installer rootfs..."
/bin/busybox mkdir -p /mnt
/bin/busybox mount -o ro,loop /cdrom/boot/installer.ext4 /mnt || {
    echo "ERROR: Cannot mount installer.ext4"
    exec /bin/busybox sh
}

# Switch to installer rootfs and run install script
echo "Starting PurpleOS installer..."
exec /bin/busybox switch_root /mnt /install.sh
EOF

chmod +x "$INITRAMFS_ROOT/init"

echo "Building initramfs archive..."
(cd "$INITRAMFS_ROOT" && find . -print0 | cpio --null -ov --format=newc 2>/dev/null | gzip -9 > "../$OUTPUT")

echo "✓ Initramfs built: $OUTPUT"
echo "  Size: $(du -h $OUTPUT | cut -f1)"
echo "  Kernel: $UBUNTU_KERNEL"
