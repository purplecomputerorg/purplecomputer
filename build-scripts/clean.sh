#!/usr/bin/env bash
# Clean all build artifacts (module-free architecture)

set -e

echo "Cleaning PurpleOS build artifacts..."

# Unmount any lingering mounts
sudo umount /opt/purple-installer/build/mnt-golden 2>/dev/null || true
sudo umount /opt/purple-installer/build/mnt-installer 2>/dev/null || true
sudo umount /opt/purple-installer/build/mnt-kernel-extract 2>/dev/null || true

# Detach any loop devices
for loop in $(losetup -a | grep purple-installer | cut -d: -f1); do
    echo "Detaching $loop..."
    sudo losetup -d "$loop" 2>/dev/null || true
done

# Remove build directory
sudo rm -rf /opt/purple-installer/build

# Remove output ISOs
sudo rm -rf /opt/purple-installer/output

# Remove Docker image
if docker images | grep -q "purple-installer-builder"; then
    echo "Removing purple-installer-builder Docker image..."
    docker rmi purple-installer-builder
fi

echo "✓ Cleanup complete"
