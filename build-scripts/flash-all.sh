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
       $0 --corrupt [scenario...]

Flash an ISO to every whitelisted USB drive currently plugged in, in parallel.

With --corrupt, flash the corrupt-test scenario ISOs (made by 'just
corrupt-test-iso all') instead: one scenario per drive, then an interactive
unplug phase tells you which stick got which scenario as you pull each one.
Positional args select scenarios (default: ${CORRUPT_SCENARIOS[*]}).
Corrupt mode never boot-settles: these drives are for one throwaway test.

Options:
  --debug       Use the newest build's debug ISO
  --no-backup   Use the newest build's standard ISO (no backup image copy)
  --corrupt     Flash corrupt-test scenario ISOs, one per drive
  --yes         Skip the confirmation prompt
  --no-settle   Skip the post-flash QEMU boot-settle (faster, but the first
                live boot on each drive will be slow)
  --help        Show this help
EOF
}

SKIP_CONFIRM=false
SKIP_SETTLE=false
CORRUPT_MODE=false
ISO_KIND=""
POSITIONAL=()
while [[ -n "${1:-}" ]]; do
    case "$1" in
        --help|-h)    usage; exit 0 ;;
        --debug|-d)   ISO_KIND=debug; shift ;;
        --no-backup)  ISO_KIND=standard; shift ;;
        --corrupt)    CORRUPT_MODE=true; shift ;;
        --yes|-y)     SKIP_CONFIRM=true; shift ;;
        --no-settle)  SKIP_SETTLE=true; shift ;;
        *)            POSITIONAL+=("$1"); shift ;;
    esac
done

# SCENARIOS[i] and SCEN_ISOS[i] pair up; empty outside corrupt mode.
SCENARIOS=()
SCEN_ISOS=()
ISO_PATH=""
if [[ "$CORRUPT_MODE" == true ]]; then
    SKIP_SETTLE=true
    SCENARIOS=("${POSITIONAL[@]}")
    (( ${#SCENARIOS[@]} )) || SCENARIOS=("${CORRUPT_SCENARIOS[@]}")
    for s in "${SCENARIOS[@]}"; do
        if [[ " ${CORRUPT_SCENARIOS[*]} " != *" $s "* ]]; then
            log_error "Unknown scenario '$s' (choose from: ${CORRUPT_SCENARIOS[*]})."
            exit 1
        fi
        iso="$(find_corrupt_iso "$s")"
        if [[ -z "$iso" ]]; then
            log_error "No corrupt-test ISO for scenario '$s' in $OUTPUT_DIR."
            log_error "Make them with 'just corrupt-test-iso all' first."
            exit 1
        fi
        warn_if_stale_corrupt_iso "$iso"
        SCEN_ISOS+=("$iso")
    done
else
    # Variant flags resolve against the NEWEST build only; an older build is
    # never picked silently. Pass a path explicitly to flash an older ISO.
    ISO_PATH="${POSITIONAL[0]:-}"
    if [[ -z "$ISO_PATH" ]]; then
        ISO_PATH="$(find_latest_iso "$ISO_KIND")"
    fi
    if [[ -z "$ISO_PATH" || ! -f "$ISO_PATH" ]]; then
        log_error "No matching ISO for the newest build in $OUTPUT_DIR."
        log_error "Run 'just build' first, or pass an ISO path explicitly."
        exit 1
    fi
fi

load_whitelist
if [[ ${#WHITELIST[@]} -eq 0 ]]; then
    log_error "flash-all requires a drive whitelist ($CONFIG_FILE)."
    log_error "For a single drive without a whitelist, use flash-to-usb.sh (just flash)."
    exit 1
fi
find_whitelisted_drives

if [[ ${#FOUND_DRIVES[@]} -eq 0 ]]; then
    log_error "No whitelisted USB drives found."
    exit 1
fi

# Per-drive parallel arrays: normal mode repeats one ISO across every drive,
# corrupt mode zips scenarios onto drives in discovery order.
ENTRIES=()
ISOS=()
SCENS=()
if [[ "$CORRUPT_MODE" == true ]]; then
    COUNT=${#SCENARIOS[@]}
    if (( ${#FOUND_DRIVES[@]} < COUNT )); then
        COUNT=${#FOUND_DRIVES[@]}
        log_error "Only $COUNT drive(s) plugged in for ${#SCENARIOS[@]} scenarios; skipping: ${SCENARIOS[*]:$COUNT}"
    elif (( ${#FOUND_DRIVES[@]} > COUNT )); then
        log_info "${#FOUND_DRIVES[@]} drives plugged in but only $COUNT scenario(s); the extra drives will be left untouched."
    fi
    for ((i = 0; i < COUNT; i++)); do
        ENTRIES+=("${FOUND_DRIVES[$i]}")
        ISOS+=("${SCEN_ISOS[$i]}")
        SCENS+=("${SCENARIOS[$i]}")
    done
else
    for entry in "${FOUND_DRIVES[@]}"; do
        ENTRIES+=("$entry")
        ISOS+=("$ISO_PATH")
        SCENS+=("")
    done
fi

echo
if [[ "$CORRUPT_MODE" == true ]]; then
    echo -e "${BOLD}${YELLOW}Will flash ${#ENTRIES[@]} corrupt-test scenario(s), one per drive, in parallel:${NC}"
else
    echo -e "${BOLD}${YELLOW}Will flash $(basename "$ISO_PATH") to ${#ENTRIES[@]} drive(s) in parallel:${NC}"
fi
for i in "${!ENTRIES[@]}"; do
    IFS='|' read -r dev size model serial <<< "${ENTRIES[$i]}"
    printf "  %-10s %-8s %-22s %-16s %s\n" "$dev" "$size" "$model" "$serial" "${SCENS[$i]:+-> ${SCENS[$i]}}"
done
echo -e "  ${RED}${BOLD}ALL DATA ON THESE DRIVES WILL BE DESTROYED${NC}"
echo

if [[ "$SKIP_CONFIRM" != true ]]; then
    read -p "Type 'yes' to continue: " confirm
    [[ "$confirm" == "yes" ]] || { log_info "Aborted."; exit 0; }
fi

# Verify each distinct ISO against its build checksum once the user commits,
# then hand the verified hash to children so they skip re-hashing 6GB apiece.
# After the prompt so it doesn't stall confirmation; still before any drive is
# written.
declare -A SHA_BY_ISO=()
for iso in "${ISOS[@]}"; do
    [[ -n "${SHA_BY_ISO[$iso]:-}" ]] && continue
    sha="$(verify_iso_checksum "$iso")" || exit 1
    SHA_BY_ISO["$iso"]="$sha"
done
init_manifest
log_info "ISO checksum(s) OK."

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
for i in "${!ENTRIES[@]}"; do
    IFS='|' read -r dev _ _ _ <<< "${ENTRIES[$i]}"
    logfile="$LOG_DIR/$(basename "$dev").log"
    echo -e "${BOLD}→ Starting flash for $dev${SCENS[$i]:+ [${SCENS[$i]}]} (tail -f $logfile)${NC}"
    VERIFIED_ISO_SHA256="${SHA_BY_ISO[${ISOS[$i]}]}" \
        "$FLASH_SCRIPT" --yes --no-udev-gate --device "$dev" \
        "${ISOS[$i]}" >"$logfile" 2>&1 &
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
# Corrupt mode skips this: a powered-off drive vanishes from the bus, so its
# unplug would be undetectable and the identification phase couldn't work.
# Safe because every write is synced and read back verified, and these test
# drives get reflashed after one use anyway.
if [[ "$CORRUPT_MODE" != true ]]; then
    for i in "${!DEVS[@]}"; do
        dev="${DEVS[$i]}"
        [[ " ${FAILED[*]} " == *" $dev "* ]] && continue
        eject_drive "$dev" || true
    done
fi

echo
log_info "QA manifest: $(manifest_path)"

# Report which software build just went onto these drives, so I can tie a shipped
# batch to a git hash without digging through the manifest. Uses the currently
# checked-out commit (build-then-flash means HEAD matches the ISO).
SUCCEEDED=$(( ${#DEVS[@]} - ${#FAILED[@]} ))
if [[ $SUCCEEDED -gt 0 && "$CORRUPT_MODE" != true ]]; then
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
            FLASH_PAYLOAD="{\"git_hash\":\"$FLASH_SHORT\",\"git_full\":\"$FLASH_FULL\",\"branch\":\"$FLASH_BRANCH\",\"iso_name\":\"$(basename "$ISO_PATH")\",\"iso_sha256\":\"${SHA_BY_ISO[$ISO_PATH]}\",\"drive_count\":$SUCCEEDED,\"flashed_at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
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

# Which physical stick got which scenario: the drives skipped the power-off
# eject, so each unplug still drops the device from /sys/block. Watch for that
# and announce the scenario as the user pulls drives one at a time.
identify_corrupt_drives() {
    sudo sync
    echo
    echo -e "${BOLD}${YELLOW}Now unplug the drives ONE at a time to identify them.${NC}"
    echo "As each drive disappears, label the stick you just pulled with its scenario."
    echo
    local remaining=() still i dev scen
    for i in "${!DEVS[@]}"; do remaining+=("$i"); done
    while (( ${#remaining[@]} )); do
        sleep 0.5
        still=()
        for i in "${remaining[@]}"; do
            dev="${DEVS[$i]}"
            if [[ -e "/sys/block/$(basename "$dev")" ]]; then
                still+=("$i")
                continue
            fi
            scen="${SCENS[$i]}"
            if [[ " ${FAILED[*]} " == *" $dev "* ]]; then
                echo -e "${RED}✗${NC} That was ${BOLD}${scen}${NC}, but its flash FAILED. Set it aside, don't test it."
            else
                echo -e "${GREEN}✓${NC} That was ${BOLD}${scen}${NC}: $(corrupt_scenario_expectation "$scen"). Label it '$scen'."
            fi
        done
        remaining=("${still[@]}")
    done
    echo
    log_info "All drives identified and unplugged."
}

if [[ "$CORRUPT_MODE" == true && ${#DEVS[@]} -gt 0 ]]; then
    identify_corrupt_drives
fi

if [[ ${#FAILED[@]} -eq 0 ]]; then
    if [[ "$CORRUPT_MODE" != true ]]; then
        echo -e "${BOLD}${GREEN}All ${#DEVS[@]} drives flashed and verified. Unplug them now.${NC}"
    fi
    exit 0
else
    echo -e "${BOLD}${RED}${#FAILED[@]} of ${#DEVS[@]} drive(s) failed: ${FAILED[*]}${NC}"
    exit 1
fi
