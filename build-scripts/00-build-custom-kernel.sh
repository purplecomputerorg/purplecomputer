#!/usr/bin/env bash
# Build custom Linux kernel with built-in drivers (module-free architecture)
# This script downloads kernel source, applies PurpleOS config fragment,
# and compiles a kernel with all essential drivers built-in.
#
# DESIGN RATIONALE:
# - Eliminates runtime module loading (no insmod, no .ko files)
# - Removes dependency on CD-ROM/isofs drivers
# - Eliminates ABI mismatch issues between kernel and modules
# - Simplifies initramfs (no /lib/modules/* needed)
# - Improves compatibility across diverse laptop hardware (2010+)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
KERNEL_BUILD_DIR="${BUILD_DIR}/kernel-build"
KERNEL_VERSION="6.8.12"  # Stable upstream kernel (matches Ubuntu 24.04 lineage)
KERNEL_MAJOR="6.x"
OUTPUT_KERNEL="${BUILD_DIR}/vmlinuz-purple"
OUTPUT_CONFIG="${BUILD_DIR}/kernel-config-purple"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Detect number of CPU cores for parallel build
NPROC=$(nproc 2>/dev/null || echo 4)

main() {
    log_info "Building custom PurpleOS kernel (module-free architecture)..."
    log_info "Kernel version: ${KERNEL_VERSION}"
    log_info "Build parallelism: ${NPROC} cores"
    echo

    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run as root"
        exit 1
    fi

    # Check for required tools
    for tool in wget tar make gcc bc bison flex libelf-dev; do
        if ! command -v "$tool" >/dev/null 2>&1 && ! dpkg -l | grep -q "^ii.*$tool"; then
            echo "ERROR: Required tool not found: $tool"
            echo "Install with: apt-get install build-essential bc bison flex libelf-dev libssl-dev"
            exit 1
        fi
    done

    mkdir -p "$BUILD_DIR"
    mkdir -p "$KERNEL_BUILD_DIR"
    cd "$KERNEL_BUILD_DIR"

    # Download kernel source
    log_step "1/6: Downloading kernel source..."
    KERNEL_TARBALL="linux-${KERNEL_VERSION}.tar.xz"
    KERNEL_URL="https://cdn.kernel.org/pub/linux/kernel/v${KERNEL_MAJOR}/${KERNEL_TARBALL}"

    if [ ! -f "$KERNEL_TARBALL" ]; then
        log_info "Downloading from ${KERNEL_URL}..."
        wget -q --show-progress "$KERNEL_URL" || {
            echo "ERROR: Failed to download kernel source"
            echo "URL: $KERNEL_URL"
            exit 1
        }
    else
        log_info "Using cached kernel source: $KERNEL_TARBALL"
    fi

    # Extract kernel source
    log_step "2/6: Extracting kernel source..."
    if [ ! -d "linux-${KERNEL_VERSION}" ]; then
        tar -xf "$KERNEL_TARBALL"
    else
        log_info "Kernel already extracted"
    fi

    cd "linux-${KERNEL_VERSION}"

    # Start with minimal defconfig
    log_step "3/6: Creating base kernel configuration..."
    make defconfig

    # Apply PurpleOS configuration fragment
    log_step "4/6: Applying PurpleOS config fragment (built-in drivers)..."
    if [ ! -f "$SCRIPT_DIR/kernel-config-fragment.config" ]; then
        echo "ERROR: Kernel config fragment not found"
        echo "Expected: $SCRIPT_DIR/kernel-config-fragment.config"
        exit 1
    fi

    # Merge configuration using kernel's merge script
    if [ -f scripts/kconfig/merge_config.sh ]; then
        scripts/kconfig/merge_config.sh -m .config "$SCRIPT_DIR/kernel-config-fragment.config"
    else
        # Fallback: manual merge
        log_info "Using manual config merge (no merge_config.sh available)"
        cat "$SCRIPT_DIR/kernel-config-fragment.config" >> .config
        make olddefconfig  # Resolve dependencies
    fi

    # Save final configuration
    cp .config "$OUTPUT_CONFIG"
    log_info "Final kernel config saved to: $OUTPUT_CONFIG"

    # Build kernel
    log_step "5/6: Compiling kernel (this may take 10-30 minutes)..."
    log_info "Building with ${NPROC} parallel jobs..."
    make -j"${NPROC}" bzImage

    # Copy kernel to output location
    log_step "6/6: Installing kernel..."
    cp arch/x86/boot/bzImage "$OUTPUT_KERNEL"

    # Generate build info
    cat > "${BUILD_DIR}/kernel-build-info.txt" <<EOF
PurpleOS Custom Kernel Build Information
=========================================

Kernel Version: ${KERNEL_VERSION}
Build Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Build Host: $(hostname)
Architecture: x86_64
Compiler: $(gcc --version | head -1)

Configuration:
- All essential drivers built-in (CONFIG_*=y)
- No runtime kernel modules required
- USB boot support (xhci, ehci, usb-storage, uas)
- SATA support (ahci, ata_piix)
- NVMe support (nvme-core, nvme)
- Filesystem support (ext4, vfat)
- No CD-ROM/isofs dependency

Output Files:
- Kernel: $OUTPUT_KERNEL
- Config: $OUTPUT_CONFIG

To verify built-in drivers:
  grep "=y" $OUTPUT_CONFIG | grep -E "(USB|SATA|NVME|EXT4|VFAT)"

Module-free design eliminates:
  - Runtime insmod/modprobe
  - Kernel module ABI mismatches
  - Missing .ko.zst files
  - Module dependency resolution
  - CD-ROM boot dependencies
EOF

    log_info "✓ Kernel build complete!"
    log_info "  Kernel: $OUTPUT_KERNEL ($(du -h $OUTPUT_KERNEL | cut -f1))"
    log_info "  Config: $OUTPUT_CONFIG"
    log_info "  Build info: ${BUILD_DIR}/kernel-build-info.txt"
    echo
    log_info "Next steps:"
    log_info "  1. Run ./02-build-initramfs.sh to create minimal initramfs"
    log_info "  2. Continue with standard build pipeline (03, 04)"
}

main "$@"
