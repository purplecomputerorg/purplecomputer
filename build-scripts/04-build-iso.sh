#!/usr/bin/env bash
# Build bootable USB/hybrid ISO (module-free architecture)
# Combines custom kernel, minimal initramfs, and installer rootfs into hybrid ISO
#
# CHANGES FROM OLD VERSION:
# - Uses custom-built kernel with drivers built-in (not extracted from golden image)
# - Creates proper hybrid ISO bootable from USB stick (not CD-ROM)
# - Simpler boot configuration (no CD-ROM assumptions)
# - Partition labeled PURPLE_INSTALLER for reliable detection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
ISO_DIR="${BUILD_DIR}/iso"
OUTPUT_DIR="/opt/purple-installer/output"
ISO_NAME="purple-installer-$(date +%Y%m%d).iso"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

main() {
    log_info "Building bootable USB/hybrid ISO (module-free architecture)..."

    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run as root"
        exit 1
    fi

    # Check prerequisites
    log_step "Checking prerequisites..."
    MISSING=""
    for file in "${BUILD_DIR}/vmlinuz-purple" "${BUILD_DIR}/initrd.img" "${BUILD_DIR}/installer.ext4"; do
        if [ ! -f "$file" ]; then
            echo "ERROR: Missing $file"
            MISSING="yes"
        fi
    done

    if [ -n "$MISSING" ]; then
        echo ""
        echo "Run previous build scripts first:"
        echo "  ./00-build-custom-kernel.sh    # Build custom kernel"
        echo "  ./02-build-initramfs.sh        # Build minimal initramfs"
        echo "  ./03-build-installer-rootfs.sh # Build installer environment"
        exit 1
    fi

    mkdir -p "$OUTPUT_DIR"
    rm -rf "$ISO_DIR"
    mkdir -p "$ISO_DIR"/{boot,isolinux,EFI/boot}

    # Copy custom kernel
    log_step "1/5: Copying custom kernel..."
    cp "${BUILD_DIR}/vmlinuz-purple" "$ISO_DIR/boot/vmlinuz"
    log_info "  Kernel size: $(du -h ${BUILD_DIR}/vmlinuz-purple | cut -f1)"

    # Copy initramfs
    log_step "2/5: Copying initramfs..."
    cp "${BUILD_DIR}/initrd.img" "$ISO_DIR/boot/initrd.img"
    log_info "  Initramfs size: $(du -h ${BUILD_DIR}/initrd.img | cut -f1)"

    # Copy installer rootfs
    log_step "3/5: Embedding installer rootfs..."
    cp "${BUILD_DIR}/installer.ext4" "$ISO_DIR/boot/installer.ext4"
    log_info "  Installer rootfs size: $(du -h ${BUILD_DIR}/installer.ext4 | cut -f1)"

    # Create ISOLINUX config (BIOS boot)
    log_step "4/5: Creating boot configuration..."
    log_info "  Configuring ISOLINUX (BIOS boot)..."
    cp /usr/lib/ISOLINUX/isolinux.bin "$ISO_DIR/isolinux/"
    cp /usr/lib/syslinux/modules/bios/*.c32 "$ISO_DIR/isolinux/"

    cat > "$ISO_DIR/isolinux/isolinux.cfg" <<'EOF'
DEFAULT install
TIMEOUT 10
PROMPT 0

LABEL install
    KERNEL /boot/vmlinuz
    APPEND initrd=/boot/initrd.img quiet console=tty0 console=ttyS0,115200n8
EOF

    # Create GRUB config (UEFI boot)
    log_info "  Configuring GRUB (UEFI boot)..."
    cat > "$ISO_DIR/EFI/boot/grub.cfg" <<'EOF'
# PurpleOS Installer GRUB configuration
set pager=0

# Only use console (serial causes errors on laptops without serial ports)
terminal_input console
terminal_output console

set default=0
set timeout=3

# Search for the ISO volume
search --no-floppy --set=root --label PURPLE_INSTALLER

menuentry "Install PurpleOS" {
    linux /boot/vmlinuz quiet
    initrd /boot/initrd.img
}

menuentry "Install PurpleOS (debug mode)" {
    linux /boot/vmlinuz console=tty0
    initrd /boot/initrd.img
}
EOF

    # Generate GRUB EFI binary using grub-mkstandalone
    # Modern Ubuntu doesn't ship prebuilt grubx64.efi, must generate it
    # Include all modules needed for UEFI ISO boot
    log_info "  Generating UEFI bootloader with grub-mkstandalone..."
    grub-mkstandalone \
        --format=x86_64-efi \
        --output="$ISO_DIR/EFI/boot/bootx64.efi" \
        --modules="part_gpt part_msdos iso9660 fat normal linux search search_label efi_gop efi_uga all_video video video_bochs video_cirrus video_fb gfxterm gfxterm_background terminal terminfo font loopback memdisk minicmd echo test cmp" \
        --locales="" \
        "boot/grub/grub.cfg=$ISO_DIR/EFI/boot/grub.cfg"

    # Create EFI System Partition (ESP) image for UEFI boot
    # UEFI firmware needs a FAT-formatted image, not bare .efi files
    log_info "  Creating EFI System Partition image..."

    # Debug: Check disk space before creating ESP image
    log_info "  [DEBUG] Disk space before ESP creation:"
    df -h / | tail -1
    df -h /opt/purple-installer | tail -1
    log_info "  [DEBUG] Build directory size: $(du -sh /opt/purple-installer/build 2>/dev/null | cut -f1)"
    log_info "  [DEBUG] ISO directory size: $(du -sh $ISO_DIR 2>/dev/null | cut -f1)"
    log_info "  [DEBUG] ISO/boot exists: $(ls -ld $ISO_DIR/boot 2>/dev/null || echo 'NO')"

    EFI_IMG="$ISO_DIR/boot/efi.img"
    # Need 10MB for ESP image because grub-mkstandalone with all modules creates ~3MB bootloader
    # 4MB was too small - mtools "Disk full" error when copying bootx64.efi into FAT image
    log_info "  [DEBUG] Creating $EFI_IMG (10MB)..."
    if ! dd if=/dev/zero of="$EFI_IMG" bs=1M count=10 status=progress 2>&1; then
        echo "ERROR: dd failed!"
        echo "Exit code: $?"
        echo "Disk space after failure:"
        df -h / | tail -1
        df -h /opt/purple-installer | tail -1
        echo "Directory contents:"
        ls -lh "$ISO_DIR/boot/" 2>/dev/null || echo "boot/ doesn't exist"
        exit 1
    fi
    log_info "  [DEBUG] dd completed successfully"

    log_info "  [DEBUG] Running mkfs.vfat..."
    if ! mkfs.vfat -F 12 "$EFI_IMG" 2>&1; then
        echo "ERROR: mkfs.vfat failed!"
        exit 1
    fi
    log_info "  [DEBUG] mkfs.vfat completed successfully"

    # Copy BOOTX64.EFI and grub.cfg into the ESP image using mtools
    mmd -i "$EFI_IMG" ::/EFI
    mmd -i "$EFI_IMG" ::/EFI/BOOT
    mcopy -i "$EFI_IMG" "$ISO_DIR/EFI/boot/bootx64.efi" ::/EFI/BOOT/BOOTX64.EFI
    mcopy -i "$EFI_IMG" "$ISO_DIR/EFI/boot/grub.cfg" ::/EFI/BOOT/grub.cfg

    # Build hybrid ISO (bootable from USB and optical media)
    log_step "5/5: Creating hybrid ISO..."
    log_info "  Building with xorriso..."

    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "PURPLE_INSTALLER" \
        -appid "PurpleOS Factory Installer" \
        -publisher "Purple Computer Project" \
        -preparer "PurpleOS Build System" \
        -eltorito-boot isolinux/isolinux.bin \
        -eltorito-catalog isolinux/boot.cat \
        -no-emul-boot \
        -boot-load-size 4 \
        -boot-info-table \
        -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
        -eltorito-alt-boot \
        -eltorito-platform efi \
        -e boot/efi.img \
        -no-emul-boot \
        -isohybrid-gpt-basdat \
        -output "${OUTPUT_DIR}/${ISO_NAME}" \
        "$ISO_DIR"

    # Generate checksums
    log_info "Generating checksums..."
    cd "$OUTPUT_DIR"
    md5sum "$ISO_NAME" > "${ISO_NAME}.md5"
    sha256sum "$ISO_NAME" > "${ISO_NAME}.sha256"

    # Display results
    echo
    log_info "✓ ISO build complete!"
    log_info "  Output: ${OUTPUT_DIR}/${ISO_NAME}"
    log_info "  Size: $(du -h ${OUTPUT_DIR}/${ISO_NAME} | cut -f1)"
    echo
    log_info "Write to USB stick with:"
    log_info "  sudo dd if=${OUTPUT_DIR}/${ISO_NAME} of=/dev/sdX bs=4M status=progress"
    log_info "  (Replace /dev/sdX with your USB device)"
    echo
    log_info "Module-free architecture benefits:"
    log_info "  ✓ No runtime kernel modules"
    log_info "  ✓ No CD-ROM dependency"
    log_info "  ✓ Direct USB boot support"
    log_info "  ✓ All drivers built into kernel"
    log_info "  ✓ Improved hardware compatibility"
}

main "$@"
