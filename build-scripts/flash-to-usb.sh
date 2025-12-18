#!/usr/bin/env bash
# Flash PurpleOS ISO to a whitelisted USB drive
# Usage: ./flash-to-usb.sh [iso-path]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="/opt/purple-installer/output"
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

# Maximum size in GB for safety (reject anything larger)
MAX_SIZE_GB=256

find_latest_iso() {
    # Find most recent ISO in output directory
    if [[ -d "$OUTPUT_DIR" ]]; then
        ls -t "$OUTPUT_DIR"/purple-*.iso 2>/dev/null | head -1
    fi
}

usage() {
    echo "Usage: $0 [iso-path]"
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
    echo "  --list      List all USB drives (for finding serial numbers)"
    echo "  --help      Show this help"
}

list_usb_drives() {
    echo -e "${BOLD}Connected USB drives:${NC}"
    echo ""
    printf "%-10s %-10s %-30s %-25s %s\n" "DEVICE" "SIZE" "MODEL" "SERIAL" "REMOVABLE"
    echo "--------------------------------------------------------------------------------------------"

    while IFS= read -r line; do
        # Parse KEY="VALUE" format from lsblk -P
        eval "$line"

        [[ "$TRAN" != "usb" ]] && continue
        [[ -z "$NAME" ]] && continue

        rm_text="no"
        [[ "$RM" == "1" ]] && rm_text="yes"

        printf "%-10s %-10s %-30s %-25s %s\n" "/dev/$NAME" "$SIZE" "$MODEL" "$SERIAL" "$rm_text"
    done < <(lsblk -d -n -o NAME,SIZE,TRAN,MODEL,RM,SERIAL -P 2>/dev/null)

    echo ""
    echo "To whitelist a drive, add its SERIAL to: $CONFIG_FILE"
}

load_whitelist() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_error "Config file not found: $CONFIG_FILE"
        echo ""
        echo "Create this file with one drive serial per line."
        echo "Example:"
        echo "  echo 'YOUR_DRIVE_SERIAL' > $CONFIG_FILE"
        echo ""
        echo "Run '$0 --list' to see connected drives and their serials."
        exit 1
    fi

    # Read non-empty, non-comment lines
    WHITELIST=()
    while IFS= read -r line; do
        # Skip empty lines and comments
        [[ -z "$line" ]] && continue
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace
        line=$(echo "$line" | xargs)
        [[ -n "$line" ]] && WHITELIST+=("$line")
    done < "$CONFIG_FILE"

    if [[ ${#WHITELIST[@]} -eq 0 ]]; then
        log_error "No drive serials found in $CONFIG_FILE"
        exit 1
    fi
}

find_whitelisted_drives() {
    FOUND_DRIVES=()

    while IFS= read -r line; do
        # Parse KEY="VALUE" format from lsblk -P
        eval "$line"

        # Must be USB
        [[ "$TRAN" != "usb" ]] && continue
        [[ -z "$SERIAL" ]] && continue

        # Check if serial is whitelisted
        for ws in "${WHITELIST[@]}"; do
            if [[ "$SERIAL" == "$ws" ]]; then
                # Parse size and check against max
                size_num=$(echo "$SIZE" | sed 's/[^0-9.]//g')
                size_unit=$(echo "$SIZE" | sed 's/[0-9.]//g')

                size_gb=0
                case "$size_unit" in
                    G) size_gb=$(echo "$size_num" | awk '{printf "%.0f", $1}') ;;
                    T) size_gb=$(echo "$size_num" | awk '{printf "%.0f", $1 * 1024}') ;;
                    M) size_gb=0 ;;  # Less than 1GB is fine
                esac

                if [[ $size_gb -gt $MAX_SIZE_GB ]]; then
                    log_warn "Skipping /dev/$NAME ($SIZE) - exceeds ${MAX_SIZE_GB}GB safety limit"
                    continue
                fi

                FOUND_DRIVES+=("/dev/$NAME|$SIZE|$MODEL|$SERIAL")
                break
            fi
        done
    done < <(lsblk -d -n -o NAME,SIZE,TRAN,MODEL,SERIAL -P 2>/dev/null)
}

select_drive() {
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
    log_info "Unmounting any partitions on $TARGET_DEV..."
    for part in "${TARGET_DEV}"*; do
        if mountpoint -q "$part" 2>/dev/null || mount | grep -q "^$part "; then
            sudo umount "$part" 2>/dev/null || true
        fi
    done

    # Get ISO details
    local iso_filename iso_size_human iso_size_bytes iso_modified iso_sha256
    iso_filename="$(basename "$ISO_PATH")"
    iso_size_human="$(du -h "$ISO_PATH" | cut -f1)"
    iso_size_bytes="$(stat -c '%s' "$ISO_PATH")"
    iso_modified="$(stat -c '%y' "$ISO_PATH" | cut -d'.' -f1)"

    # Get or calculate source SHA256
    log_info "Calculating source ISO checksum..."
    if [[ -f "${ISO_PATH}.sha256" ]]; then
        iso_sha256="$(cat "${ISO_PATH}.sha256" | awk '{print $1}')"
        log_info "Using cached checksum from ${iso_filename}.sha256"
    else
        iso_sha256="$(sha256sum "$ISO_PATH" | awk '{print $1}')"
    fi

    echo ""
    log_info "Writing ISO to $TARGET_DEV..."
    echo ""

    # Use dd with progress
    sudo dd if="$ISO_PATH" of="$TARGET_DEV" bs=4M status=progress conv=fsync

    log_info "Syncing..."
    sync

    # Verification step - read back and compare
    echo ""
    log_info "Verifying write (reading back from USB)..."
    echo ""

    # Drop caches to ensure we read from disk, not memory
    sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null || true

    # Read back exactly iso_size_bytes from the USB and calculate SHA256
    local usb_sha256
    usb_sha256="$(sudo dd if="$TARGET_DEV" bs=4M count=$(( (iso_size_bytes + 4194303) / 4194304 )) status=progress 2>/dev/null | head -c "$iso_size_bytes" | sha256sum | awk '{print $1}')"

    echo ""

    # Compare checksums
    if [[ "$iso_sha256" == "$usb_sha256" ]]; then
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
        log_info "You can safely remove $TARGET_DEV"
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
        log_error "The USB drive may be faulty or the write failed."
        log_error "Do NOT use this drive for installation."
        exit 1
    fi
}

main() {
    # Handle options
    case "${1:-}" in
        --help|-h)
            usage
            exit 0
            ;;
        --list|-l)
            list_usb_drives
            exit 0
            ;;
    esac

    # Determine ISO path
    if [[ -n "${1:-}" ]]; then
        ISO_PATH="$1"
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
    confirm_write
    write_iso
}

main "$@"
