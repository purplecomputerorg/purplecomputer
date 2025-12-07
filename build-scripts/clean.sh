#!/usr/bin/env bash
# Clean all build artifacts

set -e

echo "Cleaning PurpleOS build artifacts..."

# Unmount any lingering mounts
sudo umount /opt/purple-installer/build/mnt-golden 2>/dev/null || true
sudo umount /opt/purple-installer/build/mnt-installer 2>/dev/null || true

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
