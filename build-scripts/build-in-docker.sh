#!/usr/bin/env bash
# Build PurpleOS installer in Docker (Ubuntu ISO Remaster architecture)
# Usage: ./build-in-docker.sh [step]
#   step: optional step number to start from (0-1, default: 0)
#     0 = build golden image (pre-built Ubuntu system)
#     1 = remaster Ubuntu ISO with our payload

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

    # Run build in container
    log_info "Running build in container (starting from step $START_STEP)..."
    log_info "Architecture: Ubuntu ISO Remaster"
    log_info "  - We download official Ubuntu Server ISO"
    log_info "  - We add our payload and disable Subiquity"
    log_info "  - Ubuntu's boot stack remains untouched"

    # Mount the entire project directory (parent of build-scripts) as /purple-src
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    docker run --rm --privileged \
        -v "$SCRIPT_DIR:/build" \
        -v "$PROJECT_DIR:/purple-src" \
        -v "/opt/purple-installer:/opt/purple-installer" \
        "$IMAGE_NAME" \
        /build/build-all.sh "$START_STEP"

    log_info "Build complete!"
    log_info "Output in: /opt/purple-installer/output/"
}

main "$@"
