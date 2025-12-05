#!/bin/bash
# ============================================================================
# Purple Computer Offline ISO Builder
# ============================================================================
#
# PURPOSE: Creates a fully self-contained offline installation ISO
#
# This script builds a custom Ubuntu 24.04 ISO with:
# - Complete embedded APT repository (all packages bundled)
# - No network required during installation
# - Autoinstall configuration baked in
# - Production-grade reliability (OEM-style approach)
#
# Requirements: debmirror, xorriso, squashfs-tools, rsync
#
# Usage:
#   sudo ./build-offline-iso.sh
#
# Output: purple-computer-offline.iso (4-5GB)
# ============================================================================

set -euo pipefail

# Configuration
UBUNTU_VERSION="noble"
UBUNTU_CODENAME="24.04.3"
BASE_ISO_URL="https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso"
BASE_ISO_NAME="ubuntu-24.04.3-live-server-amd64.iso"
OUTPUT_ISO="purple-computer-offline.iso"
WORK_DIR="$(pwd)/build-offline"
REPO_DIR="$WORK_DIR/repo"
EXTRACT_DIR="$WORK_DIR/iso-extract"
MOUNT_DIR="$WORK_DIR/iso-mount"

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "This script must be run as root (for mounting ISOs)"
fi

# Get the actual user (not root)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_GID=$(id -g "$ACTUAL_USER")

# Cleanup function
cleanup() {
    info "Cleaning up..."
    umount "$MOUNT_DIR" 2>/dev/null || true
    rm -rf "$MOUNT_DIR"
}
trap cleanup EXIT

# Check dependencies
check_dependencies() {
    info "Checking dependencies..."
    local missing=()

    for cmd in xorriso rsync wget gzip yq docker apt-ftparchive; do
        if ! command -v "$cmd" &> /dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing dependencies: ${missing[*]}"
        echo ""
        echo "  Install on Ubuntu/Debian:"
        echo "    sudo apt install xorriso rsync wget gzip docker.io apt-utils"
        echo "    sudo snap install yq"
        echo ""
        echo "  Install on other distros: use your package manager to install above tools"
        exit 1
    fi

    # Check Docker is running
    if ! docker info &> /dev/null 2>&1; then
        error "Docker daemon not running."
        echo "  Start with: sudo systemctl start docker"
        echo "  Enable on boot: sudo systemctl enable docker"
        exit 1
    fi
}

# Download base ISO
download_base_iso() {
    info "Checking for base Ubuntu ISO..."

    cd "$WORK_DIR"

    if [ -f "$BASE_ISO_NAME" ]; then
        info "Base ISO already exists"
        return 0
    fi

    info "Downloading Ubuntu $UBUNTU_CODENAME ISO (~2.5GB)..."
    wget -O "$BASE_ISO_NAME" "$BASE_ISO_URL" || error "Failed to download base ISO"

    info "✓ Base ISO downloaded"
}

# Extract base ISO
extract_base_iso() {
    info "Extracting base ISO..."

    mkdir -p "$MOUNT_DIR" "$EXTRACT_DIR"
    mount -o loop "$WORK_DIR/$BASE_ISO_NAME" "$MOUNT_DIR" || error "Failed to mount ISO"

    rsync -a "$MOUNT_DIR/" "$EXTRACT_DIR/" || error "Failed to extract ISO"
    umount "$MOUNT_DIR"

    chmod -R u+w "$EXTRACT_DIR"

    info "✓ Base ISO extracted"
}

# Download packages for offline repository
download_packages() {
    info "Downloading packages for offline repository..."
    info "Extracting package list from autoinstall.yaml..."

    mkdir -p "$REPO_DIR/debs"

    # Extract packages from autoinstall.yaml using yq
    local packages
    packages=$(yq eval '.autoinstall.packages[]' "$PROJECT_ROOT/autoinstall/autoinstall.yaml" 2>/dev/null || echo "")

    if [ -z "$packages" ]; then
        error "No packages found in autoinstall.yaml"
    fi

    info "Found $(echo "$packages" | wc -w) packages to download"

    # Add critical system packages that might not be in autoinstall.yaml
    local critical_packages=(
        "ubuntu-server-minimal"
        "linux-image-generic"
        "grub-pc"
        "grub-efi-amd64"
        "grub-efi-amd64-signed"
        "shim-signed"
        "snapd"
    )

    packages="$packages ${critical_packages[*]}"

    warn "This will download ~2-3GB of packages. This may take 20-40 minutes..."

    # Write packages to a file for Docker
    echo "$packages" > "$WORK_DIR/packages.txt"

    # Download packages using Docker with Ubuntu 24.04
    info "Downloading packages in Ubuntu Docker container..."
    docker run --rm \
        -v "$REPO_DIR/debs:/debs" \
        -v "$WORK_DIR/packages.txt:/packages.txt" \
        ubuntu:24.04 \
        /bin/bash -c '
set -e
apt-get update -qq
apt-get install -y -qq dpkg-dev

cd /debs
# Fix permissions for apt sandboxing (suppresses warnings)
chown -R _apt:root /debs 2>/dev/null || true

PACKAGES=$(cat /packages.txt | tr "\n" " ")
apt-get download $(apt-cache depends --recurse --no-recommends --no-suggests \
    --no-conflicts --no-breaks --no-replaces --no-enhances \
    $PACKAGES | grep "^\w" | sort -u)

# Restore root ownership for host access
chown -R root:root /debs

echo "Downloaded $(ls -1 *.deb 2>/dev/null | wc -l) packages"
' || error "Package download failed"

    local pkg_count
    pkg_count=$(find "$REPO_DIR/debs" -name "*.deb" 2>/dev/null | wc -l)
    info "✓ Downloaded $pkg_count packages"
}

# Generate repository metadata using apt-ftparchive
generate_repo_metadata() {
    info "Generating repository metadata with apt-ftparchive..."

    cd "$REPO_DIR"

    # Create standard Debian repository structure
    mkdir -p "dists/$UBUNTU_VERSION/main/binary-amd64"
    mkdir -p pool

    # Move downloaded packages to pool
    if [ -d debs ] && [ "$(ls -A debs/*.deb 2>/dev/null)" ]; then
        mv debs/*.deb pool/ 2>/dev/null || true
        rmdir debs 2>/dev/null || true
    fi

    # Generate Packages file (scans pool automatically)
    apt-ftparchive packages pool > "dists/$UBUNTU_VERSION/main/binary-amd64/Packages"
    gzip -k "dists/$UBUNTU_VERSION/main/binary-amd64/Packages"

    # Generate Release file with all checksums
    apt-ftparchive release "dists/$UBUNTU_VERSION" > "dists/$UBUNTU_VERSION/Release"

    info "✓ Repository metadata generated with apt-ftparchive"
}

# Inject repository into ISO
inject_repository() {
    info "Injecting repository into ISO..."

    # Copy the apt-ftparchive-generated repository structure
    info "Copying repository dists/ and pool/ to ISO..."

    # Copy pool directory (contains actual .deb files organized by component)
    if [ -d "$REPO_DIR/pool" ]; then
        cp -r "$REPO_DIR/pool" "$EXTRACT_DIR/" || error "Failed to copy pool directory"
    else
        error "Repository pool directory not found at $REPO_DIR/pool"
    fi

    # Copy dists directory (contains Release, InRelease, Packages, etc.)
    if [ -d "$REPO_DIR/dists" ]; then
        cp -r "$REPO_DIR/dists" "$EXTRACT_DIR/" || error "Failed to copy dists directory"
    else
        error "Repository dists directory not found at $REPO_DIR/dists"
    fi

    # Verify critical files exist
    [ -f "$EXTRACT_DIR/dists/$UBUNTU_VERSION/Release" ] || error "Missing Release file"
    [ -f "$EXTRACT_DIR/dists/$UBUNTU_VERSION/main/binary-amd64/Packages.gz" ] || error "Missing Packages.gz"

    info "✓ Repository injected into ISO"
}

# Copy autoinstall configuration
configure_autoinstall() {
    info "Copying autoinstall configuration..."

    # Copy autoinstall.yaml as-is (no modifications)
    cp "$PROJECT_ROOT/autoinstall/autoinstall.yaml" "$EXTRACT_DIR/autoinstall.yaml"

    # Also copy to nocloud for autoinstall discovery
    mkdir -p "$EXTRACT_DIR/nocloud"
    cp "$PROJECT_ROOT/autoinstall/autoinstall.yaml" "$EXTRACT_DIR/nocloud/user-data"
    touch "$EXTRACT_DIR/nocloud/meta-data"

    info "✓ Autoinstall configuration copied"
}

# Copy Purple Computer files
copy_purple_files() {
    info "Adding Purple Computer files..."

    mkdir -p "$EXTRACT_DIR/purple_files"
    cp -r "$PROJECT_ROOT/purple_tui"/* "$EXTRACT_DIR/purple_files/"

    # Copy config files if they exist
    [ -d "$PROJECT_ROOT/autoinstall/files/systemd" ] && \
        cp -r "$PROJECT_ROOT/autoinstall/files/systemd" "$EXTRACT_DIR/purple_files/" || true
    [ -f "$PROJECT_ROOT/autoinstall/files/xinit/xinitrc" ] && \
        cp "$PROJECT_ROOT/autoinstall/files/xinit/xinitrc" "$EXTRACT_DIR/purple_files/" || true
    [ -f "$PROJECT_ROOT/autoinstall/files/alacritty/alacritty.toml" ] && \
        cp "$PROJECT_ROOT/autoinstall/files/alacritty/alacritty.toml" "$EXTRACT_DIR/purple_files/" || true

    info "✓ Purple Computer files added"
}

# Configure GRUB bootloader
configure_grub() {
    info "Configuring GRUB bootloader..."

    cat > "$EXTRACT_DIR/boot/grub/grub.cfg" <<'GRUB'
set timeout=3
set default=0
insmod all_video
set gfxpayload=keep

menuentry "Purple Computer - Automated Install (Offline)" {
    linux /casper/vmlinuz autoinstall ---
    initrd /casper/initrd
}

menuentry "Purple Computer - Safe Graphics Mode" {
    linux /casper/vmlinuz autoinstall nomodeset ---
    initrd /casper/initrd
}

menuentry "Cancel (power off)" {
    halt
}
GRUB

    info "✓ GRUB configured"
}

# Rebuild ISO
rebuild_iso() {
    info "Rebuilding ISO..."

    cd "$EXTRACT_DIR"

    # Calculate checksums
    find . -type f -print0 | xargs -0 md5sum 2>/dev/null | \
        grep -v isolinux/boot.cat > md5sum.txt || true

    cd "$WORK_DIR"

    # Extract boot parameters from original ISO
    local xorriso_opts
    xorriso_opts=$(xorriso -indev "$BASE_ISO_NAME" -report_system_area as_mkisofs 2>&1)

    local efi_partition
    efi_partition=$(echo "$xorriso_opts" | grep -o -- '--interval:local_fs:[0-9]*d-[0-9]*d::' | head -1 | sed "s/--interval:local_fs://;s/:://")

    local efi_boot_interval
    efi_boot_interval=$(echo "$xorriso_opts" | grep -o -- "appended_partition_2_start_[0-9]*s_size_[0-9]*d" | head -1)

    local efi_boot_load_size
    efi_boot_load_size=$(echo "$xorriso_opts" | grep "boot-load-size" | tail -1 | awk '{print $2}')

    if [ -z "$efi_partition" ] || [ -z "$efi_boot_interval" ]; then
        error "Failed to extract boot parameters from original ISO"
    fi

    info "Building offline ISO (this may take 5-10 minutes)..."

    xorriso -as mkisofs \
        -r -V "Purple Computer Offline" \
        -o "$PROJECT_ROOT/$OUTPUT_ISO" \
        -J -l \
        --grub2-mbr --interval:local_fs:0s-15s:zero_mbrpt,zero_gpt:"$BASE_ISO_NAME" \
        --protective-msdos-label \
        -partition_cyl_align off \
        -partition_offset 16 \
        --mbr-force-bootable \
        -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b --interval:local_fs:"${efi_partition}"::"$BASE_ISO_NAME" \
        -appended_part_as_gpt \
        -iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
        -c boot.catalog \
        -b boot/grub/i386-pc/eltorito.img \
        -no-emul-boot -boot-load-size 4 -boot-info-table \
        --grub2-boot-info \
        -eltorito-alt-boot \
        -e --interval:"${efi_boot_interval}":all:: \
        -no-emul-boot \
        -boot-load-size "$efi_boot_load_size" \
        "$EXTRACT_DIR" || error "Failed to build ISO"

    # Fix ownership
    chown "$ACTUAL_USER":"$ACTUAL_GID" "$PROJECT_ROOT/$OUTPUT_ISO"

    info "✓ ISO rebuilt successfully"
}

# Verify ISO
verify_iso() {
    info "Verifying ISO structure..."

    local verify_mount="/tmp/purple-verify-$$"
    mkdir -p "$verify_mount"

    mount -o loop "$PROJECT_ROOT/$OUTPUT_ISO" "$verify_mount" || error "Failed to mount ISO for verification"

    # Check critical paths
    [ -f "$verify_mount/autoinstall.yaml" ] || error "Missing autoinstall.yaml"
    [ -f "$verify_mount/dists/$UBUNTU_VERSION/Release" ] || error "Missing Release file"
    [ -d "$verify_mount/pool" ] || error "Missing pool directory"

    # Check for main component directory
    [ -d "$verify_mount/dists/$UBUNTU_VERSION/main/binary-amd64" ] || error "Missing main component"
    [ -f "$verify_mount/dists/$UBUNTU_VERSION/main/binary-amd64/Packages.gz" ] || error "Missing Packages.gz"

    # Verify Release file contains checksums
    if grep -q "MD5Sum:" "$verify_mount/dists/$UBUNTU_VERSION/Release" 2>/dev/null || \
       grep -q "SHA256:" "$verify_mount/dists/$UBUNTU_VERSION/Release" 2>/dev/null; then
        info "Release file contains checksums"
    else
        warn "Release file missing checksums"
    fi

    local pkg_count
    pkg_count=$(find "$verify_mount/pool" -name "*.deb" 2>/dev/null | wc -l)
    info "Verified: $pkg_count packages in ISO"

    umount "$verify_mount"
    rm -rf "$verify_mount"

    info "✓ ISO verification passed"
}

# Main build process
main() {
    info "======================================"
    info "Purple Computer Offline ISO Builder"
    info "======================================"
    echo ""

    # Create work directory
    mkdir -p "$WORK_DIR"

    check_dependencies
    download_base_iso
    extract_base_iso
    download_packages
    generate_repo_metadata
    inject_repository
    configure_autoinstall
    copy_purple_files
    configure_grub
    rebuild_iso
    verify_iso

    echo ""
    info "======================================"
    info "Build Complete!"
    info "======================================"
    info "Output: $PROJECT_ROOT/$OUTPUT_ISO"
    info "Size: $(du -h "$PROJECT_ROOT/$OUTPUT_ISO" | cut -f1)"
    echo ""
    info "Test with: qemu-system-x86_64 -m 4096 -cdrom $OUTPUT_ISO -boot d -net none"
    echo ""
    warn "Work directory kept at: $WORK_DIR"
    warn "Delete to save space: rm -rf $WORK_DIR"
}

main "$@"
