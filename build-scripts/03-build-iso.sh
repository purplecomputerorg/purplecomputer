#!/usr/bin/env bash
# Build bootable ISO with embedded FAI and local repository
# Creates a complete offline installer for Purple Computer

set -e

# Configuration
FAI_BASE="/srv/fai"
NFSROOT="${FAI_BASE}/nfsroot"
MIRROR_DIR="/opt/purple-installer/local-repo/mirror"
ISO_DIR="/opt/purple-installer/iso-build"
OUTPUT_DIR="/opt/purple-installer/output"
ISO_NAME="purple-computer-installer-$(date +%Y%m%d).iso"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    if [ ! -d "$NFSROOT" ]; then
        log_error "FAI nfsroot not found at ${NFSROOT}"
        log_error "Please run 02-build-fai-nfsroot.sh first"
        exit 1
    fi

    if [ ! -d "$MIRROR_DIR" ]; then
        log_error "Local repository not found at ${MIRROR_DIR}"
        log_error "Please run 01-create-local-repo.sh first"
        exit 1
    fi

    for cmd in xorriso mksquashfs; do
        if ! command -v $cmd &> /dev/null; then
            log_error "Required command not found: $cmd"
            exit 1
        fi
    done

    log_info "Prerequisites check passed."
}

prepare_iso_structure() {
    log_info "Preparing ISO directory structure..."

    # Clean and create ISO build directory
    rm -rf "$ISO_DIR"
    mkdir -p "$ISO_DIR"/{live,isolinux,EFI/boot,purple-repo}

    log_info "ISO directory structure created."
}

create_squashfs() {
    log_info "Creating squashfs from nfsroot (this may take several minutes)..."

    # Create squashfs filesystem from nfsroot
    mksquashfs "$NFSROOT" "$ISO_DIR/live/filesystem.squashfs" \
        -comp xz \
        -e boot \
        -noappend

    log_info "Squashfs created: $(du -h $ISO_DIR/live/filesystem.squashfs | cut -f1)"
}

copy_kernel() {
    log_info "Copying kernel and initrd..."

    # Find and copy kernel
    KERNEL=$(ls -1 ${NFSROOT}/boot/vmlinuz-* | sort -V | tail -1)
    INITRD=$(ls -1 ${NFSROOT}/boot/initrd.img-* | sort -V | tail -1)

    if [ -z "$KERNEL" ] || [ -z "$INITRD" ]; then
        log_error "Kernel or initrd not found in nfsroot"
        exit 1
    fi

    cp "$KERNEL" "$ISO_DIR/live/vmlinuz"
    cp "$INITRD" "$ISO_DIR/live/initrd.img"

    log_info "Kernel and initrd copied."
}

embed_repository() {
    log_info "Embedding local repository in ISO..."

    # Copy entire repository to ISO
    cp -r "$MIRROR_DIR"/* "$ISO_DIR/purple-repo/"

    # Calculate repository size
    REPO_SIZE=$(du -sh "$ISO_DIR/purple-repo" | cut -f1)
    log_info "Repository size: ${REPO_SIZE}"
}

create_isolinux_config() {
    log_info "Creating isolinux boot configuration..."

    # Copy isolinux files
    cp /usr/lib/ISOLINUX/isolinux.bin "$ISO_DIR/isolinux/"
    cp /usr/lib/syslinux/modules/bios/*.c32 "$ISO_DIR/isolinux/"

    # Create isolinux.cfg
    # Boot parameters:
    #   boot=live           - Use live-boot to mount squashfs
    #   toram              - Load entire squashfs to RAM (correct syntax, no =filesystem.squashfs)
    #   ip=frommedia       - Skip DHCP/network wait, use media-provided config (prevents ethernet hang)
    #   FAI_ACTION=install - Trigger FAI automated installation
    #   FAI_FLAGS=...      - verbose,createvt,reboot flags for FAI
    cat > "$ISO_DIR/isolinux/isolinux.cfg" <<'EOF'
DEFAULT purple_install
TIMEOUT 300
PROMPT 1
UI vesamenu.c32

LABEL purple_install
    MENU LABEL ^Purple Computer - Automated Installation
    KERNEL /live/vmlinuz
    APPEND initrd=/live/initrd.img boot=live toram ip= FAI_ACTION=install FAI_FLAGS=verbose,createvt,reboot root=/dev/ram0 quiet

LABEL purple_install_verbose
    MENU LABEL Purple Computer - Installation (Verbose)
    KERNEL /live/vmlinuz
    APPEND initrd=/live/initrd.img boot=live toram ip= FAI_ACTION=install FAI_FLAGS=verbose,createvt,debug,reboot root=/dev/ram0

LABEL purple_rescue
    MENU LABEL Purple Computer - Rescue Shell
    KERNEL /live/vmlinuz
    APPEND initrd=/live/initrd.img boot=live toram ip= root=/dev/ram0

MENU TITLE Purple Computer Installer
MENU BACKGROUND
MENU COLOR screen 37;40
MENU COLOR border 30;44
MENU COLOR title 1;36;44
MENU COLOR sel 7;37;40
EOF

    log_info "Isolinux configuration created."
}

create_grub_config() {
    log_info "Creating GRUB EFI boot configuration..."

    # Create grub.cfg for EFI boot
    # Boot parameters same as isolinux - see create_isolinux_config() for details
    cat > "$ISO_DIR/EFI/boot/grub.cfg" <<'EOF'
set default=0
set timeout=5

menuentry "Purple Computer - Automated Installation" {
    linux /live/vmlinuz boot=live toram ip= FAI_ACTION=install FAI_FLAGS=verbose,createvt,reboot root=/dev/ram0 quiet
    initrd /live/initrd.img
}

menuentry "Purple Computer - Installation (Verbose)" {
    linux /live/vmlinuz boot=live toram ip= FAI_ACTION=install FAI_FLAGS=verbose,createvt,debug,reboot root=/dev/ram0
    initrd /live/initrd.img
}

menuentry "Purple Computer - Rescue Shell" {
    linux /live/vmlinuz boot=live toram ip= root=/dev/ram0
    initrd /live/initrd.img
}
EOF

    # Create EFI boot image
    if [ -f /usr/lib/grub/x86_64-efi/monolithic/grubx64.efi ]; then
        cp /usr/lib/grub/x86_64-efi/monolithic/grubx64.efi "$ISO_DIR/EFI/boot/bootx64.efi"
    elif [ -f /usr/lib/grub/x86_64-efi/grubx64.efi ]; then
        cp /usr/lib/grub/x86_64-efi/grubx64.efi "$ISO_DIR/EFI/boot/bootx64.efi"
    else
        log_warn "GRUB EFI image not found, EFI boot may not work"
    fi

    log_info "GRUB EFI configuration created."
}

create_iso() {
    log_info "Creating bootable ISO image..."

    mkdir -p "$OUTPUT_DIR"

    # Create hybrid ISO with both BIOS and EFI support
    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "PURPLE_COMPUTER" \
        -appid "Purple Computer Installer" \
        -publisher "Purple Computer Project" \
        -preparer "FAI-based installer" \
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

    if [ $? -eq 0 ]; then
        log_info "ISO created successfully!"
    else
        log_error "Failed to create ISO"
        exit 1
    fi
}

generate_checksums() {
    log_info "Generating checksums..."

    cd "$OUTPUT_DIR"

    md5sum "$ISO_NAME" > "${ISO_NAME}.md5"
    sha256sum "$ISO_NAME" > "${ISO_NAME}.sha256"

    log_info "Checksums generated."
}

create_usb_instructions() {
    log_info "Creating USB write instructions..."

    cat > "${OUTPUT_DIR}/WRITE_TO_USB.txt" <<EOF
Purple Computer - Writing to USB Drive
======================================

This ISO is a hybrid image and can be written directly to a USB drive.

Linux/macOS:
-----------
1. Insert USB drive (will be completely erased!)
2. Find device name: lsblk or diskutil list
3. Write image:

   sudo dd if=${ISO_NAME} of=/dev/sdX bs=4M status=progress && sync

   Replace /dev/sdX with your USB device (e.g., /dev/sdb)

Windows:
-------
Use Rufus, balenaEtcher, or Win32DiskImager to write the ISO to USB.

Settings for Rufus:
- Partition scheme: MBR or GPT (both supported)
- Target system: BIOS or UEFI (both supported)
- Write mode: DD Image mode

Verification:
------------
After writing, verify the USB drive:

  md5sum /dev/sdX | compare with ${ISO_NAME}.md5

Installation:
------------
1. Boot from USB/CD
2. Installation will start automatically
3. Wait for completion (typically 10-20 minutes)
4. System will reboot into Purple Computer

Default credentials:
  Username: purple
  Password: purple (CHANGE IMMEDIATELY!)

For troubleshooting, select "Installation (Verbose)" from boot menu.
EOF

    log_info "USB instructions created."
}

print_summary() {
    log_info ""
    log_info "════════════════════════════════════════════════════════════"
    log_info "  Purple Computer ISO Build Complete!"
    log_info "════════════════════════════════════════════════════════════"
    log_info ""
    log_info "ISO file: ${OUTPUT_DIR}/${ISO_NAME}"
    log_info "Size: $(du -h ${OUTPUT_DIR}/${ISO_NAME} | cut -f1)"
    log_info ""
    log_info "MD5:    $(cat ${OUTPUT_DIR}/${ISO_NAME}.md5 | cut -d' ' -f1)"
    log_info "SHA256: $(cat ${OUTPUT_DIR}/${ISO_NAME}.sha256 | cut -d' ' -f1)"
    log_info ""
    log_info "Write to USB: See ${OUTPUT_DIR}/WRITE_TO_USB.txt"
    log_info ""
    log_info "The ISO includes:"
    log_info "  - FAI automated installer"
    log_info "  - Complete local package repository"
    log_info "  - Minimal X11 + terminal environment"
    log_info "  - LVM-based disk layout"
    log_info "  - Full offline installation capability"
    log_info ""
    log_info "Boot the ISO and installation will proceed automatically!"
    log_info "════════════════════════════════════════════════════════════"
}

main() {
    log_info "Starting Purple Computer ISO build..."

    check_root
    check_prerequisites
    prepare_iso_structure
    create_squashfs
    copy_kernel
    embed_repository
    create_isolinux_config
    create_grub_config
    create_iso
    generate_checksums
    create_usb_instructions
    print_summary
}

main "$@"
