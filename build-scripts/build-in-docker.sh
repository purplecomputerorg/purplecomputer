#!/usr/bin/env bash
# Build PurpleOS installer in Docker (module-free architecture)
# Usage: ./build-in-docker.sh [step]
#   step: optional step number to start from (0-4, default: 0)
#     0 = build custom kernel
#     1 = build golden image
#     2 = build initramfs
#     3 = build installer rootfs
#     4 = build ISO

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="purple-installer-builder"
START_STEP="${1:-0}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

main() {
    cd "$SCRIPT_DIR"

    # Build Docker image
    log_step "Building Docker image..."
    docker build -t "$IMAGE_NAME" .

    # Run build in container with new pipeline
    log_info "Running build in container (starting from step $START_STEP)..."
    log_info "Using module-free architecture..."
    docker run --rm --privileged \
        -v "$SCRIPT_DIR:/build" \
        -v "/opt/purple-installer:/opt/purple-installer" \
        "$IMAGE_NAME" \
        /build/build-all.sh "$START_STEP"

    log_info "Build complete!"
    log_info "Output in: /opt/purple-installer/output/"
}

main "$@"
