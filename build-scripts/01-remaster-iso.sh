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
    #
    # ARCHITECTURE (IMMUTABLE RULES):
    # - We NEVER modify squashfs
    # - Gate 2 is implemented via RUNTIME systemd units in /run
    # - The initramfs hook writes both the marker AND the systemd service to /run
    # - systemd automatically loads units from /run/systemd/system/
    #
    # SAFETY REQUIREMENTS:
    # - Explicit arming via kernel cmdline (purple.install=1)
    # - Fail-open: exits cleanly if not armed or payload missing
    # - All waits have timeouts
    # - Loud logging to console
    # - Never blocks indefinitely
    cat > "$HOOK_DIR/01_purple_installer" << 'HOOK_EOF'
#!/bin/sh
# Purple Computer Installer Hook
# Runs early in initramfs, before casper mounts squashfs
#
# TWO-GATE SAFETY MODEL:
#   Gate 1 (this hook): Check arming flag, write runtime systemd unit
#   Gate 2 (runtime systemd service): Show confirmation, require user input
#
# CRITICAL: We do NOT modify squashfs. Gate 2 is implemented by writing
# a systemd service file to /run/systemd/system/ which systemd loads at boot.
#
# This hook:
# 1. Checks if purple.install=1 is in cmdline (Gate 1)
# 2. Verifies payload exists on boot device
# 3. Writes /run/purple/armed marker
# 4. Writes /run/systemd/system/purple-confirm.service (Gate 2)
# 5. Writes /run/purple/confirm.sh (confirmation script)
# 6. Exits cleanly - casper/systemd boot continues normally

PREREQ=""
prereqs() { echo "$PREREQ"; }
case "$1" in
    prereqs) prereqs; exit 0 ;;
esac

# Source initramfs functions
. /scripts/functions

# =============================================================================
# LOUD LOGGING - all output goes to console
# =============================================================================
purple_log() {
    echo "[PURPLE] $1" >/dev/console 2>&1 || echo "[PURPLE] $1"
}

purple_log "=== Purple Computer Installer Hook ==="
purple_log "Checking arming status..."

# =============================================================================
# GATE 1: EXPLICIT ARMING CHECK
# =============================================================================
if ! grep -q "purple.install=1" /proc/cmdline 2>/dev/null; then
    purple_log "NOT ARMED: purple.install=1 not in cmdline"
    purple_log "Gate 1 CLOSED - Normal Ubuntu boot"
    exit 0
fi

purple_log "ARMED: purple.install=1 found"

# =============================================================================
# DEVICE DETECTION WITH TIMEOUT
# =============================================================================
purple_log "Waiting for devices (max 10s)..."

WAIT_COUNT=0
WAIT_MAX=10
while [ $WAIT_COUNT -lt $WAIT_MAX ]; do
    if ls /dev/sd* /dev/nvme* /dev/vd* 2>/dev/null | head -1 | grep -q .; then
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

# =============================================================================
# PAYLOAD DETECTION
# =============================================================================
purple_log "Scanning for payload..."
PAYLOAD_DEV=""
PAYLOAD_MNT=""
SCAN_COUNT=0
SCAN_MAX=20

for dev in /dev/sd* /dev/nvme*n*p* /dev/vd*; do
    [ -b "$dev" ] || continue
    SCAN_COUNT=$((SCAN_COUNT + 1))
    [ $SCAN_COUNT -gt $SCAN_MAX ] && break

    TMPMNT="/tmp/purple-check-$$"
    mkdir -p "$TMPMNT"

    if mount -o ro "$dev" "$TMPMNT" 2>/dev/null; then
        if [ -x "$TMPMNT/purple/install.sh" ]; then
            PAYLOAD_DEV="$dev"
            PAYLOAD_MNT="$TMPMNT"
            purple_log "FOUND payload on $dev"
            break
        fi
        umount "$TMPMNT" 2>/dev/null || true
    fi
    rmdir "$TMPMNT" 2>/dev/null || true
done

# =============================================================================
# FAIL-OPEN: No payload = normal boot
# =============================================================================
if [ -z "$PAYLOAD_DEV" ]; then
    purple_log "NO PAYLOAD - Normal Ubuntu boot"
    exit 0
fi

# =============================================================================
# WRITE RUNTIME ARTIFACTS TO /run
# These persist into userspace and are picked up by systemd
# =============================================================================
purple_log "Writing runtime artifacts to /run..."

# Create directories
mkdir -p /run/purple
mkdir -p /run/systemd/system/sysinit.target.wants

# 1. Write arming marker with payload info
cat > /run/purple/armed << MARKER_EOF
PAYLOAD_DEV=$PAYLOAD_DEV
PAYLOAD_MNT=$PAYLOAD_MNT
PAYLOAD_PATH=$PAYLOAD_MNT/purple
MARKER_EOF

# 2. Copy confirmation script from payload to /run
if [ -x "$PAYLOAD_MNT/purple/purple-confirm.sh" ]; then
    cp "$PAYLOAD_MNT/purple/purple-confirm.sh" /run/purple/confirm.sh
    chmod +x /run/purple/confirm.sh
    purple_log "Copied confirmation script"
else
    purple_log "WARNING: No purple-confirm.sh in payload"
    # Create minimal fallback
    cat > /run/purple/confirm.sh << 'CONFIRM_FALLBACK'
#!/bin/sh
echo "[PURPLE] ERROR: Confirmation script missing from payload"
echo "Rebooting in 10 seconds..."
sleep 10
reboot -f
CONFIRM_FALLBACK
    chmod +x /run/purple/confirm.sh
fi

# 3. Write systemd service unit to /run (picked up automatically by systemd)
cat > /run/systemd/system/purple-confirm.service << 'SERVICE_EOF'
[Unit]
Description=Purple Computer Installer (Gate 2: User Confirmation)
DefaultDependencies=no
After=sysinit.target
Before=basic.target
ConditionPathExists=/run/purple/armed

[Service]
Type=oneshot
StandardInput=tty
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
ExecStart=/run/purple/confirm.sh
TimeoutStartSec=600
SERVICE_EOF

# 4. Enable the service (symlink into sysinit.target.wants)
ln -sf ../purple-confirm.service /run/systemd/system/sysinit.target.wants/purple-confirm.service

purple_log "============================================"
purple_log "Gate 1 PASSED"
purple_log "  Payload: $PAYLOAD_DEV"
purple_log "  Runtime service written to /run"
purple_log "============================================"
purple_log "Continuing to userspace (Gate 2)..."

# Keep payload mounted - confirmation script needs it
# Exit cleanly - casper/systemd boot continues
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
    log_step "Purple Computer ISO Remaster (Two-Gate Safety Model)"
    log_info "Architecture: Initramfs marker (Gate 1) + Runtime /run service (Gate 2)"

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

    # Step 4: Extract and modify initramfs (Gate 1 + Gate 2 runtime units)
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

    # Copy confirmation script to payload (initramfs will reference it)
    log_info "Copying confirmation script to payload..."
    cp "$SCRIPT_DIR/purple-confirm.sh" "$PAYLOAD_DIR/purple-confirm.sh"
    chmod +x "$PAYLOAD_DIR/purple-confirm.sh"

    # Unmount source ISO
    umount "$WORK_DIR/iso-mount"

    # NOTE: We do NOT modify squashfs. Gate 2 is implemented via runtime
    # systemd units written to /run by the initramfs hook. This keeps the
    # live root filesystem identical to the official Ubuntu ISO.

    # Step 6: Update GRUB config for arming and debug boot
    log_step "6/7: Configuring GRUB boot entries..."

    # Add purple.install=1 to default boot entry and create debug entry
    # This arms the installer on normal boot, but allows debug boot to skip it
    GRUB_CFG="$WORK_DIR/iso-new/boot/grub/grub.cfg"
    if [ -f "$GRUB_CFG" ]; then
        log_info "Modifying GRUB config for Purple installer..."

        # Backup original
        cp "$GRUB_CFG" "${GRUB_CFG}.orig"

        # Add purple.install=1 to all linux boot lines (arms the installer)
        sed -i 's|\(linux.*casper.*\)|\1 purple.install=1 loglevel=7|g' "$GRUB_CFG"

        # Add a debug menu entry that boots without purple.install=1
        # This drops into normal Ubuntu Server live environment
        cat >> "$GRUB_CFG" << 'GRUB_DEBUG'

# Purple Computer Debug Entry - boots without running installer
menuentry "Purple Computer - Debug Mode (no install)" {
    set gfxpayload=keep
    linux /casper/vmlinuz boot=casper loglevel=7 ---
    initrd /casper/initrd
}
GRUB_DEBUG

        log_info "GRUB config updated with purple.install=1 and debug entry"
    else
        log_info "WARNING: GRUB config not found at expected location"
        ls -la "$WORK_DIR/iso-new/boot/grub/" 2>/dev/null || true
    fi

    # NOTE: Ubuntu Server 24.04 is UEFI-only and does NOT ship isolinux/syslinux.
    # Do not attempt to update or create BIOS boot configs.

    # Step 7: Rebuild ISO
    log_step "7/7: Building final ISO..."

    OUTPUT_ISO="/opt/purple-installer/output/purple-installer-$(date +%Y%m%d).iso"

    # ==========================================================================
    # IMPORTANT: Ubuntu Server 24.04 is UEFI-only
    # ==========================================================================
    # Ubuntu Server 24.04 does NOT include isolinux or BIOS boot support.
    # We use xorriso's boot metadata replay (-boot_image any replay) to inherit
    # Canonical's exact boot configuration from the source ISO.
    #
    # This ensures:
    # - Secure Boot remains intact (shim + GRUB chain)
    # - GRUB + shim configuration matches the original ISO
    # - No hardcoded assumptions about boot paths
    # - No future breakage when Canonical changes internals
    #
    # DO NOT add isolinux, isohdpfx.bin, or BIOS El Torito boot entries.
    # ==========================================================================

    xorriso -indev "$UBUNTU_ISO" \
        -outdev "$OUTPUT_ISO" \
        -volid "PURPLE_INSTALLER" \
        -boot_image any replay \
        -map "$WORK_DIR/iso-new" /

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
