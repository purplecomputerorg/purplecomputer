#!/bin/bash
# PurpleOS Factory Installer
# Called from the parent menu's install option (parent_menu.py)
#
# This script:
# 1. Detects the internal disk (excluding USB/removable devices)
# 2. Wipes the partition table
# 3. Writes the pre-built golden image (purple-os.img.zst)
# 4. Sets up UEFI boot with multi-layer fallback strategy
# 5. Returns to caller (which handles reboot)

set -eo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Loud logging to console for debugging
log() {
    echo -e "${GREEN}[PURPLE]${NC} $1" >&2
    echo "[PURPLE] $1" >/dev/console 2>/dev/null || true
}
warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
    echo "[PURPLE WARN] $1" >/dev/console 2>/dev/null || true
}
error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    echo "[PURPLE ERROR] $1" >/dev/console 2>/dev/null || true
    exit 1
}

# Catch unexpected exits (e.g. pipeline failures from USB removal) and emit
# a tagged error so the UI can display it.
trap '_rc=$?; if [ $_rc -ne 0 ]; then echo -e "${RED}[ERROR]${NC} Install failed (exit code $_rc)" >&2; echo "[PURPLE ERROR] Install failed (exit code $_rc)" >/dev/console 2>/dev/null || true; fi' EXIT

# Golden image path - set by hook via PURPLE_PAYLOAD_DIR
GOLDEN_IMAGE="${PURPLE_PAYLOAD_DIR:-/purple}/purple-os.img.zst"

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

    # Test mode: simulate a realistic install that fails (purple.failinstall=1)
    # Exercises the progress UI, error screen, and diagnostics collection
    # without touching any disk. Boot the debug ISO's "test install failure" entry.
    if grep -q 'purple\.failinstall=1' /proc/cmdline 2>/dev/null; then
        log "TEST MODE: simulating install failure"
        log "Detecting internal disk..."
        sleep 1
        log "  Found internal disk: test0 (fake)"
        log "Target disk: /dev/test0 (128GB)"
        sleep 1
        log "Writing Purple Computer to disk..."
        log "  Source: /cdrom/purple/purple-os.img.zst"
        log "  Target: /dev/test0"
        for pct in 5 12 25 40 55 70 85; do
            sleep 1
            log "  Progress: ${pct}%"
        done
        sleep 1
        log "Reloading partition table..."
        log "Disk verification passed (SHA256 match)"
        log "Waiting for partition devices..."
        for attempt in 1 2 3 4 5 6; do
            log "  Waiting for /dev/test0p1 (attempt $attempt/6)..."
            sleep 1
        done
        warn "Partition devices did not appear."
        warn "  lsblk output:"
        warn "    test0  128G  disk"
        warn "  /proc/partitions:"
        warn "    (no partitions found)"
        error "Partition devices did not appear after writing disk image. The install may have failed."
    fi

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

    # Verify golden image exists
    if [ ! -f "$GOLDEN_IMAGE" ]; then
        error "Golden image not found: $GOLDEN_IMAGE"
    fi

    # Determine partition device naming convention
    case "$TARGET" in
        nvme*|mmcblk*) PART_PREFIX="/dev/${TARGET}p" ;;
        *)             PART_PREFIX="/dev/${TARGET}" ;;
    esac

    # ======================================================================
    # PRE-WRITE CLEANUP
    # Clear old partition state so the kernel doesn't hold stale references.
    # Without this, blockdev --rereadpt fails with EBUSY after dd because
    # the kernel thinks old partitions (e.g. macOS APFS) are still in use.
    # ======================================================================
    log "Preparing disk..."

    # Unmount any existing partitions on the target disk
    for part in $(lsblk -ln -o NAME "/dev/$TARGET" 2>/dev/null | tail -n +2); do
        umount "/dev/$part" 2>/dev/null || true
    done

    # Wipe filesystem signatures (APFS, HFS+, ext4, etc.) so the kernel
    # releases old partition references. wipefs calls BLKRRPART internally,
    # which clears the kernel's partition table cache for this disk.
    # (Note: dmsetup-based APFS/LVM cleanup is intentionally not done here.
    # libdevmapper in the live environment is version-mismatched with the
    # kernel and silently fails. The post-write GPT rebuild and wipefs
    # together cover the cases that mattered.)
    wipefs -a "/dev/$TARGET" 2>/dev/null || true

    # Let udev finish processing the wipe before we start writing
    udevadm settle --timeout=5 2>/dev/null || true

    # ======================================================================
    # WRITE GOLDEN IMAGE
    # ======================================================================
    log "Writing Purple Computer to disk..."
    log "  Source: $GOLDEN_IMAGE"
    log "  Target: /dev/$TARGET"
    log "  This will take approximately 10-15 minutes..."
    log ""

    # Decompress and write, teeing the decompressed stream to sha256sum so we
    # can verify the disk contents afterwards without decompressing again.
    # The tee sends the same bytes to both dd (disk write) and sha256sum (checksum).
    WRITE_SHA256_FILE="/tmp/purple-write-sha256"
    WRITE_SIZE_FILE="/tmp/purple-write-size"
    if command -v pv >/dev/null 2>&1; then
        zstd -dc "$GOLDEN_IMAGE" \
            | tee >(sha256sum | awk '{print $1}' > "$WRITE_SHA256_FILE") \
            | tee >(wc -c > "$WRITE_SIZE_FILE") \
            | pv -s $(zstd -l "$GOLDEN_IMAGE" 2>/dev/null | tail -1 | awk '{print $5}' || echo "2G") \
            | dd of=/dev/$TARGET bs=4M conv=fsync
    else
        zstd -dc "$GOLDEN_IMAGE" \
            | tee >(sha256sum | awk '{print $1}' > "$WRITE_SHA256_FILE") \
            | tee >(wc -c > "$WRITE_SIZE_FILE") \
            | dd of=/dev/$TARGET bs=4M status=progress conv=fsync
    fi

    # ======================================================================
    # POST-WRITE VERIFICATION
    # ======================================================================
    log "Reloading partition table..."
    sync

    if [ -f "$WRITE_SHA256_FILE" ] && [ -s "$WRITE_SHA256_FILE" ] && [ -f "$WRITE_SIZE_FILE" ] && [ -s "$WRITE_SIZE_FILE" ]; then
        WRITE_SHA256=$(cat "$WRITE_SHA256_FILE")
        WRITE_SIZE=$(cat "$WRITE_SIZE_FILE" | tr -d ' ')
        log "Verifying disk write (this takes a few minutes)..."

        # Flush hardware write caches before reading back
        blockdev --flushbufs /dev/$TARGET 2>/dev/null || true
        hdparm -F /dev/$TARGET 2>/dev/null || true
        sleep 5

        # Drop page cache, then read back with O_DIRECT
        echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
        DISK_SHA256=$(dd if=/dev/$TARGET bs=4M count="$WRITE_SIZE" iflag=direct,count_bytes status=none 2>/dev/null | sha256sum | awk '{print $1}')

        if [ "$WRITE_SHA256" = "$DISK_SHA256" ]; then
            log "Disk verification passed (SHA256 match)"
        else
            warn "Disk verification: SHA256 mismatch"
            warn "  Expected: $WRITE_SHA256"
            warn "  Got:      $DISK_SHA256"
            error "Disk write verification failed. The installation may be corrupt."
        fi
        rm -f "$WRITE_SHA256_FILE" "$WRITE_SIZE_FILE"
    else
        warn "Could not capture write checksum, skipping verification"
    fi

    # ======================================================================
    # REBUILD PARTITION TABLE
    # The golden image's GPT was written assuming 512-byte logical sectors.
    # On drives with non-512B logical sectors (e.g. Apple NVMe in MacBook
    # 2016/2017 TouchBar models, which use 4096B sectors), the kernel can't
    # find the GPT header at LBA 1 and partprobe fails. The filesystem data
    # was written at correct *byte* offsets via dd, so only the GPT metadata
    # needs to be rewritten for the actual sector size.
    #
    # We do this unconditionally on every install (one code path = robust):
    #   - On 512B drives: effectively re-asserts the same layout (cheap).
    #   - On 4K drives: writes a valid GPT for the actual sector size.
    #   - On any drive larger than the golden image: places the backup GPT
    #     header at the real end of the disk (instead of mid-disk where the
    #     image left it) and extends root to span the full drive.
    #
    # Layout MUST match 00-build-golden-image.sh exactly:
    #   ESP  fat32  1MiB - 513MiB
    #   root ext4   513MiB - 100%
    # parted uses byte-based offsets (MiB), so the same commands produce
    # correct LBAs regardless of the device's logical sector size.
    # ======================================================================
    SECTOR_SIZE=$(cat /sys/block/$TARGET/queue/logical_block_size 2>/dev/null || echo 512)
    PHYS_SECTOR_SIZE=$(cat /sys/block/$TARGET/queue/physical_block_size 2>/dev/null || echo 512)
    log "Disk sector size: logical=${SECTOR_SIZE}B physical=${PHYS_SECTOR_SIZE}B"

    log "Rebuilding partition table for this disk..."
    parted -s "/dev/$TARGET" mklabel gpt
    parted -s "/dev/$TARGET" mkpart ESP fat32 1MiB 513MiB
    parted -s "/dev/$TARGET" set 1 esp on
    parted -s "/dev/$TARGET" mkpart primary ext4 513MiB 100%
    sync

    # ======================================================================
    # PARTITION DETECTION
    # Uses partprobe (BLKPG ioctl) which adds partitions individually and
    # succeeds even when udev briefly holds a different partition open.
    # blockdev --rereadpt uses BLKRRPART which fails if ANY partition is
    # held open. This is what Ubuntu Curtin and Calamares do.
    # ======================================================================
    log "Waiting for partition devices..."
    udevadm settle --timeout=5 2>/dev/null || true

    PROBE_PART="${PART_PREFIX}1"
    PARTITION_FOUND=false
    PARTPROBE_STDERR=""

    for attempt in $(seq 1 20); do
        # Capture partprobe stderr so we can report it on final failure.
        PARTPROBE_STDERR=$(partprobe "/dev/$TARGET" 2>&1 >/dev/null) || true

        # Brief pause for kernel to create device nodes, then let udev settle
        sleep 0.2
        udevadm trigger --subsystem-match=block 2>/dev/null || true
        udevadm settle --timeout=5 2>/dev/null || true

        if [ -b "$PROBE_PART" ]; then
            PARTITION_FOUND=true
            break
        fi
        log "  Waiting for $PROBE_PART (attempt $attempt/20)..."
        sleep 1
    done

    if [ "$PARTITION_FOUND" != "true" ]; then
        warn "Partition devices did not appear."
        warn "  sector size: logical=${SECTOR_SIZE}B physical=${PHYS_SECTOR_SIZE}B"
        warn "  lsblk output:"
        lsblk "/dev/$TARGET" 2>&1 | while read -r line; do warn "    $line"; done
        warn "  /proc/partitions:"
        grep "$TARGET" /proc/partitions 2>/dev/null | while read -r line; do warn "    $line"; done
        if [ -n "$PARTPROBE_STDERR" ]; then
            warn "  last partprobe stderr:"
            echo "$PARTPROBE_STDERR" | while read -r line; do warn "    $line"; done
        fi
        error "Partition devices did not appear after writing disk image. The install may have failed."
    fi

    log "Partitions ready."

    # ======================================================================
    # GROW ROOT FILESYSTEM TO FILL PARTITION
    # The golden image's ext4 was sized to the image, not the target disk.
    # After the GPT rebuild above, the root partition spans 513MiB to end of
    # disk, but the filesystem inside is still at image size. resize2fs
    # extends it to fill the partition. e2fsck -fy is required by resize2fs
    # before an offline grow; -y is safe because we just verified the dd
    # write byte-for-byte.
    # ======================================================================
    ROOT_PART_TMP="${PART_PREFIX}2"
    log "Checking root filesystem..."
    e2fsck -fy "$ROOT_PART_TMP" || warn "e2fsck reported issues (continuing)"
    log "Growing root filesystem to fill disk..."
    resize2fs "$ROOT_PART_TMP" || warn "resize2fs failed (install will use golden-image size)"

    # ==========================================================================
    # UEFI BOOT SETUP - See CLAUDE.md "UEFI Boot and Hardware Compatibility"
    # ==========================================================================
    # Signed boot chain: shim (Microsoft-signed) → GRUB (Canonical-signed) → kernel
    # Multiple EFI paths for hardware compatibility:
    # 1. /EFI/BOOT/BOOTX64.EFI (shim) + grubx64.efi - UEFI spec fallback
    # 2. /EFI/Microsoft/Boot/bootmgfw.efi (shim) + grubx64.efi - Surface, HP
    # 3. /EFI/purple/shimx64.efi + grubx64.efi - vendor path for NVRAM entry
    # 4. NVRAM Boot#### entry - bonus for compliant firmware
    # Plus: /EFI/ubuntu/grub.cfg has search config (signed GRUB's prefix)
    # Plus: Update grub.cfg with actual UUID for deterministic boot
    # ==========================================================================

    log "Setting up UEFI boot..."

    # Partition device names (PART_PREFIX set earlier during pre-write cleanup)
    EFI_PART="${PART_PREFIX}1"
    ROOT_PART="${PART_PREFIX}2"

    # Get root UUID for deterministic boot (critical fix for multi-disk systems)
    ROOT_UUID=$(blkid -s UUID -o value "$ROOT_PART" 2>/dev/null || true)
    if [ -n "$ROOT_UUID" ]; then
        log "  Root UUID: $ROOT_UUID"
    else
        warn "  Could not get root UUID, falling back to label-based boot"
    fi

    if [ -b "$EFI_PART" ]; then
        mkdir -p /mnt/efi /mnt/root
        if mount "$EFI_PART" /mnt/efi; then

            # Layer 1: Standard fallback path (already in golden image)
            # shim (BOOTX64.EFI) loads grubx64.efi from same directory
            if [ -f /mnt/efi/EFI/BOOT/BOOTX64.EFI ] && [ -f /mnt/efi/EFI/BOOT/grubx64.efi ]; then
                log "  Layer 1: /EFI/BOOT/ shim + GRUB present"
            else
                warn "  Layer 1: signed boot files missing!"
            fi

            # Layer 2: Vendor path for NVRAM entry (shim + GRUB + MOK Manager)
            mkdir -p /mnt/efi/EFI/purple
            cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/purple/shimx64.efi 2>/dev/null || true
            cp /mnt/efi/EFI/BOOT/grubx64.efi /mnt/efi/EFI/purple/grubx64.efi 2>/dev/null || true
            cp /mnt/efi/EFI/BOOT/mmx64.efi /mnt/efi/EFI/purple/mmx64.efi 2>/dev/null || true
            log "  Layer 2: /EFI/purple/ shim + GRUB"

            # Layer 3: Microsoft path (Surface, HP need this)
            # shim as bootmgfw.efi + grubx64.efi in same directory
            WINDOWS_DETECTED=0
            if [ -f /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi ]; then
                MS_SIZE=$(stat -c%s /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi 2>/dev/null || echo 0)
                # Windows bootmgfw.efi is ~1.5-2.5MB, our shim is smaller (~1.2MB)
                if [ "$MS_SIZE" -gt 1500000 ] && [ "$MS_SIZE" -lt 2800000 ]; then
                    log "  Layer 3: Windows detected, preserving bootmgfw.efi"
                    WINDOWS_DETECTED=1
                fi
            fi
            if [ "$WINDOWS_DETECTED" -eq 0 ]; then
                mkdir -p /mnt/efi/EFI/Microsoft/Boot
                cp /mnt/efi/EFI/BOOT/BOOTX64.EFI /mnt/efi/EFI/Microsoft/Boot/bootmgfw.efi
                cp /mnt/efi/EFI/BOOT/grubx64.efi /mnt/efi/EFI/Microsoft/Boot/grubx64.efi
                cp /mnt/efi/EFI/BOOT/mmx64.efi /mnt/efi/EFI/Microsoft/Boot/mmx64.efi 2>/dev/null || true
                log "  Layer 3: /EFI/Microsoft/Boot/ shim + GRUB"
            fi

            # Layer 4: NVRAM entry (bonus, not required)
            # Points to shim, which chain-loads grubx64.efi
            if command -v efibootmgr >/dev/null 2>&1; then
                # Remove existing PurpleOS entries
                for bootnum in $(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9A-Fa-f]+" | sed 's/Boot//' || true); do
                    efibootmgr -b "$bootnum" -B 2>/dev/null || true
                done

                if efibootmgr -c -d "/dev/$TARGET" -p 1 -L "PurpleOS" -l '\EFI\purple\shimx64.efi' 2>/dev/null; then
                    log "  Layer 4: NVRAM entry created"
                    # Set boot order
                    PURPLE_BOOTNUM=$(efibootmgr 2>/dev/null | grep -i "PurpleOS" | grep -oE "Boot[0-9A-Fa-f]+" | head -1 | sed 's/Boot//')
                    if [ -n "$PURPLE_BOOTNUM" ]; then
                        CURRENT_ORDER=$(efibootmgr 2>/dev/null | grep "BootOrder:" | sed 's/BootOrder: //')
                        NEW_ORDER="$PURPLE_BOOTNUM"
                        for entry in $(echo "$CURRENT_ORDER" | tr ',' ' '); do
                            [ "$entry" != "$PURPLE_BOOTNUM" ] && NEW_ORDER="$NEW_ORDER,$entry"
                        done
                        efibootmgr -o "$NEW_ORDER" 2>/dev/null || true
                    fi
                else
                    log "  Layer 4: NVRAM entry failed (fallback paths will work)"
                fi
            fi

            # Layer 5 (EFI part): Update search config with UUID
            if [ -n "$ROOT_UUID" ] && [ -f /mnt/efi/EFI/ubuntu/grub.cfg ]; then
                sed -i "s|search --no-floppy --label PURPLE_ROOT|search --no-floppy --fs-uuid $ROOT_UUID|g" /mnt/efi/EFI/ubuntu/grub.cfg
                log "  Layer 5: Updated EFI search config with UUID"
            fi

            umount /mnt/efi 2>/dev/null || true
        else
            warn "Could not mount EFI partition"
        fi

        # Layer 5 (root part): Update grub.cfg with UUID
        if [ -n "$ROOT_UUID" ]; then
            if mount "$ROOT_PART" /mnt/root 2>/dev/null; then
                if [ -f /mnt/root/boot/grub/grub.cfg ]; then
                    sed -i "s|root=LABEL=PURPLE_ROOT|root=UUID=$ROOT_UUID|g" /mnt/root/boot/grub/grub.cfg
                    sed -i "s|search --no-floppy --label PURPLE_ROOT|search --no-floppy --fs-uuid $ROOT_UUID|g" /mnt/root/boot/grub/grub.cfg
                    log "  Layer 5: Updated root grub.cfg with UUID"
                fi
                umount /mnt/root 2>/dev/null || true
            fi
        fi

        rmdir /mnt/efi /mnt/root 2>/dev/null || true
        log "UEFI boot setup complete"
    else
        error "EFI partition not found at $EFI_PART. Cannot set up boot."
    fi

    log ""
    log "============================================"
    log "Installation complete!"
    log "============================================"

    # Prep for reboot while still running as root with USB present.
    # Python cannot do these without sudo, and sudo from within Textual hangs.
    touch /run/casper-no-prompt

    # Static reboot binary on its own tmpfs (with exec+suid).
    # Ubuntu's /run is nosuid,noexec and systemd resists remounting.
    # The binary is the ONLY thing that works after USB removal:
    # /bin/sh, Python, sudo all SIGBUS on dead overlayfs code pages.
    # With --wait it shows a message, waits for Enter, then reboots.
    mkdir -p /run/purple-reboot-mount
    mount -t tmpfs -o size=1M,exec,suid tmpfs /run/purple-reboot-mount
    if [ -f /opt/purple/bin/purple-reboot ]; then
        cp /opt/purple/bin/purple-reboot /run/purple-reboot-mount/purple-reboot
        chmod 4755 /run/purple-reboot-mount/purple-reboot
        log "Reboot binary ready"
    fi

    # Sentinel last - Python polls for this to know install is done.
    touch /run/purple-install-complete

    exit 0
}

main "$@"
