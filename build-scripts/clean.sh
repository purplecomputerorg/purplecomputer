#!/usr/bin/env bash
# Clean all build artifacts

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

echo "Cleaning Purple Computer build artifacts..."

# Unmount any lingering mounts
sudo umount "$BUILD_DIR/mnt-golden" 2>/dev/null || true
sudo umount "$BUILD_DIR/mnt-golden/boot/efi" 2>/dev/null || true
sudo umount "$BUILD_DIR/remaster/iso-mount" 2>/dev/null || true

# Unmount any test/debug mounts from /tmp
sudo umount /tmp/iso_check 2>/dev/null || true
sudo umount /tmp/iso_mount 2>/dev/null || true

# Force unmount anything under installer base recursively
for i in {1..3}; do
    while read -r mount; do
        echo "Unmounting $mount..."
        sudo umount -f "$mount" 2>/dev/null || true
    done < <(mount | grep "$INSTALLER_BASE" | awk '{print $3}' | sort -r)
done

# Clean up loop devices
echo "Cleaning up loop devices..."
for loop in $(sudo losetup -a | grep -E 'purple-installer|purple-os\.img|\(deleted\)' | cut -d: -f1); do
    echo "  Detaching $loop..."
    sudo losetup -d "$loop" 2>/dev/null || true
done

# Clean up kpartx mappings
for mapping in $(ls /dev/mapper/loop* 2>/dev/null); do
    echo "  Removing kpartx mapping $mapping..."
    sudo dmsetup remove "$mapping" 2>/dev/null || true
done

# Remove build directory
echo "Removing build directory..."
if [ -d "$BUILD_DIR" ]; then
    sudo rm -rf "$BUILD_DIR"
    if [ -d "$BUILD_DIR" ]; then
        echo "ERROR: Failed to remove $BUILD_DIR"
        ls -la "$BUILD_DIR/"
        exit 1
    fi
fi
sudo mkdir -p "$BUILD_DIR"
echo "  ✓ Build directory cleaned"

# Remove output ISOs
echo "Removing output ISOs..."
sudo rm -rf "$OUTPUT_DIR"
echo "  ✓ Output directory cleaned"

# Verify clean state
echo "Verifying clean state..."
if ls "$BUILD_DIR"/* 2>/dev/null; then
    echo "ERROR: Build directory is not empty after clean!"
    exit 1
fi
echo "  ✓ Verified empty"

# Remove Docker image to force fresh build
if docker images | grep -q "purple-installer-builder"; then
    echo "Removing purple-installer-builder Docker image..."
    docker rmi purple-installer-builder 2>/dev/null || true
fi

# Prune Docker build cache
echo "Pruning Docker build cache..."
docker builder prune -af 2>/dev/null || true

echo "✓ Cleanup complete"
