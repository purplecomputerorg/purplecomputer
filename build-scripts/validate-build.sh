#!/usr/bin/env bash
# Pre-build validation and post-build debugging script
# Architecture: Ubuntu ISO Remaster

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

error() { echo -e "${RED}[ERROR]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }

ERRORS=0
WARNINGS=0

banner() {
    echo
    echo "=========================================="
    echo "  PurpleOS Build Validation"
    echo "  Architecture: Ubuntu ISO Remaster"
    echo "=========================================="
    echo
}

check_build_scripts() {
    info "Checking build scripts exist..."

    local SCRIPTS=(
        "00-build-golden-image.sh"
        "01-remaster-iso.sh"
        "build-all.sh"
        "build-in-docker.sh"
        "install.sh"
    )

    for script in "${SCRIPTS[@]}"; do
        if [ ! -f "$SCRIPT_DIR/$script" ]; then
            error "Missing build script: $script"
            ((ERRORS++))
        elif [ ! -x "$SCRIPT_DIR/$script" ]; then
            warn "Script not executable: $script"
            ((WARNINGS++))
        fi
    done

    ok "Build scripts present"
}

check_install_script() {
    info "Checking installer script..."

    local SCRIPT="$SCRIPT_DIR/install.sh"

    if [ ! -f "$SCRIPT" ]; then
        error "Installer script not found: $SCRIPT"
        ((ERRORS++))
        return
    fi

    # Check for critical components
    if ! grep -q "zstd -dc" "$SCRIPT" && ! grep -q "zstdcat" "$SCRIPT"; then
        error "Install script missing zstd decompression"
        ((ERRORS++))
    fi

    if ! grep -q "dd of=/dev/\$TARGET" "$SCRIPT"; then
        error "Install script missing dd write command"
        ((ERRORS++))
    fi

    if ! grep -q "EFI" "$SCRIPT"; then
        error "Install script missing UEFI boot setup"
        ((ERRORS++))
    fi

    ok "Installer script has critical components"
}

check_dockerfile() {
    info "Checking Dockerfile..."

    local DOCKERFILE="$SCRIPT_DIR/Dockerfile"

    if [ ! -f "$DOCKERFILE" ]; then
        error "Dockerfile not found: $DOCKERFILE"
        ((ERRORS++))
        return
    fi

    # Required packages for ISO remaster
    local REQUIRED_DEPS=(
        "squashfs-tools"
        "xorriso"
        "isolinux"
        "wget"
        "rsync"
    )

    for dep in "${REQUIRED_DEPS[@]}"; do
        if ! grep -q "$dep" "$DOCKERFILE"; then
            error "Dockerfile missing dependency: $dep"
            ((ERRORS++))
        fi
    done

    ok "Dockerfile has required dependencies"
}

check_golden_image() {
    info "Checking golden image (if exists)..."

    local GOLDEN="$BUILD_DIR/purple-os.img.zst"

    if [ ! -f "$GOLDEN" ]; then
        warn "Golden image not built yet: $GOLDEN"
        warn "Run: ./build-in-docker.sh 0"
        ((WARNINGS++))
        return
    fi

    # Check size (should be 1-2 GB compressed)
    local SIZE=$(stat -c%s "$GOLDEN" 2>/dev/null || stat -f%z "$GOLDEN" 2>/dev/null || echo "0")
    local SIZE_MB=$((SIZE / 1048576))

    if [ "$SIZE_MB" -lt 500 ]; then
        error "Golden image too small: ${SIZE_MB}MB (expected 1000-2000MB)"
        ((ERRORS++))
    elif [ "$SIZE_MB" -gt 3000 ]; then
        warn "Golden image very large: ${SIZE_MB}MB"
        ((WARNINGS++))
    else
        ok "Golden image size: ${SIZE_MB}MB"
    fi
}

check_ubuntu_iso() {
    info "Checking for Ubuntu Server ISO..."

    local ISO="$BUILD_DIR/ubuntu-24.04.1-live-server-amd64.iso"

    if [ ! -f "$ISO" ]; then
        warn "Ubuntu Server ISO not downloaded yet"
        warn "It will be downloaded during build"
        ((WARNINGS++))
        return
    fi

    local SIZE=$(stat -c%s "$ISO" 2>/dev/null || stat -f%z "$ISO" 2>/dev/null || echo "0")
    local SIZE_MB=$((SIZE / 1048576))

    if [ "$SIZE_MB" -lt 2000 ]; then
        error "Ubuntu ISO too small: ${SIZE_MB}MB (corrupted download?)"
        ((ERRORS++))
    else
        ok "Ubuntu Server ISO present: ${SIZE_MB}MB"
    fi
}

check_final_iso() {
    info "Checking final ISO (if exists)..."

    local ISO_DIR="/opt/purple-installer/output"
    local ISO=$(ls -t "$ISO_DIR"/purple-installer-*.iso 2>/dev/null | head -1)

    if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
        warn "ISO not built yet"
        warn "Run: ./build-in-docker.sh"
        ((WARNINGS++))
        return
    fi

    local SIZE=$(stat -c%s "$ISO" 2>/dev/null || stat -f%z "$ISO" 2>/dev/null || echo "0")
    local SIZE_MB=$((SIZE / 1048576))

    if [ "$SIZE_MB" -lt 3000 ]; then
        error "ISO too small: ${SIZE_MB}MB (expected 4000+ MB)"
        ((ERRORS++))
    else
        ok "ISO size: ${SIZE_MB}MB - $(basename "$ISO")"
    fi

    # Check checksums exist
    if [ -f "${ISO}.sha256" ]; then
        ok "SHA256 checksum present"
    else
        warn "SHA256 checksum missing"
        ((WARNINGS++))
    fi
}

post_boot_debug() {
    info "Post-boot debugging information..."
    echo
    echo "If the installer doesn't boot or hangs, try these steps:"
    echo
    echo "1. Check serial log (if using purple-vm):"
    echo "   sudo cat /var/log/libvirt/qemu/purplecomputer-serial.log"
    echo
    echo "2. Use Debug Mode from boot menu"
    echo
    echo "3. Access emergency shell:"
    echo "   Press Alt+F2 during installation for root shell"
    echo
    echo "4. Test in QEMU:"
    echo "   qemu-system-x86_64 -m 4096 -enable-kvm \\"
    echo "     -drive file=/opt/purple-installer/output/purple-installer-*.iso,format=raw \\"
    echo "     -drive file=test.qcow2,format=qcow2"
    echo
    echo "5. Check Secure Boot:"
    echo "   This ISO uses Ubuntu's signed boot chain - Secure Boot should work"
    echo
    echo "6. Common issues:"
    echo "   - Subiquity still starts: Check masked services in remaster script"
    echo "   - Boot hangs: Ubuntu's boot stack issue, not ours"
    echo "   - 'No target disk found': Check install.sh disk detection"
    echo
}

summary() {
    echo
    echo "=========================================="
    echo "  Validation Summary"
    echo "=========================================="

    if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
        ok "All checks passed! Build should succeed."
        echo
        info "Run the build with:"
        info "  cd build-scripts"
        info "  ./build-in-docker.sh"
    elif [ "$ERRORS" -eq 0 ]; then
        warn "$WARNINGS warning(s) found - build may succeed but review warnings"
        echo
        info "You can proceed with the build"
    else
        error "$ERRORS error(s) and $WARNINGS warning(s) found"
        echo
        error "Fix errors before building"
        exit 1
    fi
}

main() {
    banner

    check_build_scripts
    check_install_script
    check_dockerfile

    # Check build artifacts if they exist
    if [ -d "$BUILD_DIR" ]; then
        check_golden_image
        check_ubuntu_iso
        check_final_iso
    fi

    summary

    echo
    info "For boot debugging help, run: $0 --debug"

    if [ "$1" = "--debug" ] || [ "$1" = "-d" ]; then
        post_boot_debug
    fi
}

main "$@"
