#!/usr/bin/env bash
# Build Purple Computer ISO inside Docker container
# This allows building on NixOS or any non-Debian system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
IMAGE_NAME="purple-builder"
OUTPUT_DIR="/opt/purple-installer/output"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Build Docker image
build_image() {
    log_info "Building Docker image: $IMAGE_NAME"
    docker build -t "$IMAGE_NAME" "$SCRIPT_DIR"
}

# Run build inside container
run_build() {
    log_info "Running build inside Docker container..."

    # Create output directory on host if it doesn't exist
    sudo mkdir -p "$OUTPUT_DIR"

    # Run container with privileges needed for FAI
    docker run --rm -it \
        --privileged \
        -v "$REPO_ROOT:/home/tavi/purplecomputer:rw" \
        -v "$OUTPUT_DIR:/opt/purple-installer/output:rw" \
        -v /opt/purple-installer/local-repo:/opt/purple-installer/local-repo:rw \
        -v /srv/fai:/srv/fai:rw \
        "$IMAGE_NAME" \
        /bin/bash -c "
            set -e
            cd /home/tavi/purplecomputer/build-scripts

            echo '=== Step 1: Create local repository ==='
            ./01-create-local-repo.sh

            echo ''
            echo '=== Step 2: Build FAI nfsroot ==='
            ./02-build-fai-nfsroot.sh

            echo ''
            echo '=== Step 3: Build ISO ==='
            ./03-build-iso.sh

            echo ''
            echo '=== Build complete! ==='
            ls -lh /opt/purple-installer/output/
        "
}

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    log_error "Docker is not installed or not in PATH"
    log_error "On NixOS, add 'virtualisation.docker.enable = true' to your configuration"
    exit 1
fi

# Check if user can run Docker
if ! docker ps &> /dev/null; then
    log_error "Cannot run Docker commands"
    log_error "Make sure Docker daemon is running and you're in the 'docker' group"
    exit 1
fi

# Main execution
main() {
    log_info "Purple Computer Docker Build"
    echo ""

    # Check if image exists
    if ! docker images | grep -q "$IMAGE_NAME"; then
        log_info "Docker image not found, building..."
        build_image
    else
        log_info "Docker image exists, using cached version"
        log_info "To rebuild: docker rmi $IMAGE_NAME"
    fi

    echo ""
    run_build

    echo ""
    log_info "ISO build complete!"
    log_info "Output: $OUTPUT_DIR"
}

main "$@"
