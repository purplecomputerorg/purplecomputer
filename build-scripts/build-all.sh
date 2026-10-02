#!/usr/bin/env bash
# Build complete Purple Computer ISO
#
# Architecture: Live Boot + Optional Install
# - Step 0: Build root filesystem, squashfs, and golden image
# - Step 1: Remaster Ubuntu Server ISO (replace squashfs, inject install hook)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_done() { echo -e "${GREEN}[DONE]${NC} $1"; }
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

# The Pi image's chroot runs arm64 programs. The F flag makes the kernel open
# qemu now, so it works inside the chroot; the registration is kernel-wide and
# lasts until the host reboots (pi-gen does the same).
enable_arm64_emulation() {
    local reg=/proc/sys/fs/binfmt_misc qemu
    [ -e "$reg/register" ] || mount -t binfmt_misc binfmt_misc "$reg"
    if [ ! -e "$reg/qemu-aarch64" ]; then
        qemu=$(command -v qemu-aarch64-static || command -v qemu-aarch64)
        echo ':qemu-aarch64:M::\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00:\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff:'"$qemu"':F' \
            > "$reg/register"
    fi
    if ! grep -q '^flags:.*F' "$reg/qemu-aarch64"; then
        echo "ERROR: arm64 emulation is registered without the F flag, so the build chroot can't use it."
        echo "  Remove it on the host (echo -1 | sudo tee $reg/qemu-aarch64) and rebuild."
        exit 1
    fi
    log_info "arm64 emulation ready ($(sed -n 's/^interpreter //p' "$reg/qemu-aarch64"))"
}

build_pi() {
    log_step "Building the Raspberry Pi image..."
    enable_arm64_emulation
    PURPLE_ARCH=arm64 ./00-build-golden-image.sh
    log_done "Pi image ready:"
    ls -lh "$OUTPUT_DIR"/purple-pi-*.img.xz
}

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

    if [ "${PURPLE_PI:-0}" = "1" ]; then
        build_pi
        return
    fi

    START_STEP="${1:-0}"

    print_banner
    log_info "Build pipeline: 2 steps (starting from step $START_STEP)"
    echo

    if [ "$START_STEP" -le 0 ]; then
        log_step "0/1: Building root filesystem, squashfs, and golden image..."
        ./00-build-golden-image.sh
        echo
        # 32-bit CPU payload (Debian i386, install-only). Skipped on fast builds.
        if [ "${FAST_BUILD:-0}" != "1" ]; then
            log_step "0b/1: Building i386 golden image..."
            PURPLE_ARCH=i386 ./00-build-golden-image.sh
            echo
        fi
    fi

    if [ "$START_STEP" -le 1 ]; then
        log_step "1/1: Remastering ISO (replace squashfs, inject install hook)..."
        ./01-remaster-iso.sh
        echo
    fi

    print_banner
    log_done "Build complete!"
    log_done "ISO ready at: $OUTPUT_DIR/"
    echo
    ls -lh "$OUTPUT_DIR"/*.iso 2>/dev/null || true
    echo
    log_info "Write to USB stick with:"
    log_info "  sudo dd if=$OUTPUT_DIR/purple-installer-*.iso of=/dev/sdX bs=4M status=progress"
}

main "$@"
