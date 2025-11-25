#!/bin/bash
# Purple Computer ISO Builder
# This script creates a bootable Ubuntu ISO with Purple Computer pre-configured

set -e  # Exit on error

# Configuration
UBUNTU_VERSION="22.04.3"
UBUNTU_ISO_URL="https://releases.ubuntu.com/22.04/ubuntu-22.04.3-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-22.04.3-live-server-amd64.iso"
OUTPUT_ISO="purple-computer.iso"
WORK_DIR="build"
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
DEPS="xorriso isolinux curl wget"
for dep in $DEPS; do
    if ! command -v $dep &> /dev/null; then
        echo_error "$dep is not installed. Please install it first."
        echo "Run: sudo apt install xorriso isolinux curl wget"
        exit 1
    fi
done

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

# Copy files from parent directory
cp -r ../files/* "$EXTRACT_DIR/purple_files/"

# Copy autoinstall configuration
echo_info "Injecting autoinstall configuration..."
cp ../autoinstall.yaml "$EXTRACT_DIR/autoinstall.yaml"

# Modify GRUB configuration for autoinstall
echo_info "Modifying boot configuration..."
cat > "$EXTRACT_DIR/boot/grub/grub.cfg" <<'GRUB_EOF'
set timeout=5

menuentry "Install Purple Computer (Automatic)" {
    set gfxpayload=keep
    linux /casper/vmlinuz autoinstall ds=nocloud\;s=/cdrom/ quiet splash ---
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
  append initrd=/casper/initrd autoinstall ds=nocloud;s=/cdrom/ quiet splash ---
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
