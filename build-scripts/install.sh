#!/bin/bash
# PurpleOS Factory Installer
# Dead-simple disk reimaging: wipe, write image, install bootloader, reboot

set -e

echo "[DEBUG] install.sh started, set -e active"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[PURPLE]${NC} $1" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# Find target disk (anything except the boot disk)
find_target() {
    echo "[DEBUG] find_target() entered" >&2
    log "Detecting boot disk..."
    echo "[DEBUG] About to check PURPLE_INSTALLER_DEV" >&2
    log "PURPLE_INSTALLER_DEV env var: ${PURPLE_INSTALLER_DEV:-NOT SET}"
    echo "[DEBUG] Declaring local boot_disk" >&2

    local boot_disk
    echo "[DEBUG] local boot_disk declared" >&2

    # The init script passed us the installer partition device
    if [ -n "$PURPLE_INSTALLER_DEV" ]; then
        log "Installer partition: $PURPLE_INSTALLER_DEV"

        # Strip partition number to get parent disk
        # Handle: /dev/sda2 -> sda, /dev/vda1 -> vda, /dev/nvme0n1p2 -> nvme0n1
        # Use basic sed without -E for better compatibility
        boot_disk=$(echo "$PURPLE_INSTALLER_DEV" | sed 's|/dev/||' | sed 's/p*[0-9]*$//')
        log "Boot disk: $boot_disk"
    else
        log "WARNING: PURPLE_INSTALLER_DEV not set, falling back to partition detection"

        # Fallback: assume the disk with partitions is the boot disk
        for disk in /sys/block/*; do
            local disk_name
            disk_name=$(basename "$disk")

            case "$disk_name" in
                loop*|ram*|sr*) continue ;;
            esac

            # Check if has partition subdirectories with "partition" file
            for part in "$disk"/*; do
                if [ -f "$part/partition" ]; then
                    boot_disk="$disk_name"
                    log "Boot disk: $boot_disk (has partitions - fallback method)"
                    break 2
                fi
            done
        done
    fi

    log "Boot disk identified as: $boot_disk"

    # Find first disk that isn't the boot disk
    for disk in /sys/block/*; do
        name=$(basename "$disk")

        # Skip loop, ram, rom devices
        case "$name" in
            loop*|ram*|sr*) continue ;;
        esac

        # Skip the boot disk
        if [ "$name" = "$boot_disk" ]; then
            log "Skipping $name (boot disk)"
            continue
        fi

        log "Selected target: $name"
        echo "$name"
        return 0
    done

    log "ERROR: No target disk found (only boot disk available)"
    return 1
}

main() {
    log "PurpleOS Factory Installer"
    log "=========================="

    log "About to call find_target..."
    set +e  # Temporarily disable exit-on-error
    TARGET=$(find_target)
    FIND_EXIT=$?
    set -e  # Re-enable exit-on-error
    log "find_target returned: $TARGET (exit code: $FIND_EXIT)"

    if [ $FIND_EXIT -ne 0 ] || [ -z "$TARGET" ]; then
        error "No target disk found"
    fi

    log "Target disk: /dev/$TARGET"

    # Verify device exists
    if [ ! -b /dev/$TARGET ]; then
        error "Target device /dev/$TARGET not found"
    fi

    echo ""
    echo "    ----------------------------------------"
    echo "    Step 1 of 3: Writing system image"
    echo "    ----------------------------------------"
    echo ""

    # Write PurpleOS golden image to entire disk
    # The image contains: GPT partition table + EFI partition + root partition + bootloader
    zstd -dc /purple-os.img.zst | dd of=/dev/$TARGET bs=4M status=progress 2>&1

    echo ""
    echo "    ----------------------------------------"
    echo "    Step 2 of 3: Configuring system"
    echo "    ----------------------------------------"
    echo ""

    # Force kernel to re-read partition table from the new image
    log "Syncing disk..."
    sync
    blockdev --rereadpt /dev/$TARGET || true
    sleep 2  # Give kernel time to recognize new partitions

    # Register PurpleOS in UEFI boot order (required for Surface and some other laptops)
    log "Registering PurpleOS in UEFI boot menu..."

    # Determine EFI partition device name
    # For nvme: /dev/nvme0n1p1, for sata: /dev/sda1
    case "$TARGET" in
        nvme*) EFI_PART="/dev/${TARGET}p1" ;;
        *)     EFI_PART="/dev/${TARGET}1" ;;
    esac

    if [ -b "$EFI_PART" ]; then
        # Mount EFI partition temporarily
        mkdir -p /mnt/efi
        mount "$EFI_PART" /mnt/efi 2>/dev/null || true

        if command -v efibootmgr >/dev/null 2>&1; then
            # Remove any existing PurpleOS entries first
            for bootnum in $(efibootmgr | grep -i "PurpleOS" | grep -oE "Boot[0-9]+" | sed 's/Boot//'); do
                efibootmgr -b "$bootnum" -B 2>/dev/null || true
            done

            # Create new boot entry pointing to our bootloader
            efibootmgr -c -d "/dev/$TARGET" -p 1 -L "PurpleOS" -l '\EFI\BOOT\BOOTX64.EFI' 2>/dev/null && \
                log "✓ Added PurpleOS to UEFI boot menu" || \
                log "Warning: Could not add UEFI boot entry (may need manual setup)"
        else
            log "Warning: efibootmgr not available, UEFI boot entry not created"
        fi

        umount /mnt/efi 2>/dev/null || true
    fi

    echo ""
    echo "    ----------------------------------------"
    echo "    Step 3 of 3: Complete!"
    echo "    ----------------------------------------"
    echo ""
    echo "    ========================================"
    echo "    |                                      |"
    echo "    |   Installation successful!           |"
    echo "    |                                      |"
    echo "    |   Rebooting in 5 seconds...          |"
    echo "    |                                      |"
    echo "    |   Remove the USB drive when the      |"
    echo "    |   screen goes dark.                  |"
    echo "    |                                      |"
    echo "    ========================================"
    echo ""
    sleep 5
    # Use busybox reboot or kernel reboot syscall
    /bin/busybox reboot -f || echo b > /proc/sysrq-trigger
}

main "$@"
