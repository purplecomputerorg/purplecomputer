#!/usr/bin/env bash
# Build complete PurpleOS installer ISO
#
# ARCHITECTURE: Ubuntu ISO Remaster
# - Step 0: Build golden image (pre-built Ubuntu system to install)
# - Step 1: Remaster Ubuntu Server ISO (add payload, disable Subiquity)
#
# We do NOT build initramfs, casper, or the boot stack.
# We take Ubuntu's live ISO as a black box and just add our payload.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_done() { echo -e "${GREEN}[DONE]${NC} $1"; }
log_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }

print_banner() {
    echo
    echo "=========================================="
    echo "  PurpleOS Installer Build"
    echo "  Architecture: Ubuntu ISO Remaster"
    echo "=========================================="
    echo
}

main() {
    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run as root"
        exit 1
    fi

    cd "$SCRIPT_DIR"

    # Allow starting from a specific step (default: 0)
    START_STEP="${1:-0}"

    print_banner
    log_info "Build pipeline: 2 steps (starting from step $START_STEP)"
    echo

    if [ "$START_STEP" -le 0 ]; then
        log_step "0/1: Building golden image (the installed system)..."
        ./00-build-golden-image.sh
        echo
    fi

    if [ "$START_STEP" -le 1 ]; then
        log_step "1/1: Remastering Ubuntu ISO with our payload..."
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
    echo
    log_info "This ISO uses Ubuntu's official boot stack:"
    log_info "  - Signed shim + GRUB (Secure Boot works)"
    log_info "  - Ubuntu's kernel + initramfs + casper (untouched)"
    log_info "  - Our payload just added on top"
}

main "$@"
