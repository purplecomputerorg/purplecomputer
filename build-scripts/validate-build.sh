#!/usr/bin/env bash
# Pre-build validation and post-build debugging script
# Run this to check for common issues before building or after kernel panics

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
    echo "=========================================="
    echo
}

check_kernel_config() {
    info "Checking kernel configuration fragment..."

    local CONFIG="$SCRIPT_DIR/kernel-config-fragment.config"

    if [ ! -f "$CONFIG" ]; then
        error "Kernel config fragment not found: $CONFIG"
        ((ERRORS++))
        return
    fi

    # Critical configs that must be present
    local CRITICAL=(
        "CONFIG_BLK_DEV=y"
        "CONFIG_EXT4_FS=y"
        "CONFIG_PROC_FS=y"
        "CONFIG_SYSFS=y"
        "CONFIG_DEVTMPFS=y"
        "CONFIG_DEVTMPFS_MOUNT=y"
        "CONFIG_TTY=y"
        "CONFIG_VT_CONSOLE=y"
        "CONFIG_SCSI=y"
        "CONFIG_BLK_DEV_SD=y"
        "CONFIG_USB=y"
        "CONFIG_USB_STORAGE=y"
    )

    for cfg in "${CRITICAL[@]}"; do
        if ! grep -q "^${cfg}" "$CONFIG"; then
            error "Missing critical config: $cfg"
            ((ERRORS++))
        fi
    done

    # Recommended configs
    local RECOMMENDED=(
        "CONFIG_SATA_AHCI=y"
        "CONFIG_ATA_PIIX=y"
        "CONFIG_NVME_CORE=y"
        "CONFIG_USB_XHCI_HCD=y"
        "CONFIG_USB_EHCI_HCD=y"
        "CONFIG_VFAT_FS=y"
        "CONFIG_EFI=y"
    )

    for cfg in "${RECOMMENDED[@]}"; do
        if ! grep -q "^${cfg}" "$CONFIG"; then
            warn "Missing recommended config: $cfg (may reduce hardware compatibility)"
            ((WARNINGS++))
        fi
    done

    ok "Kernel config fragment syntax is valid"
}

check_initramfs_script() {
    info "Checking initramfs build script..."

    local SCRIPT="$SCRIPT_DIR/02-build-initramfs.sh"

    if [ ! -f "$SCRIPT" ]; then
        error "Initramfs build script not found: $SCRIPT"
        ((ERRORS++))
        return
    fi

    # Check for critical init script components
    if ! grep -q "#!/bin/busybox sh" "$SCRIPT"; then
        error "Init script missing busybox shebang"
        ((ERRORS++))
    fi

    if ! grep -q "mount -t proc proc /proc" "$SCRIPT"; then
        error "Init script missing /proc mount"
        ((ERRORS++))
    fi

    if ! grep -q "mount -t sysfs sys /sys" "$SCRIPT"; then
        error "Init script missing /sys mount"
        ((ERRORS++))
    fi

    if ! grep -q "mount -t devtmpfs dev /dev" "$SCRIPT"; then
        error "Init script missing /dev mount"
        ((ERRORS++))
    fi

    if ! grep -q "switch_root" "$SCRIPT"; then
        error "Init script missing switch_root command"
        ((ERRORS++))
    fi

    # Check for BusyBox installation
    if ! grep -q "cp.*busybox.*bin/" "$SCRIPT"; then
        error "Init script doesn't install BusyBox"
        ((ERRORS++))
    fi

    ok "Initramfs script has all critical components"
}

check_built_kernel() {
    info "Checking built kernel (if exists)..."

    local KERNEL="$BUILD_DIR/vmlinuz-purple"

    if [ ! -f "$KERNEL" ]; then
        warn "Kernel not built yet: $KERNEL"
        warn "Run: ./00-build-custom-kernel.sh"
        ((WARNINGS++))
        return
    fi

    # Check kernel size (should be 8-15 MB typically)
    local SIZE=$(stat -c%s "$KERNEL" 2>/dev/null || stat -f%z "$KERNEL" 2>/dev/null || echo "0")
    local SIZE_MB=$((SIZE / 1048576))

    if [ "$SIZE_MB" -lt 5 ]; then
        error "Kernel suspiciously small: ${SIZE_MB}MB (expected 8-15MB)"
        ((ERRORS++))
    elif [ "$SIZE_MB" -gt 30 ]; then
        warn "Kernel very large: ${SIZE_MB}MB (may include debug symbols)"
        ((WARNINGS++))
    else
        ok "Kernel size looks reasonable: ${SIZE_MB}MB"
    fi

    # Check kernel config
    local CONFIG="$BUILD_DIR/kernel-config-purple"
    if [ ! -f "$CONFIG" ]; then
        warn "Kernel config not found: $CONFIG"
        ((WARNINGS++))
        return
    fi

    # Verify critical drivers are built-in
    local MUST_BE_BUILTIN=(
        "CONFIG_BLK_DEV=y"
        "CONFIG_EXT4_FS=y"
        "CONFIG_USB=y"
        "CONFIG_SCSI=y"
        "CONFIG_BLK_DEV_SD=y"
    )

    for cfg in "${MUST_BE_BUILTIN[@]}"; do
        if ! grep -q "^${cfg}" "$CONFIG"; then
            error "Built kernel missing critical config: $cfg"
            ((ERRORS++))
        fi
    done

    ok "Built kernel config verified"
}

check_initramfs() {
    info "Checking built initramfs (if exists)..."

    local INITRD="$BUILD_DIR/initrd.img"

    if [ ! -f "$INITRD" ]; then
        warn "Initramfs not built yet: $INITRD"
        warn "Run: ./02-build-initramfs.sh"
        ((WARNINGS++))
        return
    fi

    # Check if it's gzip compressed
    if command -v file >/dev/null 2>&1; then
        if ! file "$INITRD" | grep -q "gzip compressed"; then
            error "Initramfs is not gzip compressed"
            ((ERRORS++))
            return
        fi
    else
        # Fallback: check magic bytes for gzip (1f 8b)
        if ! od -An -tx1 -N2 "$INITRD" | grep -q "1f 8b"; then
            error "Initramfs is not gzip compressed (check first bytes)"
            ((ERRORS++))
            return
        fi
    fi

    # Extract and check contents
    local TEMP_DIR=$(mktemp -d)
    trap "rm -rf $TEMP_DIR" EXIT

    (cd "$TEMP_DIR" && zcat "$INITRD" | cpio -i 2>/dev/null)

    # Check for critical files
    if [ ! -f "$TEMP_DIR/init" ]; then
        error "Initramfs missing /init script"
        ((ERRORS++))
    elif [ ! -x "$TEMP_DIR/init" ]; then
        error "/init script is not executable"
        ((ERRORS++))
    else
        ok "Initramfs has executable /init"
    fi

    if [ ! -f "$TEMP_DIR/bin/busybox" ]; then
        error "Initramfs missing /bin/busybox"
        ((ERRORS++))
    else
        # Check if statically linked
        if ldd "$TEMP_DIR/bin/busybox" 2>&1 | grep -q "not a dynamic executable"; then
            ok "BusyBox is statically linked"
        else
            error "BusyBox is dynamically linked (will fail in initramfs)"
            ((ERRORS++))
        fi
    fi

    # Check directory structure
    for dir in dev proc sys mnt newroot; do
        if [ ! -d "$TEMP_DIR/$dir" ]; then
            error "Initramfs missing /$dir directory"
            ((ERRORS++))
        fi
    done

    ok "Initramfs structure validated"
}

check_iso_boot_configs() {
    info "Checking ISO boot configuration script..."

    local SCRIPT="$SCRIPT_DIR/04-build-iso.sh"

    if [ ! -f "$SCRIPT" ]; then
        error "ISO build script not found: $SCRIPT"
        ((ERRORS++))
        return
    fi

    # Check for critical kernel parameters
    if ! grep -q "APPEND.*initrd=/boot/initrd.img" "$SCRIPT"; then
        error "ISOLINUX config missing initrd parameter"
        ((ERRORS++))
    fi

    if ! grep -q "linux /boot/vmlinuz" "$SCRIPT"; then
        error "GRUB config missing kernel path"
        ((ERRORS++))
    fi

    if ! grep -q "initrd /boot/initrd.img" "$SCRIPT"; then
        error "GRUB config missing initrd path"
        ((ERRORS++))
    fi

    # Check for console output (important for debugging)
    if ! grep -q "console=" "$SCRIPT"; then
        warn "Boot configs missing console= parameter (harder to debug)"
        ((WARNINGS++))
    fi

    ok "ISO boot configurations look correct"
}

check_dockerfile_deps() {
    info "Checking Dockerfile dependencies..."

    local DOCKERFILE="$SCRIPT_DIR/Dockerfile"

    if [ ! -f "$DOCKERFILE" ]; then
        error "Dockerfile not found: $DOCKERFILE"
        ((ERRORS++))
        return
    fi

    # Critical packages for kernel build
    local KERNEL_DEPS=(
        "build-essential"
        "bc"
        "bison"
        "flex"
        "libelf-dev"
        "libssl-dev"
    )

    for dep in "${KERNEL_DEPS[@]}"; do
        if ! grep -q "$dep" "$DOCKERFILE"; then
            error "Dockerfile missing kernel build dependency: $dep"
            ((ERRORS++))
        fi
    done

    # Critical packages for installer build
    local INSTALLER_DEPS=(
        "debootstrap"
        "busybox-static"
        "xorriso"
        "isolinux"
        "grub-efi-amd64-bin"
        "zstd"
    )

    for dep in "${INSTALLER_DEPS[@]}"; do
        if ! grep -q "$dep" "$DOCKERFILE"; then
            error "Dockerfile missing installer dependency: $dep"
            ((ERRORS++))
        fi
    done

    ok "Dockerfile has all required dependencies"
}

post_panic_debug() {
    info "Post-kernel-panic debugging information..."
    echo
    echo "If you're experiencing kernel panics, try these debugging steps:"
    echo
    echo "1. Add debug kernel parameters to build-scripts/04-build-iso.sh:"
    echo "   APPEND initrd=/boot/initrd.img debug ignore_loglevel earlyprintk=vga,keep"
    echo
    echo "2. Verify initramfs contents:"
    echo "   mkdir /tmp/initrd-check"
    echo "   cd /tmp/initrd-check"
    echo "   zcat $BUILD_DIR/initrd.img | cpio -i"
    echo "   ls -la init"
    echo "   ./bin/busybox --list | head -20"
    echo
    echo "3. Check kernel config for missing drivers:"
    echo "   grep '=y' $BUILD_DIR/kernel-config-purple | grep -E '(USB|SATA|NVME|EXT4)'"
    echo
    echo "4. Test in QEMU first:"
    echo "   qemu-system-x86_64 -m 2048 -cdrom /opt/purple-installer/output/purple-installer-*.iso -serial file:boot.log"
    echo
    echo "5. Check for init script errors:"
    echo "   # Boot the system and look for messages before panic"
    echo "   # Common issues: /init not found, busybox missing, mount failures"
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
        info "You can proceed with the build, but address warnings for best results"
    else
        error "$ERRORS error(s) and $WARNINGS warning(s) found"
        echo
        error "Fix errors before building to avoid kernel panics"
        exit 1
    fi
}

main() {
    banner

    check_kernel_config
    check_initramfs_script
    check_iso_boot_configs
    check_dockerfile_deps

    # Post-build checks (only if build artifacts exist)
    if [ -d "$BUILD_DIR" ]; then
        check_built_kernel
        check_initramfs
    fi

    summary

    echo
    info "For post-panic debugging, run: $0 --debug"

    if [ "$1" = "--debug" ] || [ "$1" = "-d" ]; then
        post_panic_debug
    fi
}

main "$@"
