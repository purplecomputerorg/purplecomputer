#!/usr/bin/env bash
# Build bootable ISO
# Combines kernel, initramfs, and installer rootfs into hybrid ISO

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="/opt/purple-installer/build"
ISO_DIR="${BUILD_DIR}/iso"
OUTPUT_DIR="/opt/purple-installer/output"
ISO_NAME="purple-installer-$(date +%Y%m%d).iso"

GREEN='\033[0;32m'
NC='\033[0m'
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

main() {
    log_info "Building bootable ISO..."

    if [ "$EUID" -ne 0 ]; then
        echo "This script must be run as root"
        exit 1
    fi

    # Check prerequisites
    for file in "${BUILD_DIR}/initrd.img" "${BUILD_DIR}/installer.ext4"; do
        if [ ! -f "$file" ]; then
            echo "ERROR: Missing $file"
            echo "Run previous build scripts first"
            exit 1
        fi
    done

    mkdir -p "$OUTPUT_DIR"
    rm -rf "$ISO_DIR"
    mkdir -p "$ISO_DIR"/{boot,isolinux,EFI/boot}

    # Extract kernel from golden image
    log_info "Extracting kernel from golden image..."
    GOLDEN_IMG="${BUILD_DIR}/purple-os.img"
    if [ ! -f "$GOLDEN_IMG" ]; then
        echo "ERROR: Golden image not found at $GOLDEN_IMG"
        echo "Run step 1 (build-golden-image.sh) first"
        exit 1
    fi

    # Mount golden image to extract kernel
    LOOP_DEV=$(losetup -f --show "$GOLDEN_IMG")
    kpartx -av "$LOOP_DEV"
    LOOP_NAME=$(basename "$LOOP_DEV")

    TEMP_MOUNT="${BUILD_DIR}/mnt-kernel-extract"
    mkdir -p "$TEMP_MOUNT"
    mount "/dev/mapper/${LOOP_NAME}p2" "$TEMP_MOUNT"

    KERNEL=$(ls -1 "$TEMP_MOUNT/boot/vmlinuz-"* | sort -V | tail -1)
    cp "$KERNEL" "$ISO_DIR/boot/vmlinuz"

    umount "$TEMP_MOUNT"
    kpartx -dv "$LOOP_DEV"
    losetup -d "$LOOP_DEV"
    rm -rf "$TEMP_MOUNT"

    # Copy initramfs
    log_info "Copying initramfs..."
    cp "${BUILD_DIR}/initrd.img" "$ISO_DIR/boot/initrd.img"

    # Copy installer rootfs
    log_info "Embedding installer rootfs..."
    cp "${BUILD_DIR}/installer.ext4" "$ISO_DIR/boot/installer.ext4"

    # Create ISOLINUX config (BIOS boot)
    log_info "Creating ISOLINUX boot config..."
    cp /usr/lib/ISOLINUX/isolinux.bin "$ISO_DIR/isolinux/"
    cp /usr/lib/syslinux/modules/bios/*.c32 "$ISO_DIR/isolinux/"

    cat > "$ISO_DIR/isolinux/isolinux.cfg" <<'EOF'
DEFAULT install
TIMEOUT 10
PROMPT 0

LABEL install
    KERNEL /boot/vmlinuz
    APPEND initrd=/boot/initrd.img root=LABEL=PURPLE_INSTALLER ro quiet
EOF

    # Create GRUB config (UEFI boot)
    log_info "Creating GRUB EFI boot config..."
    cat > "$ISO_DIR/EFI/boot/grub.cfg" <<'EOF'
set default=0
set timeout=1

menuentry "PurpleOS Installer" {
    linux /boot/vmlinuz root=LABEL=PURPLE_INSTALLER ro quiet
    initrd /boot/initrd.img
}
EOF

    # Copy GRUB EFI binary
    if [ -f /usr/lib/grub/x86_64-efi/monolithic/grubx64.efi ]; then
        cp /usr/lib/grub/x86_64-efi/monolithic/grubx64.efi "$ISO_DIR/EFI/boot/bootx64.efi"
    elif [ -f /usr/lib/grub/x86_64-efi/grubx64.efi ]; then
        cp /usr/lib/grub/x86_64-efi/grubx64.efi "$ISO_DIR/EFI/boot/bootx64.efi"
    fi

    # Build hybrid ISO
    log_info "Creating hybrid ISO..."
    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "PURPLE_INSTALLER" \
        -appid "PurpleOS Factory Installer" \
        -publisher "Purple Computer Project" \
        -eltorito-boot isolinux/isolinux.bin \
        -eltorito-catalog isolinux/boot.cat \
        -no-emul-boot \
        -boot-load-size 4 \
        -boot-info-table \
        -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
        -eltorito-alt-boot \
        -e EFI/boot/bootx64.efi \
        -no-emul-boot \
        -isohybrid-gpt-basdat \
        -output "${OUTPUT_DIR}/${ISO_NAME}" \
        "$ISO_DIR"

    # Generate checksums
    log_info "Generating checksums..."
    cd "$OUTPUT_DIR"
    md5sum "$ISO_NAME" > "${ISO_NAME}.md5"
    sha256sum "$ISO_NAME" > "${ISO_NAME}.sha256"

    log_info "✓ ISO ready: ${OUTPUT_DIR}/${ISO_NAME}"
    log_info "  Size: $(du -h ${OUTPUT_DIR}/${ISO_NAME} | cut -f1)"
}

main "$@"
