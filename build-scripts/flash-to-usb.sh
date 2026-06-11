#!/usr/bin/env bash
# Flash PurpleOS ISO to a whitelisted USB drive
# Usage: ./flash-to-usb.sh [iso-path]

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
CONFIG_FILE="$PROJECT_DIR/.flash-drives.conf"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

usage() {
    echo "Usage: $0 [options] [iso-path]"
    echo ""
    echo "Flash PurpleOS ISO to a whitelisted USB drive."
    echo ""
    echo "Arguments:"
    echo "  iso-path    Path to ISO file (default: most recent in $OUTPUT_DIR)"
    echo ""
    echo "Configuration:"
    echo "  Whitelisted drive serials are read from: $CONFIG_FILE"
    echo "  Create this file with one serial number per line."
    echo "  Run '$0 --list' to see connected USB drives and their serials."
    echo ""
    echo "Options:"
    echo "  --debug          Flash the debug ISO (.debug.iso) instead"
    echo "  --yes            Skip the confirmation prompt"
    echo "  --device <dev>   Target a specific device (e.g. /dev/sdb); must still be whitelisted"
    echo "  --no-udev-gate   Skip udev stop/start (caller manages the gate; used by flash-all)"
    echo "  --list           List all USB drives (for finding serial numbers)"
    echo "  --help           Show this help"
}

list_usb_drives() {
    echo -e "${BOLD}Connected USB drives:${NC}"
    echo ""
    printf "%-10s %-8s %-12s %-22s %-25s %s\n" "DEVICE" "SIZE" "VENDOR" "MODEL" "SERIAL" "RM"
    echo "----------------------------------------------------------------------------------------------------"

    while IFS= read -r line; do
        eval "$line"

        [[ "$TRAN" != "usb" ]] && continue
        [[ -z "$NAME" ]] && continue

        local vendor
        vendor=$(echo "$VENDOR" | xargs)
        rm_text="no"
        [[ "$RM" == "1" ]] && rm_text="yes"

        printf "%-10s %-8s %-12s %-22s %-25s %s\n" "/dev/$NAME" "$SIZE" "$vendor" "$MODEL" "$SERIAL" "$rm_text"
    done < <(lsblk -d -n -o NAME,SIZE,TRAN,VENDOR,MODEL,RM,SERIAL -P 2>/dev/null)

    echo ""
    echo "To whitelist a drive, add to $CONFIG_FILE:"
    echo "  - the SERIAL on its own line (exact match), OR"
    echo "  - 'model:VENDOR/MODEL max=20G' (matches any drive of that vendor+model)"
}

select_drive() {
    if [[ -n "$FORCE_DEVICE" ]]; then
        for entry in "${FOUND_DRIVES[@]}"; do
            IFS='|' read -r dev _ _ _ <<< "$entry"
            if [[ "$dev" == "$FORCE_DEVICE" ]]; then
                SELECTED="$entry"
                IFS='|' read -r TARGET_DEV TARGET_SIZE TARGET_MODEL TARGET_SERIAL <<< "$SELECTED"
                return
            fi
        done
        log_error "$FORCE_DEVICE is not a whitelisted USB drive."
        exit 1
    fi

    if [[ ${#FOUND_DRIVES[@]} -eq 0 ]]; then
        log_error "No whitelisted USB drives found!"
        echo ""
        echo "Either:"
        echo "  1. Plug in a whitelisted drive"
        echo "  2. Add your drive's serial to $CONFIG_FILE"
        echo ""
        echo "Run '$0 --list' to see connected drives."
        exit 1
    fi

    if [[ ${#FOUND_DRIVES[@]} -eq 1 ]]; then
        SELECTED="${FOUND_DRIVES[0]}"
    else
        echo -e "${BOLD}Multiple whitelisted drives found:${NC}"
        echo ""
        for i in "${!FOUND_DRIVES[@]}"; do
            IFS='|' read -r dev size model serial <<< "${FOUND_DRIVES[$i]}"
            echo "  $((i+1))) $dev - $model ($size)"
        done
        echo ""
        read -p "Select drive [1-${#FOUND_DRIVES[@]}]: " choice

        if [[ ! "$choice" =~ ^[0-9]+$ ]] || [[ $choice -lt 1 ]] || [[ $choice -gt ${#FOUND_DRIVES[@]} ]]; then
            log_error "Invalid selection"
            exit 1
        fi

        SELECTED="${FOUND_DRIVES[$((choice-1))]}"
    fi

    IFS='|' read -r TARGET_DEV TARGET_SIZE TARGET_MODEL TARGET_SERIAL <<< "$SELECTED"
}

confirm_write() {
    echo ""
    echo -e "${BOLD}${YELLOW}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${YELLOW}║                    CONFIRM USB WRITE                       ║${NC}"
    echo -e "${BOLD}${YELLOW}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Source:${NC}  $ISO_PATH"
    echo -e "  ${BOLD}Target:${NC}  $TARGET_DEV"
    echo -e "  ${BOLD}Model:${NC}   $TARGET_MODEL"
    echo -e "  ${BOLD}Size:${NC}    $TARGET_SIZE"
    echo -e "  ${BOLD}Serial:${NC}  $TARGET_SERIAL"
    echo ""
    echo -e "  ${RED}${BOLD}ALL DATA ON $TARGET_DEV WILL BE DESTROYED${NC}"
    echo ""
    read -p "Type 'yes' to continue: " confirm

    if [[ "$confirm" != "yes" ]]; then
        log_info "Aborted."
        exit 0
    fi
}

write_iso() {
    # Prompt for sudo once up front so a slow dd doesn't hit a mid-op password
    # prompt (with oflag=sync the write can take several minutes).
    sudo -v

    log_info "Unmounting any partitions on $TARGET_DEV..."
    for part in "${TARGET_DEV}"*; do
        sudo umount "$part" 2>/dev/null || true
    done

    # Block udev rule execution (incl. udisks2 auto-mount) during the flash.
    # Without this, udisks mounts FAT/ISO9660 partitions from the freshly-
    # written ISO between write and readback; mount-time FAT metadata writes
    # then corrupt the bytes our verification reads. trap guarantees udev is
    # re-enabled on any exit path.
    if [[ "$MANAGE_UDEV" == true ]]; then
        sudo udevadm control --stop-exec-queue 2>/dev/null || true
        trap 'sudo udevadm control --start-exec-queue 2>/dev/null || true' EXIT INT TERM
    fi

    # Get ISO details
    local iso_filename iso_size_human iso_size_bytes iso_modified iso_sha256
    iso_filename="$(basename "$ISO_PATH")"
    iso_size_human="$(du -h "$ISO_PATH" | cut -f1)"
    iso_size_bytes="$(stat -c '%s' "$ISO_PATH")"
    iso_modified="$(stat -c '%y' "$ISO_PATH" | cut -d'.' -f1)"

    # Reuse the hash verified at pre-flight (computed this run, checked against
    # the build sidecar), or inherited from flash-all's one-time check, so we
    # don't re-hash a 6GB ISO per drive. Fall back to computing it if unset.
    if [[ -n "${VERIFIED_ISO_SHA256:-}" ]]; then
        iso_sha256="$VERIFIED_ISO_SHA256"
    else
        log_info "Computing source ISO checksum..."
        iso_sha256="$(sha256sum "$ISO_PATH" | awk '{print $1}')"
    fi

    echo ""
    log_info "Writing ISO to $TARGET_DEV..."
    echo ""

    # oflag=sync: each write() is synchronous to the block layer, so data
    # is committed per-block instead of buffered and flushed as a burst at
    # end. Significantly more reliable on cheap USB drives whose firmware
    # buffers can lie about fast completions.
    sudo dd if="$ISO_PATH" of="$TARGET_DEV" bs=4M status=progress conv=fsync oflag=sync

    log_info "Syncing..."
    sync
    # BLKFLSBUF flushes kernel block-device buffers and, on modern kernels,
    # issues a device-level flush. We don't call hdparm -F: it sends ATA
    # commands that USB mass-storage bridges don't pass through, so it's a
    # silent no-op on USB drives.
    sudo blockdev --flushbufs "$TARGET_DEV" 2>/dev/null || true
    sleep 10

    # Verification: read back from USB and compare SHA256.
    # On mismatch, retry once with a longer flush delay before failing.
    local usb_sha256=""
    local verify_passed=false

    for verify_attempt in 1 2; do
        echo ""
        if [[ $verify_attempt -eq 1 ]]; then
            log_info "Verifying write (reading back from USB)..."
        else
            log_warn "First verification failed, retrying with extended flush..."
            sudo blockdev --flushbufs "$TARGET_DEV" 2>/dev/null || true
            sleep 15
        fi
        echo ""

        # Defense in depth: re-unmount anything that slipped past the udev
        # block (e.g. an event queued before stop-exec-queue took effect).
        for part in "${TARGET_DEV}"*; do
            sudo umount "$part" 2>/dev/null || true
        done

        # Drop kernel page cache so readback hits the device, not RAM.
        sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true

        # Read back with O_DIRECT to bypass page cache entirely.
        # iflag=count_bytes: interpret count as bytes (not blocks), so we read
        #   exactly iso_size_bytes without needing head -c in a pipeline (which
        #   could cause SIGPIPE issues with dd).
        usb_sha256="$(sudo dd if="$TARGET_DEV" bs=4M count="$iso_size_bytes" iflag=direct,count_bytes status=none 2>/dev/null | sha256sum | awk '{print $1}')"

        if [[ "$iso_sha256" == "$usb_sha256" ]]; then
            verify_passed=true
            break
        fi

        if [[ $verify_attempt -eq 1 ]]; then
            log_warn "Checksum mismatch on first read (may be cache lag)"
        fi
    done

    echo ""

    if [[ "$verify_passed" == true ]]; then
        record_manifest pass "$TARGET_DEV" "$TARGET_SERIAL" "$TARGET_MODEL" "$TARGET_SIZE" "$iso_filename" "$iso_sha256"
        echo -e "${BOLD}${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${BOLD}${GREEN}║                 FLASH COMPLETE - VERIFIED                  ║${NC}"
        echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${BOLD}ISO File:${NC}     $iso_filename"
        echo -e "  ${BOLD}ISO Size:${NC}     $iso_size_human"
        echo -e "  ${BOLD}ISO Modified:${NC} $iso_modified"
        echo ""
        echo -e "  ${BOLD}Source SHA256:${NC}"
        echo -e "    $iso_sha256"
        echo -e "  ${BOLD}USB SHA256:${NC}"
        echo -e "    $usb_sha256"
        echo ""
        echo -e "  ${GREEN}${BOLD}✓ VERIFICATION PASSED${NC}"
        echo ""
        echo -e "  ${BOLD}Target:${NC}       $TARGET_DEV ($TARGET_MODEL)"
        echo ""

        # Re-enable udev now that verification is done. udisksctl below needs
        # a running udisks2 daemon, which is driven by udev events.
        if [[ "$MANAGE_UDEV" == true ]]; then
            sudo udevadm control --start-exec-queue 2>/dev/null || true
            trap - EXIT INT TERM
        fi

        # Power-cycle the drive: kernel re-reads partition table, then udisks
        # detaches the device. Some USB controllers (e.g. Verbatim) won't boot
        # unless they re-enumerate fresh on next plug-in; this is what GNOME's
        # "safely eject" and balenaEtcher do at the end of a flash.
        # Skipped when the caller owns the udev gate: settle would deadlock
        # against the still-paused exec queue, and the parent orchestrator
        # handles re-enumeration after all children finish.
        if [[ "$MANAGE_UDEV" == true ]]; then
            sudo blockdev --rereadpt "$TARGET_DEV" 2>/dev/null || true
            sudo partprobe "$TARGET_DEV" 2>/dev/null || true
            sudo udevadm settle
            if sudo udisksctl power-off --block-device "$TARGET_DEV" 2>/dev/null; then
                log_info "Drive ejected."
            elif sudo eject "$TARGET_DEV" 2>/dev/null; then
                log_info "Drive ejected."
            else
                log_warn "Could not power-off or eject (udisksctl/eject unavailable)."
            fi
            echo ""
            echo -e "  ${BOLD}${YELLOW}→ Unplug $TARGET_DEV now.${NC}"
            echo -e "    To flash another drive, plug it back in first (or a different drive)."
        fi
    else
        echo -e "${BOLD}${RED}╔════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${BOLD}${RED}║                 VERIFICATION FAILED                        ║${NC}"
        echo -e "${BOLD}${RED}╚════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${BOLD}Source SHA256:${NC}"
        echo -e "    $iso_sha256"
        echo -e "  ${BOLD}USB SHA256:${NC}"
        echo -e "    $usb_sha256"
        echo ""
        echo -e "  ${RED}${BOLD}✗ CHECKSUMS DO NOT MATCH${NC}"
        echo ""

        # Diagnostics to localize the failure. Each check produces a distinct
        # signature: prefix mismatch = write is fundamentally broken; prefix
        # matches but full doesn't = timing/race/auto-mount corruption; I/O
        # errors in dmesg = hardware or USB-bus trouble.
        log_warn "Running diagnostics..."
        echo ""

        local iso_1mb_sha usb_1mb_sha_direct usb_1mb_sha_buffered
        iso_1mb_sha="$(head -c 1048576 "$ISO_PATH" | sha256sum | awk '{print $1}')"
        sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true
        usb_1mb_sha_direct="$(sudo dd if="$TARGET_DEV" bs=1M count=1 iflag=direct status=none 2>/dev/null | sha256sum | awk '{print $1}')"
        sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true
        usb_1mb_sha_buffered="$(sudo dd if="$TARGET_DEV" bs=1M count=1 status=none 2>/dev/null | sha256sum | awk '{print $1}')"

        echo -e "  ${BOLD}First-1MB comparison:${NC}"
        echo -e "    ISO:              $iso_1mb_sha"
        echo -e "    USB (O_DIRECT):   $usb_1mb_sha_direct"
        echo -e "    USB (buffered):   $usb_1mb_sha_buffered"
        if [[ "$iso_1mb_sha" == "$usb_1mb_sha_direct" ]]; then
            echo -e "    ${GREEN}→ First 1MB MATCHES${NC} (write started correctly; divergence is later)"
        elif [[ "$usb_1mb_sha_direct" != "$usb_1mb_sha_buffered" ]]; then
            echo -e "    ${YELLOW}→ O_DIRECT and buffered reads DIFFER${NC} (cache/coherence issue)"
        else
            echo -e "    ${RED}→ First 1MB DIFFERS${NC} (write fundamentally broken or wrong device)"
        fi
        echo ""

        echo -e "  ${BOLD}Drive info:${NC}"
        lsblk -d -n -o NAME,SIZE,TRAN,VENDOR,MODEL,SERIAL,PHY-SEC,LOG-SEC "$TARGET_DEV" 2>&1 | sed 's/^/    /'
        echo ""

        echo -e "  ${BOLD}Current mounts on ${TARGET_DEV}*:${NC}"
        findmnt -rn -o TARGET,SOURCE,FSTYPE 2>/dev/null | awk -v d="$TARGET_DEV" '$2 ~ d {print "    " $0}' || echo "    (none)"
        echo ""

        echo -e "  ${BOLD}Recent kernel messages for $(basename "$TARGET_DEV"):${NC}"
        sudo dmesg -T 2>/dev/null | grep -iE "$(basename "$TARGET_DEV")|usb.*(error|reset|disconnect)" | tail -10 | sed 's/^/    /' || echo "    (none)"
        echo ""

        record_manifest fail "$TARGET_DEV" "$TARGET_SERIAL" "$TARGET_MODEL" "$TARGET_SIZE" "$iso_filename" "$usb_sha256"
        log_error "The USB drive may be faulty or the write failed."
        log_error "Do NOT use this drive for installation."
        exit 1
    fi
}

main() {
    # Handle options
    local use_debug=false
    local skip_confirm=false
    FORCE_DEVICE=""
    MANAGE_UDEV=true
    while [[ -n "${1:-}" ]]; do
        case "$1" in
            --help|-h)
                usage
                exit 0
                ;;
            --list|-l)
                list_usb_drives
                exit 0
                ;;
            --debug|-d)
                use_debug=true
                shift
                ;;
            --yes|-y)
                skip_confirm=true
                shift
                ;;
            --device)
                FORCE_DEVICE="$2"
                shift 2
                ;;
            --no-udev-gate)
                MANAGE_UDEV=false
                shift
                ;;
            *)
                break
                ;;
        esac
    done

    # Determine ISO path
    if [[ -n "${1:-}" ]]; then
        ISO_PATH="$1"
    elif [[ "$use_debug" == true ]]; then
        ISO_PATH="$(find_latest_iso debug)"
        if [[ -z "$ISO_PATH" ]]; then
            log_error "No debug ISO found in $OUTPUT_DIR"
            echo "Run build-in-docker.sh first to generate a .debug.iso."
            exit 1
        fi
    else
        ISO_PATH="$(find_latest_iso)"
        if [[ -z "$ISO_PATH" ]]; then
            log_error "No ISO found in $OUTPUT_DIR"
            echo "Run build-in-docker.sh first, or specify path to ISO."
            exit 1
        fi
    fi

    if [[ ! -f "$ISO_PATH" ]]; then
        log_error "ISO not found: $ISO_PATH"
        echo "Run build-in-docker.sh first, or specify path to ISO."
        exit 1
    fi

    log_info "ISO: $ISO_PATH"

    # Load whitelist and find drives
    load_whitelist
    log_info "Loaded ${#WHITELIST[@]} whitelisted serial(s) from config"

    find_whitelisted_drives
    select_drive

    # Post-eject drives linger in /dev as media-less nodes until re-plugged.
    # Catch this here so we fail with a useful message instead of a cryptic
    # "No medium found" partway through dd.
    if ! sudo blockdev --getsize64 "$TARGET_DEV" >/dev/null 2>&1; then
        log_error "$TARGET_DEV has no medium."
        log_error "The drive was ejected by a previous flash. Unplug it and plug it back in, then re-run."
        exit 1
    fi

    if [[ "$skip_confirm" != true ]]; then
        confirm_write
    fi

    # Verify ISO identity only after the user commits, so the prompt is instant
    # rather than stalled behind a multi-GB hash. Still before any destructive
    # write. Skipped for flash-all children (--no-udev-gate): the parent
    # verifies once and passes the hash down via the exported VERIFIED_ISO_SHA256.
    if [[ "$MANAGE_UDEV" == true ]]; then
        VERIFIED_ISO_SHA256="$(verify_iso_checksum "$ISO_PATH")" || exit 1
        init_manifest
    fi

    write_iso
}

main "$@"
