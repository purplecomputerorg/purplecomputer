#!/usr/bin/env bash
# Build Purple Computer ISO inside Docker container
# This allows building on NixOS or any non-Debian system
#
# Usage:
#   ./build-in-docker.sh           # Run all steps (1, 2, 3)
#   ./build-in-docker.sh 2         # Start from step 2 (nfsroot + iso)
#   ./build-in-docker.sh 3         # Start from step 3 (iso only)

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
    local START_STEP="${1:-1}"
    log_info "Running build inside Docker container (starting from step $START_STEP)..."

    # Create output directory on host if it doesn't exist
    sudo mkdir -p "$OUTPUT_DIR"

    # Build command based on start step
    local BUILD_CMD="set -e; cd /home/tavi/purplecomputer/build-scripts;"

    if [ "$START_STEP" -le 1 ]; then
        BUILD_CMD="$BUILD_CMD
            echo '=== Step 1: Create local repository ==='
            ./01-create-local-repo.sh
            echo ''"
    fi

    if [ "$START_STEP" -le 2 ]; then
        BUILD_CMD="$BUILD_CMD
            echo '=== Step 2: Build FAI nfsroot ==='
            ./02-build-fai-nfsroot.sh
            echo ''"
    fi

    if [ "$START_STEP" -le 3 ]; then
        BUILD_CMD="$BUILD_CMD
            echo '=== Step 3: Build ISO ==='
            ./03-build-iso.sh
            echo ''"
    fi

    BUILD_CMD="$BUILD_CMD
            echo '=== Build complete! ==='
            ls -lh /opt/purple-installer/output/"

    # Run container with privileges needed for FAI
    docker run --rm -it \
        --privileged \
        -v "$REPO_ROOT:/home/tavi/purplecomputer:rw" \
        -v "$OUTPUT_DIR:/opt/purple-installer/output:rw" \
        -v /opt/purple-installer/local-repo:/opt/purple-installer/local-repo:rw \
        -v /srv/fai:/srv/fai:rw \
        "$IMAGE_NAME" \
        /bin/bash -c "$BUILD_CMD"
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
    local START_STEP="${1:-1}"

    # Validate step number
    if ! [[ "$START_STEP" =~ ^[1-3]$ ]]; then
        log_error "Invalid step number: $START_STEP"
        log_error "Usage: $0 [1|2|3]"
        log_error "  1 = Start from step 1 (repo + nfsroot + iso)"
        log_error "  2 = Start from step 2 (nfsroot + iso)"
        log_error "  3 = Start from step 3 (iso only)"
        exit 1
    fi

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
    run_build "$START_STEP"

    echo ""
    log_info "Build complete!"
    log_info "Output: $OUTPUT_DIR"
}

main "$@"
