#!/usr/bin/env bash
# Build complete PurpleOS installer ISO
# Orchestrates all build steps in sequence

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_done() { echo -e "${GREEN}[DONE]${NC} $1"; }

main() {
    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    cd "$SCRIPT_DIR"

    # Allow starting from a specific step (default: 1)
    START_STEP="${1:-1}"

    log_step "Building PurpleOS installer (starting from step $START_STEP)..."
    echo

    if [ "$START_STEP" -le 1 ]; then
        log_step "1/4: Building golden image..."
        ./01-build-golden-image.sh
        echo
    fi

    if [ "$START_STEP" -le 2 ]; then
        log_step "2/4: Building initramfs..."
        ./02-build-initramfs.sh
        echo
    fi

    if [ "$START_STEP" -le 3 ]; then
        log_step "3/4: Building installer rootfs..."
        ./03-build-installer-rootfs.sh
        echo
    fi

    if [ "$START_STEP" -le 4 ]; then
        log_step "4/4: Building bootable ISO..."
        ./04-build-iso.sh
        echo
    fi

    log_done "Build complete!"
    log_done "ISO ready at: /opt/purple-installer/output/"
    ls -lh /opt/purple-installer/output/*.iso 2>/dev/null || true
}

main "$@"
