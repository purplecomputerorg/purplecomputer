#!/usr/bin/env bash
# Build complete PurpleOS installer ISO (module-free architecture)
# Orchestrates all build steps in sequence
#
# ARCHITECTURE CHANGES:
# - Step 0: Build custom kernel with built-in drivers
# - Step 1: Build golden image (unchanged)
# - Step 2: Build minimal initramfs (no modules, no CD-ROM)
# - Step 3: Build installer rootfs (unchanged)
# - Step 4: Build USB-bootable hybrid ISO
#
# Total time estimate: 30-90 minutes (kernel build dominates)

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
    echo "  PurpleOS Installer Build Pipeline"
    echo "  Module-Free Architecture"
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
    log_info "Build pipeline: 5 steps (starting from step $START_STEP)"
    log_info "Estimated time: 30-90 minutes"
    echo

    if [ "$START_STEP" -le 0 ]; then
        log_step "0/5: Building custom kernel with built-in drivers..."
        log_info "This step takes 10-30 minutes depending on CPU"
        ./00-build-custom-kernel.sh
        echo
    fi

    if [ "$START_STEP" -le 1 ]; then
        log_step "1/5: Building golden image..."
        ./01-build-golden-image.sh
        echo
    fi

    if [ "$START_STEP" -le 2 ]; then
        log_step "2/5: Building minimal initramfs (no modules)..."
        ./02-build-initramfs.sh
        echo
    fi

    if [ "$START_STEP" -le 3 ]; then
        log_step "3/5: Building installer rootfs..."
        ./03-build-installer-rootfs.sh
        echo
    fi

    if [ "$START_STEP" -le 4 ]; then
        log_step "4/5: Building USB-bootable hybrid ISO..."
        ./04-build-iso.sh
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
    log_info "Module-free architecture benefits:"
    log_info "  ✓ All drivers built into kernel (USB, SATA, NVMe, ext4, vfat)"
    log_info "  ✓ No runtime module loading (no insmod, no .ko files)"
    log_info "  ✓ No CD-ROM dependency (direct USB boot)"
    log_info "  ✓ Improved reliability and hardware compatibility"
}

main "$@"
