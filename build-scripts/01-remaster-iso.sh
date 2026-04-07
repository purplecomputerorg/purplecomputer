#!/usr/bin/env bash
# Remaster Ubuntu Server ISO for Purple Computer
#
# ARCHITECTURE: Live Boot + Install Payload
# - Download official Ubuntu Server 24.04 ISO
# - Replace squashfs with Purple Computer root filesystem
# - Modify initramfs (boot splash, dotfile restore, debug mode)
# - Add golden image payload (for install-to-disk via parent menu)
# - Update GRUB config
# - Rebuild ISO (normal + debug)

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

# Fast build: use minimal compression for faster iteration
if [ "${FAST_BUILD:-0}" = "1" ]; then
    ZSTD_LEVEL=1
    ISO_TAG="-fast"
    log_info "FAST BUILD: using minimal compression"
else
    ZSTD_LEVEL=19
    ISO_TAG=""
fi

create_live_boot_hook() {
    local HOOK_DIR="$1"

    # Create the live boot hook for casper-bottom.
    # Runs AFTER casper mounts the live root and /run is set up.
    # Restores dotfiles, sets up debug mode, and shows boot splash.
    cat > "$HOOK_DIR/80_purple_installer" << 'HOOK_EOF'
#!/bin/sh
# Purple Computer Live Boot Hook (casper-bottom)
#
# Runs after casper mounts the live root. Sets up dotfiles, debug mode,
# and the boot splash. Installation is handled by the parent menu in
# the running TUI (parent_menu.py), not by this hook.

PREREQ=""
DESCRIPTION="Setting up Purple Computer..."

prereqs() { echo "$PREREQ"; }

case "$1" in
    prereqs)
        prereqs
        exit 0
        ;;
esac

# Source casper functions (required for casper-bottom scripts)
. /scripts/casper-functions

log_begin_msg "$DESCRIPTION"

purple_log() {
    echo "[PURPLE] $1" >/dev/console 2>&1 || echo "[PURPLE] $1"
}

purple_log "=== Purple Computer Live Boot Hook (casper-bottom) ==="

# Restore dotfiles that casper's adduser overwrites with skeleton copies.
# Canonical versions are stored in /etc/purple/ (which casper doesn't touch).
mkdir -p /root/home/purple
cp /root/etc/purple/xinitrc /root/home/purple/.xinitrc
chmod +x /root/home/purple/.xinitrc
chown 1000:1000 /root/home/purple/.xinitrc
touch /root/home/purple/.hushlogin
chown 1000:1000 /root/home/purple/.hushlogin
purple_log "Restored dotfiles from /etc/purple/"

# Debug mode: create flag file and enable SysRq + verbose logging
if grep -q "purple.debug=1" /proc/cmdline 2>/dev/null; then
    touch /root/opt/purple/debug
    cat > /root/etc/sysctl.d/99-purple-zzz-debug.conf << 'SYSCTL_EOF'
kernel.printk = 7 4 1 7
kernel.sysrq = 1
SYSCTL_EOF
    # Enable a login shell on tty2 so Ctrl+Alt+F2 can escape a frozen TUI
    ln -sf /lib/systemd/system/getty@.service /root/etc/systemd/system/getty.target.wants/getty@tty2.service
    purple_log "DEBUG MODE: created /opt/purple/debug, enabled SysRq, verbose logging, getty@tty2"
fi

# Show boot splash on tty1: purple background with friendly message.
# Console output goes to tty2, so tty1 is ours.
# \033]P0 redefines VT palette color 0 (black) to our purple (#2d1b4e).
printf '\033]P02d1b4e\033[H\033[2J\033[97m\033[5;7H Welcome to Purple Computer!\033[7;7H Starting up...\033[0m' > /dev/tty1 2>/dev/null

log_end_msg
exit 0
HOOK_EOF

    chmod +x "$HOOK_DIR/80_purple_installer"
}

create_install_script() {
    local DEST="$1"

    # Copy the install script to the payload directory
    cp "$SCRIPT_DIR/install.sh" "$DEST/install.sh"
    chmod +x "$DEST/install.sh"
}

main() {
    log_step "Purple Computer ISO Remaster (Live Boot + Optional Install)"
    log_info "Architecture: Live boot default, install via GRUB menu option"

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

    # Check for live squashfs
    LIVE_SQUASHFS="${BUILD_DIR}/filesystem.squashfs"
    LIVE_SIZE="${BUILD_DIR}/filesystem.size"

    if [ ! -f "$LIVE_SQUASHFS" ]; then
        echo "ERROR: Live squashfs not found: $LIVE_SQUASHFS"
        echo "Run step 0 first: ./build-all.sh 0"
        exit 1
    fi

    # Setup directories
    mkdir -p "$WORK_DIR"
    mkdir -p /opt/purple-installer/output

    # Step 1: Download Ubuntu Server ISO if needed
    log_step "1/11: Checking Ubuntu Server ISO..."
    if [ -f "$UBUNTU_ISO" ]; then
        log_info "Using cached ISO: $UBUNTU_ISO"
    else
        log_info "Downloading Ubuntu Server ISO..."
        wget -O "$UBUNTU_ISO" "$UBUNTU_ISO_URL"
    fi
    log_info "ISO size: $(du -h "$UBUNTU_ISO" | cut -f1)"

    # Step 2: Setup working directories
    log_step "2/11: Setting up working directories..."
    rm -rf "$WORK_DIR/iso-mount" "$WORK_DIR/iso-new" "$WORK_DIR/initrd-work"
    mkdir -p "$WORK_DIR/iso-mount" "$WORK_DIR/iso-new" "$WORK_DIR/initrd-work"

    # Step 3: Mount and copy ISO contents
    log_step "3/11: Extracting ISO contents..."
    mount -o loop,ro "$UBUNTU_ISO" "$WORK_DIR/iso-mount"

    # Copy everything from ISO
    rsync -a --info=progress2 "$WORK_DIR/iso-mount/" "$WORK_DIR/iso-new/"

    # Step 4: Replace squashfs with Purple Computer
    log_step "4/11: Replacing squashfs with Purple Computer..."
    # Remove ALL Ubuntu Server squashfs files and replace with ours.
    # Casper reads install-sources.yaml to know which layers to mount.
    rm -f "$WORK_DIR/iso-new/casper/"*.squashfs
    rm -f "$WORK_DIR/iso-new/casper/"*.squashfs.gpg
    rm -f "$WORK_DIR/iso-new/casper/"*.manifest
    rm -f "$WORK_DIR/iso-new/casper/"*.size
    cp "$LIVE_SQUASHFS" "$WORK_DIR/iso-new/casper/filesystem.squashfs"
    cp "$LIVE_SIZE" "$WORK_DIR/iso-new/casper/filesystem.size"

    # Rewrite install-sources.yaml to point at our single squashfs
    SQUASHFS_SIZE=$(stat -c%s "$LIVE_SQUASHFS")
    cat > "$WORK_DIR/iso-new/casper/install-sources.yaml" << SOURCES_EOF
- default: true
  id: purple-computer
  name:
    en: Purple Computer
  path: filesystem.squashfs
  size: ${SQUASHFS_SIZE}
  type: fsimage
  variant: server
SOURCES_EOF
    log_info "Squashfs replaced ($(du -h "$LIVE_SQUASHFS" | cut -f1))"

    # Replace the ISO's kernel and initrd with ours from the squashfs.
    # Everything must come from one source to avoid version mismatches.
    # The squashfs has casper installed, so its initrd supports live boot.
    # Use unsquashfs (no loop device needed, works reliably in Docker).
    log_info "Extracting kernel and initrd from squashfs..."
    SQEXT="$WORK_DIR/sq-extract"
    unsquashfs -d "$SQEXT" "$LIVE_SQUASHFS" boot/

    # Follow symlinks to get the actual versioned files
    cp -L "$SQEXT/boot/vmlinuz" "$WORK_DIR/iso-new/casper/vmlinuz"
    cp -L "$SQEXT/boot/initrd.img" "$WORK_DIR/iso-new/casper/initrd"
    PURPLE_KVER=$(readlink "$SQEXT/boot/vmlinuz" | sed 's/vmlinuz-//')
    log_info "  Kernel: $PURPLE_KVER"
    log_info "  Initrd: $(readlink "$SQEXT/boot/initrd.img")"

    rm -rf "$SQEXT"

    # Step 5: Extract and modify initramfs (boot splash, dotfiles, debug mode)
    log_step "5/11: Modifying initramfs..."

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

    # Add early splash: paint tty1 purple immediately so the user never sees
    # a black screen. This runs in init-top, before casper mounts anything.
    # (Don't write files to /run here, they're lost during switch_root.)
    log_info "Adding early splash to init-top..."
    mkdir -p "$MAIN_DIR/scripts/init-top"
    cat > "$MAIN_DIR/scripts/init-top/01_purple_splash" << 'SPLASH_EOF'
#!/bin/sh
PREREQ=""
prereqs() { echo "$PREREQ"; }
case "$1" in prereqs) prereqs; exit 0;; esac
# Redefine VT color 0 (black) to purple (#2d1b4e), clear tty1, show message.
# This is the earliest point we control the screen after GRUB hands off.
printf '\033]P02d1b4e\033[H\033[2J\033[97m\033[5;7H Welcome to Purple Computer!\033[7;7H Starting up...\033[0m' > /dev/tty1 2>/dev/null
SPLASH_EOF
    chmod +x "$MAIN_DIR/scripts/init-top/01_purple_splash"

    # Add to init-top ORDER file if it exists
    INIT_TOP_ORDER="$MAIN_DIR/scripts/init-top/ORDER"
    if [ -f "$INIT_TOP_ORDER" ]; then
        # Insert at the beginning (after any existing first line)
        sed -i '1a /scripts/init-top/01_purple_splash' "$INIT_TOP_ORDER"
    fi

    # Add our hook script to casper-bottom (NOT init-top)
    #
    # CRITICAL: casper-bottom runs AFTER the live root and /run are set up.
    # Files written to /run in init-top are LOST during switch_root.
    # This is why our previous implementation failed.
    log_info "Adding Purple installer hook to casper-bottom..."
    mkdir -p "$MAIN_DIR/scripts/casper-bottom"
    create_live_boot_hook "$MAIN_DIR/scripts/casper-bottom"

    # CRITICAL: Add our script to the ORDER file
    # Casper uses this file to determine which scripts to run and in what order.
    # Scripts not listed in ORDER are silently ignored!
    # We insert our script before 99casperboot (the final script)
    ORDER_FILE="$MAIN_DIR/scripts/casper-bottom/ORDER"
    if [ -f "$ORDER_FILE" ]; then
        log_info "Adding 80_purple_installer to casper-bottom ORDER file..."
        # Insert before the 99casperboot line
        sed -i '/99casperboot/i /scripts/casper-bottom/80_purple_installer "$@"\n[ -e /conf/param.conf ] && . /conf/param.conf' "$ORDER_FILE"
    else
        log_info "WARNING: ORDER file not found, script may not run"
    fi

    # Remove Ubuntu Server's layered squashfs config.
    # Without this, casper looks for ubuntu-server-minimal.ubuntu-server.*.squashfs
    # layers instead of mounting our single filesystem.squashfs.
    if [ -f "$MAIN_DIR/conf/conf.d/default-layer.conf" ]; then
        log_info "Removing default-layer.conf (disabling multi-layer squashfs)..."
        rm "$MAIN_DIR/conf/conf.d/default-layer.conf"
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
        (cd main && find . -print0 | cpio --null -o -H newc 2>/dev/null | zstd -${ZSTD_LEVEL} -T0) >> "$NEW_INITRD"
    elif [ "$MAIN_DIR" = "." ]; then
        # Single archive, compress the whole thing
        (find . -print0 | cpio --null -o -H newc 2>/dev/null | zstd -${ZSTD_LEVEL} -T0) > "$NEW_INITRD"
    fi

    # Replace initrd in ISO
    cp "$NEW_INITRD" "$INITRD_PATH"
    log_info "Initramfs modified successfully"

    # Step 6: Add payload to ISO
    log_step "6/11: Adding payload to ISO..."

    PAYLOAD_DIR="$WORK_DIR/iso-new/purple"
    mkdir -p "$PAYLOAD_DIR"

    # Copy golden image
    log_info "Copying golden image (this takes a while)..."
    cp "$GOLDEN_IMAGE" "$PAYLOAD_DIR/purple-os.img.zst"

    # Copy install script
    create_install_script "$PAYLOAD_DIR"

    # Unmount source ISO
    umount "$WORK_DIR/iso-mount"

    # Step 7: Replace GRUB config with live boot default + optional install
    log_step "7/11: Configuring GRUB boot menu..."

    GRUB_CFG="$WORK_DIR/iso-new/boot/grub/grub.cfg"
    if [ -f "$GRUB_CFG" ]; then
        log_info "Replacing GRUB config with Purple boot menu..."

        # Backup original
        cp "$GRUB_CFG" "${GRUB_CFG}.orig"

        # Replace with live-boot-default GRUB config
        cat > "$GRUB_CFG" << 'GRUB_PURPLE'
# Purple Computer - GRUB Configuration
# Default: live boot (no install, no disk writes)
# Optional: install to internal disk
#
# Masked services (systemd.mask=...):
#   subiquity, snapd: Ubuntu Server installer (not needed)
#   ssh: no network access
#   udisks2: prevents auto-mounting internal disk
#   casper-md5check: reads the entire squashfs at boot to verify its checksum.
#     Disabled because: (1) if the squashfs is corrupted, the system is already
#     broken (casper mounts it as root, so corrupted files cause crashes whether
#     or not the check ran), (2) the check only logs a warning, it doesn't prevent
#     boot or fix anything, (3) it adds 30-90s of boot time reading the full USB.

# Boot immediately. Purple background is handled by VT palette (kernel params)
# and init-top splash, not GRUB gfxterm (which flashes gray during init).
set timeout=0
set timeout_style=hidden
set default=0

menuentry "Purple Computer" {
    set gfxpayload=keep
    linux /casper/vmlinuz boot=casper quiet loglevel=0 systemd.show_status=false vt.global_cursor_default=0 console=tty2 console=ttyS0,115200 username=purple cloud-init=disabled systemd.mask=subiquity.service systemd.mask=snapd.service systemd.mask=snapd.socket systemd.mask=ssh.service systemd.mask=ssh.socket systemd.mask=udisks2.service systemd.mask=casper-md5check.service vt.default_red=0x2d,0xaa,0x00,0xaa,0x00,0xaa,0x00,0xaa,0x55,0xff,0x55,0xff,0x55,0xff,0x55,0xff vt.default_grn=0x1b,0x00,0xaa,0x55,0x00,0x00,0xaa,0xaa,0x55,0x55,0xff,0xff,0x55,0x55,0xff,0xff vt.default_blu=0x4e,0x00,0x00,0x00,0xaa,0xaa,0xaa,0xaa,0x55,0x55,0x55,0x55,0xff,0xff,0xff,0xff ---
    initrd /casper/initrd
}

menuentry "Boot from next volume" {
    exit
}

menuentry "UEFI Firmware Settings" {
    fwsetup
}
GRUB_PURPLE

        log_info "GRUB config replaced (live boot default)"
    else
        log_info "WARNING: GRUB config not found at expected location"
        ls -la "$WORK_DIR/iso-new/boot/grub/" 2>/dev/null || true
    fi

    # NOTE: Ubuntu Server 24.04 uses GRUB for both BIOS and UEFI boot (not isolinux).
    # Boot configuration is preserved via xorriso's -boot_image any replay.

    # Step 8: Patch EFI partition to suppress GRUB error during boot
    #
    # Ubuntu's grubx64.efi has an embedded config that checks -e "$prefix" on the
    # EFI partition. Since the EFI partition doesn't have /boot/grub/, GRUB prints
    # "error: file '/boot/' not found" before falling back to search /.disk/info.
    # Fix: add /boot/grub/grub.cfg to the EFI partition so the check passes and
    # GRUB chains to our real config without any visible error.
    log_step "8/11: Patching EFI partition..."

    # Build a fresh EFI image with latest signed binaries instead of patching the
    # ISO's tiny original. This avoids size constraints and path-guessing fragility.
    SIGNED_EFI="${BUILD_DIR}/signed-efi"
    if [ ! -f "$SIGNED_EFI/BOOTX64.EFI" ] || [ ! -f "$SIGNED_EFI/grubx64.efi" ]; then
        echo "ERROR: Signed EFI binaries not found in $SIGNED_EFI (golden image must be built first)"
        exit 1
    fi

    # Size the image to fit contents + generous padding (FAT overhead + future growth)
    EFI_CONTENT_KB=$(du -sk "$SIGNED_EFI" | cut -f1)
    EFI_SIZE_KB=$(( (EFI_CONTENT_KB + 512 + 63) / 64 * 64 ))  # round up to 64KB
    EFI_IMG="$WORK_DIR/efi-patched.img"
    dd if=/dev/zero of="$EFI_IMG" bs=1K count="$EFI_SIZE_KB" 2>/dev/null
    mkfs.vfat -F 12 "$EFI_IMG" >/dev/null

    EFI_MNT="$WORK_DIR/efi-mount"
    mkdir -p "$EFI_MNT"
    mount -o loop "$EFI_IMG" "$EFI_MNT"

    # Standard UEFI fallback path: /EFI/BOOT/
    mkdir -p "$EFI_MNT/EFI/BOOT"
    cp "$SIGNED_EFI/BOOTX64.EFI" "$EFI_MNT/EFI/BOOT/BOOTX64.EFI"
    cp "$SIGNED_EFI/grubx64.efi" "$EFI_MNT/EFI/BOOT/grubx64.efi"
    [ -f "$SIGNED_EFI/mmx64.efi" ] && cp "$SIGNED_EFI/mmx64.efi" "$EFI_MNT/EFI/BOOT/mmx64.efi"

    # Signed GRUB has prefix=/EFI/ubuntu compiled in. Also add /boot/grub/ as fallback.
    # Both chain to the ISO filesystem's real config.
    mkdir -p "$EFI_MNT/EFI/ubuntu" "$EFI_MNT/boot/grub"
    for cfg in "$EFI_MNT/EFI/ubuntu/grub.cfg" "$EFI_MNT/boot/grub/grub.cfg"; do
        cat > "$cfg" << 'EFI_GRUB_EOF'
search --file --set=root /.disk/info
set prefix=($root)/boot/grub
source $prefix/grub.cfg
EFI_GRUB_EOF
    done

    umount "$EFI_MNT"
    rmdir "$EFI_MNT"
    log_info "Built fresh EFI image (${EFI_SIZE_KB}KB) with latest signed binaries"

    # Step 9: Build normal ISO
    log_step "9/11: Building normal ISO..."

    OUTPUT_ISO="/opt/purple-installer/output/purple-installer-$(date +%Y%m%d)${ISO_TAG}.iso"

    # Remove existing ISOs (xorriso can't overwrite)
    rm -f "$OUTPUT_ISO" "${OUTPUT_ISO}.sha256"

    # Use xorriso modify mode: load original, update files, replace EFI image
    xorriso -indev "$UBUNTU_ISO" \
        -outdev "$OUTPUT_ISO" \
        -volid "PURPLE_INSTALLER" \
        -update_r "$WORK_DIR/iso-new" / \
        -boot_image any replay \
        -append_partition 2 0xEF "$EFI_IMG"

    # Generate checksum
    sha256sum "$OUTPUT_ISO" > "${OUTPUT_ISO}.sha256"

    log_info "Normal ISO built successfully!"
    log_info "Output: $OUTPUT_ISO"
    log_info "Size: $(du -h "$OUTPUT_ISO" | cut -f1)"
    log_info "SHA256: $(cat "${OUTPUT_ISO}.sha256")"

    # Step 10: Build debug ISO
    # Same squashfs/initramfs, different GRUB config: verbose boot, visible menu,
    # purple.debug=1 flag triggers debug mode in casper hook and .bashrc
    log_step "10/11: Building debug ISO..."

    DEBUG_ISO="/opt/purple-installer/output/purple-installer-$(date +%Y%m%d)${ISO_TAG}.debug.iso"
    rm -f "$DEBUG_ISO" "${DEBUG_ISO}.sha256"

    # Save normal GRUB config and write debug version
    GRUB_CFG="$WORK_DIR/iso-new/boot/grub/grub.cfg"
    cp "$GRUB_CFG" "${GRUB_CFG}.normal"

    cat > "$GRUB_CFG" << GRUB_DEBUG
# Purple Computer - DEBUG GRUB Configuration
# Verbose boot, visible menu, all diagnostics enabled
# (See normal GRUB config above for explanation of masked services)

set timeout=5
set timeout_style=menu
set default=0

menuentry "Purple Computer (DEBUG)" {
    set gfxpayload=keep
    linux /casper/vmlinuz boot=casper systemd.show_status=true username=purple cloud-init=disabled systemd.mask=subiquity.service systemd.mask=snapd.service systemd.mask=snapd.socket systemd.mask=ssh.service systemd.mask=ssh.socket systemd.mask=udisks2.service systemd.mask=casper-md5check.service purple.debug=1 ---
    initrd /casper/initrd
}

menuentry "Purple Computer (DEBUG, input test)" {
    set gfxpayload=keep
    linux /casper/vmlinuz boot=casper systemd.show_status=true username=purple cloud-init=disabled systemd.mask=subiquity.service systemd.mask=snapd.service systemd.mask=snapd.socket systemd.mask=ssh.service systemd.mask=ssh.socket systemd.mask=udisks2.service systemd.mask=casper-md5check.service purple.debug=1 purple.inputtest=1 ---
    initrd /casper/initrd
}

menuentry "Purple Computer (DEBUG, recovery shell)" {
    set gfxpayload=keep
    linux /casper/vmlinuz boot=casper single username=purple cloud-init=disabled systemd.mask=subiquity.service systemd.mask=snapd.service systemd.mask=casper-md5check.service purple.debug=1 ---
    initrd /casper/initrd
}

menuentry "Purple Computer (DEBUG, test error screen)" {
    set gfxpayload=keep
    linux /casper/vmlinuz boot=casper systemd.show_status=true username=purple cloud-init=disabled systemd.mask=subiquity.service systemd.mask=snapd.service systemd.mask=snapd.socket systemd.mask=ssh.service systemd.mask=ssh.socket systemd.mask=udisks2.service systemd.mask=casper-md5check.service purple.debug=1 purple.failx11=1 ---
    initrd /casper/initrd
}

menuentry "---" {
    true
}

menuentry "Purple Computer (production boot)" {
    set gfxpayload=keep
    linux /casper/vmlinuz boot=casper quiet loglevel=0 systemd.show_status=false vt.global_cursor_default=0 console=tty2 console=ttyS0,115200 username=purple cloud-init=disabled systemd.mask=subiquity.service systemd.mask=snapd.service systemd.mask=snapd.socket systemd.mask=ssh.service systemd.mask=ssh.socket systemd.mask=udisks2.service systemd.mask=casper-md5check.service vt.default_red=0x2d,0xaa,0x00,0xaa,0x00,0xaa,0x00,0xaa,0x55,0xff,0x55,0xff,0x55,0xff,0x55,0xff vt.default_grn=0x1b,0x00,0xaa,0x55,0x00,0x00,0xaa,0xaa,0x55,0x55,0xff,0xff,0x55,0x55,0xff,0xff vt.default_blu=0x4e,0x00,0x00,0x00,0xaa,0xaa,0xaa,0xaa,0x55,0x55,0x55,0x55,0xff,0xff,0xff,0xff ---
    initrd /casper/initrd
}

menuentry "Boot from next volume" {
    exit
}

menuentry "UEFI Firmware Settings" {
    fwsetup
}
GRUB_DEBUG

    xorriso -indev "$UBUNTU_ISO" \
        -outdev "$DEBUG_ISO" \
        -volid "PURPLE_DEBUG" \
        -update_r "$WORK_DIR/iso-new" / \
        -boot_image any replay \
        -append_partition 2 0xEF "$EFI_IMG"

    sha256sum "$DEBUG_ISO" > "${DEBUG_ISO}.sha256"

    log_info "Debug ISO built successfully!"
    log_info "Output: $DEBUG_ISO"
    log_info "Size: $(du -h "$DEBUG_ISO" | cut -f1)"
    log_info "SHA256: $(cat "${DEBUG_ISO}.sha256")"

    # Restore normal GRUB config (for clean state)
    mv "${GRUB_CFG}.normal" "$GRUB_CFG"

    # Cleanup
    log_info "Cleaning up working directories..."
    rm -rf "$WORK_DIR/iso-mount" "$WORK_DIR/iso-new" "$WORK_DIR/initrd-work" "$WORK_DIR/new-initrd"
}

main "$@"
