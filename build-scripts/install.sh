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

# Spawn emergency shell on tty2 (user can access with Alt+F2)
if [ -c /dev/tty2 ]; then
    log "Emergency shell available on tty2 (Alt+F2)"
    setsid bash </dev/tty2 >/dev/tty2 2>&1 &
fi

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

    # Debug: Check if device actually exists and is accessible
    log "Checking device /dev/$TARGET..."
    ls -la /dev/$TARGET || log "ERROR: Device node doesn't exist!"
    [ -b /dev/$TARGET ] && log "Device is a block device" || log "ERROR: Not a block device!"

    log "WARNING: This will WIPE /dev/$TARGET"
    sleep 3

    # Write PurpleOS golden image to entire disk
    # The image contains: GPT partition table + EFI partition + root partition + bootloader
    log "Writing PurpleOS image to disk (this takes ~10 min)..."
    zstd -dc /purple-os.img.zst | dd of=/dev/$TARGET bs=4M status=progress

    # Force kernel to re-read partition table from the new image
    log "Reloading partition table..."
    sync
    blockdev --rereadpt /dev/$TARGET || true
    sleep 2  # Give kernel time to recognize new partitions

    log "Verifying partitions..."
    ls -la /dev/${TARGET}* || log "Warning: partition devices not visible yet"

    # ==========================================================================
    # ROBUST UEFI BOOT SETUP - Multi-layer approach for maximum compatibility
    # ==========================================================================
    # Many firmwares (especially Surface, HP, some Dell) have buggy UEFI that:
    # - Ignores BootOrder changes from efibootmgr
    # - Resets boot order on every boot
    # - Only boots from specific paths
    #
    # Our strategy uses THREE layers of fallback:
    # 1. Standard EFI/BOOT/BOOTX64.EFI (fallback path all UEFI checks)
    # 2. EFI/Microsoft/Boot/bootmgfw.efi (some firmwares ONLY boot this)
    # 3. efibootmgr entry with explicit boot order (for compliant firmwares)
    # ==========================================================================

    log "Setting up UEFI boot (multi-layer approach for compatibility)..."

    # Determine EFI partition device name
    case "$TARGET" in
        nvme*) EFI_PART="/dev/${TARGET}p1" ;;
        *)     EFI_PART="/dev/${TARGET}1" ;;
    esac

    if [ -b "$EFI_PART" ]; then
        if mount "$EFI_PART" /mnt/efi 2>/dev/null; then

            # Layer 1: Standard fallback path (EFI/BOOT/BOOTX64.EFI)
            # This is already done during partition setup, but verify it exists
            if [ -f /mnt/efi/EFI/BOOT/BOOTX64.EFI ]; then
                log "Layer 1: EFI/BOOT/BOOTX64.EFI present (standard fallback)"
            else
                log "Warning: EFI/BOOT/BOOTX64.EFI missing!"
            fi

            # Layer 2: Microsoft bootloader path hijack
            # Some buggy firmwares (HP, some Surface) ONLY boot EFI/Microsoft/Boot/bootmgfw.efi
            # By placing our bootloader there, we ensure it boots even on these systems
            mkdir -p /mnt/efi/EFI/Microsoft/Boot
            if [ -f /mnt/efi/EFI/BOOT/BOOTX64.EFI ]; then
                cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi
                log "Layer 2: Installed to EFI/Microsoft/Boot/bootmgfw.efi (for buggy firmwares)"
            fi

            # Layer 3: Create proper UEFI boot entry and set boot order
            # This works on compliant firmwares and provides a clean boot menu entry
            if command -v efibootmgr >/dev/null 2>&1; then
                # Remove any existing PurpleOS entries first
                for bootnum in $(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9]+" | sed 's/Boot//'); do
                    efibootmgr -b "$bootnum" -B 2>/dev/null || true
                done

                # Create new boot entry
                if efibootmgr -c -d "/dev/$TARGET" -p 1 -L "PurpleOS" -l '\EFI\BOOT\BOOTX64.EFI' 2>/dev/null; then
                    log "Layer 3: Created UEFI boot entry 'PurpleOS'"

                    # Set as first in boot order
                    PURPLE_BOOTNUM=$(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9]+" | head -1 | sed 's/Boot//')
                    if [ -n "$PURPLE_BOOTNUM" ]; then
                        CURRENT_ORDER=$(efibootmgr 2>/dev/null | grep "BootOrder:" | sed 's/BootOrder: //')
                        NEW_ORDER=$(echo "$CURRENT_ORDER" | sed "s/$PURPLE_BOOTNUM,//g" | sed "s/,$PURPLE_BOOTNUM//g" | sed "s/^$PURPLE_BOOTNUM$//")
                        [ -n "$NEW_ORDER" ] && NEW_ORDER="$PURPLE_BOOTNUM,$NEW_ORDER" || NEW_ORDER="$PURPLE_BOOTNUM"
                        efibootmgr -o "$NEW_ORDER" 2>/dev/null && \
                            log "Layer 3: Set boot order to $NEW_ORDER" || \
                            log "Layer 3: Could not set boot order (firmware may ignore)"
                    fi
                else
                    log "Layer 3: Could not create UEFI entry (layers 1-2 should still work)"
                fi
            fi

            umount /mnt/efi 2>/dev/null || true
            log "UEFI boot setup complete (using 3-layer fallback strategy)"
        else
            log "Warning: Could not mount EFI partition for boot setup"
        fi
    fi

    log "Installation complete!"

    # Detect if we're running in a VM - if so, skip USB removal wait
    IS_VM=false
    if [ -f /sys/class/dmi/id/product_name ]; then
        PRODUCT=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "")
        case "$PRODUCT" in
            *"Virtual"*|*"QEMU"*|*"KVM"*|*"VMware"*|*"VirtualBox"*|*"Bochs"*)
                IS_VM=true
                log "Detected VM environment ($PRODUCT) - skipping USB removal wait"
                ;;
        esac
    fi
    # Also check for hypervisor flag in cpuinfo
    if grep -q "^flags.*hypervisor" /proc/cpuinfo 2>/dev/null; then
        IS_VM=true
        log "Detected hypervisor flag - skipping USB removal wait"
    fi

    if [ "$IS_VM" = "true" ]; then
        # VM: just show completion and reboot after brief delay
        log "================================================="
        log "             Installation complete!              "
        log "================================================="
        log "Rebooting in 5 seconds..."
        sleep 5
    else
        # Physical hardware: wait for USB removal

        # Get the USB disk name from PURPLE_INSTALLER_DEV (e.g., /dev/sda2 -> sda)
        USB_DISK=""
        if [ -n "$PURPLE_INSTALLER_DEV" ]; then
            USB_DISK=$(echo "$PURPLE_INSTALLER_DEV" | sed 's|/dev/||' | sed 's/p*[0-9]*$//')
        fi

        # Check if the boot device is actually removable
        IS_REMOVABLE=false
        if [ -n "$USB_DISK" ] && [ -f "/sys/block/$USB_DISK/removable" ]; then
            if [ "$(cat /sys/block/$USB_DISK/removable)" = "1" ]; then
                IS_REMOVABLE=true
            fi
        fi

        # Clear screen and show friendly completion message
        clear
        echo ""
        echo ""
        echo -e "${GREEN}=================================================${NC}"
        echo -e "${GREEN}                                                 ${NC}"
        echo -e "${GREEN}             All done!                           ${NC}"
        echo -e "${GREEN}                                                 ${NC}"
        echo -e "${GREEN}=================================================${NC}"
        echo ""
        echo ""
        echo -e "    Please remove the USB stick now."
        echo ""
        echo -e "    Your computer will restart automatically"
        echo -e "    once the USB stick is removed."
        echo ""
        echo ""

        # Wait for USB to be physically removed (only if removable device detected)
        if [ "$IS_REMOVABLE" = "true" ] && [ -d "/sys/block/$USB_DISK" ]; then
            while [ -d "/sys/block/$USB_DISK" ]; do
                sleep 1
            done
            # USB removed - brief pause then reboot
            echo ""
            echo -e "    USB removed. Restarting now..."
            echo ""
            sleep 2
        else
            # Fallback: countdown with option to press enter
            echo ""
            echo -e "    Rebooting in 30 seconds (or press ENTER)..."
            echo ""
            read -t 30 2>/dev/null || true
        fi
    fi

    # Use busybox reboot or kernel reboot syscall
    /bin/busybox reboot -f || echo b > /proc/sysrq-trigger
}

main "$@"
