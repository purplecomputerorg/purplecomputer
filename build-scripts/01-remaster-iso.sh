#!/usr/bin/env bash
# Remaster Ubuntu Server ISO for Purple Computer installer
#
# ARCHITECTURE: Initramfs Injection
# - Download official Ubuntu Server 24.04 ISO
# - Extract and modify initramfs only (add early hook script)
# - Leave squashfs completely untouched
# - Add payload files to ISO root
# - Rebuild ISO
#
# The hook script runs before casper, checks for our payload,
# and either runs our installer or falls through to normal boot.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
WORK_DIR="${BUILD_DIR}/remaster"
GOLDEN_IMAGE="${BUILD_DIR}/purple-os.img.zst"

# Ubuntu Server 24.04.1 LTS
UBUNTU_ISO_URL="https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-24.04.1-live-server-amd64.iso"
UBUNTU_ISO="${BUILD_DIR}/${UBUNTU_ISO_NAME}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

create_installer_hook() {
    local HOOK_DIR="$1"

    # Create the Purple installer hook script
    cat > "$HOOK_DIR/01_purple_installer" << 'HOOK_EOF'
#!/bin/sh
# Purple Computer Installer Hook
# Runs early in initramfs, before casper mounts squashfs
#
# If purple installer payload is found: run it and reboot
# If not found: exit normally and let casper continue

PREREQ=""
prereqs() { echo "$PREREQ"; }
case "$1" in
    prereqs) prereqs; exit 0 ;;
esac

# Source initramfs functions
. /scripts/functions

log_begin_msg "Checking for Purple Computer installer"

# Wait for devices to settle
sleep 2

# Find the boot device (the USB/ISO we booted from)
# Look for a device with PURPLE_INSTALLER label or purple-install script
INSTALLER_SCRIPT=""
INSTALLER_DEV=""

for dev in /dev/sd* /dev/nvme*n*p* /dev/vd*; do
    [ -b "$dev" ] || continue

    # Try to mount and check for our payload
    TMPMNT="/tmp/purple-check-$$"
    mkdir -p "$TMPMNT"

    if mount -o ro "$dev" "$TMPMNT" 2>/dev/null; then
        if [ -x "$TMPMNT/purple/install.sh" ]; then
            INSTALLER_SCRIPT="$TMPMNT/purple/install.sh"
            INSTALLER_DEV="$dev"
            log_success_msg "Found Purple installer on $dev"
            break
        fi
        umount "$TMPMNT" 2>/dev/null || true
    fi
    rmdir "$TMPMNT" 2>/dev/null || true
done

# If no installer found, let casper continue normally
if [ -z "$INSTALLER_SCRIPT" ]; then
    log_end_msg 0
    exit 0
fi

# ============================================
# PURPLE INSTALLER MODE
# ============================================

log_begin_msg "Starting Purple Computer installation"

# Clear the screen and show splash
clear
echo ""
echo "================================================="
echo ""
echo "        Purple Computer Installer"
echo ""
echo "================================================="
echo ""

# The install script is on the mounted device
# It expects PURPLE_PAYLOAD_DIR to point to the payload location
export PURPLE_PAYLOAD_DIR="$(dirname "$INSTALLER_SCRIPT")"

# Run the installer
if "$INSTALLER_SCRIPT"; then
    echo ""
    echo "Installation complete!"
    echo ""
    echo "Remove the USB drive and press Enter to reboot..."
    read -r _
    reboot -f
else
    echo ""
    echo "Installation failed!"
    echo ""
    echo "Press Enter to drop to emergency shell..."
    read -r _
    exec /bin/sh
fi

# Should not reach here
exit 0
HOOK_EOF

    chmod +x "$HOOK_DIR/01_purple_installer"
}

create_install_script() {
    local DEST="$1"

    # Copy the install script to the payload directory
    cp "$SCRIPT_DIR/install.sh" "$DEST/install.sh"
    chmod +x "$DEST/install.sh"
}

main() {
    log_step "Purple Computer ISO Remaster (Initramfs Injection)"
    log_info "Architecture: Modify initramfs, leave squashfs untouched"

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    # Check for golden image
    if [ ! -f "$GOLDEN_IMAGE" ]; then
        echo "ERROR: Golden image not found: $GOLDEN_IMAGE"
        echo "Run step 0 first: ./build-all.sh 0"
        exit 1
    fi

    # Setup directories
    mkdir -p "$WORK_DIR"
    mkdir -p /opt/purple-installer/output

    # Step 1: Download Ubuntu Server ISO if needed
    log_step "1/7: Checking Ubuntu Server ISO..."
    if [ -f "$UBUNTU_ISO" ]; then
        log_info "Using cached ISO: $UBUNTU_ISO"
    else
        log_info "Downloading Ubuntu Server ISO..."
        wget -O "$UBUNTU_ISO" "$UBUNTU_ISO_URL"
    fi
    log_info "ISO size: $(du -h "$UBUNTU_ISO" | cut -f1)"

    # Step 2: Setup working directories
    log_step "2/7: Setting up working directories..."
    rm -rf "$WORK_DIR/iso-mount" "$WORK_DIR/iso-new" "$WORK_DIR/initrd-work"
    mkdir -p "$WORK_DIR/iso-mount" "$WORK_DIR/iso-new" "$WORK_DIR/initrd-work"

    # Step 3: Mount and copy ISO contents
    log_step "3/7: Extracting ISO contents..."
    mount -o loop,ro "$UBUNTU_ISO" "$WORK_DIR/iso-mount"

    # Copy everything from ISO
    rsync -a --info=progress2 "$WORK_DIR/iso-mount/" "$WORK_DIR/iso-new/"

    # Step 4: Extract and modify initramfs
    log_step "4/7: Modifying initramfs..."

    # Find the initrd (might be named differently)
    INITRD_PATH=""
    for path in "$WORK_DIR/iso-new/casper/initrd" "$WORK_DIR/iso-new/casper/initrd.img" "$WORK_DIR/iso-new/casper/initrd.lz"; do
        if [ -f "$path" ]; then
            INITRD_PATH="$path"
            break
        fi
    done

    if [ -z "$INITRD_PATH" ]; then
        echo "ERROR: Cannot find initrd in ISO"
        ls -la "$WORK_DIR/iso-new/casper/"
        exit 1
    fi

    log_info "Found initrd: $INITRD_PATH"

    # Extract initramfs (Ubuntu uses concatenated cpio archives)
    cd "$WORK_DIR/initrd-work"
    unmkinitramfs "$INITRD_PATH" .

    # Find the main initramfs directory (contains /scripts)
    MAIN_DIR=""
    for dir in main early early2 early3; do
        if [ -d "$dir/scripts" ]; then
            MAIN_DIR="$dir"
            break
        fi
    done

    if [ -z "$MAIN_DIR" ]; then
        # Single archive format
        if [ -d "scripts" ]; then
            MAIN_DIR="."
        else
            echo "ERROR: Cannot find scripts directory in initramfs"
            ls -la
            exit 1
        fi
    fi

    log_info "Main initramfs directory: $MAIN_DIR"

    # Add our hook script
    log_info "Adding Purple installer hook..."
    create_installer_hook "$MAIN_DIR/scripts/init-top"

    # Update the ORDER file to include our hook (runs after udev so devices are available)
    if [ -f "$MAIN_DIR/scripts/init-top/ORDER" ]; then
        # Insert our script after udev
        sed -i '/udev.*\$@/a /scripts/init-top/01_purple_installer "$@"\n[ -e /conf/param.conf ] \&\& . /conf/param.conf' \
            "$MAIN_DIR/scripts/init-top/ORDER"
    fi

    # Repack initramfs
    log_info "Repacking initramfs..."

    # Ubuntu's initrd is typically: early (microcode) + early2 + early3 + main
    # We need to recreate this structure
    NEW_INITRD="$WORK_DIR/new-initrd"
    rm -f "$NEW_INITRD"

    # Repack each component
    for component in early early2 early3; do
        if [ -d "$component" ]; then
            (cd "$component" && find . -print0 | cpio --null -o -H newc 2>/dev/null) >> "$NEW_INITRD"
        fi
    done

    # Repack main (compressed with zstd for Ubuntu 24.04)
    if [ "$MAIN_DIR" = "main" ]; then
        (cd main && find . -print0 | cpio --null -o -H newc 2>/dev/null | zstd -19 -T0) >> "$NEW_INITRD"
    elif [ "$MAIN_DIR" = "." ]; then
        # Single archive, compress the whole thing
        (find . -print0 | cpio --null -o -H newc 2>/dev/null | zstd -19 -T0) > "$NEW_INITRD"
    fi

    # Replace initrd in ISO
    cp "$NEW_INITRD" "$INITRD_PATH"
    log_info "Initramfs modified successfully"

    # Step 5: Add payload to ISO
    log_step "5/7: Adding payload to ISO..."

    PAYLOAD_DIR="$WORK_DIR/iso-new/purple"
    mkdir -p "$PAYLOAD_DIR"

    # Copy golden image
    log_info "Copying golden image (this takes a while)..."
    cp "$GOLDEN_IMAGE" "$PAYLOAD_DIR/purple-os.img.zst"

    # Copy install script
    create_install_script "$PAYLOAD_DIR"

    # Unmount source ISO
    umount "$WORK_DIR/iso-mount"

    # Step 6: Update ISO metadata
    log_step "6/7: Updating ISO metadata..."

    # Update the volume label
    # (GRUB and other tools may reference this)

    # Step 7: Rebuild ISO
    log_step "7/7: Building final ISO..."

    OUTPUT_ISO="/opt/purple-installer/output/purple-installer-$(date +%Y%m%d).iso"

    # Use xorriso to rebuild ISO preserving boot structure
    xorriso -as mkisofs \
        -r -V "PURPLE_INSTALLER" \
        -o "$OUTPUT_ISO" \
        -J -joliet-long \
        -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
        -partition_offset 16 \
        -c isolinux/boot.cat \
        -b isolinux/isolinux.bin \
        -no-emul-boot -boot-load-size 4 -boot-info-table \
        -eltorito-alt-boot \
        -e boot/grub/efi.img \
        -no-emul-boot -isohybrid-gpt-basdat \
        "$WORK_DIR/iso-new"

    # Generate checksum
    sha256sum "$OUTPUT_ISO" > "${OUTPUT_ISO}.sha256"

    log_info "ISO built successfully!"
    log_info "Output: $OUTPUT_ISO"
    log_info "Size: $(du -h "$OUTPUT_ISO" | cut -f1)"
    log_info "SHA256: $(cat "${OUTPUT_ISO}.sha256")"

    # Cleanup
    log_info "Cleaning up working directories..."
    rm -rf "$WORK_DIR/iso-mount" "$WORK_DIR/iso-new" "$WORK_DIR/initrd-work" "$WORK_DIR/new-initrd"
}

main "$@"
