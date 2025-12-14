#!/usr/bin/env bash
# Remaster Ubuntu Server ISO for Purple Computer installer
#
# ARCHITECTURE: ISO Remaster (not debootstrap)
# We take an official Ubuntu Server 24.04 ISO and modify it:
# - Keep Ubuntu's entire boot stack as a black box (shim, GRUB, kernel, initramfs, casper)
# - Mask Subiquity and cloud-init services
# - Add our payload (golden image, installer script, systemd service)
# - Rebuild the ISO
#
# This avoids all casper/initramfs dependency hell by not rebuilding any of it.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
WORK_DIR="${BUILD_DIR}/remaster"
GOLDEN_IMAGE="${BUILD_DIR}/purple-os.img.zst"

# Ubuntu Server 24.04.1 LTS - smaller than Desktop, easier to modify
UBUNTU_ISO_URL="https://releases.ubuntu.com/24.04.1/ubuntu-24.04.1-live-server-amd64.iso"
UBUNTU_ISO_NAME="ubuntu-24.04.1-live-server-amd64.iso"
UBUNTU_ISO="${BUILD_DIR}/${UBUNTU_ISO_NAME}"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

cleanup() {
    log_info "Cleaning up mounts..."
    umount "${WORK_DIR}/iso-mount" 2>/dev/null || true
    umount "${WORK_DIR}/squashfs-root/dev" 2>/dev/null || true
    umount "${WORK_DIR}/squashfs-root/proc" 2>/dev/null || true
    umount "${WORK_DIR}/squashfs-root/sys" 2>/dev/null || true
}

trap cleanup EXIT

main() {
    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run as root"
        exit 1
    fi

    log_step "=== Purple Computer ISO Remaster ==="
    log_info "Architecture: Remaster official Ubuntu ISO (not debootstrap)"
    echo

    # Check for golden image
    if [ ! -f "$GOLDEN_IMAGE" ]; then
        echo "ERROR: Golden image not found: $GOLDEN_IMAGE"
        echo "Run 00-build-golden-image.sh first"
        exit 1
    fi

    mkdir -p "$BUILD_DIR"

    # Step 1: Download Ubuntu ISO if needed
    log_step "1/8: Checking for Ubuntu Server ISO..."
    if [ ! -f "$UBUNTU_ISO" ]; then
        log_info "Downloading Ubuntu Server 24.04.1 ISO..."
        log_info "URL: $UBUNTU_ISO_URL"
        wget -O "$UBUNTU_ISO" "$UBUNTU_ISO_URL"
    else
        log_info "Using existing ISO: $UBUNTU_ISO"
    fi
    log_info "ISO size: $(du -h "$UBUNTU_ISO" | cut -f1)"

    # Step 2: Setup working directories
    log_step "2/8: Setting up working directories..."
    rm -rf "$WORK_DIR"
    mkdir -p "$WORK_DIR"/{iso-mount,iso-new,squashfs-root}

    # Step 3: Mount and extract ISO
    log_step "3/8: Mounting and extracting ISO contents..."
    mount -o loop "$UBUNTU_ISO" "$WORK_DIR/iso-mount"

    # Copy everything except the large squashfs (we'll rebuild that)
    log_info "Copying ISO structure..."
    rsync -a --info=progress2 \
        --exclude='casper/filesystem.squashfs' \
        "$WORK_DIR/iso-mount/" "$WORK_DIR/iso-new/"

    # Step 4: Unsquash the live filesystem
    log_step "4/8: Extracting squashfs filesystem (this takes a few minutes)..."
    unsquashfs -d "$WORK_DIR/squashfs-root" \
        "$WORK_DIR/iso-mount/casper/filesystem.squashfs"

    # We can unmount the ISO now
    umount "$WORK_DIR/iso-mount"

    # Step 5: Modify the squashfs root
    log_step "5/8: Modifying live filesystem..."
    SQUASH="$WORK_DIR/squashfs-root"

    # 5a. Mask Subiquity and related services
    log_info "Masking Subiquity and cloud-init services..."

    # Create mask symlinks directly (more reliable than chroot systemctl)
    mkdir -p "$SQUASH/etc/systemd/system"

    # Services to mask - create symlinks to /dev/null
    SERVICES_TO_MASK=(
        "subiquity.service"
        "subiquity-service.service"
        "snap.subiquity.subiquity-service.service"
        "snap.subiquity.subiquity-server.service"
        "console-conf.service"
        "cloud-init.service"
        "cloud-init-local.service"
        "cloud-config.service"
        "cloud-final.service"
        "snapd.service"
        "snapd.socket"
        "snapd.seeded.service"
    )

    for svc in "${SERVICES_TO_MASK[@]}"; do
        ln -sf /dev/null "$SQUASH/etc/systemd/system/$svc"
        log_info "  Masked: $svc"
    done

    # 5b. Add our payload
    log_info "Adding Purple Computer payload..."

    # Copy golden image
    log_info "  Copying golden image (this takes a while)..."
    cp "$GOLDEN_IMAGE" "$SQUASH/purple-os.img.zst"
    log_info "  Golden image size: $(du -h "$SQUASH/purple-os.img.zst" | cut -f1)"

    # Copy installer script
    cp "$SCRIPT_DIR/install.sh" "$SQUASH/usr/local/bin/purple-install"
    chmod +x "$SQUASH/usr/local/bin/purple-install"
    log_info "  Installed: /usr/local/bin/purple-install"

    # 5c. Create and enable our systemd service
    log_info "Creating Purple installer service..."
    cat > "$SQUASH/etc/systemd/system/purple-installer.service" <<'SERVICE'
[Unit]
Description=Purple Computer Factory Installer
After=multi-user.target systemd-user-sessions.service
Before=subiquity.service console-conf.service
ConditionPathExists=/purple-os.img.zst

[Service]
Type=oneshot
ExecStart=/usr/local/bin/purple-install
StandardInput=tty
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE

    # Enable the service
    mkdir -p "$SQUASH/etc/systemd/system/multi-user.target.wants"
    ln -sf /etc/systemd/system/purple-installer.service \
        "$SQUASH/etc/systemd/system/multi-user.target.wants/purple-installer.service"
    log_info "  Enabled: purple-installer.service"

    # 5d. Set hostname
    echo "purple-installer" > "$SQUASH/etc/hostname"

    # 5e. Create emergency shell on tty2
    mkdir -p "$SQUASH/etc/systemd/system/getty@tty2.service.d"
    cat > "$SQUASH/etc/systemd/system/getty@tty2.service.d/autologin.conf" <<'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
AUTOLOGIN
    log_info "  Configured: Emergency shell on tty2 (Alt+F2)"

    # Step 6: Resquash the filesystem
    log_step "6/8: Rebuilding squashfs (this takes several minutes)..."
    rm -f "$WORK_DIR/iso-new/casper/filesystem.squashfs"
    mksquashfs "$SQUASH" "$WORK_DIR/iso-new/casper/filesystem.squashfs" \
        -comp xz -b 1M -Xdict-size 100% -info

    # Update filesystem.size
    du -sx --block-size=1 "$SQUASH" | cut -f1 > "$WORK_DIR/iso-new/casper/filesystem.size"
    log_info "Squashfs size: $(du -h "$WORK_DIR/iso-new/casper/filesystem.squashfs" | cut -f1)"

    # Step 7: Modify GRUB config
    log_step "7/8: Updating boot configuration..."

    # Update GRUB config for UEFI
    cat > "$WORK_DIR/iso-new/boot/grub/grub.cfg" <<'GRUB'
set timeout=3
set default=0

menuentry "Install Purple Computer" {
    linux /casper/vmlinuz boot=casper quiet console=tty0 console=ttyS0,115200n8 ---
    initrd /casper/initrd
}

menuentry "Install Purple Computer (Debug)" {
    linux /casper/vmlinuz boot=casper console=tty0 console=ttyS0,115200n8 ---
    initrd /casper/initrd
}
GRUB
    log_info "Updated: boot/grub/grub.cfg"

    # Update ISOLINUX config for BIOS
    if [ -f "$WORK_DIR/iso-new/isolinux/txt.cfg" ]; then
        cat > "$WORK_DIR/iso-new/isolinux/txt.cfg" <<'ISOLINUX'
default install
label install
  menu label ^Install Purple Computer
  kernel /casper/vmlinuz
  append initrd=/casper/initrd boot=casper quiet ---
label install-debug
  menu label Install Purple Computer (^Debug)
  kernel /casper/vmlinuz
  append initrd=/casper/initrd boot=casper ---
ISOLINUX
        log_info "Updated: isolinux/txt.cfg"
    fi

    # Update ISO volume label in boot configs
    sed -i 's/Ubuntu-Server[^ ]*/PURPLE_INSTALLER/g' "$WORK_DIR/iso-new/boot/grub/grub.cfg" 2>/dev/null || true
    sed -i 's/Ubuntu-Server[^ ]*/PURPLE_INSTALLER/g' "$WORK_DIR/iso-new/boot/grub/loopback.cfg" 2>/dev/null || true

    # Step 8: Regenerate md5sums and rebuild ISO
    log_step "8/8: Building final ISO..."

    # Regenerate md5sums
    cd "$WORK_DIR/iso-new"
    find . -type f -not -name 'md5sum.txt' -not -path './isolinux/*' -exec md5sum {} \; > md5sum.txt 2>/dev/null || true

    # Build the hybrid ISO
    log_info "Running xorriso..."

    # Determine the EFI image path (varies by Ubuntu version)
    EFI_IMG=""
    for candidate in "boot/grub/efi.img" "EFI/boot/efiboot.img" "efi.img"; do
        if [ -f "$WORK_DIR/iso-new/$candidate" ]; then
            EFI_IMG="$candidate"
            break
        fi
    done

    if [ -z "$EFI_IMG" ]; then
        # Create EFI boot image if not present
        log_info "Creating EFI boot image..."
        mkdir -p "$WORK_DIR/iso-new/EFI/boot"
        dd if=/dev/zero of="$WORK_DIR/iso-new/EFI/boot/efiboot.img" bs=1M count=8
        mkfs.vfat "$WORK_DIR/iso-new/EFI/boot/efiboot.img"
        mmd -i "$WORK_DIR/iso-new/EFI/boot/efiboot.img" ::/EFI
        mmd -i "$WORK_DIR/iso-new/EFI/boot/efiboot.img" ::/EFI/boot
        mcopy -i "$WORK_DIR/iso-new/EFI/boot/efiboot.img" "$WORK_DIR/iso-new/EFI/boot/"*.efi ::/EFI/boot/ 2>/dev/null || true
        EFI_IMG="EFI/boot/efiboot.img"
    fi

    mkdir -p /opt/purple-installer/output
    OUTPUT_ISO="/opt/purple-installer/output/purple-installer-$(date +%Y%m%d).iso"

    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "PURPLE_INSTALLER" \
        -appid "Purple Computer Factory Installer" \
        -publisher "Purple Computer Project" \
        -preparer "PurpleOS Build System" \
        -eltorito-boot isolinux/isolinux.bin \
        -eltorito-catalog isolinux/boot.cat \
        -no-emul-boot \
        -boot-load-size 4 \
        -boot-info-table \
        -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
        -eltorito-alt-boot \
        -e "$EFI_IMG" \
        -no-emul-boot \
        -isohybrid-gpt-basdat \
        -output "$OUTPUT_ISO" \
        "$WORK_DIR/iso-new"

    # Generate checksums
    cd /opt/purple-installer/output
    sha256sum "$(basename "$OUTPUT_ISO")" > "$(basename "$OUTPUT_ISO").sha256"

    # Cleanup working directory to save space
    log_info "Cleaning up working directory..."
    rm -rf "$WORK_DIR/squashfs-root"
    rm -rf "$WORK_DIR/iso-new"

    echo
    log_info "=========================================="
    log_info "ISO build complete!"
    log_info "=========================================="
    log_info "Output: $OUTPUT_ISO"
    log_info "Size: $(du -h "$OUTPUT_ISO" | cut -f1)"
    echo
    log_info "Write to USB:"
    log_info "  sudo dd if=$OUTPUT_ISO of=/dev/sdX bs=4M status=progress"
    echo
    log_info "Architecture benefits:"
    log_info "  - Uses Ubuntu's signed boot chain (Secure Boot works)"
    log_info "  - Ubuntu's kernel + initramfs + casper untouched"
    log_info "  - No dependency management - we just add our payload"
    log_info "  - Works on Surface, Dell, HP, ThinkPad out of the box"
}

main "$@"
