#!/bin/bash
# Purple Computer ISO Builder (Linux only)
# Creates a bootable Ubuntu Server ISO with Purple Computer pre-configured
# Architecture: Ubuntu Server + minimal Xorg (no desktop) + alacritty fullscreen
#
# Requirements: Linux, Docker, xorriso, curl, rsync
#
# Usage:
#   ./autoinstall/build-iso.sh         # Standard ISO (requires Enter to install)
#   ./autoinstall/build-iso.sh --test  # Test ISO (auto-installs for VM testing)
#
# All builds are offline-capable with packages bundled (~4-5GB)

set -e

# Parse arguments
TEST_MODE=false
for arg in "$@"; do
    case $arg in
        --test)
            TEST_MODE=true
            shift
            ;;
    esac
done

# Get the directory where this script lives and determine project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
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
POOL_DIR="$WORK_DIR/pool"

# Packages to bundle for offline install (must match autoinstall.yaml)
OFFLINE_PACKAGES=(
    # Display
    xorg
    xinit
    xserver-xorg-video-all
    matchbox-window-manager
    alacritty
    # Boot splash
    plymouth
    plymouth-themes
    # Python
    python3
    python3-pip
    python3-venv
    ipython3
    # Audio
    espeak-ng
    alsa-utils
    pulseaudio
    # Fonts
    fonts-noto
    fonts-noto-color-emoji
    fonts-dejavu
    # Tools
    git
    curl
    wget
    vim
    less
    # Build tools
    build-essential
    python3-dev
    # WiFi (Mac support)
    bcmwl-kernel-source
    firmware-b43-installer
    b43-fwcutter
    wpasupplicant
    wireless-tools
    iw
    rfkill
)

# Cleanup on exit
cleanup() {
    sudo umount "$MOUNT_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Linux
if [ "$(uname -s)" != "Linux" ]; then
    error "This script only runs on Linux."
    echo "  Use a Linux VM or WSL2 to build the ISO."
    exit 1
fi

# Check not root
if [ "$EUID" -eq 0 ]; then
    error "Don't run as root. Script will use sudo when needed."
    exit 1
fi

# Check dependencies
info "Checking dependencies..."
for cmd in xorriso curl rsync docker; do
    if ! command -v $cmd &> /dev/null; then
        error "$cmd is not installed."
        echo "  Install with: sudo apt install $cmd"
        [ "$cmd" = "docker" ] && echo "  Then: sudo usermod -aG docker $USER && newgrp docker"
        exit 1
    fi
done

# Check Docker running
if ! docker info &> /dev/null; then
    error "Docker daemon not running. Start it with: sudo systemctl start docker"
    exit 1
fi

# Download packages using Docker
download_packages() {
    info "Downloading packages for offline install..."
    warn "This may take 5-10 minutes on first run (cached for subsequent builds)"

    mkdir -p "$POOL_DIR"

    # Create download script
    cat > "$WORK_DIR/download-packages.sh" <<'SCRIPT'
#!/bin/bash
set -e
apt-get update

cd /pool
apt-get download $(apt-cache depends --recurse --no-recommends --no-suggests \
    --no-conflicts --no-breaks --no-replaces --no-enhances \
    "$@" | grep "^\w" | sort -u)

dpkg-scanpackages . /dev/null > Packages
gzip -k -f Packages
echo "Downloaded $(ls -1 *.deb 2>/dev/null | wc -l) packages"
SCRIPT
    chmod +x "$WORK_DIR/download-packages.sh"

    docker run --rm \
        -v "$POOL_DIR:/pool" \
        -v "$WORK_DIR/download-packages.sh:/download.sh" \
        ubuntu:24.04 \
        /bin/bash -c "/download.sh ${OFFLINE_PACKAGES[*]}"

    PKG_COUNT=$(ls -1 "$POOL_DIR"/*.deb 2>/dev/null | wc -l)
    if [ "$PKG_COUNT" -eq 0 ]; then
        error "No packages downloaded!"
        exit 1
    fi
    info "Downloaded $PKG_COUNT packages"
}

# Verify ISO checksum
verify_checksum() {
    info "Verifying ISO checksum..."

    if [ ! -f "SHA256SUMS" ] || [ "$1" = "force" ]; then
        curl -fsSL -o "SHA256SUMS" "$UBUNTU_SHA256_URL" || { error "Failed to download SHA256SUMS"; return 1; }
    fi

    EXPECTED=$(grep "$UBUNTU_ISO_NAME" SHA256SUMS | awk '{print $1}')
    [ -z "$EXPECTED" ] && { error "Checksum not found for $UBUNTU_ISO_NAME"; return 1; }

    info "Calculating checksum..."
    ACTUAL=$(sha256sum "$UBUNTU_ISO_NAME" | awk '{print $1}')

    if [ "$EXPECTED" = "$ACTUAL" ]; then
        info "✓ Checksum OK"
        return 0
    else
        error "✗ Checksum mismatch!"
        return 1
    fi
}

# Create work directory
info "Creating work directory..."
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Download Ubuntu ISO
ATTEMPTS=0
while [ $ATTEMPTS -lt 2 ]; do
    if [ ! -f "$UBUNTU_ISO_NAME" ]; then
        info "Downloading Ubuntu $UBUNTU_VERSION ISO (~2.5GB)..."
        curl -fL --progress-bar -o "$UBUNTU_ISO_NAME" "$UBUNTU_ISO_URL" || { error "Download failed"; rm -f "$UBUNTU_ISO_NAME"; exit 1; }
    else
        info "Ubuntu ISO already downloaded"
    fi

    if verify_checksum "force"; then
        break
    else
        ATTEMPTS=$((ATTEMPTS + 1))
        [ $ATTEMPTS -lt 2 ] && { warn "Retrying download..."; rm -f "$UBUNTU_ISO_NAME" "SHA256SUMS"; }
    fi
done
[ $ATTEMPTS -ge 2 ] && { error "ISO verification failed"; exit 1; }

# Extract ISO
info "Extracting ISO..."
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR" "$MOUNT_DIR"
sudo mount -o loop "$UBUNTU_ISO_NAME" "$MOUNT_DIR"
rsync -a "$MOUNT_DIR/" "$EXTRACT_DIR/"
sudo umount "$MOUNT_DIR"
chmod -R u+w "$EXTRACT_DIR"

# Download packages (or use cache)
if [ ! -f "$POOL_DIR/Packages.gz" ]; then
    download_packages
else
    info "Using cached packages ($(ls -1 "$POOL_DIR"/*.deb 2>/dev/null | wc -l) packages)"
fi

# Copy package pool to ISO
info "Adding package pool to ISO..."
mkdir -p "$EXTRACT_DIR/pool"
cp -r "$POOL_DIR"/* "$EXTRACT_DIR/pool/"

# Copy Purple Computer files
info "Adding Purple Computer files..."
mkdir -p "$EXTRACT_DIR/purple_files"
cp -r "$PROJECT_ROOT/purple_tui"/* "$EXTRACT_DIR/purple_files/"
cp -r "$PROJECT_ROOT/autoinstall/files/systemd" "$EXTRACT_DIR/purple_files/"
cp "$PROJECT_ROOT/autoinstall/files/xinit/xinitrc" "$EXTRACT_DIR/purple_files/"
cp "$PROJECT_ROOT/autoinstall/files/alacritty/alacritty.toml" "$EXTRACT_DIR/purple_files/"

# Copy Plymouth theme
info "Adding Plymouth theme..."
mkdir -p "$EXTRACT_DIR/purple_files/plymouth"
cp -r "$PROJECT_ROOT/autoinstall/files/plymouth/purple" "$EXTRACT_DIR/purple_files/plymouth/"

# Copy autoinstall config
info "Adding autoinstall configuration..."
mkdir -p "$EXTRACT_DIR/nocloud"
cp "$PROJECT_ROOT/autoinstall/autoinstall.yaml" "$EXTRACT_DIR/nocloud/user-data"
touch "$EXTRACT_DIR/nocloud/meta-data"

# Configure GRUB with larger font for high-DPI displays
info "Configuring bootloader..."

# Create larger GRUB font (if grub-mkfont available in Docker)
info "Creating larger boot font..."
docker run --rm -v "$EXTRACT_DIR/boot/grub:/grub" ubuntu:24.04 bash -c '
    apt-get update -qq && apt-get install -qq -y grub-common fonts-dejavu-core >/dev/null 2>&1
    grub-mkfont -s 32 -o /grub/fonts/dejavu_32.pf2 /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf 2>/dev/null || true
' || warn "Could not create large font, using default"

if $TEST_MODE; then
    warn "TEST MODE: Auto-install enabled"
    cat > "$EXTRACT_DIR/boot/grub/grub.cfg" <<'EOF'
set timeout=3
set default=0
insmod all_video
set gfxpayload=keep

menuentry "Purple Computer TEST INSTALL (auto-starts in 3s)" {
    linux /casper/vmlinuz autoinstall ds=nocloud\;s=/cdrom/nocloud/ quiet splash ---
    initrd /casper/initrd
}
EOF
else
    cat > "$EXTRACT_DIR/boot/grub/grub.cfg" <<'EOF'
# Purple Computer Installer
insmod all_video
insmod gfxterm

set gfxmode=1024x768,auto
set gfxpayload=keep
terminal_output gfxterm

# Load larger font if available
if [ -f /boot/grub/fonts/dejavu_32.pf2 ]; then
    loadfont /boot/grub/fonts/dejavu_32.pf2
fi

# Colors
set menu_color_normal=white/black
set menu_color_highlight=black/white

set timeout=-1
set default=0

# Show header
echo ""
echo "    PURPLE COMPUTER INSTALLER"
echo "    ========================="
echo ""
echo "    WARNING: This will ERASE ALL DATA on the disk!"
echo ""

menuentry "Install Purple Computer" {
    linux /casper/vmlinuz autoinstall ds=nocloud\;s=/cdrom/nocloud/ quiet splash ---
    initrd /casper/initrd
}

menuentry "Cancel (power off)" {
    halt
}
EOF
fi

# Calculate checksums
info "Calculating checksums..."
cd "$EXTRACT_DIR"
find . -type f -print0 | xargs -0 md5sum 2>/dev/null | grep -v isolinux/boot.cat > md5sum.txt || true

# Build ISO
info "Building ISO..."
cd "$WORK_DIR"

# Get boot parameters from source ISO
XORRISO_OPTS=$(xorriso -indev "$UBUNTU_ISO_NAME" -report_system_area as_mkisofs 2>&1)
EFI_PARTITION_INTERVAL=$(echo "$XORRISO_OPTS" | grep -o -- '--interval:local_fs:[0-9]*d-[0-9]*d::' | head -1 | sed "s/--interval:local_fs://;s/:://")
EFI_BOOT_INTERVAL=$(echo "$XORRISO_OPTS" | grep -o -- "appended_partition_2_start_[0-9]*s_size_[0-9]*d" | head -1)
EFI_BOOT_LOAD_SIZE=$(echo "$XORRISO_OPTS" | grep "boot-load-size" | tail -1 | awk '{print $2}')

[ -z "$EFI_PARTITION_INTERVAL" ] || [ -z "$EFI_BOOT_INTERVAL" ] && { error "Could not extract boot parameters"; exit 1; }

sudo xorriso -as mkisofs \
    -r -V "Purple Computer" \
    -o "$OUTPUT_ISO" \
    -J -l \
    --grub2-mbr --interval:local_fs:0s-15s:zero_mbrpt,zero_gpt:"$UBUNTU_ISO_NAME" \
    --protective-msdos-label \
    -partition_cyl_align off \
    -partition_offset 16 \
    --mbr-force-bootable \
    -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b --interval:local_fs:${EFI_PARTITION_INTERVAL}::"$UBUNTU_ISO_NAME" \
    -appended_part_as_gpt \
    -iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
    -c boot.catalog \
    -b boot/grub/i386-pc/eltorito.img \
    -no-emul-boot -boot-load-size 4 -boot-info-table \
    --grub2-boot-info \
    -eltorito-alt-boot \
    -e --interval:${EFI_BOOT_INTERVAL}:all:: \
    -no-emul-boot \
    -boot-load-size "$EFI_BOOT_LOAD_SIZE" \
    "$EXTRACT_DIR"

sudo chown "$USER:$(id -gn)" "$OUTPUT_ISO"

# Cleanup
info "Cleaning up..."
rm -rf "$WORK_DIR/mount" "$WORK_DIR/extract"

# Done
echo ""
info "======================================"
info "Purple Computer ISO built successfully!"
info "======================================"
info "ISO: $OUTPUT_ISO"
info "Size: $(du -h "$OUTPUT_ISO" | cut -f1)"
echo ""
info "Write to USB:"
info "  sudo dd if=$OUTPUT_ISO of=/dev/sdX bs=4M status=progress"
echo ""
warn "Package cache kept at: $POOL_DIR"
warn "Delete to re-download: rm -rf $POOL_DIR"
