#!/bin/bash
# Purple Computer ISO Builder
# This script creates a bootable Ubuntu Server ISO with Purple Computer pre-configured
# Architecture: Ubuntu Server + minimal Xorg (no desktop) + kitty fullscreen
#
# Run from project root: ./autoinstall/build-iso.sh
# Or from autoinstall/: ./build-iso.sh

set -e  # Exit on error

# Get the directory where this script lives and determine project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root to ensure all relative paths work correctly
cd "$PROJECT_ROOT"

# Configuration
UBUNTU_VERSION="24.04.3"
UBUNTU_ISO_URL="https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-24.04.3-live-server-amd64.iso"
UBUNTU_SHA256_URL="https://releases.ubuntu.com/24.04/SHA256SUMS"
OUTPUT_ISO="$PROJECT_ROOT/purple-computer.iso"
WORK_DIR="$PROJECT_ROOT/autoinstall/build"
MOUNT_DIR="$WORK_DIR/mount"
EXTRACT_DIR="$WORK_DIR/extract"

# Cleanup trap to unmount ISO if script exits early (Linux only, macOS uses xorriso extraction)
cleanup_mount() {
    if [ "$(uname -s)" != "Darwin" ]; then
        sudo umount "$MOUNT_DIR" 2>/dev/null || true
    fi
}
trap cleanup_mount EXIT

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo_error "Please do not run as root. This script will use sudo when needed."
    exit 1
fi

# Check dependencies
echo_info "Checking dependencies..."

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux)  IS_MACOS=false ;;
    Darwin) IS_MACOS=true ;;
    *)      echo_error "Unsupported OS: $OS"; exit 1 ;;
esac

# Check for command-line tools
COMMANDS="xorriso curl rsync"
for cmd in $COMMANDS; do
    if ! command -v $cmd &> /dev/null; then
        echo_error "$cmd is not installed. Please install it first."
        if $IS_MACOS; then
            echo "  macOS: brew install $cmd"
        else
            echo "  Debian/Ubuntu: sudo apt install $cmd"
            echo "  Fedora: sudo dnf install $cmd"
            echo "  Arch: sudo pacman -S $cmd"
            echo "  NixOS: Add $cmd to your environment.systemPackages"
        fi
        exit 1
    fi
done

# Note: Ubuntu 24.04 uses GRUB for both BIOS and UEFI boot (no isolinux needed)
echo_info "Ubuntu 24.04 uses GRUB for both BIOS and UEFI boot"

# Create work directory
echo_info "Creating work directory..."
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Function to verify SHA256 checksum
verify_iso_checksum() {
    echo_info "Verifying ISO checksum..."

    # Download SHA256SUMS if not present or if ISO was just downloaded
    if [ ! -f "SHA256SUMS" ] || [ "$1" = "force" ]; then
        echo_info "Downloading SHA256SUMS..."
        curl -fsSL -o "SHA256SUMS" "$UBUNTU_SHA256_URL" || {
            echo_error "Failed to download SHA256SUMS"
            return 1
        }
    fi

    # Extract the checksum for our ISO
    EXPECTED_SHA256=$(grep "$UBUNTU_ISO_NAME" SHA256SUMS | awk '{print $1}')

    if [ -z "$EXPECTED_SHA256" ]; then
        echo_error "Could not find checksum for $UBUNTU_ISO_NAME in SHA256SUMS"
        return 1
    fi

    # Calculate actual checksum
    echo_info "Calculating SHA256 checksum (this may take a minute)..."
    if $IS_MACOS; then
        ACTUAL_SHA256=$(shasum -a 256 "$UBUNTU_ISO_NAME" | awk '{print $1}')
    else
        ACTUAL_SHA256=$(sha256sum "$UBUNTU_ISO_NAME" | awk '{print $1}')
    fi

    # Compare checksums
    if [ "$EXPECTED_SHA256" = "$ACTUAL_SHA256" ]; then
        echo_info "✓ Checksum verification passed"
        return 0
    else
        echo_error "✗ Checksum verification failed!"
        echo_error "Expected: $EXPECTED_SHA256"
        echo_error "Got:      $ACTUAL_SHA256"
        return 1
    fi
}

# Download Ubuntu ISO if not present
DOWNLOAD_ATTEMPT=0
MAX_ATTEMPTS=2

while [ $DOWNLOAD_ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if [ ! -f "$UBUNTU_ISO_NAME" ]; then
        echo_info "Downloading Ubuntu $UBUNTU_VERSION ISO..."
        echo_warn "This is a large file (~2GB) and may take a while..."

        if curl -fL --progress-bar -o "$UBUNTU_ISO_NAME" "$UBUNTU_ISO_URL"; then
            echo_info "Download complete"
        else
            echo_error "Download failed"
            rm -f "$UBUNTU_ISO_NAME"
            exit 1
        fi
    else
        echo_info "Ubuntu ISO already downloaded"
    fi

    # Verify checksum
    if verify_iso_checksum "force"; then
        # Checksum passed, break out of loop
        break
    else
        # Checksum failed
        DOWNLOAD_ATTEMPT=$((DOWNLOAD_ATTEMPT + 1))

        if [ $DOWNLOAD_ATTEMPT -lt $MAX_ATTEMPTS ]; then
            echo_warn "Deleting corrupted ISO and retrying download (attempt $((DOWNLOAD_ATTEMPT + 1))/$MAX_ATTEMPTS)..."
            rm -f "$UBUNTU_ISO_NAME" "SHA256SUMS"
        else
            echo_error "ISO verification failed after $MAX_ATTEMPTS attempts"
            echo_error "Please check your network connection and try again"
            rm -f "$UBUNTU_ISO_NAME" "SHA256SUMS"
            exit 1
        fi
    fi
done

# Extract ISO
echo_info "Extracting Ubuntu ISO..."
mkdir -p "$EXTRACT_DIR"

# Extract ISO contents (platform-specific)
if $IS_MACOS; then
    # macOS can't mount Linux hybrid ISOs with hdiutil, use xorriso to extract
    echo_info "Using xorriso to extract ISO contents (macOS)..."
    xorriso -osirrox on -indev "$UBUNTU_ISO_NAME" -extract / "$EXTRACT_DIR"
else
    # Linux can mount the ISO directly
    mkdir -p "$MOUNT_DIR"
    sudo mount -o loop "$UBUNTU_ISO_NAME" "$MOUNT_DIR"

    # Copy contents
    echo_info "Copying ISO contents..."
    rsync -a "$MOUNT_DIR/" "$EXTRACT_DIR/"

    # Unmount
    sudo umount "$MOUNT_DIR"
fi

# Make extracted files writable
chmod -R u+w "$EXTRACT_DIR"

# Copy Purple Computer files
echo_info "Copying Purple Computer files..."
mkdir -p "$EXTRACT_DIR/purple_files"

# Copy Purple REPL code
cp -r "$PROJECT_ROOT/purple_repl"/* "$EXTRACT_DIR/purple_files/"

# Copy system configuration files
cp -r "$PROJECT_ROOT/autoinstall/files/systemd" "$EXTRACT_DIR/purple_files/"
cp "$PROJECT_ROOT/autoinstall/files/xinit/xinitrc" "$EXTRACT_DIR/purple_files/"
cp "$PROJECT_ROOT/autoinstall/files/kitty/kitty.conf" "$EXTRACT_DIR/purple_files/"

# Copy autoinstall configuration
echo_info "Injecting autoinstall configuration..."
cp "$PROJECT_ROOT/autoinstall/autoinstall.yaml" "$EXTRACT_DIR/autoinstall.yaml"

# Create user-data and meta-data for cloud-init
mkdir -p "$EXTRACT_DIR/nocloud"
cp "$PROJECT_ROOT/autoinstall/autoinstall.yaml" "$EXTRACT_DIR/nocloud/user-data"
touch "$EXTRACT_DIR/nocloud/meta-data"

# Modify GRUB configuration for autoinstall
echo_info "Modifying boot configuration..."
cat > "$EXTRACT_DIR/boot/grub/grub.cfg" <<'GRUB_EOF'
set timeout=5

menuentry "Install Purple Computer (Automatic)" {
    set gfxpayload=keep
    linux /casper/vmlinuz autoinstall ds=nocloud\;s=/cdrom/nocloud/ quiet splash ---
    initrd /casper/initrd
}

menuentry "Install Purple Computer (Manual)" {
    set gfxpayload=keep
    linux /casper/vmlinuz quiet splash ---
    initrd /casper/initrd
}
GRUB_EOF

# Update isolinux for legacy boot
if [ -f "$EXTRACT_DIR/isolinux/txt.cfg" ]; then
    cat > "$EXTRACT_DIR/isolinux/txt.cfg" <<'ISOLINUX_EOF'
default install
label install
  menu label ^Install Purple Computer (Automatic)
  kernel /casper/vmlinuz
  append initrd=/casper/initrd autoinstall ds=nocloud;s=/cdrom/nocloud/ quiet splash ---
ISOLINUX_EOF
fi

# Calculate MD5 sums
echo_info "Calculating MD5 checksums..."
cd "$EXTRACT_DIR"
rm -f md5sum.txt
if $IS_MACOS; then
    find . -type f -print0 | xargs -0 md5 -r | grep -v isolinux/boot.cat > md5sum.txt
else
    find . -type f -print0 | xargs -0 md5sum | grep -v isolinux/boot.cat > md5sum.txt
fi

# Build the new ISO
echo_info "Building Purple Computer ISO..."
cd "$WORK_DIR"
if $IS_MACOS; then
    xorriso -as mkisofs \
        -r -V "Purple Computer" \
        -o "$OUTPUT_ISO" \
        -J -l \
        -c boot.catalog \
        -b boot/grub/i386-pc/eltorito.img \
        -no-emul-boot -boot-load-size 4 -boot-info-table \
        -eltorito-alt-boot \
        -e EFI/boot/grubx64.efi \
        -no-emul-boot \
        -isohybrid-gpt-basdat \
        "$EXTRACT_DIR"
else
    sudo xorriso -as mkisofs \
        -r -V "Purple Computer" \
        -o "$OUTPUT_ISO" \
        -J -l \
        -c boot.catalog \
        -b boot/grub/i386-pc/eltorito.img \
        -no-emul-boot -boot-load-size 4 -boot-info-table \
        -eltorito-alt-boot \
        -e EFI/boot/grubx64.efi \
        -no-emul-boot \
        -isohybrid-gpt-basdat \
        "$EXTRACT_DIR"

    # Make ISO readable by user (get actual primary group instead of assuming it matches username)
    USER_GROUP=$(id -gn)
    sudo chown "$USER:$USER_GROUP" "$OUTPUT_ISO"
fi

# Cleanup
echo_info "Cleaning up..."
rm -rf "$WORK_DIR/mount" "$WORK_DIR/extract"

# Success!
echo_info "======================================"
echo_info "Purple Computer ISO built successfully!"
echo_info "======================================"
echo_info "ISO location: $OUTPUT_ISO"
echo_info "Size: $(du -h "$OUTPUT_ISO" | cut -f1)"
echo ""
echo_info "Next steps:"
echo_info "1. Write ISO to USB: sudo dd if=$OUTPUT_ISO of=/dev/sdX bs=4M status=progress"
echo_info "2. Boot from USB and installation will proceed automatically"
echo_info "3. See docs/autoinstall.md for detailed instructions"
echo ""
echo_warn "Note: Keep the build directory if you want to rebuild quickly."
echo_warn "Delete it with: rm -rf $WORK_DIR"
