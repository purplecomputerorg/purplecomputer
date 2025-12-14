#!/bin/bash
# PurpleOS Factory Installer
# Runs from Ubuntu live environment (casper-based)
#
# This script:
# 1. Detects the internal disk (excluding USB/removable devices)
# 2. Wipes the partition table
# 3. Writes the pre-built golden image (purple-os.img.zst)
# 4. Sets up UEFI boot with multi-layer fallback strategy
# 5. Reboots into the installed system

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
NC='\033[0m'

log() { echo -e "${GREEN}[PURPLE]${NC} $1" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# Spawn emergency shell on tty2 (user can access with Alt+F2)
if [ -c /dev/tty2 ]; then
    log "Emergency shell available on tty2 (Alt+F2)"
    setsid bash </dev/tty2 >/dev/tty2 2>&1 &
fi

# Display splash screen
show_splash() {
    clear
    echo ""
    echo -e "${PURPLE}=================================================${NC}"
    echo -e "${PURPLE}                                                 ${NC}"
    echo -e "${PURPLE}          Purple Computer Installer              ${NC}"
    echo -e "${PURPLE}                                                 ${NC}"
    echo -e "${PURPLE}=================================================${NC}"
    echo ""
    echo ""
}

# Find target disk (exclude USB/removable devices and the boot device)
find_target() {
    log "Detecting internal disk..."

    # In casper live environment, we need to identify and exclude the boot device
    local boot_dev=""

    # Method 1: Check /proc/cmdline for boot device hints from casper
    if grep -q "boot=casper" /proc/cmdline 2>/dev/null; then
        # Casper stores boot device info
        if [ -f /run/casper/rootfs.list ]; then
            log "  Found casper rootfs info"
        fi
    fi

    # Method 2: Find the device containing the live filesystem
    # The ISO volume is labeled PURPLE_INSTALLER
    local iso_dev=""
    iso_dev=$(blkid -L PURPLE_INSTALLER 2>/dev/null | sed 's/[0-9]*$//' || true)
    if [ -n "$iso_dev" ]; then
        boot_dev=$(basename "$iso_dev")
        log "  Boot device (ISO): $boot_dev"
    fi

    # Iterate through all block devices
    for disk in /sys/block/*; do
        [ -d "$disk" ] || continue
        local name=$(basename "$disk")

        # Skip loop, ram, rom devices
        case "$name" in
            loop*|ram*|sr*|dm-*) continue ;;
        esac

        # Skip the boot device
        if [ "$name" = "$boot_dev" ]; then
            log "  Skipping $name (boot device)"
            continue
        fi

        # Skip removable devices
        if [ -f "$disk/removable" ] && [ "$(cat $disk/removable)" = "1" ]; then
            log "  Skipping $name (removable)"
            continue
        fi

        # Check transport - skip USB
        local transport=""
        if [ -f "$disk/device/transport" ]; then
            transport=$(cat "$disk/device/transport" 2>/dev/null || echo "")
        fi
        # Also check via udevadm for more reliable detection
        if [ -z "$transport" ]; then
            transport=$(udevadm info --query=property --name=/dev/$name 2>/dev/null | grep "^ID_BUS=" | cut -d= -f2 || echo "")
        fi

        if [ "$transport" = "usb" ]; then
            log "  Skipping $name (USB transport)"
            continue
        fi

        # This appears to be an internal disk
        log "  Found internal disk: $name"
        echo "$name"
        return 0
    done

    return 1
}

# Get disk size in human-readable format
get_disk_size() {
    local disk="$1"
    local size_bytes=$(cat /sys/block/$disk/size 2>/dev/null || echo 0)
    local size_gb=$((size_bytes * 512 / 1024 / 1024 / 1024))
    echo "${size_gb}GB"
}

# Main installation routine
main() {
    show_splash

    log "Purple Computer Factory Installer"
    log "=================================="
    log ""

    # Find target disk
    TARGET=$(find_target) || error "No target disk found. Is there an internal disk?"

    TARGET_SIZE=$(get_disk_size "$TARGET")
    log "Target disk: /dev/$TARGET ($TARGET_SIZE)"

    # Safety check: Verify device exists and is a block device
    if [ ! -b "/dev/$TARGET" ]; then
        error "Device /dev/$TARGET is not a valid block device"
    fi

    # Check minimum disk size (need at least 16GB for golden image)
    local size_bytes=$(cat /sys/block/$TARGET/size 2>/dev/null || echo 0)
    local size_gb=$((size_bytes * 512 / 1024 / 1024 / 1024))
    if [ "$size_gb" -lt 16 ]; then
        error "Disk too small: ${size_gb}GB (minimum 16GB required)"
    fi

    log ""
    log "WARNING: This will ERASE ALL DATA on /dev/$TARGET"
    log ""
    sleep 3

    # Write golden image directly to disk
    log "Writing Purple Computer to disk..."
    log "  Source: /purple-os.img.zst"
    log "  Target: /dev/$TARGET"
    log "  This will take approximately 10-15 minutes..."
    log ""

    # Use pv for progress if available, otherwise dd with status=progress
    if command -v pv >/dev/null 2>&1; then
        zstd -dc /purple-os.img.zst | pv -s $(zstd -l /purple-os.img.zst 2>/dev/null | tail -1 | awk '{print $5}' || echo "2G") | dd of=/dev/$TARGET bs=4M conv=fsync
    else
        zstd -dc /purple-os.img.zst | dd of=/dev/$TARGET bs=4M status=progress conv=fsync
    fi

    # Force kernel to re-read partition table from the new image
    log "Reloading partition table..."
    sync
    blockdev --rereadpt /dev/$TARGET || true
    sleep 2

    log "Verifying partitions..."
    ls -la /dev/${TARGET}* 2>/dev/null || warn "Partition devices not visible yet"

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
        mkdir -p /mnt/efi
        if mount "$EFI_PART" /mnt/efi 2>/dev/null; then

            # Layer 1: Standard fallback path (EFI/BOOT/BOOTX64.EFI)
            if [ -f /mnt/efi/EFI/BOOT/BOOTX64.EFI ]; then
                log "  Layer 1: EFI/BOOT/BOOTX64.EFI present (standard fallback)"
            else
                warn "  Layer 1: EFI/BOOT/BOOTX64.EFI missing!"
            fi

            # Layer 2: Microsoft bootloader path hijack
            # Some buggy firmwares (HP, some Surface) ONLY boot EFI/Microsoft/Boot/bootmgfw.efi
            mkdir -p /mnt/efi/EFI/Microsoft/Boot
            if [ -f /mnt/efi/EFI/BOOT/BOOTX64.EFI ]; then
                cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi
                log "  Layer 2: Installed to EFI/Microsoft/Boot/bootmgfw.efi"
            fi

            # Layer 3: Create proper UEFI boot entry
            if command -v efibootmgr >/dev/null 2>&1; then
                # Remove any existing PurpleOS entries
                for bootnum in $(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9]+" | sed 's/Boot//' || true); do
                    efibootmgr -b "$bootnum" -B 2>/dev/null || true
                done

                # Create new boot entry
                if efibootmgr -c -d "/dev/$TARGET" -p 1 -L "PurpleOS" -l '\EFI\BOOT\BOOTX64.EFI' 2>/dev/null; then
                    log "  Layer 3: Created UEFI boot entry 'PurpleOS'"

                    # Set as first in boot order
                    PURPLE_BOOTNUM=$(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9]+" | head -1 | sed 's/Boot//' || true)
                    if [ -n "$PURPLE_BOOTNUM" ]; then
                        CURRENT_ORDER=$(efibootmgr 2>/dev/null | grep "BootOrder:" | sed 's/BootOrder: //' || true)
                        NEW_ORDER=$(echo "$CURRENT_ORDER" | sed "s/$PURPLE_BOOTNUM,//g" | sed "s/,$PURPLE_BOOTNUM//g" | sed "s/^$PURPLE_BOOTNUM$//" || true)
                        [ -n "$NEW_ORDER" ] && NEW_ORDER="$PURPLE_BOOTNUM,$NEW_ORDER" || NEW_ORDER="$PURPLE_BOOTNUM"
                        efibootmgr -o "$NEW_ORDER" 2>/dev/null && \
                            log "  Layer 3: Set boot order to $NEW_ORDER" || \
                            warn "  Layer 3: Could not set boot order"
                    fi
                else
                    warn "  Layer 3: Could not create UEFI entry (layers 1-2 should still work)"
                fi
            fi

            umount /mnt/efi 2>/dev/null || true
            log "UEFI boot setup complete"
        else
            warn "Could not mount EFI partition for boot setup"
        fi
    fi

    log ""
    log "Installation complete!"

    # Detect if we're running in a VM
    IS_VM=false
    if [ -f /sys/class/dmi/id/product_name ]; then
        PRODUCT=$(cat /sys/class/dmi/id/product_name 2>/dev/null || echo "")
        case "$PRODUCT" in
            *"Virtual"*|*"QEMU"*|*"KVM"*|*"VMware"*|*"VirtualBox"*|*"Bochs"*)
                IS_VM=true
                log "Detected VM environment ($PRODUCT)"
                ;;
        esac
    fi
    # Also check hypervisor flag
    if grep -q "^flags.*hypervisor" /proc/cpuinfo 2>/dev/null; then
        IS_VM=true
    fi

    if [ "$IS_VM" = "true" ]; then
        # VM: brief delay then reboot
        echo ""
        echo -e "${GREEN}=================================================${NC}"
        echo -e "${GREEN}             Installation complete!              ${NC}"
        echo -e "${GREEN}=================================================${NC}"
        echo ""
        log "Rebooting in 5 seconds..."
        sleep 5
    else
        # Physical hardware: show friendly message and wait for USB removal or Enter
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
        echo "    Please remove the USB stick now."
        echo ""
        echo "    Press ENTER to restart your computer,"
        echo "    or it will restart automatically in 60 seconds."
        echo ""
        echo ""

        # Wait for Enter or timeout
        read -t 60 2>/dev/null || true
    fi

    # Reboot
    log "Rebooting..."
    sync
    reboot -f || echo b > /proc/sysrq-trigger
}

main "$@"
