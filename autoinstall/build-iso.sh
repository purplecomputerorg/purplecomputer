#!/bin/bash
# Purple Computer ISO Builder
# This script creates a bootable Ubuntu Server ISO with Purple Computer pre-configured
# Architecture: Ubuntu Server + minimal Xorg (no desktop) + kitty fullscreen
#
# Run from project root: ./autoinstall/build-iso.sh
# Or from autoinstall/: ./build-iso.sh

set -e  # Exit on error

# Determine script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ "$(basename $SCRIPT_DIR)" = "autoinstall" ]; then
    PROJECT_ROOT="$SCRIPT_DIR/.."
    cd "$PROJECT_ROOT"
else
    PROJECT_ROOT="$SCRIPT_DIR"
fi

# Configuration
UBUNTU_VERSION="22.04.3"
UBUNTU_ISO_URL="https://releases.ubuntu.com/22.04/ubuntu-22.04.3-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-22.04.3-live-server-amd64.iso"
OUTPUT_ISO="purple-computer.iso"
WORK_DIR="autoinstall/build"
MOUNT_DIR="$WORK_DIR/mount"
EXTRACT_DIR="$WORK_DIR/extract"

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

# Check for command-line tools
COMMANDS="xorriso curl wget rsync"
for cmd in $COMMANDS; do
    if ! command -v $cmd &> /dev/null; then
        echo_error "$cmd is not installed. Please install it first."
        echo "  Debian/Ubuntu: sudo apt install $cmd"
        echo "  Fedora: sudo dnf install $cmd"
        echo "  Arch: sudo pacman -S $cmd"
        echo "  NixOS: Add $cmd to your environment.systemPackages"
        exit 1
    fi
done

# Check for isolinux.bin (provided by isolinux or syslinux package)
echo_info "Checking for isolinux.bin..."
ISOLINUX_FOUND=false
ISOLINUX_PATHS=(
    "/usr/lib/ISOLINUX/isolinux.bin"
    "/usr/lib/syslinux/isolinux.bin"
    "/usr/share/syslinux/isolinux.bin"
    "/usr/lib/syslinux/bios/isolinux.bin"
    "/usr/lib/SYSLINUX/isolinux.bin"
)

# Also check NixOS store if it exists
if [ -d "/nix/store" ]; then
    ISOLINUX_PATHS+=($( find /nix/store -path "*/share/syslinux/isolinux.bin" 2>/dev/null || true ))
fi

for path in "${ISOLINUX_PATHS[@]}"; do
    if [ -f "$path" ]; then
        ISOLINUX_FOUND=true
        ISOLINUX_BIN="$path"
        echo_info "Found isolinux.bin at: $path"
        break
    fi
done

if [ "$ISOLINUX_FOUND" = false ]; then
    echo_error "isolinux.bin not found in standard locations."
    echo "  Debian/Ubuntu: sudo apt install isolinux"
    echo "  Fedora: sudo dnf install syslinux"
    echo "  Arch: sudo pacman -S syslinux"
    echo "  NixOS: Add 'syslinux' to your environment.systemPackages"
    exit 1
fi

# Create work directory
echo_info "Creating work directory..."
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Download Ubuntu ISO if not present
if [ ! -f "$UBUNTU_ISO_NAME" ]; then
    echo_info "Downloading Ubuntu $UBUNTU_VERSION ISO..."
    echo_warn "This is a large file (~1.4GB) and may take a while..."
    wget -O "$UBUNTU_ISO_NAME" "$UBUNTU_ISO_URL"
else
    echo_info "Ubuntu ISO already downloaded, skipping."
fi

# Extract ISO
echo_info "Extracting Ubuntu ISO..."
mkdir -p "$MOUNT_DIR" "$EXTRACT_DIR"

# Mount ISO
sudo mount -o loop "$UBUNTU_ISO_NAME" "$MOUNT_DIR"

# Copy contents
echo_info "Copying ISO contents..."
rsync -a "$MOUNT_DIR/" "$EXTRACT_DIR/"

# Unmount
sudo umount "$MOUNT_DIR"

# Make extracted files writable
chmod -R u+w "$EXTRACT_DIR"

# Copy Purple Computer files
echo_info "Copying Purple Computer files..."
mkdir -p "$EXTRACT_DIR/purple_files"

# Copy Purple REPL code
cp -r purple_repl/* "$EXTRACT_DIR/purple_files/"

# Copy system configuration files
cp -r autoinstall/files/systemd "$EXTRACT_DIR/purple_files/"
cp autoinstall/files/xinit/xinitrc "$EXTRACT_DIR/purple_files/"
cp autoinstall/files/kitty/kitty.conf "$EXTRACT_DIR/purple_files/"

# Copy autoinstall configuration
echo_info "Injecting autoinstall configuration..."
cp autoinstall/autoinstall.yaml "$EXTRACT_DIR/autoinstall.yaml"

# Create user-data and meta-data for cloud-init
mkdir -p "$EXTRACT_DIR/nocloud"
cp autoinstall/autoinstall.yaml "$EXTRACT_DIR/nocloud/user-data"
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
sudo rm -f md5sum.txt
find -type f -print0 | sudo xargs -0 md5sum | grep -v isolinux/boot.cat | sudo tee md5sum.txt

# Build the new ISO
echo_info "Building Purple Computer ISO..."
cd ..
sudo xorriso -as mkisofs \
    -iso-level 3 \
    -full-iso9660-filenames \
    -volid "Purple Computer" \
    -eltorito-boot isolinux/isolinux.bin \
    -eltorito-catalog isolinux/boot.cat \
    -no-emul-boot \
    -boot-load-size 4 \
    -boot-info-table \
    -eltorito-alt-boot \
    -e boot/grub/efi.img \
    -no-emul-boot \
    -append_partition 2 0xef boot/grub/efi.img \
    -output "../$OUTPUT_ISO" \
    -graft-points \
        "." \
        "$EXTRACT_DIR"

cd ..

# Make ISO readable by user
sudo chown $USER:$USER "$OUTPUT_ISO"

# Cleanup
echo_info "Cleaning up..."
sudo rm -rf "$WORK_DIR/mount" "$WORK_DIR/extract"

# Success!
echo_info "======================================"
echo_info "Purple Computer ISO built successfully!"
echo_info "======================================"
echo_info "ISO location: $(pwd)/$OUTPUT_ISO"
echo_info "Size: $(du -h $OUTPUT_ISO | cut -f1)"
echo ""
echo_info "Next steps:"
echo_info "1. Write ISO to USB: sudo dd if=$OUTPUT_ISO of=/dev/sdX bs=4M status=progress"
echo_info "2. Boot from USB and installation will proceed automatically"
echo_info "3. See docs/autoinstall.md for detailed instructions"
echo ""
echo_warn "Note: Keep the build directory if you want to rebuild quickly."
echo_warn "Delete it with: rm -rf $WORK_DIR"
