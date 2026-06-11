#!/usr/bin/env bash
# Flash PurpleOS ISO to ALL whitelisted USB drives in parallel.
# Shares one udev gate across children and streams per-drive logs to /tmp.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$SCRIPT_DIR/config.sh"
source "$SCRIPT_DIR/flash-lib.sh"
CONFIG_FILE="$PROJECT_DIR/.flash-drives.conf"
FLASH_SCRIPT="$SCRIPT_DIR/flash-to-usb.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; BOLD='\033[1m'; NC='\033[0m'
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }

usage() {
    cat <<EOF
Usage: $0 [--debug] [--yes] [iso-path]

Flash an ISO to every whitelisted USB drive currently plugged in, in parallel.

Options:
  --debug   Use the most recent .debug.iso
  --yes     Skip the confirmation prompt
  --help    Show this help
EOF
}

USE_DEBUG=false
SKIP_CONFIRM=false
ISO_PATH=""
while [[ -n "${1:-}" ]]; do
    case "$1" in
        --help|-h)  usage; exit 0 ;;
        --debug|-d) USE_DEBUG=true; shift ;;
        --yes|-y)   SKIP_CONFIRM=true; shift ;;
        *)          ISO_PATH="$1"; shift ;;
    esac
done

if [[ -z "$ISO_PATH" ]]; then
    if [[ "$USE_DEBUG" == true ]]; then
        ISO_PATH="$(find_latest_iso debug)"
    else
        ISO_PATH="$(find_latest_iso)"
    fi
fi
if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
    log_error "No ISO found. Build one first or pass a path."
    exit 1
fi

# Verify the ISO once against its build checksum before flashing every drive,
# then hand the verified hash to children so they skip re-hashing 6GB apiece.
log_info "Verifying ISO against build checksum..."
VERIFIED_ISO_SHA256="$(verify_iso_checksum "$ISO_PATH")" || exit 1
export VERIFIED_ISO_SHA256
init_manifest
log_info "ISO checksum OK."

load_whitelist
find_whitelisted_drives

if [[ ${#FOUND_DRIVES[@]} -eq 0 ]]; then
    log_error "No whitelisted USB drives found."
    exit 1
fi

echo
echo -e "${BOLD}${YELLOW}Will flash $(basename "$ISO_PATH") to ${#FOUND_DRIVES[@]} drive(s) in parallel:${NC}"
for entry in "${FOUND_DRIVES[@]}"; do
    IFS='|' read -r dev size model serial <<< "$entry"
    printf "  %-10s %-8s %-22s %s\n" "$dev" "$size" "$model" "$serial"
done
echo -e "  ${RED}${BOLD}ALL DATA ON THESE DRIVES WILL BE DESTROYED${NC}"
echo

if [[ "$SKIP_CONFIRM" != true ]]; then
    read -p "Type 'yes' to continue: " confirm
    [[ "$confirm" == "yes" ]] || { log_info "Aborted."; exit 0; }
fi

# Prime sudo and keep the timestamp fresh for the duration of the run, so
# children don't hit a password prompt mid-dd on long parallel flashes.
sudo -v
( while true; do sudo -n -v 2>/dev/null || exit; sleep 60; done ) &
SUDO_KEEPALIVE_PID=$!

log_info "Pausing udev exec queue..."
sudo udevadm control --stop-exec-queue 2>/dev/null || true
cleanup() {
    kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
    sudo udevadm control --start-exec-queue 2>/dev/null || true
}
trap cleanup EXIT INT TERM

LOG_DIR="$(mktemp -d -t purple-flash-all.XXXXXX)"
log_info "Per-drive logs: $LOG_DIR"
echo

PIDS=()
DEVS=()
for entry in "${FOUND_DRIVES[@]}"; do
    IFS='|' read -r dev _ _ _ <<< "$entry"
    logfile="$LOG_DIR/$(basename "$dev").log"
    echo -e "${BOLD}→ Starting flash for $dev (tail -f $logfile)${NC}"
    "$FLASH_SCRIPT" --yes --no-udev-gate --device "$dev" \
        $([[ "$USE_DEBUG" == true ]] && echo --debug) \
        "$ISO_PATH" >"$logfile" 2>&1 &
    PIDS+=($!)
    DEVS+=("$dev")
done

echo
log_info "All flashes started. Waiting for completion..."
echo

FAILED=()
for i in "${!PIDS[@]}"; do
    if wait "${PIDS[$i]}"; then
        echo -e "${GREEN}✓${NC} ${DEVS[$i]} — verified"
    else
        echo -e "${RED}✗${NC} ${DEVS[$i]} — FAILED (see $LOG_DIR/$(basename "${DEVS[$i]}").log)"
        FAILED+=("${DEVS[$i]}")
    fi
done

echo
# Lift the gate before ejecting so udevadm settle can drain.
sudo udevadm control --start-exec-queue 2>/dev/null || true

# Re-enumerate and eject each verified drive (same pass single flashes do).
for i in "${!DEVS[@]}"; do
    dev="${DEVS[$i]}"
    [[ " ${FAILED[*]} " == *" $dev "* ]] && continue
    sudo blockdev --rereadpt "$dev" 2>/dev/null || true
    sudo partprobe "$dev" 2>/dev/null || true
done
sudo udevadm settle 2>/dev/null || true
for i in "${!DEVS[@]}"; do
    dev="${DEVS[$i]}"
    [[ " ${FAILED[*]} " == *" $dev "* ]] && continue
    sudo udisksctl power-off --block-device "$dev" 2>/dev/null \
        || sudo eject "$dev" 2>/dev/null \
        || true
done

echo
log_info "QA manifest: $(manifest_path)"
if [[ ${#FAILED[@]} -eq 0 ]]; then
    echo -e "${BOLD}${GREEN}All ${#FOUND_DRIVES[@]} drives flashed and verified. Unplug them now.${NC}"
    exit 0
else
    echo -e "${BOLD}${RED}${#FAILED[@]} of ${#FOUND_DRIVES[@]} drive(s) failed: ${FAILED[*]}${NC}"
    exit 1
fi
