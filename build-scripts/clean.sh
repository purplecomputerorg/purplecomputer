#!/usr/bin/env bash
# Clean all Purple Computer build artifacts and Docker images

set -e

echo "Cleaning Purple Computer build artifacts..."

# Remove build directories
sudo rm -rf /opt/purple-installer/local-repo
sudo rm -rf /opt/purple-installer/output
sudo rm -rf /srv/fai

# Remove Docker image
if docker images | grep -q "purple-builder"; then
    echo "Removing purple-builder Docker image..."
    docker rmi purple-builder
fi

echo "✓ Cleanup complete"
echo ""
echo "Ready to rebuild with: ./build-in-docker.sh"
