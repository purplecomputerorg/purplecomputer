#!/usr/bin/env bash
# Build minimal initramfs with busybox and Ubuntu kernel modules
# Uses standalone script to download and decompress Ubuntu modules

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
OUTPUT="${BUILD_DIR}/initrd.img"
UBUNTU_KERNEL="6.8.0-31-generic"

GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

main() {
    log_info "Building minimal initramfs with Ubuntu kernel modules..."

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    mkdir -p "$BUILD_DIR"

    # Use standalone initramfs builder
    cd "$BUILD_DIR"
    "$SCRIPT_DIR/build-initramfs-standalone.sh" "$UBUNTU_KERNEL"

    # Move output to expected location
    mv initramfs.gz "$OUTPUT"

    log_info "✓ Initramfs ready: $OUTPUT"
    log_info "  Size: $(du -h $OUTPUT | cut -f1)"
}

main "$@"
