#!/usr/bin/env bash
# Build complete Purple Computer ISO
#
# Architecture: Live Boot + Optional Install
# - Step 0: Build root filesystem, squashfs, and golden image
# - Step 1: Remaster Ubuntu Server ISO (replace squashfs, inject install hook)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_done() { echo -e "${GREEN}[DONE]${NC} $1"; }
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

print_banner() {
    echo
    echo "=========================================="
    echo "  Purple Computer Build"
    echo "  Architecture: Live Boot + Optional Install"
    echo "=========================================="
    echo
}

main() {
    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run as root"
        exit 1
    fi

    cd "$SCRIPT_DIR"

    START_STEP="${1:-0}"

    print_banner
    log_info "Build pipeline: 2 steps (starting from step $START_STEP)"
    echo

    if [ "$START_STEP" -le 0 ]; then
        log_step "0/1: Building root filesystem, squashfs, and golden image..."
        ./00-build-golden-image.sh
        echo
    fi

    if [ "$START_STEP" -le 1 ]; then
        log_step "1/1: Remastering ISO (replace squashfs, inject install hook)..."
        ./01-remaster-iso.sh
        echo
    fi

    print_banner
    log_done "Build complete!"
    log_done "ISO ready at: /opt/purple-installer/output/"
    echo
    ls -lh /opt/purple-installer/output/*.iso 2>/dev/null || true
    echo
    log_info "Write to USB stick with:"
    log_info "  sudo dd if=/opt/purple-installer/output/purple-installer-*.iso of=/dev/sdX bs=4M status=progress"
}

main "$@"
