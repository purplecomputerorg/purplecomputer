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
  --debug       Use the most recent .debug.iso
  --yes         Skip the confirmation prompt
  --no-settle   Skip the post-flash QEMU boot-settle (faster, but the first
                live boot on each drive will be slow)
  --help        Show this help
EOF
}

USE_DEBUG=false
SKIP_CONFIRM=false
SKIP_SETTLE=false
ISO_PATH=""
while [[ -n "${1:-}" ]]; do
    case "$1" in
        --help|-h)    usage; exit 0 ;;
        --debug|-d)   USE_DEBUG=true; shift ;;
        --yes|-y)     SKIP_CONFIRM=true; shift ;;
        --no-settle)  SKIP_SETTLE=true; shift ;;
        *)            ISO_PATH="$1"; shift ;;
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

# Verify the ISO against its build checksum once the user commits, then hand the
# verified hash to children so they skip re-hashing 6GB apiece. After the prompt
# so it doesn't stall confirmation; still before any drive is written.
VERIFIED_ISO_SHA256="$(verify_iso_checksum "$ISO_PATH")" || exit 1
export VERIFIED_ISO_SHA256
init_manifest
log_info "ISO checksum OK."

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

# Boot-settle: boot each verified drive once in QEMU, in parallel, so its
# controller pays the one-time post-write cost here instead of on the parent's
# first boot. A dd read pass did not clear that state; a real boot does (see
# guides/usb-flash-settle.md).
SETTLE_PIDS=()
SETTLE_DEVS=()
for i in "${!DEVS[@]}"; do
    dev="${DEVS[$i]}"
    [[ " ${FAILED[*]} " == *" $dev "* ]] && continue
    [[ "$SKIP_SETTLE" == true ]] && continue
    boot_settle_drive "$dev" "$LOG_DIR/$(basename "$dev").boot-settle.log" &
    SETTLE_PIDS+=("$!")
    SETTLE_DEVS+=("$dev")
done
if [[ ${#SETTLE_PIDS[@]} -gt 0 ]]; then
    log_info "Boot-settling ${#SETTLE_PIDS[@]} drive(s) in QEMU so the first real boot is fast (--no-settle to skip). Takes a few minutes, walk away."
    for i in "${!SETTLE_PIDS[@]}"; do
        if wait "${SETTLE_PIDS[$i]}"; then
            echo -e "${GREEN}✓${NC} ${SETTLE_DEVS[$i]}: boot-settled"
        else
            echo -e "${YELLOW}!${NC} ${SETTLE_DEVS[$i]}: boot settle incomplete, first real boot may be slow (log: $LOG_DIR/$(basename "${SETTLE_DEVS[$i]}").boot-settle.log)"
        fi
    done
fi

# Re-enumerate and eject each verified drive (same pass single flashes do).
for i in "${!DEVS[@]}"; do
    dev="${DEVS[$i]}"
    [[ " ${FAILED[*]} " == *" $dev "* ]] && continue
    eject_drive "$dev" || true
done

echo
log_info "QA manifest: $(manifest_path)"

# Report which software build just went onto these drives, so I can tie a shipped
# batch to a git hash without digging through the manifest. Uses the currently
# checked-out commit (build-then-flash means HEAD matches the ISO).
SUCCEEDED=$(( ${#DEVS[@]} - ${#FAILED[@]} ))
if [[ $SUCCEEDED -gt 0 ]]; then
    # Prefer the version baked into the ISO (build-<hash>-<date>, from the .version
    # sidecar 01-remaster-iso.sh writes next to the ISO): that's the commit the
    # software was actually built from. Fall back to the checked-out commit only
    # for older ISOs with no sidecar, which may be AHEAD of what's on the drive.
    FLASH_VERSION=""; FLASH_SHORT=""; FLASH_FULL=""; FLASH_BRANCH=""; FLASH_SRC=""
    if [[ -f "${ISO_PATH}.version" ]]; then
        FLASH_VERSION="$(tr -d '[:space:]' < "${ISO_PATH}.version")"
        FLASH_SRC="iso"
        if [[ "$FLASH_VERSION" == build-*-* ]]; then
            _v="${FLASH_VERSION#build-}"; FLASH_SHORT="${_v%-*}"  # strip build- prefix and -date suffix
        else
            FLASH_SHORT="$FLASH_VERSION"
        fi
        FLASH_FULL="$(git -C "$PROJECT_DIR" rev-parse "$FLASH_SHORT" 2>/dev/null || true)"
    else
        FLASH_SHORT="$(git -C "$PROJECT_DIR" rev-parse --short HEAD 2>/dev/null || true)"
        FLASH_FULL="$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || true)"
        FLASH_BRANCH="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
        FLASH_VERSION="$FLASH_SHORT"
        FLASH_SRC="head"
    fi
    if [[ -n "$FLASH_SHORT" ]]; then
        echo
        echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        if [[ "$FLASH_SRC" == "iso" ]]; then
            echo -e "${BOLD}  Flashed software: ${FLASH_SHORT}${NC}  (from ISO, ${SUCCEEDED} drive(s))"
            echo -e "  build: ${FLASH_VERSION}"
            [[ -n "$FLASH_FULL" ]] && echo -e "  full: ${FLASH_FULL}"
        else
            echo -e "${BOLD}  Flashed software: ${FLASH_SHORT}${NC}  (${FLASH_BRANCH}, ${SUCCEEDED} drive(s))"
            echo -e "  full: ${FLASH_FULL}"
            echo -e "  ${YELLOW}note: this ISO has no .version sidecar, so this is the checked-out commit, which may be ahead of what was built.${NC}"
            git -C "$PROJECT_DIR" diff --quiet HEAD 2>/dev/null || \
                echo -e "  ${YELLOW}note: working tree is dirty too.${NC}"
        fi
        echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

        # Record this batch to the orders app (private flashes table) so the hash
        # shows in the software dropdown when stamping shipments. Best effort:
        # never fails or delays the flash. The endpoint URL and password come from
        # build-scripts/.env (FLASH_LOG_URL, ADMIN_PASSWORD_PROD), which may be a
        # plain file or a symlink to a central machine secrets file. Nothing
        # sensitive is hard-coded in this public repo.
        [[ -f "$SCRIPT_DIR/.env" ]] && source "$SCRIPT_DIR/.env"
        if [[ -n "${FLASH_LOG_URL:-}" && -n "${ADMIN_PASSWORD_PROD:-}" ]]; then
            FLASH_PAYLOAD="{\"git_hash\":\"$FLASH_SHORT\",\"git_full\":\"$FLASH_FULL\",\"branch\":\"$FLASH_BRANCH\",\"iso_name\":\"$(basename "$ISO_PATH")\",\"iso_sha256\":\"$VERIFIED_ISO_SHA256\",\"drive_count\":$SUCCEEDED,\"flashed_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            # Cloudflare Access service-token headers, if the endpoint is behind
            # Access (both set in build-scripts/.env). Omitted headers just mean
            # the request relies on the app's Basic Auth alone.
            CF_HEADERS=()
            [[ -n "${CF_ACCESS_CLIENT_ID:-}" ]] && CF_HEADERS+=(-H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID")
            [[ -n "${CF_ACCESS_CLIENT_SECRET:-}" ]] && CF_HEADERS+=(-H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET")
            if curl -fsS --max-time 15 -u ":$ADMIN_PASSWORD_PROD" "${CF_HEADERS[@]}" \
                    -H 'Content-Type: application/json' \
                    -X POST "$FLASH_LOG_URL" -d "$FLASH_PAYLOAD" >/dev/null 2>&1; then
                echo -e "${GREEN}Recorded to the orders app; it shows in the software dropdown now.${NC}"
            else
                echo -e "${YELLOW}Could not reach the orders app to record this flash. The hash above is still yours to use.${NC}"
            fi
        else
            echo -e "${YELLOW}FLASH_LOG_URL/ADMIN_PASSWORD_PROD not set in build-scripts/.env, so this flash was not recorded to the orders app. Hash above is still yours to use.${NC}"
        fi
    fi
fi

if [[ ${#FAILED[@]} -eq 0 ]]; then
    echo -e "${BOLD}${GREEN}All ${#FOUND_DRIVES[@]} drives flashed and verified. Unplug them now.${NC}"
    exit 0
else
    echo -e "${BOLD}${RED}${#FAILED[@]} of ${#FOUND_DRIVES[@]} drive(s) failed: ${FAILED[*]}${NC}"
    exit 1
fi
