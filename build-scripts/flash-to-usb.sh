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
    echo "  iso-path    Path to ISO file. Without one, you'll be asked which of"
    echo "              the newest build's ISOs to flash."
    echo ""
    echo "Drive selection:"
    echo "  Drives whitelisted in $CONFIG_FILE (one serial per line)"
    echo "  are picked automatically. Without a whitelist match, you'll be asked to"
    echo "  choose among plugged-in USB drives of 64GB or smaller; bigger drives"
    echo "  (which could be real data disks) can only be flashed when whitelisted."
    echo "  Run '$0 --list' to see connected USB drives and their serials."
    echo ""
    echo "Options:"
    echo "  --debug          Flash the newest build's debug ISO (visible boot menu)"
    echo "  --no-backup      Flash the newest build's standard ISO (no backup image copy)"
    echo "  --corrupt        Flash the newest corrupt-test ISO (made by 'just corrupt-test-iso')"
    echo "  --yes            Skip all prompts (default ISO: newest build, with-backup"
    echo "                   if present, else standard)"
    echo "  --device <dev>   Target a specific device (e.g. /dev/sdb); must still be whitelisted"
    echo "  --no-settle      Skip the post-flash QEMU boot-settle (first real boot will be slow)"
    echo "  --settle-only    Skip flashing; just boot-settle and eject an already-flashed drive"
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

# No whitelisted drive is plugged in: offer small USB drives interactively so
# a quick tinker flash needs no whitelist setup, while anything that could be
# a real data disk (over MAX_UNLISTED_BYTES) stays whitelist-only. Never used
# by non-interactive paths (--yes, --device, flash-all): those require the
# whitelist so automation can't pick a drive on its own.
select_unlisted_drive() {
    if [[ "$SKIP_CONFIRM" == true ]]; then
        log_error "No whitelisted USB drives found (--yes requires a whitelisted drive)."
        echo "Add your drive's serial to $CONFIG_FILE, or run without --yes to pick interactively."
        exit 1
    fi

    find_candidate_drives
    if [[ ${#CANDIDATE_DRIVES[@]} -eq 0 ]]; then
        log_error "No whitelisted USB drives found, and no small USB drives to offer."
        echo ""
        echo "Plug in a USB stick of 64GB or smaller, or whitelist a bigger drive:"
        echo "  Run '$0 --list' to see connected drives, then add a serial to $CONFIG_FILE"
        exit 1
    fi

    echo ""
    echo -e "${BOLD}No whitelisted drive found. USB drives of 64GB or smaller:${NC}"
    echo ""
    for i in "${!CANDIDATE_DRIVES[@]}"; do
        IFS='|' read -r dev size model serial mounted <<< "${CANDIDATE_DRIVES[$i]}"
        local flag=""
        [[ -n "$mounted" ]] && flag="  ${YELLOW}(has mounted partitions, in use?)${NC}"
        echo -e "  $((i+1))) $dev - $model ($size, serial $serial)$flag"
    done
    echo ""
    echo -e "  ${RED}${BOLD}The chosen drive will be COMPLETELY ERASED.${NC}"
    local choice
    choice="$(read_menu_choice "${#CANDIDATE_DRIVES[@]}" "Flash which drive? [1-${#CANDIDATE_DRIVES[@]}, or Enter to cancel]: ")" || exit 1
    if [[ -z "$choice" ]]; then
        log_info "Aborted."
        exit 0
    fi
    IFS='|' read -r TARGET_DEV TARGET_SIZE TARGET_MODEL TARGET_SERIAL _ <<< "${CANDIDATE_DRIVES[$((choice-1))]}"
    UNLISTED_DRIVE=true
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
        select_unlisted_drive
        return
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
        local choice
        choice="$(read_menu_choice "${#FOUND_DRIVES[@]}" "Select drive [1-${#FOUND_DRIVES[@]}]: ")" || exit 1
        if [[ -z "$choice" ]]; then
            log_error "Invalid selection"
            exit 1
        fi

        SELECTED="${FOUND_DRIVES[$((choice-1))]}"
    fi

    IFS='|' read -r TARGET_DEV TARGET_SIZE TARGET_MODEL TARGET_SERIAL <<< "$SELECTED"
}

die_no_iso() {
    log_error "No $1 found in $OUTPUT_DIR."
    echo "Run 'just build' first, or pass a path to an ISO."
    exit 1
}

# Read a 1-based menu choice for a list of $1 items; echoes the choice, or
# nothing when the user just presses Enter. Exits on invalid input.
read_menu_choice() {
    local count="$1" prompt="$2" choice
    read -p "$prompt" choice
    [[ -z "$choice" ]] && return 0
    if [[ ! "$choice" =~ ^[0-9]+$ ]] || [[ $choice -lt 1 ]] || [[ $choice -gt $count ]]; then
        log_error "Invalid selection"
        exit 1
    fi
    echo "$choice"
}

# Resolve a specific variant of the newest build, or, when it's missing, offer
# the newest older build of that variant with an explicit confirmation. Never
# silently flashes an older build.
resolve_variant() {
    local kind="$1" label
    case "$kind" in
        debug) label="debug" ;;
        *)     label="standard (no backup image)" ;;
    esac
    ISO_PATH="$(find_latest_iso "$kind")"
    [[ -n "$ISO_PATH" ]] && return 0

    local stem older
    stem="$(latest_build_stem)"
    older="$(newest_iso_of_variant "$kind")"
    if [[ -z "$stem" || -z "$older" ]]; then
        die_no_iso "$label ISO"
    fi
    log_warn "The newest build ($(basename "$stem")) has no $label ISO."
    if [[ "$SKIP_CONFIRM" == true ]]; then
        log_error "Newest $label ISO is from an OLDER build: $older"
        log_error "Refusing to pick it silently under --yes. Pass its path explicitly."
        exit 1
    fi
    echo ""
    read -p "Flash the OLDER $(basename "$older") instead? Type 'yes' to continue: " answer
    if [[ "$answer" != "yes" ]]; then
        log_info "Aborted."
        exit 0
    fi
    ISO_PATH="$older"
}

# Newest deliberately-corrupted test ISO (excluded from all normal ISO
# discovery, so it needs its own resolution path).
resolve_corrupt_iso() {
    ISO_PATH="$(ls -t "$OUTPUT_DIR"/*.corrupt-test*.iso 2>/dev/null | head -1 || true)"
    if [[ -z "$ISO_PATH" ]]; then
        log_error "No corrupt-test ISO found in $OUTPUT_DIR."
        echo "Make one with 'just corrupt-test-iso' first."
        exit 1
    fi
    local stem="${ISO_PATH%%.corrupt-test*}"
    stem="${stem%.with-backup}"
    stem="${stem%.debug}"
    if [[ "$stem" != "$(latest_build_stem)" ]]; then
        log_warn "This corrupt-test ISO comes from an OLDER build than the newest."
        log_warn "Re-run 'just corrupt-test-iso' to make one from the newest build."
    fi
}

# No ISO path and no variant flag: show the newest build's variants and ask
# point blank which one to flash.
select_iso() {
    local stem
    stem="$(latest_build_stem)"
    [[ -n "$stem" ]] || die_no_iso "ISO"

    local labels=() paths=() f
    f="$(variant_path "$stem" backup)"
    [[ -f "$f" ]] && { paths+=("$f"); labels+=("standard + backup image (recommended: install self-heals if the USB decays)"); }
    f="$(variant_path "$stem" standard)"
    [[ -f "$f" ]] && { paths+=("$f"); labels+=("standard (smaller, no backup image copy)"); }
    f="$(variant_path "$stem" debug)"
    [[ -f "$f" ]] && { paths+=("$f"); labels+=("debug (visible boot menu, verbose logs, for troubleshooting)"); }

    local version=""
    [[ -f "${paths[0]}.version" ]] && version="  [$(cat "${paths[0]}.version")]"
    echo ""
    echo -e "${BOLD}Newest build: $(basename "$stem")${version}${NC}"

    if [[ "$SKIP_CONFIRM" == true || ${#paths[@]} -eq 1 ]]; then
        ISO_PATH="${paths[0]}"
        log_info "Using ${labels[0]%% (*}: $(basename "$ISO_PATH")"
        return 0
    fi

    echo ""
    for i in "${!paths[@]}"; do
        echo "  $((i+1))) ${labels[$i]}"
        echo "       $(basename "${paths[$i]}")"
    done
    echo ""
    local choice
    choice="$(read_menu_choice "${#paths[@]}" "Flash which one? [1-${#paths[@]}, default 1]: ")" || exit 1
    [[ -n "$choice" ]] || choice=1
    ISO_PATH="${paths[$((choice-1))]}"
}

run_boot_settle() {
    local settle_log
    settle_log="$(mktemp -t purple-boot-settle.XXXXXX.log)"
    log_info "Boot-settling $TARGET_DEV in QEMU so the first real boot is fast (--no-settle to skip)..."
    if boot_settle_drive "$TARGET_DEV" "$settle_log"; then
        log_info "Boot settle complete."
    else
        log_warn "Boot settle incomplete; first real boot may be slow (QEMU log: $settle_log)"
    fi
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
    if [[ "$UNLISTED_DRIVE" == true ]]; then
        echo -e "  ${YELLOW}${BOLD}This drive is NOT in your whitelist. Double-check it's the right one.${NC}"
        echo ""
    fi
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

        # Boot the drive once in QEMU so its controller pays the one-time
        # post-write cost here; otherwise the parent's first boot is slow.
        # Skipped for flash-all children: the parent boot-settles all drives
        # in parallel after its own udev gate lifts.
        if [[ "$MANAGE_UDEV" == true && "$SKIP_SETTLE" != true ]]; then
            run_boot_settle
        fi

        # Power-cycle so the drive re-enumerates fresh on next plug-in.
        # Skipped when the caller owns the udev gate: udevadm settle would
        # deadlock against the still-paused exec queue, and the parent
        # orchestrator handles re-enumeration after all children finish.
        if [[ "$MANAGE_UDEV" == true ]]; then
            if eject_drive "$TARGET_DEV"; then
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
    local iso_kind=""
    FORCE_DEVICE=""
    MANAGE_UDEV=true
    SKIP_SETTLE=false
    SETTLE_ONLY=false
    SKIP_CONFIRM=false
    UNLISTED_DRIVE=false
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
                iso_kind=debug
                shift
                ;;
            --no-backup)
                iso_kind=standard
                shift
                ;;
            --corrupt)
                iso_kind=corrupt
                shift
                ;;
            --yes|-y)
                SKIP_CONFIRM=true
                shift
                ;;
            --device)
                FORCE_DEVICE="$2"
                shift 2
                ;;
            --no-settle)
                SKIP_SETTLE=true
                shift
                ;;
            --settle-only)
                SETTLE_ONLY=true
                shift
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

    # Determine ISO path (irrelevant when only settling an already-flashed drive)
    if [[ "$SETTLE_ONLY" != true ]]; then
        if [[ -n "${1:-}" ]]; then
            ISO_PATH="$1"
            if [[ ! -f "$ISO_PATH" ]]; then
                log_error "ISO not found: $ISO_PATH"
                exit 1
            fi
        elif [[ "$iso_kind" == corrupt ]]; then
            resolve_corrupt_iso
        elif [[ -n "$iso_kind" ]]; then
            resolve_variant "$iso_kind"
        else
            select_iso
        fi

        log_info "ISO: $ISO_PATH"
    fi

    # Load whitelist and find drives
    load_whitelist
    if [[ ${#WHITELIST[@]} -gt 0 ]]; then
        log_info "Loaded ${#WHITELIST[@]} whitelisted serial(s) from config"
    fi

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

    if [[ "$SETTLE_ONLY" == true ]]; then
        sudo -v
        run_boot_settle
        if eject_drive "$TARGET_DEV"; then
            log_info "Drive ejected. Unplug $TARGET_DEV now."
        fi
        exit 0
    fi

    if [[ "$SKIP_CONFIRM" != true ]]; then
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
